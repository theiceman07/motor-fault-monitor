#!/usr/bin/env bash
# Shows (1) anonymous client refused, (2) password+TLS client works. Save the output as M4 evidence.
# Usage: bash test_mqtt.sh <host> <user> <password>   (run from deploy/mosquitto, certs/ must exist)
HOST="$1"; USER="$2"; PASS="$3"; T=factory/motor/score
echo "--- anonymous (should FAIL)"; mosquitto_pub -h "$HOST" -p 8883 --cafile certs/ca.crt -t "$T" -m 0.1; echo "exit=$?"
echo "--- authenticated TLS (should work)"
mosquitto_sub -h "$HOST" -p 8883 --cafile certs/ca.crt -u "$USER" -P "$PASS" -t "$T" -C 1 -W 5 &
sleep 1; mosquitto_pub -h "$HOST" -p 8883 --cafile certs/ca.crt -u "$USER" -P "$PASS" -t "$T" -m 0.42; echo "exit=$?"; wait
