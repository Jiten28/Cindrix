"""Entry point — replaces `python gemini_retrieval.py` as the way to run
Cindrix from Phase 1 onward."""

from app import create_app
from app.config import settings

app = create_app()

if __name__ == "__main__":
    for warning in settings.warn_if_missing():
        print(f"[warning] {warning}")
    app.run(host=settings.HOST, port=settings.PORT, debug=settings.DEBUG)
