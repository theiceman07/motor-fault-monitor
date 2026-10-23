import sys
import time
from pathlib import Path

import joblib
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import drift_report  # noqa: E402
import ota_model  # noqa: E402
from conftest import make_features  # noqa: E402
from motor_fault.inference import ModelLoadError, find_latest_model  # noqa: E402


def _save(art, path):
    joblib.dump(art, path)
    return path


def test_install_then_rollback_restores_previous(artifact, tmp_path):
    d = tmp_path / "models"
    a1 = _save(artifact, tmp_path / "v1.joblib")
    a2 = _save(artifact, tmp_path / "v2.joblib")
    v1 = ota_model.install(a1, d)
    time.sleep(0.01)
    v2 = ota_model.install(a2, d)
    assert find_latest_model(d) == v2
    moved, active = ota_model.rollback(d)
    assert active == v1 and moved.parent.name == "archive" and moved.exists()
    assert find_latest_model(d) == v1


def test_invalid_artifact_is_rejected_and_nothing_changes(artifact, tmp_path):
    d = tmp_path / "models"
    good = ota_model.install(_save(artifact, tmp_path / "v1.joblib"), d)
    bad = tmp_path / "bad.joblib"
    bad.write_text("not a model")
    with pytest.raises(ModelLoadError):
        ota_model.install(bad, d)
    assert find_latest_model(d) == good and len(list(d.glob("model_*.joblib"))) == 1


def test_rollback_with_no_model_raises(tmp_path):
    with pytest.raises(ModelLoadError):
        ota_model.rollback(tmp_path / "models")


def test_drift_flags_shifted_feature_only():
    base = make_features(n=200, seed=1)
    cur = make_features(n=200, seed=2)
    cur["ax_rms_g"] = cur["ax_rms_g"] + 0.1                  # 10 baseline standard deviations
    rows = {r["feature"]: r for r in drift_report.drift_table(base, cur)}
    assert rows["ax_rms_g"]["flag"] and rows["ax_rms_g"]["z"] > 5
    assert not rows["ay_rms_g"]["flag"]
