# Cindrix

A voice-enabled RAG assistant with a particle-sphere visual identity.

**Repo:** https://github.com/Jiten28/Cindrix
**Live demo:** https://cindrix-ai.onrender.com/

---

## Pipeline

Voice input → Sarvam speech-to-text → chunking + FAISS vector retrieval
over the ai4bharat/MSMARCO-XI dataset → Groq-primary / Gemini-fallback
generation → guardrailed, grounded answer → spoken back via the browser's
Web Speech API.

## How it works

- **Speech-to-text:** Sarvam (`saaras:v3`), selected automatically whenever
  `SARVAM_API_KEY` is set and swappable via `STT_PROVIDER`. The browser's
  native Web Speech API is the keyless fallback so a fresh clone has working
  voice input with no account.
- **Chunking:** four strategies rather than a single naive split —
  fixed-size with overlap, semantic sentence-packing, metadata-aware passage
  units, and a hybrid router that indexes short passages whole and sub-splits
  only long ones (`app/rag/chunking.py`).
- **Retrieval:** FAISS-backed vector store (`IndexFlatIP` over L2-normalized
  vectors, so inner product is cosine), with a numpy exact-search fallback.
  Embeddings are Gemini `gemini-embedding-001` (3072-dim), asymmetric between
  document and query.
- **Generation:** Groq (`openai/gpt-oss-120b`, primary) with automatic
  fallback to Gemini if Groq's retry budget is exhausted, and a clean
  user-facing error if both fail (`app/ai/retry.py`).
- **Guardrails:** unsafe-input blocking, off-topic screening, and a
  calibrated three-band grounding decision — the system answers strictly from
  retrieved context, declines when the corpus is related but no match is
  confident, or falls through to a conversational answer when the corpus
  simply isn't about the question. It declines rather than guess.
- **Latency:** `python -m app.rag.benchmark` reports real P50/P70/P100
  timings per pipeline stage. The vector search itself is sub-millisecond
  (P70 ~0.8 ms) — three orders of magnitude under the 200 ms retrieval
  target. The measurable cost is the query-embedding network call (~0.48 s
  P70) and answer generation (~1.8 s P70), so end-to-end latency is
  generation-bound, not retrieval-bound. Full per-stage table in
  [`docs/Testing.md`](docs/Testing.md).
- **Harness:** per-provider retry with exponential backoff on transient
  failures, provider fallback, retry-budget exhaustion handling, and graceful
  mid-stream close around the generation path.

## Features

- Conversational memory across a session
- Live weather lookup (Open-Meteo — keyless, no signup; Gemini estimate
  fallback for places it can't geocode)
- Live crypto price lookup (CoinGecko)
- Web and image search
- Voice input and output, with regenerate and per-conversation history
- User auth, per-user history, admin panel
- Analytics dashboard (message counts, tool usage, average latency)

## Identity

Cindrix's visual presence is a sphere made of individual particles
(220-point Fibonacci lattice) that changes shape and motion by state:

| State     | Behavior                                                          |
| --------- | ------------------------------------------------------------------ |
| Idle      | Compressed sphere, gentle breathing pulse                         |
| Listening | Particles wander outward and back individually                    |
| Thinking  | Sphere rotates faster — the rotation itself reads as "processing" |
| Speaking  | A ripple wave travels around the sphere in sync with audio        |

Full spec in [`docs/Design.md`](docs/Design.md).

## Tech stack

**Backend:** Python, Flask, Gemini API, Groq API, Sarvam API, FAISS
**Frontend:** HTML5, CSS3, vanilla JS — particle-sphere and starfield
canvas rendering
**Storage:** JSON-file-based (conversations, users, analytics)

## Project docs

- [`docs/PRD.md`](docs/PRD.md) — product goals and scope
- [`docs/Architecture.md`](docs/Architecture.md) — tech stack, data flow, RAG pipeline design
- [`docs/Rules.md`](docs/Rules.md) — coding boundaries and conventions
- [`docs/Phases.md`](docs/Phases.md) — capability overview and delivery history
- [`docs/Design.md`](docs/Design.md) — visual identity, colors, animation spec
- [`docs/Memory.md`](docs/Memory.md) — technical decisions and project history
- [`docs/Testing.md`](docs/Testing.md) — test coverage and verified latency numbers

## Setup

```bash
git clone https://github.com/Jiten28/Cindrix.git
cd Cindrix
pip install -r requirements.txt
cp .env.example .env
# then edit .env with your real keys — see .env.example for what each does
```

Required keys: `GOOGLE_API_KEY` (Gemini), `GROQ_API_KEY`, `SARVAM_API_KEY`
(free tier available for all three — see `.env.example` for signup notes).

Ingest the knowledge base once before running the RAG path:

```bash
python -m app.rag.ingest
```

> **Free-tier note:** Gemini's free embedding tier is rate-limited
> (~100 requests/min, ~1000/day), each text in a batch counting
> individually. The default ingest (`RAG_INGEST_MAX_ROWS=75` → ~868 passage
> chunks) fits within the daily cap in a single run. The run logs any chunks
> it couldn't embed and saves an honest partial index rather than silently
> dropping them.

Run:

```bash
python run.py
```
