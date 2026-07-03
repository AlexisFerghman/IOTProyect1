from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - permitido en entornos sin python-dotenv
    load_dotenv = None


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET_DIR = PROJECT_ROOT / "app" / "dataset"
DEFAULT_EMBEDDINGS_DIR = PROJECT_ROOT / "app" / "embeddings"


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    return default if value is None or value.strip() == "" else value.strip()


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return int(value)


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return float(value)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_path(value: str, default_path: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


@dataclass(frozen=True)
class Settings:
    stream_url: str
    api_host: str
    api_port: int
    mqtt_host: str
    mqtt_port: int
    mqtt_username: str
    mqtt_password: str
    mqtt_topic: str
    mqtt_client_id: str
    mqtt_tls_enabled: bool
    mqtt_tls_ca_certs: Path
    mqtt_tls_insecure: bool
    frame_interval_seconds: float
    confidence_threshold: float
    mqtt_event_cooldown_seconds: int
    face_detect_scale_factor: float
    face_detect_min_neighbors: int
    face_detect_min_size: int
    recognition_model_name: str
    dataset_dir: Path
    embeddings_dir: Path

    @property
    def embeddings_file(self) -> Path:
        return self.embeddings_dir / "face_embeddings.npz"

    @property
    def embeddings_metadata_file(self) -> Path:
        return self.embeddings_dir / "face_embeddings.meta.json"

    @classmethod
    def from_env(cls) -> "Settings":
        if load_dotenv is not None:
            load_dotenv()
        dataset_dir = _resolve_path(_env_str("DATASET_DIR", str(DEFAULT_DATASET_DIR)), DEFAULT_DATASET_DIR)
        embeddings_dir = _resolve_path(
            _env_str("EMBEDDINGS_DIR", str(DEFAULT_EMBEDDINGS_DIR)), DEFAULT_EMBEDDINGS_DIR
        )
        return cls(
            stream_url=_env_str("STREAM_URL", "http://10.223.236.145/stream"),
            api_host=_env_str("API_HOST", "0.0.0.0"),
            api_port=_env_int("API_PORT", 5000),
            mqtt_host=_env_str("MQTT_HOST", "10.254.148.141"),
            mqtt_port=_env_int("MQTT_PORT", 8883),
            mqtt_username=_env_str("MQTT_USERNAME", "esp32cam"),
            mqtt_password=_env_str("MQTT_PASSWORD", "esp32cam"),
            mqtt_topic=_env_str("MQTT_TOPIC", "smarthome/equipoXX/camara/evento"),
            mqtt_client_id=_env_str("MQTT_CLIENT_ID", "iot-face-recognition"),
            mqtt_tls_enabled=_env_bool("MQTT_TLS_ENABLED", True),
            mqtt_tls_ca_certs=_resolve_path(
                _env_str("MQTT_TLS_CA_CERTS", "mosquitto/certs/ca.crt"),
                PROJECT_ROOT / "mosquitto" / "certs" / "ca.crt",
            ),
            mqtt_tls_insecure=_env_bool("MQTT_TLS_INSECURE", False),
            frame_interval_seconds=_env_float("FRAME_INTERVAL_SECONDS", 1.0),
            confidence_threshold=_env_float("CONFIDENCE_THRESHOLD", 0.75),
            mqtt_event_cooldown_seconds=_env_int("MQTT_EVENT_COOLDOWN_SECONDS", 10),
            face_detect_scale_factor=_env_float("FACE_DETECT_SCALE_FACTOR", 1.1),
            face_detect_min_neighbors=_env_int("FACE_DETECT_MIN_NEIGHBORS", 5),
            face_detect_min_size=_env_int("FACE_DETECT_MIN_SIZE", 60),
            recognition_model_name=_env_str("RECOGNITION_MODEL_NAME", "ArcFace"),
            dataset_dir=dataset_dir,
            embeddings_dir=embeddings_dir,
        )
