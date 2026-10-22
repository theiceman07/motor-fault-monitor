"""Typed configuration with validation."""
from __future__ import annotations

import math
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
MODEL_DIR = PROJECT_ROOT / "data" / "models"
CONFIG_PATH = PROJECT_ROOT / "config.yaml"

SENSOR_MODES = ("simulation", "mpu6050", "adxl345")


class ConfigError(ValueError):
    """Raised for invalid configuration values."""


@dataclass(frozen=True)
class AppConfig:
    sample_rate_hz: float = 50.0
    window_seconds: float = 1.0
    min_window_fill: float = 0.8
    stale_timeout_s: float = 2.0
    debounce_windows: int = 3
    i2c_bus: int = 1
    mpu6050_address: int = 0x68
    mpu6050_range_g: int = 2
    adxl345_address: int = 0x53

    def __post_init__(self) -> None:
        if not (math.isfinite(self.sample_rate_hz) and 1 <= self.sample_rate_hz <= 1000):
            raise ConfigError("sample_rate_hz must be between 1 and 1000")
        if not (math.isfinite(self.window_seconds) and 0.1 <= self.window_seconds <= 60):
            raise ConfigError("window_seconds must be between 0.1 and 60")
        if not 0 < self.min_window_fill <= 1:
            raise ConfigError("min_window_fill must be in (0, 1]")
        if self.stale_timeout_s <= 0:
            raise ConfigError("stale_timeout_s must be > 0")
        if self.debounce_windows < 1:
            raise ConfigError("debounce_windows must be >= 1")
        if self.mpu6050_range_g not in (2, 4, 8, 16):
            raise ConfigError("mpu6050_range_g must be 2, 4, 8 or 16")
        if self.window_seconds * self.sample_rate_hz < 4:
            raise ConfigError("window must contain at least 4 samples at the requested rate")

    @property
    def min_samples(self) -> int:
        return max(3, int(self.sample_rate_hz * self.window_seconds * self.min_window_fill))


def load_config(path: Path | None = None, **overrides: Any) -> AppConfig:
    """Load config.yaml (if present) and apply keyword overrides."""
    path = path or CONFIG_PATH
    values: dict[str, Any] = {}
    if path.exists():
        loaded = yaml.safe_load(path.read_text()) or {}
        if not isinstance(loaded, dict):
            raise ConfigError(f"{path} must contain a mapping")
        known = {f.name for f in fields(AppConfig)}
        unknown = set(loaded) - known
        if unknown:
            raise ConfigError(f"Unknown config keys: {sorted(unknown)}")
        values.update(loaded)
    values.update({k: v for k, v in overrides.items() if v is not None})
    return AppConfig(**values)
