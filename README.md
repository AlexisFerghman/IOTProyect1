# IOTProyect1

## Conexion MQTT segura

La aplicacion publica los eventos de deteccion por MQTT sobre TLS con el certificado autofirmado ubicado en `mosquitto/certs/ca.crt`.

Credenciales por defecto:

- Usuario: `esp32cam`
- Contraseña: `esp32cam`

Variables relevantes:

- `MQTT_HOST`: direccion del broker Mosquitto
- `MQTT_PORT`: puerto TLS del broker, por defecto `8883`
- `MQTT_TLS_ENABLED`: activa la verificacion TLS
- `MQTT_TLS_CA_CERTS`: ruta al CA certificate autofirmado