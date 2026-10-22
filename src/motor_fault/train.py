"""Isolation Forest training from raw recordings or feature CSVs."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from . import __version__
from .features import FEATURE_NAMES, features_from_raw
from .data_store import DataFormatError, RAW_COLUMNS, read_raw_csv
from .inference import ARTIFACT_VERSION


class TrainingError(ValueError):
    pass


@dataclass
class TrainParams:
    n_estimators: int = 100
    contamination: float | str = "auto"   # thresholding assumption, NOT real fault prevalence
    max_samples: int | float | str = "auto"
    random_state: int = 42
    holdout_runs: int = 0


def load_features(paths: list[Path], window_seconds: float, sample_rate_hz: float,
                  min_fill: float = 0.8) -> pd.DataFrame:
    frames = []
    min_samples = max(3, int(sample_rate_hz * window_seconds * min_fill))
    for p in paths:
        header = pd.read_csv(p, nrows=0).columns
        if "ax_g" in header:
            try:
                frames.append(features_from_raw(read_raw_csv(p), window_seconds, min_samples))
            except DataFormatError as exc:
                raise TrainingError(str(exc)) from exc
        elif set(FEATURE_NAMES) <= set(header):
            df = pd.read_csv(p, dtype={"label": str})
            if "run_id" not in df or "sensor_mode" not in df:
                raise TrainingError(f"{p}: feature CSV needs run_id and sensor_mode columns")
            frames.append(df)
        else:
            raise TrainingError(f"{p}: not a raw ({RAW_COLUMNS}) or feature CSV")
    if not frames:
        raise TrainingError("No input files")
    df = pd.concat(frames, ignore_index=True)
    df["label"] = df["label"].fillna("") if "label" in df else ""
    return df


def train_model(df: pd.DataFrame, params: TrainParams, *, window_seconds: float, sample_rate_hz: float,
                confirm_normal: bool = False, allow_simulation: bool = False) -> tuple[dict, dict]:
    """Returns (artifact, summary). Trains only on normal windows."""
    if df.empty:
        raise TrainingError("No windows available (recordings too short or empty)")
    feats = df[FEATURE_NAMES].to_numpy(dtype=float)
    if not np.isfinite(feats).all():
        raise TrainingError("Feature data contains NaN/inf")
    modes = sorted(df["sensor_mode"].unique())
    if len(modes) != 1:
        raise TrainingError(f"Mixed sensor modes in training data: {modes}")
    mode = modes[0]
    if mode == "simulation" and not allow_simulation:
        raise TrainingError("Input is simulated data. Use --allow-simulation for software smoke tests only.")

    warnings: list[str] = []
    labels = df["label"].fillna("").astype(str)
    if (labels == "normal").any():
        train_df = df[labels == "normal"]
        excluded = int((labels != "normal").sum())
        if excluded:
            warnings.append(f"{excluded} windows with non-'normal' or blank labels excluded from training")
    elif (labels == "").all():
        if not confirm_normal:
            raise TrainingError("Data is unlabelled. Re-run with --confirm-normal to assert it is normal operation.")
        train_df = df
    else:
        raise TrainingError(f"No windows labelled 'normal' (labels: {sorted(set(labels))})")

    runs = list(dict.fromkeys(train_df["run_id"]))
    held: list[str] = []
    if params.holdout_runs:
        if len(runs) <= params.holdout_runs:
            raise TrainingError("holdout_runs must be smaller than the number of normal runs")
        held = runs[-params.holdout_runs:]
    fit_df = train_df[~train_df["run_id"].isin(held)]
    if len(runs) < 3:
        warnings.append("Fewer than 3 normal runs: model will not capture run-to-run/session variation")
    if len(fit_df) < 30:
        warnings.append(f"Only {len(fit_df)} training windows; results will be unreliable")
    if mode == "simulation":
        warnings.append("SIMULATED training data: for software testing only, not a real model")

    est = IsolationForest(n_estimators=params.n_estimators, contamination=params.contamination,
                          max_samples=params.max_samples, random_state=params.random_state)
    est.fit(fit_df[FEATURE_NAMES].to_numpy(dtype=float))

    now = datetime.now(timezone.utc)
    meta = {"runs": list(dict.fromkeys(fit_df["run_id"])), "n_windows": int(len(fit_df)),
            "held_out_runs": held, "package_version": __version__}
    artifact = {
        "artifact_version": ARTIFACT_VERSION, "estimator": est, "feature_names": list(FEATURE_NAMES),
        "trained_at_utc": now.isoformat(), "sensor_mode": mode, "sample_rate_hz": sample_rate_hz,
        "window_seconds": window_seconds, "params": asdict(params), "training_metadata": meta,
    }
    summary = {"trained_at_utc": now.isoformat(), "sensor_mode": mode, "n_runs": len(meta["runs"]),
               "n_training_windows": meta["n_windows"], "params": asdict(params),
               "window_seconds": window_seconds, "sample_rate_hz": sample_rate_hz,
               "note": ("Training-set statistics are not evidence of fault-detection quality. "
                        "Evaluate on separate labelled runs."),
               "warnings": warnings}
    if held:
        h = train_df[train_df["run_id"].isin(held)]
        pred = est.predict(h[FEATURE_NAMES].to_numpy(dtype=float))
        summary["held_out_normal_runs"] = held
        summary["held_out_windows"] = int(len(h))
        summary["held_out_flagged_fraction"] = float((pred == -1).mean())
    return artifact, summary


def save_artifact(artifact: dict, summary: dict, model_dir: Path) -> Path:
    model_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = model_dir / f"model_{stamp}.joblib"
    joblib.dump(artifact, path)
    path.with_suffix(".summary.json").write_text(json.dumps(summary, indent=2))
    return path
