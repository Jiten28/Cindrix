"""Environment-based settings for Cindrix."""

import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "").strip()
TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "").strip()

# --- Groq (primary generation provider) -----------------------------------
# Groq primary + Gemini fallback, both required (unlike the optional TAVILY key).
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "").strip()
# Not llama-3.3-70b-versatile — Groq deprecated it; gpt-oss-120b is the replacement.
GROQ_MODEL: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip()

GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-flash-latest").strip()
GEMINI_EMBEDDING_MODEL: str = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001").strip()

# --- STT provider ----------------------------------------------------------
# Sarvam is the real provider; the browser Web Speech API is a keyless dev
# fallback that only exists so `git clone && flask run` has working voice input
# with no account. Defaults to Sarvam whenever a key is present, so a configured
# deployment is never silently downgraded to the browser path.
SARVAM_API_KEY: str = os.getenv("SARVAM_API_KEY", "").strip()
STT_PROVIDER: str = os.getenv(
    "STT_PROVIDER", "sarvam" if SARVAM_API_KEY else "webspeech"
).strip().lower()
SARVAM_STT_MODEL: str = os.getenv("SARVAM_STT_MODEL", "saaras:v3").strip()
# "unknown" = auto-detect across the Indic languages the corpus covers.
SARVAM_STT_LANGUAGE: str = os.getenv("SARVAM_STT_LANGUAGE", "unknown").strip()

# --- RAG / vector store ----------------------------------------------------
RAG_DATASET_NAME: str = os.getenv("RAG_DATASET_NAME", "ai4bharat/MSMARCO-XI").strip()
RAG_DATASET_LANGUAGE: str = os.getenv("RAG_DATASET_LANGUAGE", "hi").strip()
RAG_DATASET_SPLIT: str = os.getenv("RAG_DATASET_SPLIT", "train").strip()
# The dataset is 10M+ rows/language. The binding limit isn't the (cached) shard
# download but Gemini's free-tier embedding quota (~100 contents/min), so ingest
# is capped to a bounded, fully-embedded subset. Raise this on a paid tier.
RAG_INGEST_MAX_ROWS: int = int(os.getenv("RAG_INGEST_MAX_ROWS", "75"))
# Deliberately NOT under data/ — data/ is the mutable runtime volume (uploads,
# history) and a hosted persistent disk mounted there would shadow anything
# baked into the image. The index is read-only build output, so it ships with
# the code instead.
RAG_INDEX_DIR: str = os.getenv("RAG_INDEX_DIR", "rag_index").strip()
# Cosine bands that decide what happens after a knowledge-base search. Both
# were calibrated against the built index rather than guessed — see
# docs/Architecture.md. gemini-embedding-001 compresses same-language
# similarity into a narrow range, so a single floor can't separate "this is in
# the corpus" from "this merely looks like it". Measured over the shipped
# 868-chunk index by `python -m app.rag.benchmark`: 28 in-corpus queries scored
# 0.65-0.83, and 10 out-of-corpus queries (Hindi and English, general knowledge,
# how-to, current-value lookups) topped out at 0.659 — so 0.75 clears every
# observed non-match by 0.09. The decline band below it is deliberately narrow:
# it covers the genuinely ambiguous overlap, not everything that fails to ground,
# because declining a general question is worse than answering it conversationally.
#
#   >= RAG_MIN_RELEVANCE   answer strictly from the retrieved excerpts
#   >= RAG_DECLINE_FLOOR   related material, no confident match -> decline
#   below                  corpus isn't about this -> answer conversationally
RAG_MIN_RELEVANCE: float = float(os.getenv("RAG_MIN_RELEVANCE", "0.75"))
RAG_DECLINE_FLOOR: float = float(os.getenv("RAG_DECLINE_FLOOR", "0.70"))


# Model selector — current ids for the two providers this app uses, each tagged
# with its provider so retry.py routes a selection to the right primary. Groq is
# first and the default; its id tracks GROQ_MODEL.
AVAILABLE_MODELS = [
    {"id": GROQ_MODEL, "label": "Groq GPT-OSS 120B (recommended)", "provider": "groq"},
    {"id": "gemini-flash-latest", "label": "Gemini Flash", "provider": "gemini"},
    {"id": "gemini-3.6-flash", "label": "Gemini 3.6 Flash", "provider": "gemini"},
    {"id": "gemini-3.5-flash-lite", "label": "Gemini 3.5 Flash-Lite (fastest)", "provider": "gemini"},
]

# Lookups derived from AVAILABLE_MODELS.
_MODELS_BY_ID = {m["id"]: m for m in AVAILABLE_MODELS}
# Gemini-only ids — gemini_client.py validates overrides against this set, so a
# Groq id from the UI is never sent to the Gemini API as a model name.
GEMINI_MODEL_IDS = {m["id"] for m in AVAILABLE_MODELS if m["provider"] == "gemini"}
# Default when the client sends none — the first entry (Groq).
DEFAULT_MODEL_ID = AVAILABLE_MODELS[0]["id"]


def model_provider(model_id: Optional[str]) -> str:
    """Provider ('groq'/'gemini') for a selector model id; unknown/absent -> default (Groq)."""
    entry = _MODELS_BY_ID.get(model_id)
    if entry:
        return entry["provider"]
    return _MODELS_BY_ID[DEFAULT_MODEL_ID]["provider"]

# Always-admin emails, independent of the "first user is admin" bootstrap.
# Comma-separated in .env; kept out of source since this repo is public.
ADMIN_EMAILS = {
    e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()
}

# Random per-run key if unset (sessions won't survive a restart). Set a real
# FLASK_SECRET_KEY before deploying.
import secrets as _secrets  # noqa: E402
SECRET_KEY: str = os.getenv("FLASK_SECRET_KEY", "").strip() or _secrets.token_hex(32)

UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "data/uploads").strip()
EMBEDDING_DIR: str = os.getenv("EMBEDDING_DIR", "data/embeddings").strip()
MAX_UPLOAD_MB: int = int(os.getenv("MAX_UPLOAD_MB", "15"))

# Flask
DEBUG: bool = os.getenv("FLASK_DEBUG", "true").lower() == "true"
HOST: str = os.getenv("HOST", "127.0.0.1")
PORT: int = int(os.getenv("PORT", "5000"))


def warn_if_missing() -> list[str]:
    """Human-readable warnings for missing optional config, printed once at startup."""
    warnings = []
    if not GOOGLE_API_KEY:
        warnings.append("GOOGLE_API_KEY not set — Gemini (fallback generation provider), and general web search via Gemini's Google Search grounding, won't work.")
    if not GROQ_API_KEY:
        warnings.append("GROQ_API_KEY not set — Groq (primary generation provider) won't work; RAG-serving calls will fall straight to Gemini every time instead of Groq-then-Gemini.")
    if not TAVILY_API_KEY:
        warnings.append("TAVILY_API_KEY not set — image search ('image of X') disabled; general web search is unaffected (uses Gemini directly).")
    if not SARVAM_API_KEY:
        warnings.append("SARVAM_API_KEY not set — voice input falls back to the browser Web Speech API (dev only, Chrome/Edge, no server-side transcription).")
    return warnings
