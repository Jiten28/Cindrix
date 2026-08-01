"""Flask application factory."""

import os

from flask import Flask, send_from_directory

from app.config import settings

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")


def create_app() -> Flask:
    app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
    app.secret_key = settings.SECRET_KEY

    from app.api.routes import bp as api_bp
    app.register_blueprint(api_bp)

    from app.api.auth_routes import bp as auth_bp
    app.register_blueprint(auth_bp)

    from app.api.admin_routes import bp as admin_bp
    app.register_blueprint(admin_bp)

    @app.route("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.route("/health")
    def health():
        return {"status": "ok", "service": "nimbus-ai"}

    return app
