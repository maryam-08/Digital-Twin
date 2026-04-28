"""
simulator.py — Local Solar Panel Simulator
============================================
Replaces the Wokwi ESP32 simulation. Generates realistic solar panel data
and publishes to MQTT exactly like the ESP32 would.

Run this FIRST before bridge.py and digital_twin_student_b.py
"""

import time
import json
import random
import math
import paho.mqtt.client as mqtt

# ===================== MQTT CONFIGURATION =====================
# Must match bridge.py and digital_twin_student_b.py
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
CLIENT_ID = "ESP32_SolarTwin_A"

# Topics (matching sketch.ino)
TOPIC_TELEMETRY = "solar/telemetry"
TOPIC_VOLTAGE = "solar/voltage"
TOPIC_CURRENT = "solar/current"
TOPIC_POWER = "solar/power"
TOPIC_SOC = "solar/soc"
TOPIC_ALERT = "solar/alert"
TOPIC_COMMAND = "solar/command"

# ===================== BATTERY SIMULATION =====================
battery_capacity_mAh = 2000.0
remaining_mAh = 2000.0
load_on = True

# ===================== SOLAR MODEL =====================
def solar_voltage():
    """Simulate solar panel voltage (matches ESP32 logic)"""
    base = 13.2
    t = (time.time() % 25)
    if 15 <= t < 21:
        return 11.8 + (time.time() % 1) * 0.3
    return base + math.sin(time.time() / 2.0) * 0.4

def solar_current():
    """Simulate solar panel current (matches ESP32 logic)"""
    base = 220
    t = (time.time() % 25)
    if 15 <= t < 21:
        return 60 + random.uniform(-5, 5)
    return base + random.uniform(-15, 15)

# ===================== MQTT CALLBACKS =====================
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"✓ Connected to MQTT broker at {MQTT_BROKER}")
        client.subscribe(TOPIC_COMMAND)
        print(f"✓ Subscribed to {TOPIC_COMMAND}")
    else:
        print(f"✗ Connection failed with code {rc}")

def on_message(client, userdata, msg):
    """Handle incoming commands (load shedding)"""
    command = msg.payload.decode()
    global load_on
    print(f"\n📨 Command received: {command}")
    
    if command == "shed_load":
        load_on = False
        print("⚠️  LOAD SHEDDING ACTIVATED")
    elif command == "restore_load":
        load_on = True
        print("✓ LOAD RESTORED")

def on_disconnect(client, userdata, rc):
    if rc != 0:
        print(f"⚠️  Unexpected disconnection. Reconnecting...")
        client.reconnect()

# ===================== MAIN LOOP =====================
def main():
    global remaining_mAh, load_on
    
    # Setup MQTT client
    client = mqtt.Client(client_id=CLIENT_ID, clean_session=True)
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect
    
    # Connect to broker
    print(f"Connecting to MQTT broker {MQTT_BROKER}:{MQTT_PORT}...")
    client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    client.loop_start()
    
    print("\n" + "="*50)
    print("☀️  SOLAR PANEL SIMULATOR RUNNING")
    print("="*50)
    print("Publishing to MQTT topics:")
    print(f"  • {TOPIC_TELEMETRY} (JSON)")
    print(f"  • {TOPIC_VOLTAGE}, {TOPIC_CURRENT}, {TOPIC_POWER}")
    print(f"  • {TOPIC_SOC}, {TOPIC_ALERT}")
    print(f"\nListening for commands on {TOPIC_COMMAND}")
    print("="*50 + "\n")
    
    try:
        while True:
            # ── Generate solar values ──────────────────────
            voltage = solar_voltage()
            current_mA = solar_current()
            power_mW = voltage * current_mA
            
            # ── Battery model ─────────────────────────────
            time_hours = 1.0 / 3600.0  # 1 second in hours
            used_mAh = current_mA * time_hours
            
            if load_on:
                remaining_mAh -= used_mAh
            remaining_mAh = max(0, min(remaining_mAh, battery_capacity_mAh))
            soc = (remaining_mAh / battery_capacity_mAh) * 100.0
            
            # ── Alert logic ───────────────────────────────
            if soc < 15:
                alert = "CRITICAL_BATTERY_SHUTDOWN"
            elif soc < 30:
                alert = "LOW_BATTERY_WARNING"
            else:
                alert = "BATTERY_OK"
            
            # ── Publish individual topics (backward compat) ──
            client.publish(TOPIC_VOLTAGE, f"{voltage:.2f}")
            client.publish(TOPIC_CURRENT, f"{current_mA:.2f}")
            client.publish(TOPIC_POWER, f"{power_mW:.2f}")
            client.publish(TOPIC_SOC, f"{soc:.2f}")
            client.publish(TOPIC_ALERT, alert)
            
            # ── Publish JSON telemetry (primary) ──────────
            telemetry = {
                "voltage": round(voltage, 2),
                "current_mA": round(current_mA, 1),
                "power_mW": round(power_mW, 1),
                "soc": round(soc, 1),
                "alert": alert,
                "load_on": load_on
            }
            client.publish(TOPIC_TELEMETRY, json.dumps(telemetry))
            
            # ── Console output ────────────────────────────
            load_status = "LOAD ON" if load_on else "LOAD OFF"
            print(f"V: {voltage:.2f}V | I: {current_mA:.1f}mA | P: {power_mW:.1f}mW | "
                  f"SOC: {soc:.1f}% | {load_status} | {alert}")
            
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n\n✓ Simulator stopped by user")
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    main()