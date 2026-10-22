#!/usr/bin/env python3
"""Evaluate a saved model on labelled raw recordings NOT used for training."""
import _bootstrap  # noqa: F401
import argparse
import sys
from pathlib import Path

import pandas as pd

from motor_fault.config import MODEL_DIR, load_config
from motor_fault.features import FEATURE_NAMES
from motor_fault.inference import AnomalyDetector, ModelLoadError, find_latest_model, load_model
from motor_fault.train import TrainingError, load_features


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", nargs="+", required=True, type=Path)
    ap.add_argument("--model", type=Path, default=None, help="default: newest in data/models")
    a = ap.parse_args(argv)
    try:
        model = load_model(a.model or find_latest_model(MODEL_DIR))
        cfg = load_config(window_seconds=model.window_seconds, sample_rate_hz=model.sample_rate_hz)
        df = load_features(a.input, cfg.window_seconds, cfg.sample_rate_hz, cfg.min_window_fill)
    except (ModelLoadError, TrainingError, FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    det = AnomalyDetector(model)
    df["pred"] = [det.evaluate(r).prediction for r in df[FEATURE_NAMES].to_dict("records")]
    df["label"] = df["label"].replace("", "(unlabelled)")
    print(f"Model: {model.version} (trained on {model.sensor_mode}); evaluated windows: {len(df)}")
    t = df.groupby("label")["pred"].agg(windows="count", flagged=lambda s: int((s == -1).sum()))
    t["flagged_fraction"] = (t["flagged"] / t["windows"]).round(3)
    print(t.to_string())
    print("\nflagged_fraction on 'normal' = false-positive rate; on fault labels = detection rate.")
    print("Only meaningful on runs/sessions not used for training and with few runs it is a rough indication.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
