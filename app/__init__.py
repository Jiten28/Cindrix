"""Flask application factory."""

from flask import Flask


def create_app() -> Flask:
    app = Flask(__name__)

    from app.api.routes import bp as api_bp
    app.register_blueprint(api_bp)

    @app.route("/health")
    def health():
        return {"status": "ok", "service": "nimbus-ai"}

    return app
