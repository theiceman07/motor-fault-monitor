# M4 Threat model
| Level | Threat | Mitigation (mark the two you applied and tested) |
|---|---|---|
| Sensor/device | Loose or failed MPU6050 gives stale data | Stale-timeout -> `SENSOR ERROR` (`stale_timeout_s` in config.yaml); no silent fallback to simulation |
| Network | Anonymous or eavesdropped MQTT | Broker with `allow_anonymous false`, password file, TLS on 8883 (`deploy/mosquitto`); test: `test_mqtt.sh` |
| Software | Dashboard exposed on LAN without auth | Bind to 127.0.0.1 / firewall rule; document port |
| Model | Bad update breaks detection | Keep previous model file; rollback after OTA v1 -> v2 |

Applied and demonstrated: 1) ____ 2) ____ (evidence file names: ____)

Status: network mitigation (MQTT password + TLS) was tested on a PC on 2026-10-23: `docs/evidence/mqtt_selftest_pc_2026-10-23.txt`. Repeat on the Pi and list your own two applied mitigations above.
