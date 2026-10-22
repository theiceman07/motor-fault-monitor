"""Build sensors/models from names; keeps hardware choice explicit."""
from __future__ import annotations

from pathlib import Path

from .config import MODEL_DIR, AppConfig
from .inference import LoadedModel, ModelLoadError, check_compatible, find_latest_model, load_model
from .sensor_adxl345 import ADXL345Sensor
from .sensor_base import SensorInterface
from .sensor_mpu6050 import MPU6050Sensor
from .sensor_simulator import SimulatedSensor


def make_sensor(mode: str, cfg: AppConfig) -> SensorInterface:
    if mode == "simulation":
        return SimulatedSensor(cfg.sample_rate_hz)
    if mode == "mpu6050":
        return MPU6050Sensor(cfg.i2c_bus, cfg.mpu6050_address, cfg.mpu6050_range_g)
    if mode == "adxl345":
        return ADXL345Sensor(cfg.i2c_bus, cfg.adxl345_address)
    raise ValueError(f"Unknown sensor mode '{mode}'")


def try_load_model(mode: str, cfg: AppConfig, path: Path | None = None,
                   model_dir: Path = MODEL_DIR) -> tuple[LoadedModel | None, str | None]:
    """Returns (model, problem). Never raises for missing/incompatible models."""
    path = path or find_latest_model(model_dir)
    if path is None:
        return None, ("No trained model. Collect normal data: python scripts/collect_data.py --mode "
                      f"{mode} --label normal --duration 120 ; then python scripts/train_model.py --input <csv>")
    try:
        model = load_model(path)
        check_compatible(model, mode, cfg.window_seconds)
        return model, None
    except (ModelLoadError, ValueError) as exc:
        return None, str(exc)
