"""Entry point — runs the Cindrix Flask app."""

from app import create_app
from app.config import settings

app = create_app()

if __name__ == "__main__":
    for warning in settings.warn_if_missing():
        print(f"[warning] {warning}")
    app.run(host=settings.HOST, port=settings.PORT, debug=settings.DEBUG)
