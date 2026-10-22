import numpy as np
import pandas as pd
import pytest

from motor_fault.features import FEATURE_NAMES, extract_features, features_from_raw


def test_known_values():
    w = np.array([[1, 0, 0], [-1, 0, 0], [1, 0, 0], [-1, 0, 0]], float)
    f = extract_features(w)
    assert f["ax_rms_g"] == pytest.approx(1.0)
    assert f["ax_std_g"] == pytest.approx(1.0)
    assert f["ax_peak_abs_g"] == 1.0
    assert f["ax_peak_to_peak_g"] == 2.0
    assert f["ay_rms_g"] == 0.0
    assert f["magnitude_rms_g"] == pytest.approx(1.0)
    assert list(f) == FEATURE_NAMES


@pytest.mark.parametrize("bad", [np.empty((0, 3)), np.zeros((1, 3)), np.zeros((5, 2)),
                                 np.array([[np.nan, 0, 0]] * 5), np.array([[np.inf, 0, 0]] * 5)])
def test_invalid_windows(bad):
    with pytest.raises(ValueError):
        extract_features(bad, min_samples=3)


def test_features_from_raw_windows():
    n = 100
    df = pd.DataFrame({"timestamp_utc": [f"t{i}" for i in range(n)], "elapsed_seconds": np.arange(n) / 50,
                       "ax_g": 0.1, "ay_g": 0.0, "az_g": 1.0, "sensor_mode": "mpu6050", "run_id": "a", "label": "normal"})
    out = features_from_raw(df, 1.0, 40)
    assert len(out) == 2 and (out["sample_count"] == 50).all()
    assert (out["label"] == "normal").all()
    assert len(features_from_raw(df, 1.0, 60)) == 0  # too short
