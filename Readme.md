# Cindrix

A voice-enabled RAG assistant with a particle-sphere visual identity.

**Repo:** https://github.com/Jiten28/Cindrix
**Live demo:** https://cindrix-ai.onrender.com/

---

## Pipeline

Voice input → Sarvam speech-to-text → chunking + FAISS vector retrieval
over the ai4bharat/MSMARCO-XI dataset → Groq-primary/Gemini-fallback
generation → guardrailed, grounded answer → spoken back via the browser's
Web Speech API.

## Hackathon compliance

- **STT:** Sarvam (`saaras:v3`), swappable via `STT_PROVIDER` config —
  the browser's native Web Speech API remains available as a dev fallback
- **Chunking:** three real strategies — fixed-size with overlap, semantic/
  sentence-packed, and metadata-aware — not a single naive approach
- **Retrieval:** FAISS-backed vector store, numpy exact-search fallback
- **Generation:** Groq (primary, `openai/gpt-oss-120b`) with automatic
  fallback to Gemini if Groq's retry budget is exhausted; a clean
  user-facing error if both fail — see `app/ai/retry.py`
- **Guardrails:** off-topic screening, unsafe-input blocking, and a
  grounding threshold — the system declines to answer rather than
  guess when retrieved context doesn't support a claim
- **Latency:** `python -m app.rag.benchmark` reports real P50/P70/P100
  timing per pipeline stage (embed → retrieve → generate). Measured
  against the real index (2026-08-21): FAISS retrieval ~1 ms (P70
  1.16 ms), Groq generation ~1 s (P70 1.08 s) — so end-to-end is
  generation-bound. Retrieval sits three orders of magnitude under the
  200 ms target; a full generated answer costs ~1 s of model time that no
  index choice can shrink. Full table and caveats in `docs/Testing.md`
  §17b
- **Harness:** retries with transient-failure recovery, exhaustion
  handling, and graceful mid-stream close around the generation path

## What's already working

- Conversational memory across a session
- Live weather lookup (Open-Meteo — keyless, no signup; Gemini estimate
  fallback for places it can't geocode)
- Live crypto price lookup (CoinGecko)
- Web and image search
- Voice input/output (Sarvam for hackathon compliance, browser Web
  Speech API as dev fallback)
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

Full spec in `docs/Design.md`.

## Tech stack

**Backend:** Python, Flask, Gemini API, Groq API, Sarvam API, FAISS
**Frontend:** HTML5, CSS3, vanilla JS — particle-sphere and starfield
canvas rendering
**Storage:** JSON-file-based (conversations, users, analytics)

## Project docs

Developed with a six-file planning structure:

- [`docs/PRD.md`](docs/PRD.md) — what's being built and why
- [`docs/Architecture.md`](docs/Architecture.md) — tech stack, data flow, RAG pipeline design
- [`docs/Rules.md`](docs/Rules.md) — coding boundaries and conventions
- [`docs/Phases.md`](docs/Phases.md) — the build roadmap
- [`docs/Design.md`](docs/Design.md) — visual identity, colors, animation spec
- [`docs/Memory.md`](docs/Memory.md) — living development log
- [`docs/Testing.md`](docs/Testing.md) — test coverage and real-environment verification status

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

> **Free-tier note:** Gemini's free embedding tier has a hard cap of
> **1000 requests/day** (plus a ~100/min limit), each text in a batch
> counting individually. The default ingest (`RAG_INGEST_MAX_ROWS=100` →
> ~1000 passage chunks) sits right at that daily ceiling — effectively one
> full ingest per day per key. The run logs any chunks it couldn't embed
> and saves an honest partial index rather than silently dropping them.

Run:

```bash
python run.py
```
