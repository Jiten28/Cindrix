"""Flask application factory."""

import os

from flask import Flask, send_from_directory

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")


def create_app() -> Flask:
    app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")

    from app.api.routes import bp as api_bp
    app.register_blueprint(api_bp)

    @app.route("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.route("/health")
    def health():
        return {"status": "ok", "service": "nimbus-ai"}

    return app
