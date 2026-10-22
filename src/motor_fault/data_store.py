"""CSV persistence for raw readings and window predictions."""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Sequence

import pandas as pd

from .features import FEATURE_COLUMNS, FEATURE_NAMES, WINDOW_META

RAW_COLUMNS = ["timestamp_utc", "elapsed_seconds", "ax_g", "ay_g", "az_g", "sensor_mode", "run_id", "label"]
PREDICTION_COLUMNS = (
    WINDOW_META + FEATURE_NAMES
    + ["anomaly_score", "prediction", "alert_active", "model_version", "label"]
)


def new_run_id(mode: str, label: str = "", now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    safe = "".join(c for c in label if c.isalnum() or c in "-_")
    return f"{mode}_{now:%Y%m%dT%H%M%S%f}Z" + (f"_{safe}" if safe else "")


class CsvWriter:
    """Append-only CSV writer. Refuses to overwrite an existing file."""

    def __init__(self, path: Path, columns: Sequence[str]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.columns = list(columns)
        try:
            self._fh: IO[str] | None = open(path, "x", newline="", encoding="utf-8")
        except FileExistsError as exc:
            raise FileExistsError(f"Refusing to overwrite existing file: {path}") from exc
        self._w = csv.DictWriter(self._fh, fieldnames=self.columns, extrasaction="ignore")
        self._w.writeheader()
        self._fh.flush()
        self.rows = 0

    def write(self, row: dict) -> None:
        if self._fh is None:
            raise ValueError("writer is closed")
        self._w.writerow(row)
        self.rows += 1

    def flush(self) -> None:
        if self._fh is not None:
            self._fh.flush()

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None


class DataFormatError(ValueError):
    pass


def read_raw_csv(path: Path) -> pd.DataFrame:
    """Read and validate a raw readings CSV."""
    df = pd.read_csv(path, dtype={"label": str, "run_id": str})
    missing = [c for c in RAW_COLUMNS if c not in df.columns]
    if missing:
        raise DataFormatError(f"{path}: missing required columns {missing}")
    if df.empty:
        raise DataFormatError(f"{path}: file has no rows")
    df["label"] = df["label"].fillna("")
    return df


def csv_bytes(path: Path | None) -> bytes | None:
    """File contents for download, or None if missing or header-only."""
    if path is None or not path.exists():
        return None
    data = path.read_bytes()
    return data if data.count(b"\n") > 1 else None


def df_to_csv_bytes(df: pd.DataFrame) -> bytes | None:
    if df.empty:
        return None
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode()


__all__ = ["RAW_COLUMNS", "PREDICTION_COLUMNS", "FEATURE_COLUMNS", "CsvWriter", "new_run_id",
           "read_raw_csv", "csv_bytes", "df_to_csv_bytes", "DataFormatError"]
