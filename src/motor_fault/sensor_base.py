"""Sensor abstraction shared by acquisition and the dashboard."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable


class SensorError(RuntimeError):
    """Sensor could not be opened/read, or returned invalid data."""


@dataclass(frozen=True)
class Sample:
    utc: datetime      # timezone-aware UTC
    mono: float        # time.monotonic() seconds
    ax: float          # acceleration in g (includes gravity)
    ay: float
    az: float


@runtime_checkable
class SensorInterface(Protocol):
    mode: str  # 'mpu6050' | 'adxl345' | 'simulation'

    def open(self) -> None: ...
    def read_g(self) -> tuple[float, float, float]:
        """Return (ax, ay, az) in g or raise SensorError."""
        ...
    def close(self) -> None: ...
