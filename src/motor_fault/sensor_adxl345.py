"""ADXL345 driver over I2C. Implemented from the datasheet; NOT tested on hardware.

The MPU6050 is the supported first hardware target.
"""
from __future__ import annotations

import logging
from typing import Any

from .sensor_base import SensorError

log = logging.getLogger(__name__)

_DEVID = 0x00
_BW_RATE = 0x2C
_POWER_CTL = 0x2D
_DATA_FORMAT = 0x31
_DATAX0 = 0x32
_LSB_PER_G = 256.0  # FULL_RES mode: 3.9 mg/LSB at every range


class ADXL345Sensor:
    mode = "adxl345"

    def __init__(self, bus_num: int = 1, address: int = 0x53, bus: Any = None) -> None:
        self.bus_num, self.address = bus_num, address
        self._bus = bus
        self._owns_bus = bus is None

    def open(self) -> None:
        try:
            if self._bus is None:
                from smbus2 import SMBus
                self._bus = SMBus(self.bus_num)
            dev = self._bus.read_byte_data(self.address, _DEVID)
            if dev != 0xE5:
                raise SensorError(f"ADXL345 DEVID=0x{dev:02X}, expected 0xE5")
            self._bus.write_byte_data(self.address, _BW_RATE, 0x0B)       # 200 Hz ODR
            self._bus.write_byte_data(self.address, _DATA_FORMAT, 0x08)   # FULL_RES, +-2 g base
            self._bus.write_byte_data(self.address, _POWER_CTL, 0x08)     # measure
        except (OSError, ImportError) as exc:
            self.close()
            raise SensorError(f"ADXL345 open failed: {exc}") from exc

    def read_g(self) -> tuple[float, float, float]:
        if self._bus is None:
            raise SensorError("ADXL345 not open")
        try:
            d = self._bus.read_i2c_block_data(self.address, _DATAX0, 6)
        except OSError as exc:
            raise SensorError(f"ADXL345 read failed: {exc}") from exc
        if len(d) != 6:
            raise SensorError(f"ADXL345 short read ({len(d)} bytes)")
        out = []
        for i in (0, 2, 4):
            v = d[i] | (d[i + 1] << 8)  # little-endian
            out.append((v - 65536 if v & 0x8000 else v) / _LSB_PER_G)
        return out[0], out[1], out[2]

    def close(self) -> None:
        if self._bus is not None and self._owns_bus:
            try:
                self._bus.close()
            except OSError:
                pass
            self._bus = None
