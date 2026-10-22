"""Model artifact loading and window scoring.

SECURITY: joblib/pickle can execute code. Only load artifacts created by this
project from your own data/models directory.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import joblib
import numpy as np

from .features import FEATURE_NAMES

ARTIFACT_VERSION = 1

NORMAL = "NORMAL"
ANOMALY = "ANOMALY"
SENSOR_ERROR = "SENSOR ERROR"
INSUFFICIENT = "INSUFFICIENT DATA"
NO_MODEL = "MODEL NOT TRAINED"
SIMULATION = "SIMULATION"
IDLE = "IDLE"


class ModelLoadError(RuntimeError):
    pass


class FeatureMismatchError(ValueError):
    pass


@dataclass(frozen=True)
class LoadedModel:
    estimator: Any
    feature_names: list[str]
    version: str
    sensor_mode: str
    sample_rate_hz: float
    window_seconds: float
    metadata: dict


@dataclass(frozen=True)
class WindowResult:
    score: float       # decision_function: lower = more anomalous, < 0 = outlier. Not a probability.
    prediction: int    # 1 inlier, -1 outlier
    state: str         # NORMAL / ANOMALY


def find_latest_model(model_dir: Path) -> Path | None:
    files = sorted(model_dir.glob("model_*.joblib")) if model_dir.exists() else []
    return files[-1] if files else None


def load_model(path: Path | None) -> LoadedModel:
    if path is None or not Path(path).exists():
        raise ModelLoadError("No model artifact found")
    try:
        art = joblib.load(path)
    except Exception as exc:  # corrupt/incompatible pickle
        raise ModelLoadError(f"Cannot load {path}: {exc}") from exc
    required = {"artifact_version", "estimator", "feature_names", "trained_at_utc",
                "sensor_mode", "sample_rate_hz", "window_seconds"}
    if not isinstance(art, dict) or required - set(art):
        raise ModelLoadError(f"{path} is not a valid motor_fault artifact")
    if art["artifact_version"] != ARTIFACT_VERSION:
        raise ModelLoadError(f"Unsupported artifact version {art['artifact_version']}")
    if list(art["feature_names"]) != FEATURE_NAMES:
        raise FeatureMismatchError("Model feature names/order differ from this code version; retrain")
    return LoadedModel(art["estimator"], list(art["feature_names"]), Path(path).stem,
                       art["sensor_mode"], float(art["sample_rate_hz"]), float(art["window_seconds"]),
                       dict(art.get("training_metadata", {})))


def check_compatible(model: LoadedModel, sensor_mode: str, window_seconds: float) -> None:
    """Raise ModelLoadError if the model must not be used with the current setup."""
    if model.sensor_mode != sensor_mode:
        raise ModelLoadError(
            f"Model was trained on '{model.sensor_mode}' data but the current mode is '{sensor_mode}'")
    if abs(model.window_seconds - window_seconds) > 1e-9:
        raise ModelLoadError(
            f"Model window is {model.window_seconds}s but current window is {window_seconds}s")


class AnomalyDetector:
    def __init__(self, model: LoadedModel) -> None:
        self.model = model

    def evaluate(self, features: Mapping[str, float]) -> WindowResult:
        missing = [n for n in self.model.feature_names if n not in features]
        if missing:
            raise FeatureMismatchError(f"Missing features: {missing}")
        x = np.array([[features[n] for n in self.model.feature_names]], dtype=float)
        if not np.isfinite(x).all():
            raise FeatureMismatchError("Features contain NaN or infinite values")
        score = float(self.model.estimator.decision_function(x)[0])
        pred = int(self.model.estimator.predict(x)[0])
        return WindowResult(score, pred, state_from_prediction(pred))


def state_from_prediction(pred: int) -> str:
    if pred == 1:
        return NORMAL
    if pred == -1:
        return ANOMALY
    raise ValueError(f"Unexpected prediction {pred}")

