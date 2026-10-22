#!/usr/bin/env python3
"""Train an Isolation Forest on normal-operation recordings."""
import _bootstrap  # noqa: F401
import argparse
import json
import sys
from pathlib import Path

from motor_fault.config import MODEL_DIR, ConfigError, load_config
from motor_fault.train import TrainParams, TrainingError, load_features, save_artifact, train_model


def _maxs(v: str):
    if v == "auto":
        return v
    return float(v) if "." in v else int(v)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", nargs="+", required=True, type=Path, help="raw or feature CSV file(s)")
    ap.add_argument("--confirm-normal", action="store_true",
                    help="assert that UNLABELLED input contains only normal operation")
    ap.add_argument("--allow-simulation", action="store_true", help="permit simulated data (software tests only)")
    ap.add_argument("--n-estimators", type=int, default=100)
    ap.add_argument("--contamination", default="auto",
                    help="'auto' or a float in (0, 0.5]; a thresholding assumption, not real fault prevalence")
    ap.add_argument("--max-samples", type=_maxs, default="auto")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--holdout-runs", type=int, default=0, help="hold out last N normal runs to report flag rate")
    ap.add_argument("--sample-rate", type=float, default=None)
    ap.add_argument("--window-seconds", type=float, default=None)
    ap.add_argument("--model-dir", type=Path, default=MODEL_DIR)
    a = ap.parse_args(argv)
    try:
        cfg = load_config(sample_rate_hz=a.sample_rate, window_seconds=a.window_seconds)
        cont = a.contamination if a.contamination == "auto" else float(a.contamination)
        if cont != "auto" and not 0 < cont <= 0.5:
            ap.error("--contamination must be 'auto' or in (0, 0.5]")
        params = TrainParams(a.n_estimators, cont, a.max_samples, a.seed, a.holdout_runs)
        df = load_features(a.input, cfg.window_seconds, cfg.sample_rate_hz, cfg.min_window_fill)
        art, summary = train_model(df, params, window_seconds=cfg.window_seconds,
                                   sample_rate_hz=cfg.sample_rate_hz, confirm_normal=a.confirm_normal,
                                   allow_simulation=a.allow_simulation)
    except (TrainingError, ConfigError, FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    path = save_artifact(art, summary, a.model_dir)
    print(json.dumps(summary, indent=2))
    print(f"Model saved: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
