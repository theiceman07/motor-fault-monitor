#!/usr/bin/env bash
# Self-signed CA + server cert for the broker. Usage: bash gen_certs.sh <broker-hostname-or-ip>
set -euo pipefail
HOST="${1:?broker hostname or IP}"; mkdir -p certs; cd certs
openssl req -x509 -newkey rsa:2048 -nodes -days 365 -subj "/CN=edge-ca" -keyout ca.key -out ca.crt
openssl req -newkey rsa:2048 -nodes -subj "/CN=$HOST" -keyout server.key -out server.csr
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial -days 365 -out server.crt
echo "Created certs/ca.crt server.crt server.key. Create a user: mosquitto_passwd -c passwd <user>"
