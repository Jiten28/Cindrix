# Architecture.md

## Tech Stack

### Backend

- Python 3.11+
- Flask (FastAPI acceptable as a drop-in swap if async/streaming needs outgrow Flask)
- Gemini API (primary model provider; abstracted behind a provider interface so
  more models can be added later)
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

## Current State (Prototype)

What actually exists in the repo right now, before Phase 1 work begins:

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

`gemini_retrieval.py` currently holds everything: Gemini calls, keyword-based
intent routing (crypto/weather/image/search/chit-chat), JSON conversation
memory, and TTS. Phase 1 splits this single file apart into the `app/`
structure below — `app/ai/` gets the Gemini client, `app/agents/` gets the
routing logic (upgraded from keyword-matching to real intent handling),
`app/memory/` gets the history persistence, `app/tools/` gets weather/search/
crypto. Nothing here is thrown away; it's relocated and formalized.

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
