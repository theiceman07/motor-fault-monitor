#!/usr/bin/env python3
"""Publish per-window motor results (from the newest data/processed/*_windows.csv) to MQTT over TLS.

Run alongside the dashboard while monitoring. Topic default: factory/motor/score
Payload: {"ts", "score", "prediction", "alert", "model", "run"}
Credentials come from --user/--password or env MQTT_USER / MQTT_PASSWORD (never commit them).
--dry-run prints payloads instead of connecting (for a smoke test without a broker).
"""
import _bootstrap  # noqa: F401
import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

from motor_fault.config import PROCESSED_DIR


def row_to_payload(row: dict, run: str) -> dict:
    return {"ts": row.get("window_end_utc") or row.get("timestamp_utc") or "",
            "score": float(row["anomaly_score"]), "prediction": int(float(row["prediction"])),
            "alert": str(row.get("alert_active", "")).lower() in ("1", "true"),
            "model": row.get("model_version", ""), "run": run}


def newest_windows_csv(d: Path) -> Path | None:
    files = sorted(d.glob("*_windows.csv"), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=8883)
    ap.add_argument("--cafile", default="deploy/mosquitto/certs/ca.crt")
    ap.add_argument("--user", default=os.environ.get("MQTT_USER"))
    ap.add_argument("--password", default=os.environ.get("MQTT_PASSWORD"))
    ap.add_argument("--topic", default="factory/motor/score")
    ap.add_argument("--dir", type=Path, default=PROCESSED_DIR)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    client = None
    if not a.dry_run:
        import paho.mqtt.client as mqtt
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        client.tls_set(ca_certs=a.cafile)
        if a.user:
            client.username_pw_set(a.user, a.password)
        client.connect(a.host, a.port)
        client.loop_start()
    seen, path = 0, None
    try:
        while True:
            newest = newest_windows_csv(a.dir)
            if newest != path:
                path, seen = newest, 0
            if path:
                rows = list(csv.DictReader(path.open(newline="")))
                for r in rows[seen:]:
                    msg = json.dumps(row_to_payload(r, path.stem))
                    if client:
                        client.publish(a.topic, msg, qos=1)
                    else:
                        print(a.topic, msg)
                seen = len(rows)
            time.sleep(1)
    except KeyboardInterrupt:
        return 0
    finally:
        if client:
            client.loop_stop()
            client.disconnect()


if __name__ == "__main__":
    sys.exit(main())
