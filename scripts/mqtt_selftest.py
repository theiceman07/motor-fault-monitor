#!/usr/bin/env python3
"""Security self-test for the Mosquitto broker (M4 Secure MQTT): refusals AND a working login, in one run.
Usage: MQTT_USER=u MQTT_PASSWORD=p python scripts/mqtt_selftest.py --host <broker> --cafile deploy/mosquitto/certs/ca.crt
Checks: anonymous refused, wrong password refused, plain (non-TLS) connection refused, untrusted certificate refused,
correct login over TLS can publish and receive. Exit code 0 only if every check passes. Save the output as evidence."""
import argparse
import os
import ssl
import sys
import threading
import time

import paho.mqtt.client as mqtt

TOPIC = "factory/selftest"


def connect_result(host, port, timeout=6, tls=None, user=None, password=None):
    """Returns (connected: bool, detail: str). tls: None = plain TCP, else cafile path or '' for system CAs."""
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    done, out = threading.Event(), {}

    def on_connect(client, userdata, flags, rc, props=None):
        out["rc"] = rc
        done.set()

    c.on_connect = on_connect
    try:
        if tls is not None:
            c.tls_set(ca_certs=tls or None, cert_reqs=ssl.CERT_REQUIRED)
        if user is not None:
            c.username_pw_set(user, password)
        c.connect(host, port, keepalive=10)
        c.loop_start()
        ok = done.wait(timeout)
    except Exception as exc:                      # TLS/handshake/socket errors
        return False, f"{type(exc).__name__}: {str(exc)[:80]}"
    finally:
        c.loop_stop()
        try:
            c.disconnect()
        except Exception:
            pass
    if not ok:
        return False, "no CONNACK before timeout"
    rc = out["rc"]
    return (not rc.is_failure), str(rc)


def roundtrip(host, port, cafile, user, password, timeout=8):
    got, ready = threading.Event(), threading.Event()
    payload = f"selftest-{time.time()}"
    sub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    sub.tls_set(ca_certs=cafile)
    sub.username_pw_set(user, password)
    sub.on_subscribe = lambda *a, **k: ready.set()
    sub.on_message = lambda c, u, m: got.set() if m.payload.decode() == payload else None
    sub.on_connect = lambda c, u, f, rc, p=None: c.subscribe(TOPIC, qos=1)
    sub.connect(host, port)
    sub.loop_start()
    try:
        if not ready.wait(timeout):
            return False, "subscribe not acknowledged"
        pub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        pub.tls_set(ca_certs=cafile)
        pub.username_pw_set(user, password)
        pub.connect(host, port)
        pub.loop_start()
        pub.publish(TOPIC, payload, qos=1).wait_for_publish(timeout)
        ok = got.wait(timeout)
        pub.loop_stop()
        pub.disconnect()
        return ok, "message received" if ok else "message not received"
    finally:
        sub.loop_stop()
        sub.disconnect()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=8883)
    ap.add_argument("--cafile", default="deploy/mosquitto/certs/ca.crt")
    ap.add_argument("--user", default=os.environ.get("MQTT_USER"))
    ap.add_argument("--password", default=os.environ.get("MQTT_PASSWORD"))
    a = ap.parse_args()
    if not a.user or a.password is None:
        sys.exit("set MQTT_USER and MQTT_PASSWORD (or --user/--password)")
    checks = []
    ok, d = connect_result(a.host, a.port, tls=a.cafile)
    checks.append(("anonymous over TLS is refused", not ok, d))
    ok, d = connect_result(a.host, a.port, tls=a.cafile, user=a.user, password=a.password + "x")
    checks.append(("wrong password is refused", not ok, d))
    ok, d = connect_result(a.host, a.port, tls=None, user=a.user, password=a.password, timeout=4)
    checks.append(("plain (non-TLS) connection is refused", not ok, d))
    ok, d = connect_result(a.host, a.port, tls="", user=a.user, password=a.password)
    checks.append(("untrusted certificate is refused", not ok, d))
    ok, d = connect_result(a.host, a.port, tls=a.cafile, user=a.user, password=a.password)
    checks.append(("correct login over TLS connects", ok, d))
    ok, d = roundtrip(a.host, a.port, a.cafile, a.user, a.password)
    checks.append(("publish + receive over TLS works", ok, d))
    width = max(len(c[0]) for c in checks)
    for name, passed, detail in checks:
        print(f"{'PASS' if passed else 'FAIL'}  {name:{width}s}  [{detail}]")
    sys.exit(0 if all(c[1] for c in checks) else 1)


if __name__ == "__main__":
    main()
