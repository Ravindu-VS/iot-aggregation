#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClientSecureBearSSL.h>
#include <Wire.h>
#include <Adafruit_AHTX0.h>
#include <memory>

// -------- Wi-Fi --------
const char* WIFI_SSID = "Your_WiFi_SSID";
const char* WIFI_PASSWORD = "Your_WiFi_Password";

const char* API_PATH = "/data";

#ifndef CLOUD_API_BASE_URL
#define CLOUD_API_BASE_URL "https://<api-id>.execute-api.<region>.amazonaws.com/Prod/data"
#endif

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

  std::unique_ptr<BearSSL::WiFiClientSecure> client(new BearSSL::WiFiClientSecure);
  client->setInsecure();
  HTTPClient http;

  String url = String(CLOUD_API_BASE_URL) + API_PATH;
  Serial.print("Posting to: ");
  Serial.println(url);
  if (!http.begin(*client, url)) {
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

  int code = -1;
  String response;
  for (int attempt = 1; attempt <= 2; attempt++) {
    code = http.POST(body);
    if (code > 0) {
      response = http.getString();
    } else {
      response = String("HTTP client error ") + String(code);
    }

    if (code >= 0 || attempt == 2) {
      break;
    }

    Serial.print("Transient HTTP error, retrying attempt ");
    Serial.println(attempt + 1);
    http.end();
    if (WiFi.status() != WL_CONNECTED) {
      connectWifi();
    }
    delay(1000);
    if (!http.begin(*client, url)) {
      Serial.println("HTTP begin failed on retry");
      return false;
    }
    http.addHeader("Content-Type", "application/json");
  }

  Serial.print("POST code: ");
  Serial.println(code);
  Serial.print("Response: ");
  Serial.println(response);

  http.end();

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
