#!/bin/sh
set -eu

INTERVALO="${PREDICCION_INTERVALO_SEGUNDOS:-60}"

echo "Servicio de regresion iniciado."
echo "Ejecutando modelo cada ${INTERVALO} segundos."

while true; do
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Ejecutando modeloRegresion.py"

  if python /app/modeloRegresion.py; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Ejecucion completada."
  else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Error ejecutando modeloRegresion.py"
  fi

  sleep "$INTERVALO"
done