from __future__ import annotations

from datetime import datetime, timezone
from threading import Event, Thread
import time

from app.config.settings import Settings
from app.mqtt.publisher import MQTTPublisher
from app.recognition.embedding_service import EmbeddingService
from app.recognition.face_detector import FaceDetector
from app.recognition.face_recognizer import FaceRecognizer
from app.services.app_state import AppState, DetectionSnapshot
from app.services.stream_service import StreamService


class DetectionWorker:
    def __init__(
        self,
        settings: Settings,
        stream_service: StreamService,
        detector: FaceDetector,
        embedding_service: EmbeddingService,
        recognizer: FaceRecognizer,
        mqtt_publisher: MQTTPublisher,
        state: AppState,
    ) -> None:
        self._settings = settings
        self._stream_service = stream_service
        self._detector = detector
        self._embedding_service = embedding_service
        self._recognizer = recognizer
        self._mqtt_publisher = mqtt_publisher
        self._state = state
        self._stop_event = Event()
        self._thread = Thread(target=self._run, daemon=True)
        self._last_processed_at = 0.0

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            now = time.monotonic()
            if now - self._last_processed_at < self._settings.frame_interval_seconds:
                time.sleep(0.05)
                continue

            frame = self._stream_service.read_latest()
            if frame is None:
                time.sleep(0.2)
                continue

            self._last_processed_at = now
            face_box = self._detector.detect_largest_face(frame)
            if face_box is None:
                snapshot = DetectionSnapshot(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    person_detected=False,
                    known_person=False,
                    person_name=None,
                    confidence=0.0,
                )
                self._state.update_detection(snapshot)
                print("[FACE_DETECT] No se detecto rostro en el frame muestreado")
                continue

            try:
                face_crop = self._detector.crop_face(frame, face_box)
                embedding = self._embedding_service.extract_embedding(face_crop)
                recognition = self._recognizer.recognize(embedding)
                snapshot = DetectionSnapshot(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    person_detected=True,
                    known_person=recognition.known_person,
                    person_name=recognition.person_name,
                    confidence=recognition.confidence,
                )
                self._state.update_detection(snapshot)

                print(
                    f"[FACE_DETECT] Rostro valido detectado x={face_box.x} y={face_box.y} "
                    f"w={face_box.w} h={face_box.h}"
                )
                print(
                    f"[FACE_RECOGNITION] known={recognition.known_person} person={recognition.person_name} "
                    f"confidence={recognition.confidence:.4f}"
                )

                signature = f"{snapshot.known_person}:{snapshot.person_name or 'unknown'}"
                if self._state.can_publish(signature, time.time(), self._settings.mqtt_event_cooldown_seconds):
                    payload = snapshot.to_dict()
                    self._mqtt_publisher.publish(payload)
            except Exception as exc:
                print(f"[FACE_RECOGNITION] Error procesando el rostro detectado: {exc}")
