"""Background sampling thread and streaming window builder."""
from __future__ import annotations

import logging
import math
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Callable

import numpy as np

from .sensor_base import Sample, SensorError, SensorInterface

log = logging.getLogger(__name__)


class WindowBuilder:
    """Collects samples into fixed-duration windows keyed on monotonic time."""

    def __init__(self, window_seconds: float) -> None:
        self.window_seconds = window_seconds
        self._buf: list[Sample] = []
        self._start: float | None = None

    def add(self, s: Sample) -> list[Sample] | None:
        """Returns the completed window's samples when ``s`` begins a new window."""
        if self._start is None:
            self._start = s.mono
        done = None
        if s.mono - self._start >= self.window_seconds:
            done = self._buf
            self._buf = []
            self._start = s.mono
        self._buf.append(s)
        return done

    def reset(self) -> None:
        self._buf, self._start = [], None


def samples_to_array(samples: list[Sample]) -> np.ndarray:
    return np.array([[s.ax, s.ay, s.az] for s in samples], dtype=float).reshape(-1, 3)


class SamplingThread:
    """Reads a sensor at ~rate_hz. Errors are reported, never replaced with fake data."""

    def __init__(self, sensor: SensorInterface, rate_hz: float,
                 on_sample: Callable[[Sample], None],
                 on_status: Callable[[str | None], None] | None = None,
                 retry_seconds: float = 1.0) -> None:
        self.sensor, self.rate_hz = sensor, rate_hz
        self.on_sample, self.on_status = on_sample, on_status or (lambda _e: None)
        self.retry_seconds = retry_seconds
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="sampler", daemon=True)
        self._stamps: deque[float] = deque(maxlen=200)
        self.sample_count = 0
        self.last_error: str | None = None

    def start(self) -> None:
        self._thread.start()

    def stop(self, timeout: float = 3.0) -> None:
        self._stop.set()
        self._thread.join(timeout)
        try:
            self.sensor.close()
        except Exception:  # closing must never raise into shutdown
            log.exception("sensor close failed")

    @property
    def alive(self) -> bool:
        return self._thread.is_alive()

    def achieved_rate_hz(self) -> float:
        st = list(self._stamps)
        if len(st) < 2 or st[-1] <= st[0]:
            return 0.0
        return (len(st) - 1) / (st[-1] - st[0])

    def _set_error(self, msg: str | None) -> None:
        if msg != self.last_error:
            (log.error if msg else log.info)("sensor %s", msg or "recovered")
        self.last_error = msg
        self.on_status(msg)

    def _run(self) -> None:
        period = 1.0 / self.rate_hz
        opened = False
        next_t = time.monotonic()
        while not self._stop.is_set():
            try:
                if not opened:
                    self.sensor.open()
                    opened = True
                    self._set_error(None)
                    next_t = time.monotonic()
                ax, ay, az = self.sensor.read_g()
                if not all(math.isfinite(v) for v in (ax, ay, az)):
                    raise SensorError("sensor returned non-finite values")
                now = time.monotonic()
                self._stamps.append(now)
                self.sample_count += 1
                self.on_sample(Sample(datetime.now(timezone.utc), now, ax, ay, az))
            except SensorError as exc:
                self._set_error(str(exc))
                opened = False
                try:
                    self.sensor.close()
                except Exception:
                    pass
                self._stop.wait(self.retry_seconds)
                continue
            except Exception as exc:  # unexpected: surface as sensor error, keep log trace
                log.exception("unexpected sampler failure")
                self._set_error(f"unexpected error: {exc}")
                opened = False
                self._stop.wait(self.retry_seconds)
                continue
            next_t += period
            delay = next_t - time.monotonic()
            if delay > 0:
                self._stop.wait(delay)
            else:
                next_t = time.monotonic()  # fell behind; do not burst
