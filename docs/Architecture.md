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
Cindrix/
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
Cindrix/
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
Cindrix/
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

## Voice I/O

Both directions of voice run entirely client-side in `frontend/js/app.js`,
with no dedicated voice backend or added server dependency:

- **Input (STT):** two providers, switched by `STT_PROVIDER` (see
  `app/config/settings.py`):
  - `webspeech` (default): the browser's native `SpeechRecognition` (Web
    Speech API), entirely client-side, no key needed. Dev/fallback path,
    unchanged from Hackathon Phase 1.
  - `sarvam`: server-side, via `app/ai/stt.py` calling Sarvam's
    `/speech-to-text` REST endpoint (`saaras:v3`, Indic-language-focused —
    picked over ElevenLabs for that reason, since it matches the
    MSMARCO-XI corpus this app retrieves against). Required for hackathon
    compliance (Web Speech API doesn't qualify per the task brief) —
    used for the hackathon live link/demo video specifically, not a
    replacement of the dev path. The frontend records audio via
    `MediaRecorder` + a small Web Audio volume analyser for
    silence-based auto-stop (WebSpeech gets end-of-speech detection for
    free from the browser; raw audio recording doesn't, so it's built in
    `frontend/js/app.js`), then POSTs the clip to `/api/stt`.
    `SARVAM_API_KEY` never reaches the browser — only the backend holds
    it, per `Rules.md`. `/api/config` tells the frontend which provider
    is live so it wires up the right one at page load.
  Both providers funnel into the exact same `sendMessage(transcript,
  true)` call once a final transcript exists — the RAG routing, retry
  handling, and TTS output described below are identical regardless of
  which one produced the text.
- **Output (TTS):** the browser's native `speechSynthesis`
  (`SpeechSynthesisUtterance`), not a server-side library — a
  server-rendered-audio approach (e.g. the old CLI prototype's `pyttsx3`)
  doesn't produce audio in a deployed browser context on Render, and would
  add an audio-upload/-download round-trip before the RAG pipeline even
  starts. Doing STT/TTS client-side avoids that round-trip entirely,
  which matters for the streaming-response latency target in `PRD.md`.
  Microsoft's "Natural"/"Online" neural voices are preferred when
  available via `speechSynthesis.getVoices()` (Edge-only, 250+ voices,
  far more natural than default voices) — Chrome/Firefox/Safari fall back
  gracefully to whatever default voice they expose; Edge is never
  hard-required. `pyttsx3` stays in `requirements.txt`/the old CLI
  prototype for reference only — nothing in the current app routes
  through it.
- Sphere state (`listening` / `thinking` / `speaking`) is driven off this
  same flow — see `Design.md` for the state table and `Memory.md` for a
  logged fix to a bug where typed (non-voice) replies were briefly and
  incorrectly entering the `speaking` state during streaming.

## Retrieval, Vector Store & Guardrails (hackathon track)

Everything below lives under `app/rag/` plus small hooks in
`app/ai/embeddings.py`, `app/ai/retry.py`, and `app/agents/router.py`.
Added to satisfy the HHGoa hackathon's grading criteria — see
`docs/Memory.md`'s dated entry for the priority list this came from.

### Dataset

`ai4bharat/MSMARCO-XI` (`app/rag/dataset.py`) — the hackathon-mandated
corpus, not a sample. Verified directly against the live HuggingFace
dataset card while building this (dataset schemas/APIs go stale in
training data, so this was looked up fresh rather than assumed): 14
Indic-language configs, ~10.1M rows per language in the `train` split,
row shape `{query, query_id, query_type, target_lang, Eng_Query,
Eng_Answer, passages: {is_selected, English_passages,
Translated_passages}}`. Loaded via HuggingFace `datasets` with
`streaming=True` — never bulk-downloads the multi-GB file — and capped at
`RAG_INGEST_MAX_ROWS` (default 2000). **Disclosed scope decision, not a
hidden shortcut:** ingesting all 10M+ rows per language isn't a realistic
hackathon-timeline operation (embedding cost and time alone rule it out);
the cap uses real, unmodified rows from the real dataset, just a bounded
number of them. Raise `RAG_INGEST_MAX_ROWS` for a larger index if time/
budget allows before submission.

`datasets` is soft-imported — if it's not installed, `load_msmarco_xi()`
falls back to a small local fixture built from the dataset card's own
documented example row, with a loud warning logged every time (never
silently mistaken for the real dataset). This project was built in a
sandboxed session with no network access to `pip install datasets`, so
that fallback is exercised by necessity — install it before trusting the
knowledge base for the real submission.

### Chunking strategies (`app/rag/chunking.py`)

Three, because different content calls for different chunking:

- **`fixed_size_chunks`** — character-window with overlap (the same
  approach `app/tools/documents.py`'s `chunk_text` already used for
  user-uploaded PDFs/DOCX/TXT). Good default when a text's structure is
  unknown or irregular.
- **`semantic_chunks`** — packs whole sentences into a chunk up to a
  target size, never cutting a sentence in half. Sentence boundary
  detection includes `।` (Devanagari danda) alongside `.!?`, since this
  runs over Hindi/Indic text, not just English. A full sentence tokenizer
  (spaCy/NLTK) would be a new major dependency per `Rules.md` for a
  problem a regex handles well enough here.
- **`metadata_aware_chunks`** — the one actually used for MSMARCO-XI
  ingestion. Each dataset row already arrives pre-segmented into passages
  (`passages.Translated_passages`); this strategy treats each given
  passage as one chunk rather than re-splitting it, and attaches the
  metadata the dataset already provides (`is_selected` ground-truth
  relevance, `query_id`, language, passage index). Re-chunking an
  already-short, already-coherent MS MARCO passage would be as likely to
  cut it awkwardly as to improve it, and would sever the direct link to
  `is_selected` that makes the dataset's own relevance labels usable
  later (e.g. for retrieval-quality validation against ground truth,
  not built yet but the metadata is there if it's worth doing).

### Vector store (`app/rag/vector_store.py`)

Replaces the old brute-force in-memory cosine loop that used to live
directly in `app/ai/embeddings.py`'s `top_k_chunks()`. Backed by **FAISS**
(`IndexFlatIP` for small collections — exact, just no longer a hand-
written Python loop; `IndexIVFFlat` once a collection passes ~10k
vectors, a genuine approximate-nearest-neighbor index) — picked over a
hosted/server vector DB (Pinecone, Weaviate, etc.) because it needs no
running service or network dependency, fitting this project's existing
no-external-infra pattern (JSON files, SQLite-when-needed), and over
Chroma because FAISS is the leaner dependency for a pure similarity-
search need with no extra features this project uses. Vectors are
L2-normalized on insert so inner product doubles as cosine similarity —
one index type serves both the small per-document case and the large
corpus case.

`faiss` is soft-imported too (not installed in the sandboxed session this
was built in) — falls back to an exact numpy-based search, loudly logged
every time a store is built without it, so it's never mistaken for the
real thing in a benchmark or demo. Persists to disk via `.save()`/
`.load()` (JSON for chunks/metadata + a native FAISS index file, or a
pickle of the raw vectors in fallback mode).

`top_k_chunks()` in `embeddings.py` now builds a small `VectorStore` per
call instead of looping by hand — same behavior at the small scale it
actually runs at (a single upload's chunks), but going through the same
real abstraction the much larger MSMARCO-XI index uses, so there's one
implementation to keep correct, not two.

### Router wiring (`app/agents/router.py`)

A new `knowledge_base_rag` path sits between the existing attachment-RAG
path and the final plain-conversational fallback: general queries (no
tool intent, no active attachment) that aren't obvious chit-chat/
greetings are checked against the persisted MSMARCO-XI index before
falling through. **If no index has been built yet** (`python -m
app.rag.ingest` hasn't been run), `get_kb_store()` returns `None` and
every general query behaves exactly as it did before this priority —
this only activates once a knowledge base actually exists on disk.

**Product-behavior tradeoff worth flagging explicitly** (see `Rules.md`:
"ask before an architectural decision not already specified"): once an
index IS built, a general query that doesn't ground well against it gets
an honest decline (see Guardrails below) rather than falling back to
Cindrix's normal general-knowledge conversational ability. That's the
right behavior for hackathon grading (a "Voice-Enabled RAG Model" should
visibly refuse to answer outside its indexed corpus, not quietly
fall back to being a generic chatbot while still implying it's grounded)
but it does mean Cindrix becomes less generally chatty once the
hackathon's knowledge base is live — worth a deliberate decision before
deploying the same build for the Amdocs internship demo, where broad
conversational ability was the original goal. Easiest lever if that
tradeoff needs to go the other way for a given deployment: don't run
`ingest.py` (or point `RAG_DATASET_LANGUAGE` at an unbuilt
index), and the app reverts to pre-hackathon behavior automatically.

### Guardrails (`app/rag/guardrails.py`)

Three checks, deliberately heuristic/keyword-based rather than a second
LLM call per guardrail check — the <200ms latency target (see below)
doesn't leave room for an extra model round-trip just to gate another
one. A real moderation API or LLM-based check would be a reasonable
upgrade later; that's a new external dependency/cost decision, which
`Rules.md` says to flag rather than add unprompted, so it isn't built.

1. `is_unsafe()` — blocks clearly unsafe input (self-harm, weapons
   synthesis, CSAM, unauthorized-access instructions) before it reaches
   retrieval or generation at all. Pattern-matches full phrasings, not
   single trigger words, to keep false positives low (a genuine question
   like "how do bomb disposal robots work" doesn't trip it — verified by
   test).
2. `is_offtopic_for_kb()` — screens out queries not worth attempting
   knowledge-base retrieval for (tool-intent messages, greetings, near-
   empty input), so those still get normal conversational handling
   instead of a forced "not grounded" decline for something that was
   never meant to be a factual lookup.
3. `check_grounding()` — after retrieval, whether the top result clears
   `RAG_MIN_RELEVANCE` (default 0.55 cosine similarity). Below it, the
   router yields `guardrails.DECLINE_MESSAGE` and **never calls Gemini at
   all** for that turn (verified by test — the generation mock is
   asserted not-called) — this is a real hard stop, not just a prompt
   instruction hoping the model declines on its own.

### Retry & structured error recovery (`app/ai/retry.py`)

Wraps the Gemini call in both RAG-serving paths (`document_rag` and the
new `knowledge_base_rag`) — not a blanket change to every call site
(weather, plain chat, tool search), since this was scoped to "the RAG
path specifically, since that's what's graded."

Built directly against a real production failure: a transient `503
UNAVAILABLE` from Gemini surfaced to a user as raw `(Gemini error: 503
UNAVAILABLE. {'error': {'code': 503, ...}})` text in the chat. Since
`gemini_client.py`'s `stream_gemini()` catches its own exceptions and
*yields* an error string rather than raising, `stream_with_retry()`
detects "was this transient" by pattern-matching the first yielded chunk
(503/429/timeout-shaped), not by catching an exception. Retries (up to 2,
exponential backoff) only happen before any real content has reached the
caller — once a chunk of the actual answer is out, retrying would
duplicate it, so a later failure just closes the stream gracefully with a
short trailer note instead, per `Rules.md`'s "streaming responses must
gracefully close on error, not hang the UI."

### Latency harness (`app/rag/benchmark.py`)

Instruments three live per-query stages — embed query, vector retrieval,
generation — across a small test-query set, reporting P50/P70/P100 per
stage and end-to-end. Target: under 200ms end-to-end (P70).

**Deliberately excludes ingest-time chunking/embedding from the per-query
number** — chunking the corpus happens once at ingest (`app/rag/
ingest.py`), not on every live query, so counting it per-query would
mischaracterize what a real user's request actually costs. That's
disclosed here rather than silently interpreted, since a literal reading
of "instrument chunking + retrieval + generation" could otherwise suggest
re-chunking per query, which would be straightforwardly bad engineering.

Runs honestly rather than fabricating numbers: if `GOOGLE_API_KEY` isn't
set, `embed_query`/`stream_gemini` both short-circuit without a real
network call (existing behavior, unchanged), so the report is marked
`"is_self_test": true` with an explicit note, and `meets_target` is
forced `false` — it never claims to hit the target using numbers that
didn't involve a real model call. This project was built in a sandboxed
session with no `GOOGLE_API_KEY`/network access, so the only numbers
produced so far are self-test ones proving the harness mechanics work,
not real production latency — **run `python -m app.rag.benchmark` with a
real key before trusting or reporting any actual P50/P70/P100 for the
submission.**

## Deployment
- Dockerfile + docker-compose for local parity
- CI-ready structure (lint + test on push)
- Target hosts: Render or Railway for the live demo