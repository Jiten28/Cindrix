# Nimbus AI

A calm, ever-present AI companion — conversational chatbot with persistent
memory, tool use, and a particle-sphere visual identity, built as a final-month
Amdocs internship project.

This repo started as a CLI Gemini assistant (conversation memory, weather,
crypto price, web/image search, text-to-speech). It's being rebuilt into a full
product: modular backend, streaming chat UI, RAG over uploaded documents, voice
I/O, and an animated particle-sphere presence instead of a static chat window.

---

## What's already working

Carried over from the original prototype, now being folded into the new
architecture:

- Conversational memory across a session (persisted to JSON, moving to SQLite)
- Live weather lookup (OpenWeather, with a Gemini fallback when no key is set)
- Live crypto price lookup (CoinGecko)
- Web and image search (Google Custom Search API)
- Text-to-speech responses (`pyttsx3`)
- Conversation logging

## What's being added

See `docs/Phases.md` for the full roadmap. Short version:

- **Phase 1** — Flask backend, streaming Gemini responses, session memory,
  particle-sphere UI, voice input/output
- **Phase 2** — Image understanding, PDF/DOCX upload with RAG, OCR, tool-calling
  architecture for search/weather
- **Phase 3** — Analytics dashboard, conversation export, full chat history
- **Phase 4** — Authentication, per-user memory, model selector, admin panel
- **Phase 5** — Docker, CI, live deployment, stretch goals

## Identity

Nimbus's visual presence is a sphere made of individual particles (Fibonacci
lattice, no clumping) that changes shape and motion by state:

| State     | Behavior                                                          |
| --------- | ----------------------------------------------------------------- |
| Idle      | Compressed sphere, gentle breathing pulse                         |
| Listening | Particles wander outward and back individually                    |
| Thinking  | Sphere rotates faster — the rotation itself reads as "processing" |
| Speaking  | A ripple wave travels around the sphere in sync with audio        |

Full spec in `docs/Design.md`.

## Project docs

This repo is developed with a six-file planning structure so any AI coding
assistant (or future you) can pick up context instantly:

- [`docs/PRD.md`](docs/PRD.md) — what's being built and why
- [`docs/Architecture.md`](docs/Architecture.md) — tech stack, folder structure, data flow
- [`docs/Rules.md`](docs/Rules.md) — coding boundaries and conventions
- [`docs/Phases.md`](docs/Phases.md) — the build roadmap
- [`docs/Design.md`](docs/Design.md) — visual identity, colors, animation spec
- [`docs/Memory.md`](docs/Memory.md) — living development log, updated every milestone

## Tech stack

**Backend:** Python, Flask, Gemini API, SQLite (dev) → PostgreSQL (future)
**Frontend:** HTML5, CSS3, vanilla JS, GSAP, Three.js (particle sphere), Lottie
**Storage:** SQLite, with an embeddings store for RAG

## Setup

```bash
git clone https://github.com/Jiten28/Nimbus-AI.git
cd nimbus-ai
pip install -r requirements.txt
```

Create a `.env` file:

```
GOOGLE_API_KEY=your_google_api_key_here
GOOGLE_CSE_ID=your_custom_search_engine_id_here
OPENWEATHER_API_KEY=your_openweather_api_key_here
HISTORY_FILE=conv_history.json
```

Run:

```bash
python run.py
```

## Status

Actively in development. See `docs/Memory.md` for the current milestone and
what's in progress.
