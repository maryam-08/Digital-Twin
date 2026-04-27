# simulator.py — Synthetic Microgrid Data Publisher
import paho.mqtt.client as mqtt
import json, time, random, math

MQTT_BROKER = "localhost"
MQTT_PORT   = 1883
PUBLISH_INTERVAL = 5  # seconds

client = mqtt.Client()
client.connect(MQTT_BROKER, MQTT_PORT, 60)

def generate_reading(t):
    """Generate realistic, time-correlated microgrid values."""
    # Simulate solar irradiance cycle (peaks at midday)
    solar_factor = max(0, math.sin(math.pi * (t % 86400) / 86400))
    
    return {
        "node_id":     "node_01",
        "source":      "solar",
        "location":    "site_A",
        "voltage":     round(random.uniform(17.0, 19.0), 2),
        "soc":         round(random.uniform(20, 95) * solar_factor + 5, 1),  # SOC rises with sun
        "current":     round(random.uniform(0.5, 5.5) * solar_factor, 2),
        "power_kw":    round(random.uniform(0.1, 3.5) * solar_factor, 3),
        "temperature": round(random.gauss(28.0, 3.0), 1),
        "timestamp":   int(time.time())
    }

print(f"[SIM] Publishing to {MQTT_BROKER} every {PUBLISH_INTERVAL}s...")
t = 0
while True:
    payload = generate_reading(t)
    client.publish("microgrid/solar/node_01", json.dumps(payload))
    print(f"[SIM] → {payload}")
    t += PUBLISH_INTERVAL
    time.sleep(PUBLISH_INTERVAL)