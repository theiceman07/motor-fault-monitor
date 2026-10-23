#!/usr/bin/env bash
# Run the secure broker in Docker. Needs certs/ (gen_certs.sh) and passwd (mosquitto_passwd) in this folder.
# Mosquitto 2.1 refuses password/key files with loose permissions, so they are copied inside the container
# with the right owner and mode instead of being used directly from the bind mount.
set -euo pipefail
export MSYS_NO_PATHCONV=1
HERE="$(pwd -W 2>/dev/null || pwd)"
docker rm -f edge-mosq >/dev/null 2>&1 || true
docker run -d --name edge-mosq -p 8883:8883 --user root \
  -v "$HERE/mosquitto.conf:/src/mosquitto.conf:ro" -v "$HERE/certs:/src/certs:ro" -v "$HERE/passwd:/src/passwd:ro" \
  --entrypoint sh eclipse-mosquitto:2 -c '
    mkdir -p /mosquitto/certs /mosquitto/config &&
    cp /src/mosquitto.conf /mosquitto/config/mosquitto.conf && cp /src/passwd /mosquitto/config/passwd && cp /src/certs/ca.crt /src/certs/server.crt /src/certs/server.key /mosquitto/certs/ &&
    chown mosquitto:mosquitto /mosquitto/config/passwd /mosquitto/certs/server.key &&
    chmod 600 /mosquitto/config/passwd /mosquitto/certs/server.key &&
    exec mosquitto -c /mosquitto/config/mosquitto.conf'
sleep 3
docker logs edge-mosq 2>&1 | tail -6
