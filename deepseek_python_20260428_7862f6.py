"""
digital_twin_student_b.py — Solar Digital Twin Dashboard
==========================================================
Queries InfluxDB every second and displays real-time:
  • Physical vs Virtual SOC
  • Voltage & Power trends
  • Twin synchronization error
  • Predicted time until critical battery

Prerequisites:
    - simulator.py running (Terminal 1)
    - bridge.py running (Terminal 2)
    - InfluxDB with solar_twin bucket
"""

import time
import threading
from collections import deque
from datetime import datetime, timezone
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from scipy.optimize import fsolve
from influxdb_client import InfluxDBClient

# ===================== CONFIGURATION =====================
# ⚠️ UPDATE THESE to match your InfluxDB setup
INFLUX_URL = "http://localhost:8086"
INFLUX_TOKEN = "YOUR_INFLUXDB_TOKEN"      # ⚠️ REPLACE
INFLUX_ORG = "your-org"                   # ⚠️ REPLACE
INFLUX_BUCKET = "solar_twin"
MEASUREMENT = "solar_panel"

# Display settings
WINDOW_SECONDS = 120
REFRESH_MS = 1000

# ===================== SOLAR PHYSICS MODEL =====================
Isc_ref = 3.0
Voc_ref = 21.6
n_ideal = 1.3
Rs = 0.5
Rsh = 300.0
T_ref = 298.15
q = 1.602e-19
k = 1.381e-23

def Vt(T):
    return n_ideal * k * T / q

def Iph(G, T):
    return Isc_ref * (G / 1000) * (1 + 0.0045 * (T - T_ref))

def I0(T):
    return Isc_ref / (np.exp(Voc_ref / Vt(T)) - 1)

def pv_current(V, G=1000.0, T=298.15):
    def eq(I):
        return (I - Iph(G, T) + I0(T) * (np.exp((V + I * Rs) / Vt(T)) - 1) + (V + I * Rs) / Rsh)
    sol, _, flag, _ = fsolve(eq, Iph(G, T) * 0.9, full_output=True)
    return max(float(sol[0]), 0.0)

# ===================== DIGITAL TWIN =====================
C_bat_Ah = 10.0
V_bat = 12.0
P_load = 25.0

class DigitalTwin:
    def __init__(self, window=120):
        self.soc_twin = 90.0
        self.last_ts = None
        self.times = deque(maxlen=window)
        self.voltages = deque(maxlen=window)
        self.currents = deque(maxlen=window)
        self.powers = deque(maxlen=window)
        self.soc_real = deque(maxlen=window)
        self.soc_virt = deque(maxlen=window)
        self.sync_err = deque(maxlen=window)
        self.pred_min = deque(maxlen=window)
        self.alerts = deque(maxlen=window)
        self._lock = threading.Lock()

    def ingest(self, row: dict):
        ts = row.get("_time", datetime.now(timezone.utc))
        soc = float(row.get("soc", self.soc_twin))
        v = float(row.get("voltage", 0))
        i = float(row.get("current_mA", 0))
        p = float(row.get("power_mW", 0))
        alert = str(row.get("alert", "BATTERY_OK"))

        # Physics step
        P_solar = v * i / 1000.0
        P_net = P_solar - P_load
        I_bat = P_net / V_bat
        delta = (I_bat / C_bat_Ah) * (1 / 3600) * 100

        if self.last_ts is None:
            self.soc_twin = soc
        else:
            self.soc_twin = np.clip(self.soc_twin + delta, 0, 100)
            elapsed = (ts - self.last_ts).total_seconds()
            if elapsed > 60:
                self.soc_twin = soc * 0.98
        self.last_ts = ts

        err = abs(self.soc_twin - soc) / max(soc, 1e-3) * 100
        pred = (self.soc_twin - 20) / abs(delta) / 60 if delta < 0 and self.soc_twin > 20 else 999

        with self._lock:
            t_label = ts.strftime("%H:%M:%S")
            self.times.append(t_label)
            self.voltages.append(v)
            self.currents.append(i)
            self.powers.append(p)
            self.soc_real.append(soc)
            self.soc_virt.append(self.soc_twin)
            self.sync_err.append(err)
            self.pred_min.append(min(pred, 120))
            self.alerts.append(alert)

    def snapshot(self):
        with self._lock:
            return {
                "times": list(self.times),
                "voltages": list(self.voltages),
                "currents": list(self.currents),
                "powers": list(self.powers),
                "soc_real": list(self.soc_real),
                "soc_virt": list(self.soc_virt),
                "sync_err": list(self.sync_err),
                "pred_min": list(self.pred_min),
                "alerts": list(self.alerts),
            }

# ===================== INFLUXDB POLLING =====================
twin = DigitalTwin()

def poll_influx():
    client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    query_api = client.query_api()
    
    flux_query = f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -2s)
  |> filter(fn: (r) => r._measurement == "{MEASUREMENT}")
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> last()
'''
    
    print("✓ InfluxDB polling started")
    while True:
        try:
            tables = query_api.query(flux_query, org=INFLUX_ORG)
            for table in tables:
                for record in table.records:
                    twin.ingest(dict(record.values))
        except Exception as e:
            print(f"⚠️  Query error: {e}")
        time.sleep(1)

poll_thread = threading.Thread(target=poll_influx, daemon=True)
poll_thread.start()

# ===================== DASHBOARD =====================
fig, axes = plt.subplots(2, 2, figsize=(15, 9))
fig.suptitle("☀️  Solar Digital Twin — Live Dashboard", fontsize=15, fontweight="bold")
fig.patch.set_facecolor("#0f172a")

for ax in axes.flat:
    ax.set_facecolor("#1e293b")
    ax.tick_params(colors="#94a3b8")
    for spine in ax.spines.values():
        spine.set_edgecolor("#334155")

ax_soc = axes[0, 0]
ax_power = axes[0, 1]
ax_err = axes[1, 0]
ax_pred = axes[1, 1]

ALERT_COLOR = {
    "BATTERY_OK": "#22c55e",
    "LOW_BATTERY_WARNING": "#f59e0b",
    "CRITICAL_BATTERY_SHUTDOWN": "#ef4444"
}

def update(frame):
    data = twin.snapshot()
    if not data["times"]:
        return

    xs = range(len(data["times"]))

    # SOC Panel
    ax_soc.cla()
    ax_soc.set_facecolor("#1e293b")
    ax_soc.plot(xs, data["soc_real"], color="#38bdf8", lw=2, label="Physical SOC")
    ax_soc.plot(xs, data["soc_virt"], color="#f472b6", lw=1.5, ls="--", label="Virtual Twin SOC")
    ax_soc.axhline(20, color="#ef4444", ls=":", lw=1.5, label="Critical")
    ax_soc.fill_between(xs, data["soc_real"], data["soc_virt"], alpha=0.15, color="#f59e0b")
    ax_soc.set_ylim(0, 105)
    ax_soc.set_title("Battery SOC — Physical vs Virtual", color="#e2e8f0")
    ax_soc.legend(loc="upper right", fontsize=8, facecolor="#1e293b", labelcolor="#e2e8f0")
    ax_soc.set_ylabel("SOC (%)", color="#94a3b8")
    
    if data["alerts"]:
        colour = ALERT_COLOR.get(data["alerts"][-1], "#94a3b8")
        ax_soc.set_title(f"Battery SOC  ●  {data['alerts'][-1]}", color=colour)

    # Power Panel
    ax_power.cla()
    ax_power.set_facecolor("#1e293b")
    ax_power.plot(xs, data["voltages"], color="#fbbf24", lw=2, label="Voltage (V)")
    ax2 = ax_power.twinx()
    ax2.plot(xs, data["powers"], color="#a78bfa", lw=2, label="Power (mW)")
    ax_power.set_title("Voltage & Power", color="#e2e8f0")
    ax_power.set_ylabel("Voltage (V)", color="#fbbf24")
    ax2.set_ylabel("Power (mW)", color="#a78bfa")

    # Sync Error Panel
    ax_err.cla()
    ax_err.set_facecolor("#1e293b")
    ax_err.fill_between(xs, data["sync_err"], alpha=0.4, color="#f97316")
    ax_err.plot(xs, data["sync_err"], color="#ea580c", lw=1.5)
    ax_err.axhline(5, color="#ef4444", ls="--", lw=2, label="5% limit")
    ax_err.set_title("Twin Synchronisation Error", color="#e2e8f0")
    ax_err.set_ylabel("Error (%)", color="#94a3b8")
    ax_err.legend(fontsize=8, facecolor="#1e293b", labelcolor="#e2e8f0")

    # Prediction Panel
    ax_pred.cla()
    ax_pred.set_facecolor("#1e293b")
    pred_display = [p if p < 120 else np.nan for p in data["pred_min"]]
    ax_pred.plot(xs, pred_display, color="#34d399", lw=2)
    ax_pred.fill_between(xs, pred_display, alpha=0.2, color="#34d399")
    ax_pred.axhline(15, color="#ef4444", ls=":", lw=1.5, label="Alert < 15 min")
    ax_pred.set_title("Predicted Time to Critical SOC", color="#e2e8f0")
    ax_pred.set_ylabel("Minutes", color="#94a3b8")
    ax_pred.legend(fontsize=8, facecolor="#1e293b", labelcolor="#e2e8f0")

    # X-axis labels
    for ax in [ax_soc, ax_power, ax_err, ax_pred]:
        if data["times"]:
            step = max(1, len(data["times"]) // 5)
            ticks = list(range(0, len(data["times"]), step))
            labels = [data["times"][i] for i in ticks]
            ax.set_xticks(ticks)
            ax.set_xticklabels(labels, rotation=20, fontsize=7, color="#64748b")

    fig.tight_layout(rect=[0, 0, 1, 0.95])

ani = animation.FuncAnimation(fig, update, interval=REFRESH_MS, cache_frame_data=False)
plt.show()