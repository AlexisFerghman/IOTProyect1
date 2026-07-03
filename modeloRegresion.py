import json
import paho.mqtt.client as mqtt
from datetime import datetime, timedelta

import pandas as pd
from sklearn.linear_model import LinearRegression


# ===========================
# Configuración
# ===========================

CSV_PATH = "datos_temperatura.csv"
OUTPUT_JSON = "prediccion.json"

VENTANA_HORAS = 6
MINUTOS_PREDICCION = 30

cliente = mqtt.Client()

cliente.connect("localhost",1883)

# ===========================
# Leer CSV
# ===========================

df = pd.read_csv(CSV_PATH)

# Eliminar filas que corresponden a cabeceras repetidas
df = df[df["timestamp"] != "timestamp"].copy()

df["timestamp"] = pd.to_datetime(df["timestamp"])

df = df.sort_values("timestamp")


# ===========================
# Filtrar últimas 6 horas
# ===========================

ultima_fecha = df["timestamp"].max()

limite = ultima_fecha - timedelta(hours=VENTANA_HORAS)

df = df[df["timestamp"] >= limite]


# Verificar datos suficientes

if len(df) < 2:
    raise Exception("No existen suficientes datos para entrenar el modelo.")


# ===========================
# Preparar entrenamiento
# ===========================

tiempo_inicio = df["timestamp"].min()

df["segundos"] = (
    df["timestamp"] - tiempo_inicio
).dt.total_seconds()

X = df[["segundos"]]

y = df["temperatura"]


# ===========================
# Entrenar modelo
# ===========================

modelo = LinearRegression()

modelo.fit(X, y)


# ===========================
# Predicción
# ===========================

ultimo_segundo = df["segundos"].max()

segundos_futuros = MINUTOS_PREDICCION * 60

x_pred = [[ultimo_segundo + segundos_futuros]]

temperatura_predicha = modelo.predict(x_pred)[0]


hora_predicha = ultima_fecha + timedelta(minutes=MINUTOS_PREDICCION)


# ===========================
# Guardar resultado
# ===========================

resultado = {
    "fecha_entrenamiento": ultima_fecha.strftime("%Y-%m-%d %H:%M:%S"),
    "fecha_prediccion": hora_predicha.strftime("%Y-%m-%d %H:%M:%S"),
    "temperatura_predicha": round(float(temperatura_predicha), 2),
    "muestras_utilizadas": len(df),
    "ventana_horas": VENTANA_HORAS
}

mensaje = {
    "valor": round(temperatura_predicha,2),
    "horizon_min":30
}

cliente.publish(
    "smarthome/equipoHector/prediccion/temperatura",
    json.dumps(mensaje)
)

print(resultado)