"""Monitoring session: sampling + windowing + inference + alerts + bounded history."""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .acquisition import SamplingThread, WindowBuilder, samples_to_array
from .alerts import AlertPolicy
from .config import AppConfig, PROCESSED_DIR, RAW_DIR
from .data_store import PREDICTION_COLUMNS, RAW_COLUMNS, CsvWriter, new_run_id
from .features import extract_features
from .inference import (ANOMALY, IDLE, INSUFFICIENT, NO_MODEL, SENSOR_ERROR, SIMULATION,
                        AnomalyDetector, FeatureMismatchError, LoadedModel)
from .sensor_base import Sample, SensorInterface

log = logging.getLogger(__name__)


class MonitorSession:
    def __init__(self, cfg: AppConfig, sensor: SensorInterface, model: LoadedModel | None,
                 model_problem: str | None = None, label: str = "", record_raw: bool = True,
                 raw_dir: Path = RAW_DIR, processed_dir: Path = PROCESSED_DIR,
                 history_samples: int = 1000, history_windows: int = 300) -> None:
        self.cfg, self.sensor, self.model, self.model_problem = cfg, sensor, model, model_problem
        self.detector = AnomalyDetector(model) if model else None
        self.label, self.mode = label, sensor.mode
        self.run_id = new_run_id(self.mode, label)
        self.raw_path = raw_dir / f"{self.run_id}.csv" if record_raw else None
        self.pred_path = processed_dir / f"{self.run_id}_windows.csv"
        self._raw = CsvWriter(self.raw_path, RAW_COLUMNS) if self.raw_path else None
        self._pred = CsvWriter(self.pred_path, PREDICTION_COLUMNS)
        self._lock = threading.Lock()
        self._t0: float | None = None
        self._builder = WindowBuilder(cfg.window_seconds)
        self._alerts = AlertPolicy(cfg.debounce_windows)
        self.samples: deque[Sample] = deque(maxlen=history_samples)
        self.windows: deque[dict] = deque(maxlen=history_windows)
        self.events: deque[dict] = deque(maxlen=100)
        self.sensor_error: str | None = None
        self.last_sample_mono: float | None = None
        self.last_window_state: str = IDLE
        self.last_window_note = ""
        self.alert_active = False
        self._last_flush = time.monotonic()
        self._thread = SamplingThread(sensor, cfg.sample_rate_hz, self._on_sample, self._on_status)

    # lifecycle
    def start(self) -> None:
        self._event("INFO", f"Monitoring started ({self.mode}), run {self.run_id}")
        self._thread.start()

    def stop(self) -> None:
        self._thread.stop()
        with self._lock:
            for w in (self._raw, self._pred):
                if w:
                    w.close()
        self._event("INFO", "Monitoring stopped")

    @property
    def running(self) -> bool:
        return self._thread.alive

    # callbacks (sampler thread)
    def _event(self, level: str, msg: str) -> None:
        self.events.appendleft({"time_utc": datetime.now(timezone.utc).strftime("%H:%M:%S"),
                                "level": level, "message": msg})

    def _on_status(self, err: str | None) -> None:
        with self._lock:
            if err and err != self.sensor_error:
                self._event("ERROR", f"Sensor: {err}")
            elif not err and self.sensor_error:
                self._event("INFO", "Sensor recovered")
            self.sensor_error = err
            if err:
                self._builder.reset()

    def _on_sample(self, s: Sample) -> None:
        with self._lock:
            if self._t0 is None:
                self._t0 = s.mono
            self.samples.append(s)
            self.last_sample_mono = s.mono
            if self._raw:
                self._raw.write({"timestamp_utc": s.utc.isoformat(), "elapsed_seconds": f"{s.mono - self._t0:.4f}",
                                 "ax_g": f"{s.ax:.6f}", "ay_g": f"{s.ay:.6f}", "az_g": f"{s.az:.6f}",
                                 "sensor_mode": self.mode, "run_id": self.run_id, "label": self.label})
            done = self._builder.add(s)
            if done is not None:
                self._process_window(done)
            if s.mono - self._last_flush > 1.0:
                for w in (self._raw, self._pred):
                    if w:
                        w.flush()
                self._last_flush = s.mono

    def _process_window(self, w: list[Sample]) -> None:
        if len(w) < self.cfg.min_samples:
            self.last_window_state = INSUFFICIENT
            self.last_window_note = f"{len(w)} samples, need {self.cfg.min_samples}"
            return
        feats = extract_features(samples_to_array(w))
        row = {"run_id": self.run_id, "window_start_utc": w[0].utc.isoformat(),
               "window_end_utc": w[-1].utc.isoformat(), "sample_count": len(w),
               "sensor_mode": self.mode, **feats, "label": self.label,
               "anomaly_score": "", "prediction": "", "alert_active": "", "model_version": ""}
        if self.detector:
            try:
                res = self.detector.evaluate(feats)
            except FeatureMismatchError as exc:
                self.last_window_state, self.last_window_note = NO_MODEL, str(exc)
                return
            active, raised = self._alerts.update(res.prediction)
            self.alert_active = active
            if raised:
                self._event("ALERT", f"Anomaly: {self.cfg.debounce_windows} consecutive anomalous windows"
                                     + (" (SIMULATED)" if self.mode == "simulation" else ""))
            row.update(anomaly_score=f"{res.score:.6f}", prediction=res.prediction,
                       alert_active=int(active), model_version=self.model.version)  # type: ignore[union-attr]
            self.last_window_state, self.last_window_note = res.state, ""
        row["_t"] = w[-1].utc
        self.windows.append({k: (float(v) if k in ("anomaly_score",) and v != "" else v) for k, v in row.items()})
        self._pred.write(row)

    # reading (UI thread)
    def snapshot(self) -> dict:
        with self._lock:
            now = time.monotonic()
            age = None if self.last_sample_mono is None else now - self.last_sample_mono
            stale = self.running and age is not None and age > self.cfg.stale_timeout_s
            if not self.running:
                status, detail = IDLE, "Monitoring stopped"
            elif self.sensor_error or stale:
                status, detail = SENSOR_ERROR, self.sensor_error or f"No sample for {age:.1f}s"
            elif self.detector is None:
                status, detail = NO_MODEL, self.model_problem or "No model"
            elif self.last_window_state in (INSUFFICIENT, NO_MODEL):
                status, detail = self.last_window_state, self.last_window_note
            elif self.last_window_state == IDLE:
                status, detail = IDLE, "Waiting for first window"
            elif self.mode == "simulation":
                status, detail = SIMULATION, f"Simulated data. Last window: {self.last_window_state}"
            else:
                status, detail = self.last_window_state, ""
            return {
                "status": status, "detail": detail, "mode": self.mode, "alert_active": self.alert_active,
                "last_window_state": self.last_window_state,
                "samples": list(self.samples), "windows": list(self.windows), "events": list(self.events),
                "rate_hz": self._thread.achieved_rate_hz(), "target_rate_hz": self.cfg.sample_rate_hz,
                "sample_age_s": age, "run_id": self.run_id, "raw_path": self.raw_path,
                "pred_path": self.pred_path, "model_version": self.model.version if self.model else None,
            }
