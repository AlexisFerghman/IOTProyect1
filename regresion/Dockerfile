FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    CSV_PATH=/shared/datos_temperatura.csv \
    PREDICCION_PATH=/shared/prediccion.json \
    MQTT_BROKER=mosquitto \
    MQTT_PORT=8883 \
    MQTT_USER=esp32cam \
    MQTT_PASSWORD=esp32cam \
    MQTT_CA_CERT=/app/mosquitto/certs/ca.crt \
    PREDICCION_INTERVALO_SEGUNDOS=600

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates cron \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --upgrade pip \
    && pip install numpy==1.26.4 pandas==2.2.2 paho-mqtt==2.1.0

COPY modeloRegresion.py ./modeloRegresion.py
COPY cronjob ./cronjob

RUN cp /app/cronjob /etc/cron.d/regresion \
    && chmod 0644 /etc/cron.d/regresion \
    && touch /var/log/cron.log

CMD ["sh", "-c", "printenv > /etc/environment && cron && tail -f /var/log/cron.log"]
