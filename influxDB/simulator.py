# simulator.py — Synthetic Microgrid Data Publisher
import paho.mqtt.client as mqtt
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
import json

BROKER = "broker.hivemq.com"
INFLUX_URL = "http://localhost:8086"
INFLUX_TOKEN = "LYTUt9Lrt1CnPbJYUbw2-pmtPyliT-mqdcjkMV0Z119iyPSqSR1kJ_JEAClDU6s0l5MxvtREdJoTeSkmSZfAoQ=="
INFLUX_ORG = "Microgrid_Project"
INFLUX_BUCKET = "solar"

influx = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
write_api = influx.write_api(write_options=SYNCHRONOUS)



def on_message(client, userdata, msg):
    topic = msg.topic
    field = topic.split("/")[-1]
    payload = msg.payload.decode()

    # Handle alert topic separately (it's JSON)
    if field == "alert":
        try:
            data = json.loads(payload)
            point = (Point("solar_panel")
                     .field("alert_level", data.get("level", "unknown"))
                     .field("alert_soc", float(data.get("soc", 0))))
            write_api.write(bucket=INFLUX_BUCKET, record=point)
            print(f"Wrote alert: {data}")
        except Exception as e:
            print(f"Alert parse error: {e}")
        return

    # Handle numeric topics
    try:
        value = float(payload)
        point = Point("solar_panel").field(field, value)
        write_api.write(bucket=INFLUX_BUCKET, record=point)
        print(f"Wrote {field}={value} to InfluxDB")
    except ValueError:
        print(f"Skipping: {topic}: {payload}")

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_message = on_message
client.connect(BROKER, 1883)
client.subscribe("solar/voltage")
client.subscribe("solar/current")
client.subscribe("solar/power")
client.subscribe("solar/soc")
client.subscribe("solar/alert")

client.loop_forever()