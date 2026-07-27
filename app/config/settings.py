"""Environment-based settings for Nimbus.

Ported from the top of gemini_retrieval.py — all the os.getenv() calls that
used to sit at module level in the CLI script now live here, so every other
module imports config instead of touching os.environ directly.
"""

import os
from dotenv import load_dotenv

load_dotenv()

GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "").strip()
GOOGLE_CSE_ID: str = os.getenv("GOOGLE_CSE_ID", "").strip()
GOOGLE_API_LOCATION: str = os.getenv("GOOGLE_API_LOCATION", "us").strip()
OPENWEATHER_API_KEY: str = os.getenv("OPENWEATHER_API_KEY", "").strip()
HISTORY_FILE: str = os.getenv("HISTORY_FILE", "data/conv_history.json").strip()

GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip()

# Flask
DEBUG: bool = os.getenv("FLASK_DEBUG", "true").lower() == "true"
HOST: str = os.getenv("HOST", "127.0.0.1")
PORT: int = int(os.getenv("PORT", "5000"))


def warn_if_missing() -> list[str]:
    """Returns a list of human-readable warnings for missing optional config.
    Called once at startup so the developer sees what's disabled, same as the
    print() warnings that used to run in gemini_retrieval.py's __main__ block.
    """
    warnings = []
    if not GOOGLE_API_KEY:
        warnings.append(
            "GOOGLE_API_KEY not set — Gemini & Custom Search won't work.")
    if not GOOGLE_CSE_ID:
        warnings.append("GOOGLE_CSE_ID not set — web/image search disabled.")
    if not OPENWEATHER_API_KEY:
        warnings.append(
            "OPENWEATHER_API_KEY not set — weather will use Gemini (approximate).")
    return warnings
