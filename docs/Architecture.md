# Architecture.md

## Tech Stack

### Backend
- Python 3.11+
- Flask (FastAPI acceptable as a drop-in swap if async/streaming needs outgrow Flask)
- Gemini API via the `google-genai` SDK (primary model provider; abstracted
  behind `app/ai/gemini_client.py` so more models can be added later — note:
  the older `google-generativeai` package and `gemini-1.5-x` models are
  deprecated/shut down, don't reintroduce them — see `Memory.md`)
- LangChain — optional, only if it earns its complexity; otherwise hand-rolled
  RAG/tool-calling is fine and easier to explain in a review
- SQLite (dev) → PostgreSQL (future)
- Redis — future response/session caching

### Frontend
- HTML5 / CSS3 (custom, no Bootstrap/Tailwind)
- Vanilla JavaScript
- Three.js (or lightweight Canvas 2D) — renders the core particle-sphere identity
- GSAP (surrounding UI state transitions and micro-interactions)
- LottieFiles (supplementary micro-animations)

## High-Level Flow

```
Browser (frontend/)
   │  fetch / WebSocket (streaming)
   ▼
Flask app (app/api/) ──► app/agents/  (decides: answer directly, call a tool, or
   │                        pull from memory/RAG)
   │
   ├──► app/ai/        (Gemini client, prompt templates, streaming handler)
   ├──► app/memory/     (short-term session memory + long-term persisted memory)
   ├──► app/tools/       (web search, weather, file/PDF parsing, OCR)
   ├──► app/analytics/  (event logging → dashboard aggregation)
   ├──► app/auth/       (Phase 4: login/session)
   └──► app/database/   (SQLite models: users, conversations, messages, memory,
                          analytics events)
```

Request lifecycle for a chat turn:
1. Frontend sends user message (+ optional file/image) to `app/api/`.
2. API layer validates input, loads session context from `app/memory/`.
3. `app/agents/` decides the response strategy: direct LLM call, RAG lookup
   (`app/tools/` + embeddings in `data/embeddings/`), or tool call (search/weather).
4. `app/ai/` streams the model response back through the API layer via
   Server-Sent Events or WebSocket.
5. `app/memory/` persists the turn (short-term always, long-term if flagged
   relevant).
6. `app/analytics/` logs the event (latency, tokens, tool used, sentiment).
7. Frontend renders the streamed text and drives the particle sphere's state
   (idle → listening → thinking → speaking) off the stream lifecycle events.

## Current State (Phases 1–3 complete)

`gemini_retrieval.py` has been fully split apart; real frontend, real
multi-conversation backend, analytics, export:

```text
Nimbus-AI/
├── docs/
│   ├── PRD.md
│   ├── Architecture.md
│   ├── Design.md
│   ├── Rules.md
│   ├── Phases.md
│   └── Memory.md
├── app/
│   ├── __init__.py            # Flask app factory — sets secret_key, serves frontend/ as static
│   ├── config/settings.py     # includes AVAILABLE_MODELS (Phase 4 model selector) and SECRET_KEY
│   ├── ai/
│   │   ├── gemini_client.py   # chat + vision, both take an optional validated `model` override (Phase 4)
│   │   └── embeddings.py      # Gemini embeddings + cosine similarity (RAG)
│   ├── tools/
│   │   ├── weather.py, crypto.py, search.py
│   │   └── documents.py       # PDF/TXT/DOCX extraction + chunking
│   ├── memory/
│   │   ├── conversation_store.py   # per-user, per-conversation JSON storage (Phase 3, scoped in Phase 4)
│   │   ├── attachment_store.py     # per-user active document/image slot (Phase 2, scoped in Phase 4)
│   │   └── session_memory.py       # superseded by conversation_store.py — kept as reference
│   ├── analytics/events.py    # event logging + summary (Phase 3); now tags/filters by user_id (Phase 4)
│   ├── auth/
│   │   ├── users_store.py     # JSON user storage, password hashing (Phase 4)
│   │   └── current_user.py    # current_user_id()/current_user()/is_admin() session helpers
│   ├── agents/router.py       # tool routing + detect_tool() classification; threads user_id + model
│   └── api/
│       ├── routes.py          # /api/chat, /api/conversations*, /api/upload, /api/attachment,
│       │                       # /api/analytics/summary, /api/models — all user-scoped
│       ├── auth_routes.py     # /api/auth/signup, /login, /logout, /me, /change-password
│       └── admin_routes.py    # /api/admin/users, /api/admin/stats — is_admin gated
├── frontend/
│   ├── index.html
│   ├── css/style.css
│   └── js/app.js, particle-sphere.js, starfield.js
├── examples/
│   ├── conv_history.example.json   # sample output, not live data (legacy — see session_memory.py note)
│   └── chat.log.example            # sample output, not live data
├── data/                            # gitignored
│   ├── conversations/<user_id>/     # one subdirectory per user, one JSON file per conversation + _index.json
│   ├── embeddings/_attachments/     # one active-attachment JSON per user_id
│   ├── uploads/                     # uploaded documents/images
│   ├── users.json                   # user accounts (hashed passwords only)
│   └── analytics_events.json
├── .env.example
├── .gitignore
├── README.md
├── requirements.txt
├── run.py
└── gemini_retrieval.py              # legacy — superseded by app/, kept for reference
```

`gemini_retrieval.py` no longer runs anything — `run.py` is the real entry
point now. It's kept in the repo only as a reference for what the original
prototype looked like; delete it whenever that's no longer useful.

The section below is the original Phase 1 planning target, kept for history —
compare against the tree above to see what changed during actual
implementation (notably: `examples/`, `.env.example`, and `.gitignore` weren't
in the original plan, and `tests/` still doesn't exist).

## Original Phase 1 Planning Target

What actually existed in the repo before Phase 1 work began:

```text
Nimbus-AI/
├── docs/
│   ├── PRD.md
│   ├── Architecture.md
│   ├── Design.md
│   ├── Rules.md
│   ├── Phases.md
│   └── Memory.md
├── examples/
│   ├── conv_history.example.json   # sample output, not live data
│   └── chat.log.example            # sample output, not live data
├── .env.example
├── .gitignore
├── README.md
├── gemini_retrieval.py             # CLI entry point — all current logic lives here
└── requirements.txt
```

`gemini_retrieval.py` used to hold everything: Gemini calls, keyword-based
intent routing (crypto/weather/image/search/chit-chat), JSON conversation
memory, and TTS. That's now split across the `app/` structure shown above and
in the target structure below — `app/ai/` has the Gemini client, `app/agents/`
has the routing logic (still keyword-based — upgrading to real intent
handling is still open, see `Memory.md`), `app/memory/` has history
persistence, `app/tools/` has weather/search/crypto. Nothing was thrown away;
it was relocated and formalized.

## Target Folder Structure (Phase 1+)

```text
Nimbus-AI/
│
├── app/
│   ├── api/          # Flask routes / blueprints, request validation
│   ├── ai/           # Model provider clients, prompt templates, streaming
│   ├── agents/        # Orchestration: routing between direct answer / tool / RAG
│   ├── memory/        # Short-term (session) + long-term (persisted) memory
│   ├── tools/          # Web search, weather, file parsing, OCR, RAG retrieval
│   ├── analytics/      # Event logging, aggregation for dashboard
│   ├── auth/           # Login, sessions, admin (Phase 4)
│   ├── database/       # SQLAlchemy models, migrations
│   ├── services/       # Cross-cutting business logic used by multiple routes
│   ├── utils/           # Small stateless helpers
│   └── config/          # Env-based settings, model configs
│
├── frontend/
│   ├── assets/
│   │   ├── icons/
│   │   ├── avatar/       # Particle-sphere renderer assets/shaders, Lottie states
│   │   ├── animations/
│   │   └── sounds/
│   ├── css/
│   ├── js/
│   ├── components/
│   └── pages/
│
├── docs/
│   ├── PRD.md
│   ├── Architecture.md
│   ├── Design.md
│   ├── Rules.md
│   ├── Phases.md
│   └── Memory.md
│
├── data/
│   ├── chat_logs/
│   ├── uploads/
│   ├── embeddings/
│   └── cache/
│
├── examples/
│   ├── conv_history.example.json
│   └── chat.log.example
│
├── tests/
├── .env.example
├── .gitignore
├── requirements.txt
├── run.py
└── README.md
```

## Database Schema (initial draft)
- `users` — id, email, hashed_password, created_at (Phase 4)
- `conversations` — id, user_id (nullable pre-auth), title, model_used, created_at
- `messages` — id, conversation_id, role, content, sentiment, created_at
- `memory_entries` — id, user_id/conversation_id, summary, embedding_ref, created_at
- `analytics_events` — id, event_type, conversation_id, latency_ms, tool_used,
  created_at

## Integration Points
- **Gemini API** — primary LLM, streaming responses
- **Web search tool** — pluggable provider behind `app/tools/`
- **Weather API** — simple REST lookup tool
- **RAG pipeline** — file upload → parse (PDF/DOCX/TXT) → chunk → embed → store in
  `data/embeddings/` → retrieve on query

## Deployment
- Dockerfile + docker-compose for local parity
- CI-ready structure (lint + test on push)
- Target hosts: Render or Railway for the live demo