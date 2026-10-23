#!/usr/bin/env python3
"""Drift report: compare window-feature statistics of a later run against a baseline of normal runs (M4 reliability).

Usage: python scripts/drift_report.py --baseline data/raw/<normal_1>.csv [more...] --current data/raw/<later>.csv [--out report.md]
For each feature: baseline mean/std, current mean, shift in baseline standard deviations (z). |z| >= 3 is flagged.
Reports statistics only; it does not say whether drift is harmful.
"""
import _bootstrap  # noqa: F401
import argparse
import sys
from pathlib import Path

import numpy as np

from motor_fault.config import load_config
from motor_fault.features import FEATURE_NAMES
from motor_fault.train import TrainingError, load_features


def drift_table(base, cur, threshold: float = 3.0) -> list[dict]:
    rows = []
    for f in FEATURE_NAMES:
        mu, sd = float(base[f].mean()), float(base[f].std(ddof=1)) if len(base) > 1 else 0.0
        cm = float(cur[f].mean())
        z = (cm - mu) / sd if sd > 1e-12 else (0.0 if abs(cm - mu) < 1e-12 else float("inf"))
        rows.append({"feature": f, "base_mean": mu, "base_std": sd, "cur_mean": cm, "z": z, "flag": abs(z) >= threshold})
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--baseline", nargs="+", required=True, type=Path)
    ap.add_argument("--current", nargs="+", required=True, type=Path)
    ap.add_argument("--threshold", type=float, default=3.0)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    cfg = load_config()
    try:
        base = load_features(a.baseline, cfg.window_seconds, cfg.sample_rate_hz, cfg.min_window_fill)
        cur = load_features(a.current, cfg.window_seconds, cfg.sample_rate_hz, cfg.min_window_fill)
    except (TrainingError, FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    rows = drift_table(base, cur, a.threshold)
    lines = [f"# Drift report ({len(base)} baseline windows, {len(cur)} current windows, flag |z| >= {a.threshold})", "",
             "| feature | baseline mean | baseline std | current mean | shift (z) | flag |", "|---|---|---|---|---|---|"]
    lines += [f"| {r['feature']} | {r['base_mean']:.4f} | {r['base_std']:.4f} | {r['cur_mean']:.4f} | {r['z']:+.2f} | {'DRIFT' if r['flag'] else ''} |" for r in rows]
    lines += ["", f"Flagged features: {sum(r['flag'] for r in rows)} of {len(rows)}"]
    text = "\n".join(lines)
    print(text)
    if a.out:
        a.out.write_text(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
