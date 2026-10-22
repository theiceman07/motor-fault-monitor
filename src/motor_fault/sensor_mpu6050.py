"""MPU6050 / GY-521 accelerometer driver over I2C (smbus2)."""
from __future__ import annotations

import logging
from typing import Any

from .sensor_base import SensorError

log = logging.getLogger(__name__)

_PWR_MGMT_1 = 0x6B
_ACCEL_CONFIG = 0x1C
_ACCEL_XOUT_H = 0x3B
_WHO_AM_I = 0x75
_RANGE_BITS = {2: 0x00, 4: 0x08, 8: 0x10, 16: 0x18}
_LSB_PER_G = {2: 16384.0, 4: 8192.0, 8: 4096.0, 16: 2048.0}


def _s16(hi: int, lo: int) -> int:
    v = (hi << 8) | lo
    return v - 65536 if v & 0x8000 else v


class MPU6050Sensor:
    mode = "mpu6050"

    def __init__(self, bus_num: int = 1, address: int = 0x68, range_g: int = 2, bus: Any = None) -> None:
        if range_g not in _RANGE_BITS:
            raise ValueError("range_g must be 2, 4, 8 or 16")
        self.bus_num, self.address, self.range_g = bus_num, address, range_g
        self._bus = bus  # injectable for tests
        self._owns_bus = bus is None

    def open(self) -> None:
        try:
            if self._bus is None:
                from smbus2 import SMBus
                self._bus = SMBus(self.bus_num)
            who = self._bus.read_byte_data(self.address, _WHO_AM_I)
            if who != 0x68:
                log.warning("WHO_AM_I=0x%02X (expected 0x68); may be a clone or different address wiring", who)
            self._bus.write_byte_data(self.address, _PWR_MGMT_1, 0x00)  # wake
            self._bus.write_byte_data(self.address, _ACCEL_CONFIG, _RANGE_BITS[self.range_g])
        except (OSError, ImportError) as exc:
            self._drop_bus()
            raise SensorError(f"MPU6050 open failed on bus {self.bus_num} addr 0x{self.address:02X}: {exc}") from exc

    def read_g(self) -> tuple[float, float, float]:
        if self._bus is None:
            raise SensorError("MPU6050 not open")
        try:
            d = self._bus.read_i2c_block_data(self.address, _ACCEL_XOUT_H, 6)
        except OSError as exc:
            raise SensorError(f"MPU6050 read failed: {exc}") from exc
        if len(d) != 6:
            raise SensorError(f"MPU6050 short read ({len(d)} bytes)")
        k = _LSB_PER_G[self.range_g]
        return _s16(d[0], d[1]) / k, _s16(d[2], d[3]) / k, _s16(d[4], d[5]) / k

    def _drop_bus(self) -> None:
        if self._bus is not None and self._owns_bus:
            try:
                self._bus.close()
            except OSError:
                pass
            self._bus = None

    def close(self) -> None:
        self._drop_bus()
