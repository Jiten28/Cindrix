# Capabilities & Delivery History

This document describes what Cindrix delivers, organized by capability area,
with the design decisions behind each. It is a record of the product as built,
not a task tracker.

---

## Core chat experience

A streaming conversational assistant with short-term memory and an animated
visual identity.

- **Backend:** a Flask application (`app/api`, `app/config`, `run.py`) with
  token-by-token streaming responses. Generation is built on the `google-genai`
  SDK for Gemini and the Groq SDK — `google-genai`, not the older
  `google-generativeai` package.
- **Memory:** session-scoped conversation memory stored as JSON files rather
  than SQLite. The storage interface is kept stable so the backing store can be
  swapped later without touching callers.
- **Identity:** a particle sphere (not a face) whose shape and motion track the
  conversation lifecycle — idle, listening, thinking, and speaking states wired
  to the stream. See [`Design.md`](Design.md) for the rationale behind the
  particle-sphere identity.
- **Interface:** a composer, streaming message list, and a left sidebar with new
  chat and per-conversation history. Dark and light themes, and a mouse-reactive
  sphere.
- **Voice:** a turn-based voice chat loop — speech-to-text in, text-to-speech
  out — not just single-shot dictation.

## Tools and understanding

Cindrix can look things up live and reason over uploaded content.

- **Weather:** keyless Open-Meteo lookup (geocoding + forecast, WMO code to
  text), with a Gemini estimate fallback for places it cannot geocode.
- **Crypto:** live price lookup via CoinGecko.
- **Search:** general web search (through Gemini's Google Search grounding) and
  image search (via Tavily).
- **Documents:** PDF, TXT, and DOCX upload with text extraction
  (`app/tools/documents.py`), chunked and embedded for retrieval so the user can
  ask questions about a specific uploaded file. Uploads made before a
  conversation exists attach to it once it is created.
- **Vision:** image upload with Gemini vision understanding.

Tool intent is classified before generation (`app/agents/router.py`) so the
analytics label matches whatever actually answered the turn.

## Knowledge-base RAG

A retrieval pipeline over the ai4bharat/MSMARCO-XI dataset (Hindi shard).

- **Chunking:** four strategies rather than one naive split — fixed-size with
  overlap, semantic sentence-packing, metadata-aware passage units, and a hybrid
  router that indexes short passages whole and sub-splits only the long tail.
- **Vector store:** FAISS `IndexFlatIP` over L2-normalized vectors (inner
  product equals cosine), with a numpy exact-search fallback. Embeddings are
  Gemini `gemini-embedding-001` (3072-dim), asymmetric between document and
  query task types.
- **Grounding decision:** a calibrated three-band guardrail — answer strictly
  from retrieved excerpts, decline when related material scores below a
  confident match, or fall through to a conversational answer when the corpus
  is not about the question at all.
- **Generation:** Groq (`openai/gpt-oss-120b`) primary with Gemini fallback,
  through a shared retry/fallback layer.
- **Latency:** a benchmark harness (`app/rag/benchmark.py`) reports per-stage
  P50/P70/P100 timings. Numbers and methodology are in [`Testing.md`](Testing.md).

## Insight and analytics

Usage is logged and made visible.

- **Event logging:** every chat turn records the tool used, latency, and message
  length (`app/analytics/events.py`).
- **Dashboard:** a sidebar modal showing total messages, average latency, a
  tool-usage breakdown, and messages-per-day — rendered with plain elements
  rather than a charting library, consistent with the rest of the frontend.
- **History:** full per-conversation storage (`app/memory/conversation_store.py`,
  one JSON file per conversation) replaced an earlier single shared history
  file. The sidebar list is real; clicking an entry loads that conversation.
  The earlier `session_memory.py` is superseded by this and kept only for
  reference.
- **Export:** any conversation exports to Markdown or JSON via
  `/api/conversations/<id>/export`.

## Accounts and multi-user

- **Authentication:** signup, login, and sessions via Flask's signed-cookie
  session — the simplest fit for a same-origin single-page app. Browsing without
  an account still works; everything falls into a shared `guest` bucket.
- **Isolation:** conversations and attachments are stored per user, so accounts
  cannot see each other's data.
- **Admin panel:** a user list with per-user conversation and message counts,
  gated by an `is_admin` flag. The first account created is auto-flagged admin;
  additional admins can be named by email in configuration.
- **Model selector:** a UI backed by a real provider abstraction. Each model is
  tagged with its provider (Groq `openai/gpt-oss-120b` default, plus three
  Gemini variants), and selecting one changes which provider is primary for that
  turn — the other becomes the fallback — end-to-end through the retry layer. A
  Gemini override is validated against a Gemini-only allow-list before it can
  reach the API, so a stray or Groq id can never be sent as a Gemini model name.
- **Account pages:** settings (display name, change password) and profile
  (account info, join date, admin badge).

## Deployment and quality

- **Containerization:** a `Dockerfile` (gunicorn, not the Flask dev server),
  `docker-compose.yml` for local parity with a volume-mounted `data/`, and a
  `.dockerignore`.
- **Hosting:** a Render blueprint (`render.yaml`) provides the live deployment.
  The read-only vector index ships in the image (outside `data/`) so a mounted
  runtime volume cannot shadow it.
- **CI:** a GitHub Actions workflow runs a compile check, the pytest suite, and
  a frontend JS syntax check on every push and pull request.
- **Tests:** an automated pytest suite (48 tests) covering the health endpoint,
  frontend serving, model listing, and chat input validation; all four chunking
  strategies; vector-store retrieval and save/load round-tripping; the dataset
  shard loader; every guardrail band; the retry and provider-fallback chain in
  both streaming and non-streaming form; provider routing by model id; and
  weather detection, city extraction, and the Open-Meteo response path.

## Scope boundaries

Deliberately out of scope: OCR for scanned documents, an offline/plugin mode,
smart recommendations, a native mobile app, and full-text search across past
conversations (history browsing ships; search across it does not).
