#include <WiFi.h>
#include <PubSubClient.h>

// ===================== WIFI & MQTT =====================
const char* ssid = "Wokwi-GUEST";
const char* password = "";

const char* mqttServer = "broker.hivemq.com";
const int mqttPort = 1883;
const char* clientID = "ESP32_SolarTwin_A";

// ===================== TOPICS =====================
const char* topicVoltage = "solar/voltage";
const char* topicCurrent = "solar/current";
const char* topicPower   = "solar/power";
const char* topicSOC     = "solar/soc";
const char* topicCommand = "solar/command";
const char* topicAlert   = "solar/alert";
const char* topicCSV     = "solar/csv";

// ===================== LOAD =====================
const int loadPin = 2;
bool loadOn = true;

// ===================== BATTERY =====================
float batteryCapacity_mAh = 2000.0;
float remaining_mAh = 2000.0;

// ===================== MQTT =====================
WiFiClient espClient;
PubSubClient mqttClient(espClient);

// ===================== SOLAR MODEL =====================
float solarVoltage() {
  float base = 13.2;

  long t = (millis() / 1000) % 25;

  // CLOUD EVENT
  if (t >= 15 && t < 21) {
    return 11.8 + (millis() % 1000) / 1000.0 * 0.3;
  }

  return base + sin(millis() / 2000.0) * 0.4;
}

float solarCurrent() {
  float base = 220;

  long t = (millis() / 1000) % 25;

  // CLOUD EVENT
  if (t >= 15 && t < 21) {
    return 60 + random(-5, 5);
  }

  return base + random(-15, 15);
}

// ===================== MQTT CALLBACK =====================
void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String message = "";

  for (int i = 0; i < length; i++) {
    message += (char)payload[i];
  }

  Serial.print("Command received: ");
  Serial.println(message);

  if (message == "shed_load") {
    loadOn = false;
    digitalWrite(loadPin, LOW);
    Serial.println(">>> LOAD SHED");
  }

  if (message == "restore_load") {
    loadOn = true;
    digitalWrite(loadPin, HIGH);
    Serial.println(">>> LOAD RESTORED");
  }
}

// ===================== WIFI =====================
void connectWiFi() {
  Serial.print("Connecting WiFi");
  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("\nWiFi Connected");
}

// ===================== MQTT =====================
void connectMQTT() {
  while (!mqttClient.connected()) {
    Serial.print("Connecting MQTT...");

    if (mqttClient.connect(clientID)) {
      Serial.println("connected");

      mqttClient.subscribe(topicCommand);
    } else {
      Serial.print("failed rc=");
      Serial.println(mqttClient.state());
      delay(2000);
    }
  }
}

// ===================== CSV EXPORT =====================
void publishCSV(float v, float i, float p, float soc) {
  char msg[120];
  sprintf(msg, "%.2f,%.1f,%.2f,%.1f", v, i, p, soc);
  mqttClient.publish(topicCSV, msg);
}

// ===================== SETUP =====================
void setup() {
  Serial.begin(115200);

  pinMode(loadPin, OUTPUT);
  digitalWrite(loadPin, HIGH);

  connectWiFi();

  mqttClient.setServer(mqttServer, mqttPort);
  mqttClient.setCallback(mqttCallback);

  connectMQTT();

  Serial.println("SYSTEM READY");
}

// ===================== LOOP =====================
unsigned long lastPublish = 0;

void loop() {
  if (!mqttClient.connected()) connectMQTT();
  mqttClient.loop();

  if (millis() - lastPublish > 1000) {
    lastPublish = millis();

    // ===== SOLAR VALUES =====
    float voltage = solarVoltage();
    float current_mA = solarCurrent();
    float power_mW = voltage * current_mA;

    // ===== BATTERY MODEL =====
    float timeHours = 1.0 / 3600000.0 * 1000;
    float used_mAh = current_mA * timeHours;

    if (loadOn) {
      remaining_mAh -= used_mAh;
    }

    if (remaining_mAh < 0) remaining_mAh = 0;
    if (remaining_mAh > batteryCapacity_mAh)
      remaining_mAh = batteryCapacity_mAh;

    float soc = (remaining_mAh / batteryCapacity_mAh) * 100.0;

    // ===== ALERT SYSTEM =====
    String alert = "BATTERY_OK";

    if (soc < 15) {
      alert = "CRITICAL_BATTERY_SHUTDOWN";
    } else if (soc < 30) {
      alert = "LOW_BATTERY_WARNING";
    }

    mqttClient.publish(topicAlert, alert.c_str());

    // ===== MQTT PUBLISH =====
    char buf[20];

    dtostrf(voltage, 6, 2, buf);
    mqttClient.publish(topicVoltage, buf);

    dtostrf(current_mA, 6, 2, buf);
    mqttClient.publish(topicCurrent, buf);

    dtostrf(power_mW, 6, 2, buf);
    mqttClient.publish(topicPower, buf);

    dtostrf(soc, 6, 2, buf);
    mqttClient.publish(topicSOC, buf);

    // ===== CSV EXPORT =====
    publishCSV(voltage, current_mA, power_mW, soc);

    // ===== SERIAL OUTPUT =====
    Serial.printf(
      "V: %.2fV | I: %.1fmA | P: %.1fmW | SOC: %.1f%% | %s | ALERT: %s\n",
      voltage, current_mA, power_mW, soc,
      loadOn ? "LOAD ON" : "LOAD OFF",
      alert.c_str()
    );
  }
}