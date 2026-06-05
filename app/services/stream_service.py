from __future__ import annotations

from dataclasses import dataclass
from threading import Lock, Thread
import time

import cv2
import numpy as np


@dataclass
class StreamFrame:
    frame: np.ndarray | None = None
    updated_at: float = 0.0


class StreamService:
    def __init__(self, stream_url: str) -> None:
        self._stream_url = stream_url
        self._lock = Lock()
        self._latest = StreamFrame()
        self._stop = False
        self._thread = Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop = True
        self._thread.join(timeout=5)

    def read_latest(self) -> np.ndarray | None:
        with self._lock:
            if self._latest.frame is None:
                return None
            return self._latest.frame.copy()

    def _run(self) -> None:
        while not self._stop:
            capture = cv2.VideoCapture(self._stream_url)
            try:
                capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception:
                pass
            if not capture.isOpened():
                print(f"[STREAM] No se pudo abrir el stream: {self._stream_url}")
                time.sleep(2)
                continue

            print(f"[STREAM] Conectado al stream MJPEG: {self._stream_url}")
            while not self._stop:
                success, frame = capture.read()
                if not success or frame is None:
                    print("[STREAM] Reintentando conexion al stream")
                    break
                with self._lock:
                    self._latest = StreamFrame(frame=frame.copy(), updated_at=time.time())
                time.sleep(0.01)
            capture.release()
            time.sleep(2)
