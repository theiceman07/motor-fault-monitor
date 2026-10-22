#!/usr/bin/env python3
"""Scan the I2C bus, identify MPU6050/ADXL345 and read a few samples."""
import _bootstrap  # noqa: F401
import argparse
import sys

from motor_fault.config import load_config
from motor_fault.factory import make_sensor
from motor_fault.sensor_base import SensorError


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bus", type=int, default=None)
    ap.add_argument("--sensor", choices=["mpu6050", "adxl345"], default="mpu6050")
    ap.add_argument("--samples", type=int, default=20)
    a = ap.parse_args(argv)
    cfg = load_config(i2c_bus=a.bus)
    try:
        from smbus2 import SMBus
        with SMBus(cfg.i2c_bus) as bus:
            found = []
            for addr in range(0x03, 0x78):
                try:
                    bus.read_byte(addr)
                    found.append(addr)
                except OSError:
                    pass
        print("Devices found:", [f"0x{x:02X}" for x in found] or "none")
    except (OSError, ImportError) as exc:
        print(f"ERROR opening I2C bus {cfg.i2c_bus}: {exc}\nEnable I2C: sudo raspi-config -> Interface Options -> I2C",
              file=sys.stderr)
        return 2
    sensor = make_sensor(a.sensor, cfg)
    try:
        sensor.open()
        for _ in range(a.samples):
            ax, ay, az = sensor.read_g()
        print(f"{a.sensor} OK. Last sample: ax={ax:.3f} ay={ay:.3f} az={az:.3f} g (expect |a| ~ 1 g at rest)")
    except SensorError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    finally:
        sensor.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
