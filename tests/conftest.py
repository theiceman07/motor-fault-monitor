import numpy as np
import pandas as pd
import pytest

from motor_fault.features import FEATURE_NAMES
from motor_fault.train import TrainParams, train_model


def make_features(n=60, seed=0, mode="mpu6050", runs=3, label="normal", scale=1.0):
    rng = np.random.default_rng(seed)
    X = rng.normal(0.1 * scale, 0.01, (n, len(FEATURE_NAMES)))
    df = pd.DataFrame(X, columns=FEATURE_NAMES)
    df["run_id"] = [f"r{i % runs}" for i in range(n)]
    df["sensor_mode"] = mode
    df["label"] = label
    return df


@pytest.fixture
def artifact():
    art, _ = train_model(make_features(), TrainParams(n_estimators=20), window_seconds=1.0, sample_rate_hz=50)
    return art
