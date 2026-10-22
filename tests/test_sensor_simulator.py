import math

import pytest

from motor_fault.acquisition import SamplingThread
from motor_fault.sensor_base import SensorError, SensorInterface
from motor_fault.sensor_mpu6050 import MPU6050Sensor
from motor_fault.sensor_simulator import SimulatedSensor


def test_simulator_shape_and_mode():
    s = SimulatedSensor(50, seed=1)
    assert isinstance(s, SensorInterface) and s.mode == "simulation"
    vals = [s.read_g() for _ in range(100)]
    assert all(len(v) == 3 and all(math.isfinite(x) for x in v) for v in vals)


class FakeBus:
    def __init__(self, fail=False):
        self.fail, self.writes = fail, []

    def read_byte_data(self, a, r):
        if self.fail:
            raise OSError(121, "Remote I/O error")
        return 0x68

    def write_byte_data(self, a, r, v):
        self.writes.append((r, v))

    def read_i2c_block_data(self, a, r, n):
        if self.fail:
            raise OSError(121, "Remote I/O error")
        return [0x00, 0x00, 0x00, 0x00, 0x40, 0x00]  # az = 16384 -> 1 g


def test_mpu6050_conversion():
    s = MPU6050Sensor(bus=FakeBus())
    s.open()
    assert s.read_g() == pytest.approx((0, 0, 1.0))


def test_mpu6050_negative_value():
    bus = FakeBus()
    bus.read_i2c_block_data = lambda a, r, n: [0xC0, 0x00, 0, 0, 0, 0]  # -16384
    s = MPU6050Sensor(bus=bus)
    s.open()
    assert s.read_g()[0] == pytest.approx(-1.0)


def test_mpu6050_failure_raises_sensor_error():
    with pytest.raises(SensorError):
        MPU6050Sensor(bus=FakeBus(fail=True)).open()


def test_no_silent_simulation_fallback():
    got, errs = [], []
    th = SamplingThread(MPU6050Sensor(bus=FakeBus(fail=True)), 50, got.append, errs.append, retry_seconds=0.05)
    th.start()
    import time
    time.sleep(0.3)
    th.stop()
    assert got == [] and errs and errs[-1]
