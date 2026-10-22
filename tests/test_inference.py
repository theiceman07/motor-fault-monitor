import joblib
import pytest

from motor_fault.alerts import AlertPolicy
from motor_fault.features import FEATURE_NAMES
from motor_fault.inference import (ANOMALY, NORMAL, AnomalyDetector, FeatureMismatchError, ModelLoadError,
                                   check_compatible, find_latest_model, load_model, state_from_prediction)
from motor_fault.train import TrainingError, TrainParams, train_model
from conftest import make_features


def test_mapping():
    assert state_from_prediction(1) == NORMAL and state_from_prediction(-1) == ANOMALY
    with pytest.raises(ValueError):
        state_from_prediction(0)


def test_save_load_and_score(tmp_path, artifact):
    p = tmp_path / "model_x.joblib"
    joblib.dump(artifact, p)
    assert find_latest_model(tmp_path) == p
    m = load_model(p)
    det = AnomalyDetector(m)
    normal = {n: 0.1 for n in FEATURE_NAMES}
    far = {n: 50.0 for n in FEATURE_NAMES}
    assert det.evaluate(normal).prediction == 1
    r = det.evaluate(far)
    assert r.prediction == -1 and r.score < 0 and r.state == ANOMALY


def test_missing_model(tmp_path):
    assert find_latest_model(tmp_path) is None
    with pytest.raises(ModelLoadError):
        load_model(None)


def test_feature_order_mismatch(tmp_path, artifact):
    artifact["feature_names"] = list(reversed(FEATURE_NAMES))
    p = tmp_path / "m.joblib"
    joblib.dump(artifact, p)
    with pytest.raises(FeatureMismatchError):
        load_model(p)


def test_missing_or_nan_feature(tmp_path, artifact):
    p = tmp_path / "m.joblib"
    joblib.dump(artifact, p)
    det = AnomalyDetector(load_model(p))
    f = {n: 0.1 for n in FEATURE_NAMES}
    with pytest.raises(FeatureMismatchError):
        det.evaluate({k: v for k, v in f.items() if k != "ax_rms_g"})
    f["ax_rms_g"] = float("nan")
    with pytest.raises(FeatureMismatchError):
        det.evaluate(f)


def test_compat(tmp_path, artifact):
    p = tmp_path / "m.joblib"
    joblib.dump(artifact, p)
    m = load_model(p)
    check_compatible(m, "mpu6050", 1.0)
    with pytest.raises(ModelLoadError):
        check_compatible(m, "simulation", 1.0)
    with pytest.raises(ModelLoadError):
        check_compatible(m, "mpu6050", 2.0)


def test_training_guards():
    p = TrainParams(n_estimators=10)
    with pytest.raises(TrainingError):
        train_model(make_features(mode="simulation"), p, window_seconds=1, sample_rate_hz=50)
    with pytest.raises(TrainingError):
        train_model(make_features().iloc[0:0], p, window_seconds=1, sample_rate_hz=50)
    unl = make_features(label="")
    with pytest.raises(TrainingError):
        train_model(unl, p, window_seconds=1, sample_rate_hz=50)
    art, s = train_model(unl, p, window_seconds=1, sample_rate_hz=50, confirm_normal=True)
    assert s["n_training_windows"] == 60
    mixed = make_features(label="imbalance")
    with pytest.raises(TrainingError):
        train_model(mixed, p, window_seconds=1, sample_rate_hz=50)


def test_holdout_by_run():
    _, s = train_model(make_features(), TrainParams(n_estimators=10, holdout_runs=1),
                       window_seconds=1, sample_rate_hz=50)
    assert s["held_out_normal_runs"] == ["r2"] and 0 <= s["held_out_flagged_fraction"] <= 1


def test_debounce():
    a = AlertPolicy(3)
    assert [a.update(-1)[0] for _ in range(3)] == [False, False, True]
    assert a.update(1)[0] is False
