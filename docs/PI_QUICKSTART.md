# Raspberry Pi 5 quick start: motor monitor (Raspberry Pi OS Bookworm 64-bit)
Written on a PC and **not yet tested on a Pi**: if a step fails, note the error and fix this file.

## 1. Install and get the code
```bash
sudo apt update && sudo apt install -y git python3-venv python3-pip i2c-tools
sudo raspi-config nonint do_i2c 0 && sudo reboot            # enable I2C (or raspi-config -> Interface Options -> I2C)
git clone https://github.com/theiceman07/motor-fault-monitor.git && cd motor-fault-monitor
git switch -c <your-first-name>                              # your own branch for your own evidence (docs/BRANCHING.md)
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip && pip install -r requirements.txt pytest
python -m pytest -q                                          # expect: 34 passed
```

## 2. Wire the MPU6050 and check it (M4 sensor data)
VCC to 3.3 V (pin 1), GND to GND (pin 6), SDA to GPIO2 (pin 3), SCL to GPIO3 (pin 5). Never power the motor from GPIO: use its own supply and a driver with a common ground.
```bash
i2cdetect -y 1                                  # expect 0x68
python scripts/check_i2c.py --sensor mpu6050
```
Screenshot both outputs. Mount the sensor rigidly and keep orientation, voltage and mounting identical for every run.

## 3. Record data (3 normal + 3 fault runs, plus 5 extra normal runs for the false-alarm count)
```bash
python scripts/collect_data.py --mode hardware --sensor mpu6050 --label normal --duration 60      # x3, separate starts
python scripts/collect_data.py --mode hardware --sensor mpu6050 --label imbalance --duration 60   # x3, safe and guarded
```
Never use `--mode simulation` data as evidence; it is for software tests only. Commit the CSVs from `data/raw/` on your branch (they are git-ignored by default: use `git add -f`).

## 4. Train on normal data only and run
```bash
python scripts/train_model.py --input data/raw/*_normal.csv --holdout-runs 1
python scripts/evaluate_model.py --input <held-out normal csv> <fault csvs>
streamlit run app.py --server.address 127.0.0.1        # choose Real hardware -> Start, then inject the fault
```
Count false alarms over the 5 extra normal runs and explain your threshold (`--contamination`, `debounce_windows` in `config.yaml`).

## 5. Secure MQTT and reliability (M4)
```bash
sudo apt install -y mosquitto mosquitto-clients && cd deploy/mosquitto && bash gen_certs.sh <pi-hostname-or-ip>
mosquitto_passwd -c passwd <user>        # then: sudo chown mosquitto: passwd && sudo chmod 600 passwd; run mosquitto with mosquitto.conf
cd ../.. && MQTT_USER=<user> MQTT_PASSWORD=<password> python scripts/mqtt_selftest.py --host <pi-hostname-or-ip>
MQTT_USER=<user> MQTT_PASSWORD=<password> python scripts/mqtt_bridge.py --host <pi-hostname-or-ip> --cafile deploy/mosquitto/certs/ca.crt
python scripts/ota_model.py install <model.joblib>; python scripts/ota_model.py rollback
python scripts/drift_report.py --baseline <normal csvs> --current <later csv>
```
Save the self-test output as evidence. Never commit `passwd`, `certs/` or passwords. Details and a PC example: `README.md`, `docs/evidence/`.

## 6. Auto-start
Edit user and paths in `deploy/motor-monitor.service`, copy to `/etc/systemd/system/`, `sudo systemctl enable --now motor-monitor`, then `sudo reboot` and confirm it is back.

Evidence rules: commit only numbers you measured yourself, on your own branch, with the milestone in the commit message.
