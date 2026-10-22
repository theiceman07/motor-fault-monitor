"""Window feature extraction.

Acceleration is in g and INCLUDES gravity (no filtering / gravity removal in v1).
Use a consistent mounting orientation: RMS and peak features of the axis aligned
with gravity contain the ~1 g offset; std and peak-to-peak do not.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

AXES = ("ax", "ay", "az")
FEATURE_NAMES: list[str] = (
    [f"{a}_rms_g" for a in AXES]
    + [f"{a}_std_g" for a in AXES]
    + [f"{a}_peak_abs_g" for a in AXES]
    + [f"{a}_peak_to_peak_g" for a in AXES]
    + ["magnitude_rms_g"]
)
WINDOW_META = ["run_id", "window_start_utc", "window_end_utc", "sample_count", "sensor_mode"]
FEATURE_COLUMNS = WINDOW_META + FEATURE_NAMES + ["label"]


def extract_features(window: np.ndarray, min_samples: int = 2) -> dict[str, float]:
    """Features from a finite array of shape (n_samples, 3), in g."""
    arr = np.asarray(window, dtype=float)
    if arr.ndim != 2 or arr.shape[1] != 3:
        raise ValueError(f"window must have shape (n, 3), got {arr.shape}")
    if arr.shape[0] == 0:
        raise ValueError("window is empty")
    if arr.shape[0] < min_samples:
        raise ValueError(f"window has {arr.shape[0]} samples, need at least {min_samples}")
    if not np.isfinite(arr).all():
        raise ValueError("window contains NaN or infinite values")
    rms = np.sqrt(np.mean(arr**2, axis=0))
    std = np.std(arr, axis=0)
    peak = np.max(np.abs(arr), axis=0)
    p2p = np.ptp(arr, axis=0)
    mag_rms = float(np.sqrt(np.mean(np.sum(arr**2, axis=1))))
    out: dict[str, float] = {}
    for prefix, vals in (("rms", rms), ("std", std), ("peak_abs", peak), ("peak_to_peak", p2p)):
        for a, v in zip(AXES, vals):
            out[f"{a}_{prefix}_g"] = float(v)
    out["magnitude_rms_g"] = mag_rms
    return out


def features_from_raw(raw: pd.DataFrame, window_seconds: float, min_samples: int) -> pd.DataFrame:
    """Fixed, non-overlapping windows per run, binned by ``elapsed_seconds``."""
    rows: list[dict] = []
    for run_id, g in raw.groupby("run_id", sort=False):
        g = g.dropna(subset=["ax_g", "ay_g", "az_g", "elapsed_seconds"])
        g = g[np.isfinite(g[["ax_g", "ay_g", "az_g"]].to_numpy()).all(axis=1)]
        if g.empty:
            continue
        bins = np.floor(g["elapsed_seconds"].to_numpy() / window_seconds).astype(int)
        for b in np.unique(bins):
            w = g[bins == b]
            if len(w) < min_samples:
                continue
            labels = w["label"].fillna("").astype(str).unique()
            label = labels[0] if len(labels) == 1 else ""
            rows.append({
                "run_id": run_id,
                "window_start_utc": w["timestamp_utc"].iloc[0],
                "window_end_utc": w["timestamp_utc"].iloc[-1],
                "sample_count": len(w),
                "sensor_mode": w["sensor_mode"].iloc[0],
                **extract_features(w[["ax_g", "ay_g", "az_g"]].to_numpy(), min_samples=min_samples),
                "label": label,
            })
    return pd.DataFrame(rows, columns=FEATURE_COLUMNS)
