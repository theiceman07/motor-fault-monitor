#!/usr/bin/env python3
"""Record a labelled raw-data run to data/raw/. Never falls back to simulation."""
import _bootstrap  # noqa: F401
import argparse
import logging
import sys
import time

from motor_fault.acquisition import SamplingThread
from motor_fault.config import RAW_DIR, ConfigError, load_config
from motor_fault.data_store import RAW_COLUMNS, CsvWriter, new_run_id
from motor_fault.factory import make_sensor
from motor_fault.sensor_base import Sample, SensorError


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=["hardware", "simulation"], required=True)
    ap.add_argument("--sensor", choices=["mpu6050", "adxl345"], default="mpu6050",
                    help="hardware sensor type (only with --mode hardware)")
    ap.add_argument("--label", default="", help="e.g. normal, imbalance, loose_mount")
    ap.add_argument("--duration", type=float, default=60.0, help="seconds")
    ap.add_argument("--sample-rate", type=float, default=None)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.duration <= 0:
        ap.error("--duration must be > 0")
    try:
        cfg = load_config(sample_rate_hz=args.sample_rate)
    except ConfigError as exc:
        ap.error(str(exc))
    mode = "simulation" if args.mode == "simulation" else args.sensor
    sensor = make_sensor(mode, cfg)
    try:
        sensor.open()  # fail fast; no fallback
    except SensorError as exc:
        print(f"ERROR: {exc}\nCheck wiring, enable I2C (sudo raspi-config), and run: python scripts/check_i2c.py",
              file=sys.stderr)
        return 2
    if mode == "simulation":
        print("NOTE: SIMULATED data - for software testing only.")

    run_id = new_run_id(mode, args.label)
    writer = CsvWriter(RAW_DIR / f"{run_id}.csv", RAW_COLUMNS)
    t0: list[float] = []

    def on_sample(s: Sample) -> None:
        if not t0:
            t0.append(s.mono)
        writer.write({"timestamp_utc": s.utc.isoformat(), "elapsed_seconds": f"{s.mono - t0[0]:.4f}",
                      "ax_g": f"{s.ax:.6f}", "ay_g": f"{s.ay:.6f}", "az_g": f"{s.az:.6f}",
                      "sensor_mode": mode, "run_id": run_id, "label": args.label})

    errors: list[str] = []
    th = SamplingThread(sensor, cfg.sample_rate_hz, on_sample, lambda e: e and errors.append(e))
    th.start()
    start = time.monotonic()
    try:
        while time.monotonic() - start < args.duration:
            time.sleep(0.25)
    except KeyboardInterrupt:
        print("Interrupted; saving what was recorded.")
    elapsed = time.monotonic() - start
    th.stop()
    writer.close()
    n = th.sample_count
    expected = int(elapsed * cfg.sample_rate_hz)
    print(f"Samples: {n}  Elapsed: {elapsed:.1f}s  Achieved rate: {n / elapsed if elapsed else 0:.1f} Hz "
          f"(requested {cfg.sample_rate_hz} Hz)  Missing vs requested: {max(0, expected - n)}")
    print(f"Output: {writer.path}")
    if errors:
        print(f"WARNING: {len(errors)} sensor error report(s); last: {errors[-1]}", file=sys.stderr)
    if n == 0:
        print("ERROR: no samples recorded.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
