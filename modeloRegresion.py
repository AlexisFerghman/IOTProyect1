import json
import ssl
from datetime import datetime, timedelta

import pandas as pd
import numpy as np
import paho.mqtt.client as mqtt

# ===========================
# Configuración
# ===========================

CSV_PATH = "datos_temperatura.csv"

VENTANA_HORAS = 6
MINUTOS_PREDICCION = 30

# MQTT
MQTT_BROKER = "10.254.148.141"
MQTT_PORT = 8883
MQTT_USER = "esp32cam"
MQTT_PASSWORD = "esp32cam"

CA_CERT = "mosquitto/certs/ca.crt"

TOPIC_PREDICCION = "smarthome/equipoHector/prediccion/temperatura"

# ===========================
# MQTT
# ===========================

conectado = False

def on_connect(client, userdata, flags, reason_code, properties=None):
    global conectado

    if reason_code == 0:
        conectado = True
        print("Conectado al broker MQTT.")
    else:
        print(f"Error al conectar: {reason_code}")

cliente = mqtt.Client(
    mqtt.CallbackAPIVersion.VERSION2
)

cliente.username_pw_set(MQTT_USER, MQTT_PASSWORD)

cliente.tls_set(
    ca_certs=CA_CERT,
    certfile=None,
    keyfile=None,
    cert_reqs=ssl.CERT_REQUIRED,
    tls_version=ssl.PROTOCOL_TLS_CLIENT
)

cliente.on_connect = on_connect

cliente.connect(MQTT_BROKER, MQTT_PORT)

cliente.loop_start()

# ===========================
# Leer CSV
# ===========================

df = pd.read_csv(CSV_PATH)

# Eliminar cabeceras repetidas
df = df[df["timestamp"] != "timestamp"].copy()

# Convertir timestamp
df["timestamp"] = pd.to_datetime(
    df["timestamp"],
    errors="coerce"
)

# Convertir temperatura a número
df["temperatura"] = pd.to_numeric(
    df["temperatura"],
    errors="coerce"
)

# Eliminar filas inválidas
df = df.dropna(subset=["timestamp", "temperatura"])

df = df.sort_values("timestamp")
# ===========================
# Últimas 6 horas
# ===========================

ultima_fecha = df["timestamp"].max()

limite = ultima_fecha - timedelta(hours=VENTANA_HORAS)

df = df[df["timestamp"] >= limite]

if len(df) < 2:
    raise Exception("No existen suficientes datos para entrenar el modelo.")

# ===========================
# Preparar datos
# ===========================

tiempo_inicio = df["timestamp"].min()

df["segundos"] = (
    df["timestamp"] - tiempo_inicio
).dt.total_seconds()

X = df[["segundos"]]

y = df["temperatura"]

# ===========================
# Ajuste mediante regresión lineal
# ===========================

# polyfit devuelve la pendiente (m) y la ordenada al origen (b)
m, b = np.polyfit(df["segundos"], df["temperatura"], 1)

# Tiempo futuro (30 minutos)
ultimo_segundo = df["segundos"].max()
x_futuro = ultimo_segundo + MINUTOS_PREDICCION * 60

# Predicción usando la recta y = mx + b
temperatura_predicha = m * x_futuro + b
hora_predicha = ultima_fecha + timedelta(
    minutes=MINUTOS_PREDICCION
)

resultado = {
    "fecha_entrenamiento": ultima_fecha.strftime("%Y-%m-%d %H:%M:%S"),
    "fecha_prediccion": hora_predicha.strftime("%Y-%m-%d %H:%M:%S"),
    "temperatura_predicha": round(temperatura_predicha, 2),
    "muestras_utilizadas": len(df),
    "ventana_horas": VENTANA_HORAS
}

print(json.dumps(resultado, indent=4))

# ===========================
# Publicar MQTT
# ===========================

mensaje = {
    "valor": round(temperatura_predicha, 2),
    "horizon_min": MINUTOS_PREDICCION
}

if conectado:

    info = cliente.publish(
        TOPIC_PREDICCION,
        json.dumps(mensaje),
        qos=1
    )

    info.wait_for_publish()

    print("Predicción publicada correctamente.")

else:
    print("No fue posible conectar al broker MQTT.")

cliente.loop_stop()
cliente.disconnect()