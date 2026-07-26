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

## Project structure

```
Nimbus-AI/
├── docs/                          # planning docs (see below)
├── examples/
│   ├── conv_history.example.json  # sample output — not live data
│   └── chat.log.example           # sample output — not live data
├── .env.example
├── .gitignore
├── README.md
├── gemini_retrieval.py            # current CLI prototype entry point
└── requirements.txt
```

Running the app locally creates its own `conv_history.json` and `chat.log` at
the repo root — these are gitignored and stay on your machine. The files in
`examples/` are static reference copies committed to the repo so anyone
browsing it can see what output looks like without running anything.

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
cd Nimbus-AI
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in your keys:

```dotenv
# Google API Key for both Gemini + Custom Search
GOOGLE_API_KEY=

# Google Custom Search Engine ID (from https://programmablesearchengine.google.com/)
GOOGLE_CSE_ID=

# Optional: store history file path
HISTORY_FILE=conv_history.json

GOOGLE_API_LOCATION=us
```

```bash
cp .env.example .env
# then edit .env with your real keys
```

Run (current CLI prototype — `run.py` arrives in Phase 1 once the Flask app exists):

```bash
python gemini_retrieval.py
```

## Status

Actively in development. See `docs/Memory.md` for the current milestone and
what's in progress.
