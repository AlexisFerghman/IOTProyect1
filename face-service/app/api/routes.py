from __future__ import annotations

from flask import Blueprint, Flask, jsonify

from app.services.app_state import AppState


def create_api(state: AppState) -> Flask:
    app = Flask(__name__)
    api = Blueprint("api", __name__)

    @api.get("/health")
    def health() -> tuple[dict[str, str], int]:
        return {"status": "ok"}, 200

    @api.get("/last_detection")
    def last_detection():
        snapshot = state.get_last_detection()
        return jsonify(snapshot.to_dict())

    app.register_blueprint(api)
    return app
