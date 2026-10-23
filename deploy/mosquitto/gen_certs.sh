#!/usr/bin/env bash
# Self-signed CA + server cert for the broker. Usage: bash gen_certs.sh <broker-hostname-or-ip>
# The certificate carries a subjectAltName (required by modern TLS clients): the name you pass must be the one clients connect to.
set -euo pipefail
export MSYS_NO_PATHCONV=1            # Git Bash on Windows would otherwise rewrite /CN=... as a path
HOST="${1:?broker hostname or IP}"; mkdir -p certs; cd certs
if [[ "$HOST" =~ ^[0-9.]+$ ]]; then SAN="IP:$HOST"; else SAN="DNS:$HOST"; fi
printf "subjectAltName=%s\n" "$SAN" > san.ext
openssl req -x509 -newkey rsa:2048 -nodes -days 365 -subj "/CN=edge-ca" -keyout ca.key -out ca.crt
openssl req -newkey rsa:2048 -nodes -subj "/CN=$HOST" -keyout server.key -out server.csr
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial -days 365 -extfile san.ext -out server.crt
echo "Created certs/ca.crt server.crt server.key (SAN $SAN). Create a user: mosquitto_passwd -c passwd <user>"
