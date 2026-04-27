# bridge.py — MQTT → InfluxDB Bridge
import json
import paho.mqtt.client as mqtt
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from datetime import datetime, timezone

# ─── Config ───────────────────────────────────────────────
MQTT_BROKER   = "localhost"
MQTT_PORT     = 1883
MQTT_TOPIC    = "microgrid/#"   # subscribe to all microgrid subtopics

INFLUX_URL    = "http://localhost:8086"
INFLUX_TOKEN  = "LYTUt9Lrt1CnPbJYUbw2-pmtPyliT-mqdcjkMV0Z119iyPSqSR1kJ_JEAClDU6s0l5MxvtREdJoTeSkmSZfAoQ=="
INFLUX_ORG    = "Microgrid_Project"
INFLUX_BUCKET = "Microgrid_Data"
# ──────────────────────────────────────────────────────────

client_influx = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
write_api = client_influx.write_api(write_options=SYNCHRONOUS)

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        
        point = (
            Point("microgrid_metrics")               # measurement name
            .tag("node_id",   payload.get("node_id", "node_01"))
            .tag("source",    payload.get("source", "solar"))
            .tag("location",  payload.get("location", "site_A"))
            .field("voltage",    float(payload["voltage"]))
            .field("soc",        float(payload["soc"]))
            .field("current",    float(payload.get("current", 0.0)))
            .field("power_kw",   float(payload.get("power_kw", 0.0)))
            .field("temperature",float(payload.get("temperature", 25.0)))
            .time(datetime.now(timezone.utc), WritePrecision.S)
        )
        
        write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)
        print(f"[✓] Written: {payload}")
        
    except Exception as e:
        print(f"[✗] Error: {e}")

mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
mqtt_client.on_message = on_message
mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
mqtt_client.subscribe(MQTT_TOPIC)
mqtt_client.loop_forever()