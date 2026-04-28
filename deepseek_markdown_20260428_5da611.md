# Solar Digital Twin — No Wokwi Required!

## 🎯 Overview
This version replaces Wokwi/ESP32 with a local Python simulator that:
- Generates identical solar panel data
- Publishes to the same MQTT topics
- Responds to load shedding commands
- Works completely FREE

## 📋 Prerequisites

1. **Python 3.8+** installed
2. **InfluxDB v2** installed locally or cloud account
3. Install dependencies:
```bash
pip install -r requirements.txt