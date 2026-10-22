"""Debounced alert policy. Raw predictions are always preserved separately."""
from __future__ import annotations


class AlertPolicy:
    """Alert becomes active after N consecutive anomalous windows; clears on a normal one."""

    def __init__(self, consecutive: int = 3) -> None:
        if consecutive < 1:
            raise ValueError("consecutive must be >= 1")
        self.consecutive = consecutive
        self._streak = 0
        self.active = False

    def update(self, prediction: int) -> tuple[bool, bool]:
        """Feed a prediction (1 / -1). Returns (alert_active, newly_raised)."""
        was = self.active
        if prediction == -1:
            self._streak += 1
            if self._streak >= self.consecutive:
                self.active = True
        else:
            self._streak = 0
            self.active = False
        return self.active, self.active and not was

    def reset(self) -> None:
        self._streak = 0
        self.active = False
