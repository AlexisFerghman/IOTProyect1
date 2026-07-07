from __future__ import annotations

import signal
import time

from app.api.routes import create_api
from app.api.server import FlaskServer
from app.config.settings import Settings
from app.mqtt.publisher import MQTTPublisher
from app.recognition.embedding_service import EmbeddingService
from app.recognition.face_detector import FaceDetector
from app.recognition.face_recognizer import FaceRecognizer
from app.services.app_state import AppState
from app.services.detection_worker import DetectionWorker
from app.services.stream_service import StreamService


def build_runtime() -> tuple[FlaskServer, DetectionWorker, StreamService, MQTTPublisher]:
    settings = Settings.from_env()
    detector = FaceDetector(
        scale_factor=settings.face_detect_scale_factor,
        min_neighbors=settings.face_detect_min_neighbors,
        min_size=settings.face_detect_min_size,
    )
    embedding_service = EmbeddingService(settings, detector)
    index = embedding_service.load_or_build_index()
    recognizer = FaceRecognizer(settings, index)
    mqtt_publisher = MQTTPublisher(settings)
    mqtt_publisher.connect()
    stream_service = StreamService(settings.stream_url)
    stream_service.start()
    state = AppState()
    worker = DetectionWorker(
        settings=settings,
        stream_service=stream_service,
        detector=detector,
        embedding_service=embedding_service,
        recognizer=recognizer,
        mqtt_publisher=mqtt_publisher,
        state=state,
    )
    worker.start()
    app = create_api(state)
    server = FlaskServer(app, settings.api_host, settings.api_port)
    return server, worker, stream_service, mqtt_publisher


def main() -> None:
    server, worker, stream_service, mqtt_publisher = build_runtime()
    stop_requested = False

    def _stop_handler(signum, frame):
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGINT, _stop_handler)
    signal.signal(signal.SIGTERM, _stop_handler)

    server.start()
    print("[API] Servidor Flask iniciado")

    try:
        while not stop_requested:
            time.sleep(0.5)
    finally:
        worker.stop()
        stream_service.stop()
        server.stop()
        mqtt_publisher.close()
        print("[API] Aplicacion detenida")


if __name__ == "__main__":
    main()
