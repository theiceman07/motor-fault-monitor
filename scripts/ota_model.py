#!/usr/bin/env python3
"""Model update with rollback (M4 reliability: OTA v1 -> v2 and back).

The app uses the newest data/models/model_*.joblib. This script:
  install <artifact>  validate the artifact loads, then add it as the newest model (older ones stay)
  rollback            move the newest model (and its summary) to data/models/archive/ so the previous one is active again
  status              list models, active one first
Nothing is deleted; an invalid artifact is rejected before anything changes.
"""
import _bootstrap  # noqa: F401
import argparse
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from motor_fault.config import MODEL_DIR
from motor_fault.inference import FeatureMismatchError, ModelLoadError, find_latest_model, load_model


def models(model_dir: Path) -> list[Path]:
    return sorted(model_dir.glob("model_*.joblib")) if model_dir.exists() else []


def install(artifact: Path, model_dir: Path) -> Path:
    load_model(artifact)                                   # raises ModelLoadError / FeatureMismatchError if bad
    model_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    dest = model_dir / f"model_{stamp}.joblib"
    shutil.copy2(artifact, dest)
    summary = artifact.with_suffix(".summary.json")
    if summary.exists():
        shutil.copy2(summary, dest.with_suffix(".summary.json"))
    return dest


def rollback(model_dir: Path) -> tuple[Path, Path | None]:
    """Returns (archived model, new active model or None)."""
    current = find_latest_model(model_dir)
    if current is None:
        raise ModelLoadError("no model to roll back")
    archive = model_dir / "archive"
    archive.mkdir(exist_ok=True)
    moved = archive / current.name
    shutil.move(str(current), moved)
    s = current.with_suffix(".summary.json")
    if s.exists():
        shutil.move(str(s), archive / s.name)
    return moved, find_latest_model(model_dir)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["install", "rollback", "status"])
    ap.add_argument("artifact", nargs="?", type=Path)
    ap.add_argument("--model-dir", type=Path, default=MODEL_DIR)
    a = ap.parse_args(argv)
    try:
        if a.action == "install":
            if a.artifact is None:
                ap.error("install needs an artifact path")
            prev = find_latest_model(a.model_dir)
            new = install(a.artifact, a.model_dir)
            print(f"installed {new.name}; previous active: {prev.name if prev else 'none'}")
        elif a.action == "rollback":
            moved, active = rollback(a.model_dir)
            print(f"archived {moved.name}; active now: {active.name if active else 'none (app will report MODEL NOT TRAINED)'}")
        else:
            ms = models(a.model_dir)
            for i, m in enumerate(reversed(ms)):
                print(("ACTIVE  " if i == 0 else "         ") + m.name)
            if not ms:
                print("no models")
    except (ModelLoadError, FeatureMismatchError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
