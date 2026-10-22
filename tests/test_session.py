import time

import joblib

from motor_fault.config import AppConfig
from motor_fault.dashboard_state import MonitorSession
from motor_fault.inference import IDLE, NO_MODEL, SENSOR_ERROR, load_model
from motor_fault.sensor_base import SensorError
from motor_fault.sensor_simulator import SimulatedSensor


class DeadSensor:
    mode = "mpu6050"

    def open(self):
        raise SensorError("disconnected")

    def read_g(self):
        raise SensorError("disconnected")

    def close(self):
        pass


def run(sensor, model, tmp_path, secs=2.6):
    cfg = AppConfig(sample_rate_hz=50, window_seconds=0.5, debounce_windows=2)
    s = MonitorSession(cfg, sensor, model, None if model else "no model", raw_dir=tmp_path, processed_dir=tmp_path)
    s.start()
    time.sleep(secs)
    snap = s.snapshot()
    s.stop()
    return s, snap


def test_sensor_error_state(tmp_path):
    _, snap = run(DeadSensor(), None, tmp_path, 0.5)
    assert snap["status"] == SENSOR_ERROR and snap["samples"] == []


def test_no_model_simulation(tmp_path):
    _, snap = run(SimulatedSensor(50), None, tmp_path)
    assert snap["status"] == NO_MODEL and len(snap["samples"]) > 20


def test_simulation_with_model_and_csv(tmp_path, artifact):
    artifact["sensor_mode"] = "simulation"
    p = tmp_path / "model_s.joblib"
    joblib.dump(artifact, p)
    s, snap = run(SimulatedSensor(50), load_model(p), tmp_path)
    assert snap["status"] == "SIMULATION" and snap["rate_hz"] > 0
    import pandas as pd
    raw = pd.read_csv(s.raw_path)
    assert set(raw["sensor_mode"]) == {"simulation"}
    pred = pd.read_csv(s.pred_path)
    assert len(pred) >= 2 and set(pred["prediction"]) <= {1, -1}
