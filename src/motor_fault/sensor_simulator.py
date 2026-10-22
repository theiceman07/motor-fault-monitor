"""Synthetic sensor for UI/software smoke tests only. NOT real data."""
from __future__ import annotations

import math

import numpy as np


class SimulatedSensor:
    """Gravity on Z plus a ~25 Hz-ish motor vibration and noise.

    Set ``fault = True`` to inject a larger, modulated vibration for demos.
    """

    mode = "simulation"

    def __init__(self, sample_rate_hz: float = 50.0, seed: int | None = None) -> None:
        self.sample_rate_hz = sample_rate_hz
        self.fault = False
        self._rng = np.random.default_rng(seed)
        self._n = 0
        self._open = False
        self._phase = float(self._rng.uniform(0, 2 * math.pi))

    def open(self) -> None:
        self._open = True

    def close(self) -> None:
        self._open = False

    def read_g(self) -> tuple[float, float, float]:
        t = self._n / self.sample_rate_hz
        self._n += 1
        w = 2 * math.pi * 7.3  # below Nyquist at the default 50 Hz rate
        # slow amplitude wander so windows differ like real runs do
        amp = 0.05 * (1.0 + 0.15 * math.sin(2 * math.pi * 0.05 * t + self._phase)
                      + 0.05 * math.sin(2 * math.pi * 0.31 * t + 2 * self._phase))
        ax = amp * math.sin(w * t)
        ay = amp * 0.6 * math.cos(w * t)
        az = 1.0 + amp * 0.3 * math.sin(2 * w * t)
        if self.fault:
            mod = 1.0 + 0.5 * math.sin(2 * math.pi * 0.7 * t)
            ax += 0.25 * mod * math.sin(1.9 * w * t)
            ay += 0.20 * mod * math.cos(1.9 * w * t)
            az += 0.15 * mod * math.sin(3.1 * w * t)
        noise = self._rng.normal(0.0, 0.01, 3)
        return ax + noise[0], ay + noise[1], az + noise[2]
