import json
import ssl
import time
import os
from datetime import datetime, timedelta

import pandas as pd
import numpy as np
import paho.mqtt.client as mqtt

# ===========================
# Configuración
# ===========================

CSV_PATH = os.getenv("CSV_PATH", "/shared/datos_temperatura.csv")
PREDICCION_PATH = os.getenv("PREDICCION_PATH", "/shared/prediccion.json")
VENTANA_HORAS = 6
MINUTOS_PREDICCION = 30

UMBRAL_TEMPERATURA = 30.0
    
# MQTT
MQTT_BROKER = os.getenv("MQTT_BROKER", "10.254.148.141")
MQTT_PORT = int(os.getenv("MQTT_PORT", "8883"))
MQTT_USER = os.getenv("MQTT_USER", "esp32cam")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "esp32cam")

CA_CERT = os.getenv("MQTT_CA_CERT", "./mosquitto/certs/ca.crt")

TOPIC_PREDICCION = "smarthome/equipoHector/prediccion/temperatura"

TOPIC_ALERTA = "smarthome/equipoHector/alerta"

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

timeout = 10

while not conectado and timeout > 0:
    time.sleep(0.5)
    timeout -= 0.5

if not conectado:
    print("No se pudo conectar al broker MQTT.")
    exit(1)

# ===========================
# Leer CSV
# ===========================

if not os.path.exists(CSV_PATH) or os.path.getsize(CSV_PATH) == 0:
    raise FileNotFoundError(
        f"No existe el CSV de temperatura o está vacío: {CSV_PATH}"
    )

df = pd.read_csv(CSV_PATH)

columnas_requeridas = {"timestamp", "temperatura"}
if not columnas_requeridas.issubset(df.columns):
    raise ValueError(
        f"El CSV debe contener las columnas: {', '.join(sorted(columnas_requeridas))}"
    )

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
    "fecha_registro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "fecha_entrenamiento": ultima_fecha.strftime("%Y-%m-%d %H:%M:%S"),
    "fecha_prediccion": hora_predicha.strftime("%Y-%m-%d %H:%M:%S"),
    "temperatura_predicha": round(temperatura_predicha, 2),
    "muestras_utilizadas": len(df),
    "ventana_horas": VENTANA_HORAS
}

print(json.dumps(resultado, indent=4))

# ===========================
# Guardar historial JSON
# ===========================

os.makedirs(os.path.dirname(PREDICCION_PATH), exist_ok=True)

predicciones = []

if os.path.exists(PREDICCION_PATH) and os.path.getsize(PREDICCION_PATH) > 0:
    try:
        with open(PREDICCION_PATH, "r", encoding="utf-8") as archivo:
            contenido = json.load(archivo)

        if isinstance(contenido, list):
            predicciones = contenido
        elif isinstance(contenido, dict):
            predicciones = contenido.get("predicciones", [])
    except json.JSONDecodeError:
        print("Advertencia: prediccion.json inválido. Se recreará el historial.")

predicciones.append(resultado)

with open(PREDICCION_PATH, "w", encoding="utf-8") as archivo:
    json.dump({"predicciones": predicciones}, archivo, indent=4)

print(f"Predicción almacenada en {PREDICCION_PATH}.")

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

    if temperatura_predicha > UMBRAL_TEMPERATURA:
        print("Advertencia: La temperatura predicha supera el umbral.")

        alerta = {
            "mensaje": "La temperatura predicha supera el umbral.",
            "valor": round(temperatura_predicha, 2),
            "horizon_min": MINUTOS_PREDICCION
        }


        info_alerta = cliente.publish(
            TOPIC_ALERTA,
            json.dumps(alerta),
            qos=1
        )
        info_alerta.wait_for_publish()
        print("Alerta publicada correctamente.")


else:
    print("No fue posible conectar al broker MQTT.")

cliente.loop_stop()
cliente.disconnect()
