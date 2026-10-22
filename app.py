"""Motor Health Monitor - local Streamlit dashboard.  Run: streamlit run app.py"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import atexit  # noqa: E402

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from motor_fault.config import MODEL_DIR, ConfigError, load_config  # noqa: E402
from motor_fault.dashboard_state import MonitorSession  # noqa: E402
from motor_fault.data_store import csv_bytes  # noqa: E402
from motor_fault.factory import make_sensor, try_load_model  # noqa: E402
from motor_fault.features import FEATURE_NAMES  # noqa: E402
from motor_fault.inference import (ANOMALY, IDLE, INSUFFICIENT, NO_MODEL, NORMAL,  # noqa: E402
                                   SENSOR_ERROR, SIMULATION)

st.set_page_config(page_title="Motor Health Monitor", layout="wide")

STYLE = {
    NORMAL: ("#1b7f3b", "#e8f5ec"), ANOMALY: ("#b3261e", "#fdecea"), SENSOR_ERROR: ("#8a4b00", "#fff1dc"),
    NO_MODEL: ("#555", "#eee"), SIMULATION: ("#5b3fa0", "#f1ecfb"), INSUFFICIENT: ("#6b5d00", "#fff9d6"),
    IDLE: ("#444", "#f2f2f2"),
}


@st.cache_resource
def holder() -> dict:
    h: dict = {"session": None}
    atexit.register(lambda: h["session"] and h["session"].stop())
    return h


H = holder()


def current() -> MonitorSession | None:
    return H["session"]


st.title("Motor Health Monitor")

# ---------------- sidebar ----------------
sess = current()
running = bool(sess and sess.running)
with st.sidebar:
    st.header("Setup")
    mode_ui = st.radio("Mode", ["Simulation", "Real hardware"], disabled=running)
    sensor_type = "simulation"
    if mode_ui == "Real hardware":
        sensor_type = st.selectbox("Sensor", ["mpu6050", "adxl345"], disabled=running,
                                   help="MPU6050 is the supported first target; ADXL345 is untested on hardware.")
    rate = st.number_input("Sample rate (Hz, requested)", 5, 500, 50, disabled=running)
    win = st.number_input("Window (s)", 0.5, 10.0, 1.0, 0.5, disabled=running)
    debounce = st.number_input("Alert after N consecutive anomalous windows", 1, 20, 3, disabled=running)
    label = st.text_input("Recording label (optional)", "", disabled=running,
                          help="e.g. normal, imbalance. Stored in the CSV.")
    models = sorted(MODEL_DIR.glob("model_*.joblib")) if MODEL_DIR.exists() else []
    choice = st.selectbox("Model", ["(latest)"] + [m.name for m in models], disabled=running)
    c1, c2 = st.columns(2)
    start = c1.button("Start / new recording", disabled=running, type="primary")
    stop = c2.button("Stop", disabled=not running)
    if running and sess and sess.mode == "simulation":
        sim_fault = st.toggle("Inject SIMULATED fault (demo)", value=getattr(sess.sensor, "fault", False))
        sess.sensor.fault = sim_fault  # type: ignore[attr-defined]

if stop and sess:
    sess.stop()
    st.rerun()

if start:
    try:
        cfg = load_config(sample_rate_hz=float(rate), window_seconds=float(win), debounce_windows=int(debounce))
        model, problem = try_load_model(sensor_type, cfg, None if choice == "(latest)" else MODEL_DIR / choice)
        if sess:
            sess.stop()
        H["session"] = MonitorSession(cfg, make_sensor(sensor_type, cfg), model, problem, label=label.strip())
        H["session"].start()
        st.rerun()
    except (ConfigError, FileExistsError, ValueError) as exc:
        st.error(str(exc))

sess = current()

# ---------------- live panel ----------------
def render_status(snap: dict) -> None:
    fg, bg = STYLE.get(snap["status"], STYLE[IDLE])
    st.markdown(
        f"<div style='background:{bg};border-left:8px solid {fg};padding:14px 18px;border-radius:6px'>"
        f"<div style='font-size:1.8rem;font-weight:700;color:{fg}'>{snap['status']}</div>"
        f"<div style='color:{fg}'>{snap['detail']}</div></div>", unsafe_allow_html=True)
    if snap["alert_active"]:
        st.error("ALERT: consecutive anomalous windows detected" + (" (simulated data)" if snap["mode"] == "simulation" else ""))


@st.fragment(run_every=1)
def live_panel() -> None:
    s = current()
    if s is None:
        cfg = load_config()
        model, problem = try_load_model(sensor_type, cfg)
        render_status({"status": NO_MODEL if model is None else IDLE,
                       "detail": problem or "Press Start", "alert_active": False, "mode": sensor_type})
        if mode_ui == "Simulation":
            st.info("Simulation mode produces SYNTHETIC demo data. It is not a real motor measurement.")
        return
    snap = s.snapshot()
    render_status(snap)
    if snap["mode"] == "simulation":
        st.warning("SIMULATION: all readings are synthetic demo data.")
    if s.model is None and snap["status"] != IDLE:
        st.info("No usable model. Record normal data with `python scripts/collect_data.py --mode hardware "
                "--label normal --duration 120`, then `python scripts/train_model.py --input data/raw/<file>.csv`.")
    samples = snap["samples"]
    c = st.columns(5)
    if samples:
        last = samples[-1]
        c[0].metric("X (g)", f"{last.ax:.3f}")
        c[1].metric("Y (g)", f"{last.ay:.3f}")
        c[2].metric("Z (g)", f"{last.az:.3f}")
    c[3].metric("Achieved rate", f"{snap['rate_hz']:.1f} Hz", f"target {snap['target_rate_hz']:.0f}", delta_color="off")
    age = snap["sample_age_s"]
    c[4].metric("Last sample", "never" if age is None else f"{age:.1f}s ago")
    if samples:
        t0 = samples[-1].mono
        fig = go.Figure()
        for name, attr in (("X", "ax"), ("Y", "ay"), ("Z", "az")):
            fig.add_scatter(x=[x.mono - t0 for x in samples], y=[getattr(x, attr) for x in samples], name=name, mode="lines")
        fig.update_layout(title="Acceleration (g, includes gravity)", xaxis_title="seconds (relative)",
                          yaxis_title="g", height=320, margin=dict(t=40, b=30))
        st.plotly_chart(fig, width="stretch")
    wins = snap["windows"]
    if wins:
        wdf = pd.DataFrame(wins)
        st.subheader("Latest window features")
        st.dataframe(wdf[FEATURE_NAMES].tail(1).T.rename(columns={wdf.index[-1]: "value"}), height=250)
        if (wdf["prediction"] != "").any():
            sc = wdf[wdf["prediction"] != ""]
            fig2 = go.Figure(go.Scatter(x=sc["window_end_utc"], y=sc["anomaly_score"].astype(float), mode="lines+markers",
                                        marker=dict(color=["#b3261e" if p == -1 else "#1b7f3b" for p in sc["prediction"]])))
            fig2.add_hline(y=0, line_dash="dash")
            fig2.update_layout(title="Anomaly score per window (decision_function; <0 = outlier; not a probability)",
                               height=260, margin=dict(t=40, b=30))
            st.plotly_chart(fig2, width="stretch")
        else:
            fig3 = go.Figure(go.Scatter(x=wdf["window_end_utc"], y=wdf["magnitude_rms_g"], mode="lines+markers"))
            fig3.update_layout(title="Magnitude RMS per window (g)", height=260, margin=dict(t=40, b=30))
            st.plotly_chart(fig3, width="stretch")
    st.subheader("Recent events")
    if snap["events"]:
        st.dataframe(pd.DataFrame(snap["events"]), hide_index=True, height=200)
    else:
        st.caption("No events yet.")


live_panel()

# ---------------- downloads ----------------
st.subheader("Export")
st.caption("Downloads reflect the data written at the time of the last page interaction (press Stop for the full file).")
d1, d2 = st.columns(2)
raw_b = csv_bytes(sess.raw_path) if sess else None
pred_b = csv_bytes(sess.pred_path) if sess else None
if raw_b:
    d1.download_button("Download raw readings CSV", raw_b, file_name=sess.raw_path.name, mime="text/csv")  # type: ignore[union-attr]
else:
    d1.caption("Raw readings: no rows yet.")
if pred_b:
    d2.download_button("Download window features + predictions CSV", pred_b, file_name=sess.pred_path.name, mime="text/csv")  # type: ignore[union-attr]
else:
    d2.caption("Window predictions: no rows yet.")
with st.expander("About scores and limits"):
    st.markdown("Isolation Forest flags *unusual* windows relative to the normal data it was trained on; it does not "
                "diagnose a fault type. Score < 0 = outlier, higher = more normal; it is not a calibrated probability. "
                "Not a safety system. Validate on real runs before trusting it.")
