#include <SPI.h>
#include <WiFi101.h>
#include <WiFiUdp.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <Adafruit_AHTX0.h>
#include <coap-simple.h>

// =====================================================
// CONFIGURACIÓN WI-FI
// =====================================================
const char* ssid = "autoicc";
const char* password = "autitos12";

// =====================================================
// CONFIGURACIÓN MQTT SEGURO
// =====================================================

// Verifica que esta sea realmente la IP del broker.
// En tu código actual aparece 10.254.148.141.
const char* mqtt_server = "10.254.148.141";

// Puerto MQTT con TLS
const int mqtt_port = 1883;

const char* mqtt_client_name =
  "MKR1000_SmartHome_EquipoHector";

// Credenciales Mosquitto
const char* mqtt_username = "mi_usuario";
const char* mqtt_password = "equipoHector";

// =====================================================
// CONFIGURACIÓN COAP
// =====================================================

// IP del computador donde corre Node-RED.
// Esta IP puede ser distinta a la del broker.
IPAddress nodeRedIp(10, 254, 148, 141);

// Puerto estándar CoAP
const int coap_port = 5683;

// Recurso CoAP
const char* coap_recurso_temperatura =
  "temperatura";

// =====================================================
// TÓPICOS MQTT
// =====================================================
const char* topic_datos =
  "smarthome/equipoHector/datos";

const char* topic_temperatura =
  "smarthome/equipoHector/temperatura";

const char* topic_humedad =
  "smarthome/equipoHector/humedad";

const char* topic_mq6 =
  "smarthome/equipoHector/gas/mq6";

const char* topic_mq7 =
  "smarthome/equipoHector/gas/mq7";

const char* topic_microfono =
  "smarthome/equipoHector/sonido/microfono";

const char* topic_control_led =
  "smarthome/equipoHector/control/led";

// =====================================================
// PINES
// =====================================================
const int pinLED = 6;
const int pinMQ6 = A1;
const int pinMQ7 = A2;
const int pinMicrofono = A4;

// =====================================================
// OBJETOS GLOBALES
// =====================================================

// Cliente TCP seguro con TLS.
// El certificado CA ya quedó cargado en el MKR1000.
WiFiClient mqttClient;
PubSubClient client(mqttClient);

// Cliente UDP para CoAP
WiFiUDP udp;
Coap coap(udp);

// Sensor AHT20 / AM2315C
Adafruit_AHTX0 aht;

// =====================================================
// ESTADO DEL SISTEMA
// =====================================================
bool aht_conectado = false;

float temperaturaActual = -99.9;
float humedadActual = -99.9;

// Control de reconexión MQTT
unsigned long ultimoIntentoMQTT = 0;
const unsigned long intervaloReconexionMQTT = 5000;

// Control de envío de sensores
unsigned long ultimoEnvioSensores = 0;
const unsigned long intervaloSensores = 5000;

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

  Serial.print("IP asignada al MKR1000: ");
  Serial.println(WiFi.localIP());
}

// =====================================================
// CALLBACK MQTT
// =====================================================
void callbackMQTT(
  char* topic,
  byte* payload,
  unsigned int length
) {
  String mensaje = "";

  for (unsigned int i = 0; i < length; i++) {
    mensaje += (char)payload[i];
  }

  Serial.print("Mensaje MQTT recibido en [");
  Serial.print(topic);
  Serial.print("]: ");
  Serial.println(mensaje);

  if (String(topic) == topic_control_led) {
    if (mensaje == "ON") {
      digitalWrite(pinLED, HIGH);
      Serial.println("-> Acción: LED encendido");

    } else if (mensaje == "OFF") {
      digitalWrite(pinLED, LOW);
      Serial.println("-> Acción: LED apagado");
    }
  }
}

// =====================================================
// CONEXIÓN MQTT SEGURA NO BLOQUEANTE
// =====================================================
void mantenerConexionMQTT() {
  if (client.connected()) {
    return;
  }

  unsigned long ahora = millis();

  if (
    ultimoIntentoMQTT != 0 &&
    ahora - ultimoIntentoMQTT <
      intervaloReconexionMQTT
  ) {
    return;
  }

  ultimoIntentoMQTT = ahora;

  Serial.print(
    "Intentando conexión MQTT segura... "
  );

  bool conectado = client.connect(
    mqtt_client_name,
    mqtt_username,
    mqtt_password
  );

  if (conectado) {
    Serial.println(
      "Conectado al broker MQTT seguro."
    );

    bool suscrito =
      client.subscribe(topic_control_led);

    if (suscrito) {
      Serial.println(
        "Suscrito al tópico de control LED."
      );
    } else {
      Serial.println(
        "ERROR: no fue posible suscribirse al LED."
      );
    }

  } else {
    Serial.print("Error MQTT, rc=");
    Serial.println(client.state());

    Serial.println(
      "Se intentará nuevamente en 5 segundos."
    );
  }
}

// =====================================================
// CALLBACK DE RESPUESTA COAP
// =====================================================
void callbackRespuestaCoap(
  CoapPacket &packet,
  IPAddress ip,
  int port
) {
  Serial.print(
    "Respuesta CoAP recibida desde "
  );

  Serial.print(ip);
  Serial.print(":");
  Serial.println(port);

  Serial.print("Código CoAP: ");
  Serial.println(packet.code);

  if (
    packet.payload != NULL &&
    packet.payloadlen > 0
  ) {
    char respuesta[packet.payloadlen + 1];

    memcpy(
      respuesta,
      packet.payload,
      packet.payloadlen
    );

    respuesta[packet.payloadlen] = '\0';

    Serial.print("Contenido respuesta: ");
    Serial.println(respuesta);

  } else {
    Serial.println(
      "Node-RED confirmó el mensaje sin contenido."
    );
  }
}

// =====================================================
// ENVIAR TEMPERATURA POR COAP
// =====================================================
void enviarTemperaturaCoap(
  float temperatura
) {
  StaticJsonDocument<64> doc;

  float temperaturaRedondeada =
    round(temperatura * 100.0) / 100.0;

  doc["temperatura"] =
    temperaturaRedondeada;

  char jsonBuffer[64];

  size_t largo = serializeJson(
    doc,
    jsonBuffer,
    sizeof(jsonBuffer)
  );

  uint16_t messageId = coap.send(
    nodeRedIp,
    coap_port,
    coap_recurso_temperatura,
    COAP_CON,
    COAP_PUT,
    NULL,
    0,
    (const uint8_t*)jsonBuffer,
    largo,
    COAP_APPLICATION_JSON
  );

  if (messageId != 0) {
    Serial.print(
      "Temperatura enviada por CoAP: "
    );

    Serial.println(jsonBuffer);

    Serial.print("Destino: coap://");
    Serial.print(nodeRedIp);
    Serial.print(":");
    Serial.print(coap_port);
    Serial.print("/");
    Serial.println(
      coap_recurso_temperatura
    );

    Serial.print("Message ID CoAP: ");
    Serial.println(messageId);

  } else {
    Serial.println(
      "ERROR: no se pudo crear el paquete CoAP."
    );
  }
}

// =====================================================
// PUBLICAR JSON FLOAT POR MQTT
// =====================================================
void publicarJSONFloat(
  const char* topic,
  const char* key,
  float valor
) {
  if (!client.connected()) {
    return;
  }

  StaticJsonDocument<64> doc;
  doc[key] = valor;

  char jsonBuffer[64];

  serializeJson(
    doc,
    jsonBuffer,
    sizeof(jsonBuffer)
  );

  bool publicado =
    client.publish(topic, jsonBuffer);

  if (!publicado) {
    Serial.print(
      "ERROR publicando MQTT en: "
    );
    Serial.println(topic);
  }
}

// =====================================================
// PUBLICAR JSON INT POR MQTT
// =====================================================
void publicarJSONInt(
  const char* topic,
  const char* key,
  int valor
) {
  if (!client.connected()) {
    return;
  }

  StaticJsonDocument<64> doc;
  doc[key] = valor;

  char jsonBuffer[64];

  serializeJson(
    doc,
    jsonBuffer,
    sizeof(jsonBuffer)
  );

  bool publicado =
    client.publish(topic, jsonBuffer);

  if (!publicado) {
    Serial.print(
      "ERROR publicando MQTT en: "
    );
    Serial.println(topic);
  }
}

// =====================================================
// LEER TEMPERATURA Y HUMEDAD
// =====================================================
bool leerSensorAHT() {
  if (!aht_conectado) {
    temperaturaActual = -99.9;
    humedadActual = -99.9;
    return false;
  }

  sensors_event_t humidity;
  sensors_event_t temp;

  aht.getEvent(&humidity, &temp);

  temperaturaActual =
    temp.temperature;

  humedadActual =
    humidity.relative_humidity;

  return true;
}

// =====================================================
// SETUP
// =====================================================
void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println(
    "Iniciando SmartHome IoT - Equipo Hector"
  );

  pinMode(pinLED, OUTPUT);
  digitalWrite(pinLED, LOW);

  // WiFi
  setup_wifi();

  // MQTT seguro
  client.setServer(
    mqtt_server,
    mqtt_port
  );

  client.setCallback(callbackMQTT);

  // Ajustes opcionales MQTT
  client.setKeepAlive(60);
  client.setSocketTimeout(15);

  // Sensor AHT
  if (!aht.begin()) {
    Serial.println(
      "ERROR: no se encontró el sensor AHT20."
    );

    Serial.println(
      "Revisar SDA, SCL, VCC y GND."
    );

    aht_conectado = false;

  } else {
    Serial.println(
      "Sensor AHT20 inicializado."
    );

    aht_conectado = true;

    leerSensorAHT();

    Serial.print(
      "Temperatura inicial: "
    );

    Serial.print(temperaturaActual);
    Serial.println(" °C");
  }

  // CoAP
  coap.response(
    callbackRespuestaCoap
  );

  if (coap.start(coap_port)) {
    Serial.println(
      "Cliente CoAP iniciado."
    );

    Serial.print(
      "Puerto local CoAP: "
    );

    Serial.println(coap_port);

    Serial.print(
      "Destino CoAP: coap://"
    );

    Serial.print(nodeRedIp);
    Serial.print(":");
    Serial.print(coap_port);
    Serial.print("/");
    Serial.println(
      coap_recurso_temperatura
    );

  } else {
    Serial.println(
      "ERROR: no se pudo iniciar CoAP."
    );
  }
}

// =====================================================
// LOOP PRINCIPAL
// =====================================================
void loop() {
  // Mantener MQTT seguro
  mantenerConexionMQTT();

  // Procesar mensajes MQTT
  client.loop();

  // Procesar mensajes CoAP
  coap.loop();

  unsigned long ahora = millis();

  if (
    ahora - ultimoEnvioSensores >=
      intervaloSensores
  ) {
    ultimoEnvioSensores = ahora;

    // Lecturas analógicas
    int valorMQ6 =
      analogRead(pinMQ6);

    int valorMQ7 =
      analogRead(pinMQ7);

    int valorMicrofono =
      analogRead(pinMicrofono);

    // Lectura AHT
    bool lecturaAhtValida =
      leerSensorAHT();

    // ===============================================
    // PUBLICACIÓN MQTT SEGURA
    // ===============================================
    if (client.connected()) {
      publicarJSONFloat(
        topic_temperatura,
        "temperatura",
        temperaturaActual
      );

      publicarJSONFloat(
        topic_humedad,
        "humedad",
        humedadActual
      );

      publicarJSONInt(
        topic_mq6,
        "mq6",
        valorMQ6
      );

      publicarJSONInt(
        topic_mq7,
        "mq7",
        valorMQ7
      );

      publicarJSONInt(
        topic_microfono,
        "microfono",
        valorMicrofono
      );

      Serial.println(
        "Datos publicados por MQTT seguro."
      );

    } else {
      Serial.println(
        "MQTT seguro no conectado."
      );
    }

    // ===============================================
    // ENVÍO COAP
    // ===============================================
    if (lecturaAhtValida) {
      enviarTemperaturaCoap(
        temperaturaActual
      );

    } else {
      Serial.println(
        "No se envió CoAP: lectura AHT inválida."
      );
    }

    // ===============================================
    // MONITOR SERIAL
    // ===============================================
    Serial.println(
      "----------------------------"
    );

    Serial.print("Temperatura: ");
    Serial.print(temperaturaActual);
    Serial.println(" °C");

    Serial.print("Humedad: ");
    Serial.print(humedadActual);
    Serial.println(" %");

    Serial.print("MQ6: ");
    Serial.println(valorMQ6);

    Serial.print("MQ7: ");
    Serial.println(valorMQ7);

    Serial.print("Micrófono: ");
    Serial.println(valorMicrofono);

    Serial.println(
      "----------------------------"
    );
  }
}