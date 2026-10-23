import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mqtt_bridge import newest_windows_csv, row_to_payload  # noqa: E402


def test_row_to_payload():
    p = row_to_payload({"anomaly_score": "-0.12", "prediction": "-1", "alert_active": "True",
                        "model_version": "model_x"}, "run1")
    assert p["score"] == -0.12 and p["prediction"] == -1 and p["alert"] is True and p["run"] == "run1"


def test_newest_none(tmp_path):
    assert newest_windows_csv(tmp_path) is None
    (tmp_path / "a_windows.csv").write_text("x")
    assert newest_windows_csv(tmp_path).name == "a_windows.csv"
