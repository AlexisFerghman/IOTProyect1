from __future__ import annotations

import importlib
import json
from typing import Any

try:
    mqtt = importlib.import_module("paho.mqtt.client")
except ModuleNotFoundError as exc:  # pragma: no cover - dependencias instaladas en Docker
    raise ModuleNotFoundError("Falta instalar paho-mqtt en el entorno de ejecucion") from exc

from app.config.settings import Settings


class MQTTPublisher:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = mqtt.Client(client_id=settings.mqtt_client_id, protocol=mqtt.MQTTv311)
        self._connected = False
        if settings.mqtt_username:
            self._client.username_pw_set(settings.mqtt_username, settings.mqtt_password)

        def _on_connect(client, userdata, flags, reason_code, properties=None):
            self._connected = True
            print(f"[MQTT] Conexion establecida con codigo {reason_code}")

        def _on_disconnect(client, userdata, reason_code, properties=None):
            self._connected = False
            print(f"[MQTT] Conexion cerrada con codigo {reason_code}")

        self._client.on_connect = _on_connect
        self._client.on_disconnect = _on_disconnect

    def connect(self) -> None:
        try:
            self._client.connect(self._settings.mqtt_host, self._settings.mqtt_port, keepalive=60)
            self._client.loop_start()
            self._connected = True
            print(f"[MQTT] Conectado a {self._settings.mqtt_host}:{self._settings.mqtt_port}")
        except Exception as exc:
            self._connected = False
            print(f"[MQTT] No fue posible conectar al broker: {exc}")

    def publish(self, payload: dict[str, Any]) -> None:
        if not self._connected:
            self.connect()
            if not self._connected:
                print("[MQTT] Evento omitido porque el broker no esta disponible")
                return
        message = json.dumps(payload, ensure_ascii=False)
        try:
            result = self._client.publish(self._settings.mqtt_topic, message, qos=0, retain=False)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                print(f"[MQTT] Evento publicado en {self._settings.mqtt_topic}")
            else:
                print(f"[MQTT] Error al publicar evento: rc={result.rc}")
        except Exception as exc:
            self._connected = False
            print(f"[MQTT] Error al publicar evento: {exc}")

    def close(self) -> None:
        try:
            self._client.loop_stop()
            self._client.disconnect()
            self._connected = False
        except Exception:
            pass
