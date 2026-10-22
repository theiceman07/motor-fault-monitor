> **Origin:** this repo starts from code in https://github.com/theiceman07/fault-detection (initial commit be818c2). Model weights from that repo are NOT included. All measurements, datasets and results added here are produced by me on my own device; see the commit history.

# Motor Health Monitor (Raspberry Pi 5)

Local motor-vibration anomaly detection: IMU/accelerometer over I²C → window features → scikit-learn
`IsolationForest` → Streamlit dashboard with live charts, alerts and CSV export. No cloud, no network at runtime.

> **Prototype, not a safety system.** Isolation Forest reports *unusual* windows relative to the normal data it was
> trained on. It does not diagnose fault types and is **not validated** until you test it on real recordings from your
> own motor and sensor. Simulation data is for software smoke tests only.

## Install
```bash
sudo apt update && sudo apt install -y python3-venv python3-pip i2c-tools
cd "<project folder>"
python3 -m venv .venv && source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pytest -q
```

## Run in simulation mode (no hardware)
```bash
streamlit run app.py --server.address 127.0.0.1
```
Choose **Simulation** → *Start*. Without a model the status is `MODEL NOT TRAINED`. To get a demo model:
```bash
python scripts/collect_data.py --mode simulation --label normal --duration 100   # repeat 3x
python scripts/train_model.py --input data/raw/simulation_*_normal.csv --allow-simulation
```
Restart monitoring; status shows `SIMULATION` (with the last window's NORMAL/ANOMALY in the detail line). Use the
"Inject SIMULATED fault" toggle to see the anomaly path. Simulation-trained models are only usable in simulation mode.

## Wiring (MPU6050 / GY-521) — verify against your breakout's documentation
| Sensor | Pi 5 pin |
|---|---|
| VCC | 3.3 V (pin 1) — only if your board supports it |
| GND | GND (pin 6) |
| SDA | GPIO2 / pin 3 |
| SCL | GPIO3 / pin 5 |

Never power the motor from GPIO. Use an external supply and a proper driver/MOSFET with common ground. Mount the sensor
rigidly, keep wires away from rotating parts.

Enable I²C: `sudo raspi-config` → Interface Options → I2C, reboot, then `i2cdetect -y 1` (MPU6050 usually `0x68`,
ADXL345 `0x53`). Then:
```bash
python scripts/check_i2c.py --sensor mpu6050
```
ADXL345 support is written from the datasheet and untested on hardware; MPU6050 is the supported target.

## Real-data workflow
1. Mount sensor; keep orientation, voltage, load and placement consistent. Acceleration **includes gravity**.
2. Collect several normal runs across separate starts/sessions:
   `python scripts/collect_data.py --mode hardware --sensor mpu6050 --label normal --duration 120`
   (fails with exit code 2 and never falls back to simulation if the sensor can't be read).
3. Train: `python scripts/train_model.py --input data/raw/<normal_1>.csv data/raw/<normal_2>.csv data/raw/<normal_3>.csv --holdout-runs 1`
   Unlabelled data requires `--confirm-normal`. Options: `--n-estimators`, `--contamination` (a thresholding assumption,
   not the real fault rate), `--max-samples`, `--seed`.
4. Optionally record safe, guarded abnormal runs with `--label imbalance` (etc.) and evaluate on runs *not used for
   training*: `python scripts/evaluate_model.py --input <labelled csvs>`.
5. `streamlit run app.py`, choose **Real hardware**, *Start*.

Windows: fixed 1 s, non-overlapping. Features per axis: RMS, std, peak |a|, peak-to-peak; plus magnitude RMS.
Sample rate defaults to 50 Hz from a Python loop; the achieved rate is displayed and logged. It cannot capture
high-frequency bearing faults. Defaults live in `config.yaml`.

## Statuses
`NORMAL`, `ANOMALY` (model inlier/outlier), `SENSOR ERROR` (I²C failure, stale/invalid data — independent of the ML
model), `INSUFFICIENT DATA`, `MODEL NOT TRAINED` (missing or incompatible model, e.g. trained on other sensor mode or
window length), `SIMULATION`, `IDLE`. The score is `decision_function` (<0 = outlier; not a probability). A prominent
alert needs N consecutive anomalous windows (default 3); raw per-window predictions are always kept in the CSV.

## Data files (git-ignored)
- `data/raw/<run_id>.csv`: `timestamp_utc, elapsed_seconds, ax_g, ay_g, az_g, sensor_mode, run_id, label`
- `data/processed/<run_id>_windows.csv`: `run_id, window_start_utc, window_end_utc, sample_count, sensor_mode`, 13
  feature columns, `anomaly_score, prediction (1/-1), alert_active, model_version, label`
- `data/models/model_<utc>.joblib` + `.summary.json`. Only load models you created: joblib files can execute code.

Files are never overwritten; each run gets a unique name. Streamlit should stay bound to localhost.

## Troubleshooting
- `/dev/i2c-1` missing → I²C not enabled. Nothing at `i2cdetect` → check wiring/power/address (AD0 pin).
- Achieved rate far below target → lower the rate or reduce Pi load.
- `MODEL NOT TRAINED` with a message → model mode/window mismatch; retrain with matching settings.
- Frequent false alarms → collect more normal runs across sessions; consider `--contamination` and the debounce setting.

## Layout
`app.py` dashboard · `src/motor_fault/` library · `scripts/` CLIs · `tests/` (`pytest -q`, no hardware needed).
