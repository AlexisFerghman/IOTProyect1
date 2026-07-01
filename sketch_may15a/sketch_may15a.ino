#include <SPI.h>
#include <WiFi101.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <Adafruit_AHTX0.h>

// =====================================================
// CONFIGURACIÓN WI-FI
// =====================================================
const char* ssid = "autoicc";
const char* password = "autitos12";

// =====================================================
// CONFIGURACIÓN MQTT
// =====================================================
const char* mqtt_server = "10.254.148.141";
const int mqtt_port = 1883;
const char* mqtt_client_name = "MKR1000_SmartHome_EquipoHector";

const char* mqtt_user = "mi_usuario"; 
const char* mqtt_password = "equipoHector";

// =====================================================
// TÓPICOS MQTT - JERARQUÍA ORDENADA
// =====================================================

// JSON general con todos los datos
const char* topic_datos = "smarthome/equipoHector/datos";

// Tópicos individuales de sensores
const char* topic_temperatura = "smarthome/equipoHector/temperatura";
const char* topic_humedad = "smarthome/equipoHector/humedad";
const char* topic_mq6 = "smarthome/equipoHector/gas/mq6";
const char* topic_mq7 = "smarthome/equipoHector/gas/mq7";
const char* topic_microfono = "smarthome/equipoHector/sonido/microfono";

// Tópico de control para el LED
const char* topic_control_led = "smarthome/equipoHector/control/led";

// =====================================================
// PINES
// =====================================================
const int pinLED = 6; // Pin 0 asignado para el LED
const int pinMQ6 = A1;
const int pinMQ7 = A2;
const int pinMicrofono = A4;

// =====================================================
// OBJETOS GLOBALES
// =====================================================
WiFiClient espClient;
PubSubClient client(espClient);
Adafruit_AHTX0 aht;

bool aht_conectado = false;

// =====================================================
// CONEXIÓN WI-FI
// =====================================================
void setup_wifi() {
  delay(10);

  Serial.println();
  Serial.print("Conectando a red WiFi: ");
  Serial.println(ssid);

  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println();
  Serial.println("WiFi conectado correctamente.");
  Serial.print("IP asignada: ");
  Serial.println(WiFi.localIP());
}

// =====================================================
// CALLBACK MQTT
// Se ejecuta cuando Node-RED envía mensajes al Arduino
// =====================================================
void callback(char* topic, byte* payload, unsigned int length) {
  String mensaje = "";

  for (unsigned int i = 0; i < length; i++) {
    mensaje += (char)payload[i];
  }

  Serial.print("Mensaje recibido en tópico [");
  Serial.print(topic);
  Serial.print("]: ");
  Serial.println(mensaje);

  // =================================================
  // LÓGICA DE CONTROL: Enceder/Apagar LED
  // =================================================
  if (String(topic) == topic_control_led) {
    if (mensaje == "ON") {
      digitalWrite(pinLED, HIGH);
      Serial.println("-> Acción: LED Encendido");
    } else if (mensaje == "OFF") {
      digitalWrite(pinLED, LOW);
      Serial.println("-> Acción: LED Apagado");
    }
  }
}

// =====================================================
// RECONEXIÓN MQTT
// =====================================================
void reconnect() {
  while (!client.connected()) {
    Serial.print("Intentando conexión MQTT... ");

    if (client.connect(mqtt_client_name, mqtt_user, mqtt_password)) {
      Serial.println("Conectado al broker MQTT.");
      
      // SUSCRIPCIÓN AL TÓPICO DEL LED
      client.subscribe(topic_control_led);
      Serial.println("Suscrito a tópico de control LED.");

    } else {
      Serial.print("Error, rc=");
      Serial.print(client.state());
      Serial.println(". Reintentando en 5 segundos...");
      delay(5000);
    }
  }
}

// =====================================================
// PUBLICAR VALOR FLOAT COMO TEXTO
// =====================================================
void publicarFloat(const char* topic, float valor) {
  String mensaje = String(valor, 2);
  client.publish(topic, mensaje.c_str());
}
/*
// =====================================================
// FUNCIONES AUXILIARES PARA ENVIAR DATOS
// =====================================================
void publicarInt(const char* topic, int valor) {
  char mensaje[16];
  itoa(valor, mensaje, 10);
  client.publish(topic, mensaje);
}
*/
void publicarJSONFloat(const char* topic, const char* key, float valor) {
  StaticJsonDocument<64> doc; // Memoria pequeña, suficiente para una sola variable
  doc[key] = valor;
  char jsonBuffer[64];
  serializeJson(doc, jsonBuffer);
  client.publish(topic, jsonBuffer);
}

void publicarJSONInt(const char* topic, const char* key, int valor) {
  StaticJsonDocument<64> doc; 
  doc[key] = valor;
  char jsonBuffer[64];
  serializeJson(doc, jsonBuffer);
  client.publish(topic, jsonBuffer);
}

// =====================================================
// SETUP
// =====================================================
void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("Iniciando sistema SmartHome IoT - Equipo Hector");

  // Configurar pines de salida
  pinMode(pinLED, OUTPUT);
  // pinMode(pinBuzzer, OUTPUT); // Comentado temporalmente para evitar error de compilación

  digitalWrite(pinLED, LOW);
  // digitalWrite(pinBuzzer, LOW);

  // Conexión Wi-Fi
  setup_wifi();

  // Configuración MQTT
  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(callback);

  // Inicializar sensor AM2315C / AHT20
  if (!aht.begin()) {
    Serial.println("ERROR: No se pudo encontrar el sensor AM2315C / AHT20.");
    Serial.println("Revisa conexión SDA, SCL, VCC y GND.");
    aht_conectado = false;
  } else {
    Serial.println("Sensor AM2315C / AHT20 inicializado correctamente.");
    aht_conectado = true;
  }
}

// =====================================================
// LOOP PRINCIPAL
// =====================================================
void loop() {
  // Mantener conexión MQTT
  if (!client.connected()) {
    reconnect();
  }

  // Es vital mantener esto para que el Arduino escuche los mensajes entrantes (como el del LED)
  client.loop();

  // Enviar datos cada 5 segundos
  static unsigned long lastMsg = 0;
  unsigned long ahora = millis();

  if (ahora - lastMsg > 5000) {
    lastMsg = ahora;

    // =================================================
    // 1. LECTURA DE SENSORES ANALÓGICOS
    // =================================================
    int valorMQ6 = analogRead(pinMQ6);
    int valorMQ7 = analogRead(pinMQ7);
    int valorMicrofono = analogRead(pinMicrofono);

    // =================================================
    // 2. LECTURA DE TEMPERATURA Y HUMEDAD
    // =================================================
    float temperatura = -99.9;
    float humedad = -99.9;

    if (aht_conectado) {
      sensors_event_t humidity, temp;
      aht.getEvent(&humidity, &temp);

      temperatura = temp.temperature;
      humedad = humidity.relative_humidity;
    }

    // =================================================
    // 3. PUBLICAR JSON INDIVIDUALES
    // =================================================
    publicarJSONFloat(topic_temperatura, "temperatura", temperatura);
    publicarJSONFloat(topic_humedad, "humedad", humedad);
    publicarJSONInt(topic_mq6, "mq6", valorMQ6);
    publicarJSONInt(topic_mq7, "mq7", valorMQ7);
    publicarJSONInt(topic_microfono, "microfono", valorMicrofono);

    Serial.println("Datos enviados en formato JSON individualmente.");
  }
}