from __future__ import annotations

from threading import Thread

from werkzeug.serving import make_server


class FlaskServer:
    def __init__(self, app, host: str, port: int) -> None:
        self._server = make_server(host, port, app)
        self._thread = Thread(target=self._server.serve_forever, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._thread.join(timeout=5)
