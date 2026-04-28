"""
bridge.py — MQTT → InfluxDB Bridge
====================================
Subscribes to solar/telemetry (JSON) and writes to InfluxDB v2.
Works with both real ESP32 and simulator.py as data source.

Prerequisites:
    1. Install InfluxDB v2 locally or use InfluxDB Cloud
    2. Create bucket named 'solar_twin'
    3. Generate API token with read/write access
    4. Fill in INFLUX_TOKEN and INFLUX_ORG below
"""

import json
import logging
from datetime import datetime, timezone
import paho.mqtt.client as mqtt
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

# ===================== CONFIGURATION =====================
# MQTT Settings (must match simulator.py or ESP32)
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
MQTT_TOPIC = "solar/telemetry"
MQTT_TOPICS_LEGACY = [
    "solar/voltage", "solar/current", "solar/power",
    "solar/soc", "solar/alert"
]
CLIENT_ID = "bridge_influx_01"

# InfluxDB Settings - ⚠️ UPDATE THESE!
INFLUX_URL = "http://localhost:8086"      # or your InfluxDB Cloud URL
INFLUX_TOKEN = "YOUR_INFLUXDB_TOKEN"      # ⚠️ REPLACE WITH YOUR TOKEN
INFLUX_ORG = "your-org"                   # ⚠️ REPLACE WITH YOUR ORG
INFLUX_BUCKET = "solar_twin"
MEASUREMENT = "solar_panel"

# ===================== LOGGING SETUP =====================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger(__name__)

# ===================== INFLUXDB CLIENT =====================
try:
    influx_client = InfluxDBClient(
        url=INFLUX_URL,
        token=INFLUX_TOKEN,
        org=INFLUX_ORG
    )
    write_api = influx_client.write_api(write_options=SYNCHRONOUS)
    log.info("✓ InfluxDB client initialized")
except Exception as e:
    log.error(f"✗ Failed to initialize InfluxDB: {e}")
    log.error("  Make sure InfluxDB is running and credentials are correct")
    exit(1)

# Legacy topic buffer
_legacy_buffer = {}

def write_to_influx(data: dict):
    """Write a single telemetry point to InfluxDB."""
    try:
        point = (
            Point(MEASUREMENT)
            .tag("device", "ESP32_SolarTwin_A")
            .tag("alert", str(data.get("alert", "UNKNOWN")))
            .tag("load_on", str(data.get("load_on", True)))
            .field("voltage", float(data["voltage"]))
            .field("current_mA", float(data["current_mA"]))
            .field("power_mW", float(data["power_mW"]))
            .field("soc", float(data["soc"]))
            .time(datetime.now(timezone.utc), WritePrecision.SECONDS)
        )
        write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)
        log.info(
            "✓ Written → V=%.2fV  I=%.1fmA  P=%.1fmW  SOC=%.1f%%  alert=%s",
            data["voltage"], data["current_mA"],
            data["power_mW"], data["soc"], data.get("alert")
        )
    except Exception as e:
        log.error(f"✗ Write failed: {e}")

# ===================== MQTT CALLBACKS =====================
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        log.info(f"✓ Connected to MQTT broker")
        client.subscribe(MQTT_TOPIC)
        log.info(f"✓ Subscribed to {MQTT_TOPIC}")
        for topic in MQTT_TOPICS_LEGACY:
            client.subscribe(topic)
    else:
        log.error(f"✗ Connection failed with code {rc}")

def on_message(client, userdata, msg):
    global _legacy_buffer
    topic = msg.topic
    payload = msg.payload.decode().strip()
    
    # Primary: JSON telemetry
    if topic == MQTT_TOPIC:
        try:
            data = json.loads(payload)
            write_to_influx(data)
        except json.JSONDecodeError:
            log.warning(f"Bad JSON on {topic}: {payload}")
        return
    
    # Legacy: Individual topics
    field_map = {
        "solar/voltage": ("voltage", float),
        "solar/current": ("current_mA", float),
        "solar/power": ("power_mW", float),
        "solar/soc": ("soc", float),
        "solar/alert": ("alert", str),
    }
    
    if topic in field_map:
        key, cast = field_map[topic]
        try:
            _legacy_buffer[key] = cast(payload)
        except ValueError:
            log.warning(f"Cannot cast {payload} on {topic}")
            return
        
        required = {"voltage", "current_mA", "power_mW", "soc"}
        if required.issubset(_legacy_buffer.keys()):
            write_to_influx(dict(_legacy_buffer))
            _legacy_buffer.clear()

def on_disconnect(client, userdata, rc):
    if rc != 0:
        log.warning("⚠️  Disconnected from MQTT. Auto-reconnecting...")

# ===================== MAIN =====================
def main():
    client = mqtt.Client(client_id=CLIENT_ID, clean_session=True)
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect
    
    log.info(f"Connecting to MQTT broker...")
    client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    
    log.info("\n" + "="*50)
    log.info("🌉 BRIDGE RUNNING")
    log.info("="*50)
    log.info(f"MQTT: {MQTT_BROKER}:{MQTT_PORT} → InfluxDB: {INFLUX_URL}")
    log.info("Waiting for telemetry data...\n")
    
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        log.info("\n✓ Bridge stopped by user")
    finally:
        influx_client.close()
        log.info("✓ InfluxDB connection closed")

if __name__ == "__main__":
    main()