#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClient.h>
#include <Wire.h>
#include <Adafruit_AHTX0.h>

// -------- Wi-Fi --------
const char* WIFI_SSID = "Your Wi-Fi SSID";
const char* WIFI_PASSWORD = "Your Wi-Fi Password";

// API server: use your PC/Laptop LAN IP (not localhost)
const char* API_HOST = "192.168.137.1";
const uint16_t API_PORT = 5000;
const char* API_PATH = "/data";

// Node identity
const char* NODE_ID = "NODE_TH";
const char* SENSOR_ID = "SENSOR-TH-01";

// AHT21 setup (inside the ENS160+AHT21 module)
Adafruit_AHTX0 aht;
bool ahtReady = false;

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

bool publishMetrics(float temperature, float humidity) {
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
      "\"temperature\":" + String(temperature, 2) + "," +
      "\"humidity\":" + String(humidity, 2) +
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

  Wire.begin();
  if (!aht.begin()) {
    Serial.println("AHT21 init failed; check wiring and I2C address");
  } else {
    Serial.println("AHT21 initialized");
    ahtReady = true;
  }

  connectWifi();
}

void loop() {
  if (millis() - lastPublishMs < PUBLISH_INTERVAL_MS) {
    delay(50);
    return;
  }
  lastPublishMs = millis();

  if (!ahtReady) {
    Serial.println("AHT21 not ready; skipping publish");
    return;
  }

  sensors_event_t humidityEvent;
  sensors_event_t temperatureEvent;
  aht.getEvent(&humidityEvent, &temperatureEvent);

  float humidity = humidityEvent.relative_humidity;
  float temperature = temperatureEvent.temperature;

  if (isnan(temperature) || isnan(humidity)) {
    Serial.println("AHT21 read failed; skipping publish");
    return;
  }

  Serial.print("Temperature: ");
  Serial.print(temperature);
  Serial.print(" C, Humidity: ");
  Serial.print(humidity);
  Serial.println(" %");

  publishMetrics(temperature, humidity);
}
