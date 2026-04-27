#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClient.h>
#include <Wire.h>
#include <Adafruit_BMP085.h>

// -------- Wi-Fi --------
const char* WIFI_SSID = "Your Wi-Fi SSID";
const char* WIFI_PASSWORD = "Your Wi-Fi Password";

// API server: use your PC/Laptop LAN IP (not localhost)
const char* API_HOST = "192.168.137.1";
const uint16_t API_PORT = 5000;
const char* API_PATH = "/data";

// Node identity
const char* NODE_ID = "NODE_PA";
const char* SENSOR_ID = "SENSOR-PA-01";

// Sensor setup
Adafruit_BMP085 bmp;
bool bmpReady = false;

// MQ-3 analog input on ESP8266 A0.
const int MQ3_ANALOG_PIN = A0;

// Tune these after calibration for your module and board.
const float MQ3_ADC_MAX = 1023.0f;
const float MQ3_ETOH_BASELINE = 180.0f;
const float MQ3_ETOH_SLOPE = 3.2f;

// Publish every 10 seconds
const unsigned long PUBLISH_INTERVAL_MS = 10000;
unsigned long lastPublishMs = 0;

void connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  Serial.print("Connecting to Wi-Fi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  Serial.print("Wi-Fi connected. IP: ");
  Serial.println(WiFi.localIP());
}

bool initializeSensors() {
  Wire.begin();

  if (!bmp.begin()) {
    Serial.println("BMP180 init failed; check wiring and I2C connection");
    return false;
  }

  Serial.println("BMP180 initialized");
  bmpReady = true;
  return true;
}

float readEthanolPpmApprox() {
  int raw = analogRead(MQ3_ANALOG_PIN);
  float normalized = raw / MQ3_ADC_MAX;

  // Basic inverse curve to make higher gas concentration produce higher ppm estimates.
  float safeRaw = raw > 1 ? (float)raw : 1.0f;
  float ratio = (MQ3_ETOH_BASELINE / safeRaw) - 1.0f;
  if (ratio < 0.0f) {
    ratio = 0.0f;
  }

  float ethanol = normalized * 40.0f + ratio * MQ3_ETOH_SLOPE * 10.0f;
  if (ethanol < 0.0f) ethanol = 0.0f;
  if (ethanol > 300.0f) ethanol = 300.0f;
  return ethanol;
}

bool readSensorMetrics(float& pressure, float& ethanol) {
  if (!bmpReady) {
    return false;
  }

  pressure = bmp.readPressure() / 100.0f;
  ethanol = readEthanolPpmApprox();

  if (isnan(pressure) || isnan(ethanol)) {
    return false;
  }

  return true;
}

bool publishMetrics(float pressure, float ethanol) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Wi-Fi disconnected, reconnecting...");
    connectWifi();
  }

  WiFiClient client;
  HTTPClient http;

  String url = String("http://") + API_HOST + ":" + API_PORT + API_PATH;
  Serial.print("Posting to: ");
  Serial.println(url);
  if (!http.begin(client, url)) {
    Serial.println("HTTP begin failed");
    return false;
  }

  http.addHeader("Content-Type", "application/json");

  String body = String("{") +
    "\"node_id\":\"" + NODE_ID + "\"," +
    "\"sensor_id\":\"" + SENSOR_ID + "\"," +
    "\"metrics\":{" +
      "\"pressure\":" + String(pressure, 2) + "," +
      "\"ethanol\":" + String(ethanol, 2) +
    "}" +
  "}";

  int code = http.POST(body);
  String response = http.getString();
  http.end();

  Serial.print("POST code: ");
  Serial.println(code);
  Serial.print("Response: ");
  Serial.println(response);

  return code >= 200 && code < 300;
}

void setup() {
  Serial.begin(115200);
  delay(200);

  if (!initializeSensors()) {
    Serial.println("Sensor initialization failed; fix wiring before publishing");
  }
  connectWifi();

  Serial.println("Running in live sensor mode (BMP180 + MQ-3)");
}

void loop() {
  if (millis() - lastPublishMs < PUBLISH_INTERVAL_MS) {
    delay(50);
    return;
  }
  lastPublishMs = millis();

  float pressure;
  float ethanol;
  if (!readSensorMetrics(pressure, ethanol)) {
    Serial.println("Sensor read failed; skipping publish");
    return;
  }

  Serial.print("Pressure: ");
  Serial.print(pressure);
  Serial.print(" hPa, Ethanol(approx): ");
  Serial.print(ethanol);
  Serial.println(" ppm");

  publishMetrics(pressure, ethanol);
}
