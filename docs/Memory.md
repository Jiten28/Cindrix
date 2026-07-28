# Memory.md — Living Development Log

> Update this file at the end of every milestone/session. Any AI assistant
> picking up this project should read this file FIRST, before touching code.
> Purpose: avoid re-reading the whole codebase or re-deriving decisions already
> made.

Last updated: end of Phase 1 / start of Phase 2

---

## Current Status

Phase 1 is complete and working end-to-end: real backend, real frontend, real
Gemini responses, tested locally. Starting Phase 2 (file upload, RAG, image
understanding).

## Completed Work

**Backend** — `gemini_retrieval.py` (the original CLI prototype) has been fully
split into `app/`:

- `app/config/settings.py` — env config
- `app/ai/gemini_client.py` — Gemini calls, **rebuilt on the `google-genai` SDK**
  (see Known Issues / Architecture Decisions — the original `google-generativeai`
  package and `gemini-1.5-flash` model are both dead)
- `app/tools/weather.py`, `crypto.py`, `search.py` — ported directly, unchanged logic
- `app/memory/session_memory.py` — JSON-based history (`data/conv_history.json`)
- `app/agents/router.py` — keyword-based routing (weather/crypto/search/general),
  still simple regex matching — upgrading this to real intent classification is
  still an open task, not yet started
- `app/api/routes.py` — `POST /api/chat` (streaming), `GET /api/history`
- `run.py` — entry point, replaces `python gemini_retrieval.py`

**Frontend** — `frontend/` built from scratch:

- Particle-sphere identity (`js/particle-sphere.js`) — Fibonacci-lattice sphere,
  ~220 points, 4 states (idle/listening/thinking/speaking) exactly per `Design.md`
- Starfield background (`js/starfield.js`) — sparse, dim, respects
  `prefers-reduced-motion`
- Landing view (centered search + suggestion chips) that transitions into a
  chat view on first message — matches the mockup layout
- `app.js` wires: streaming fetch to `/api/chat`, markdown rendering (bold,
  inline code, code fences — hand-rolled, not a library), a full turn-based
  **voice chat loop** (mic -> send -> spoken reply -> auto-relisten -> repeat,
  browser `SpeechRecognition` + `speechSynthesis`, no backend voice work
  needed), and a voice picker for available system voices
- Flask now serves the frontend directly (`app/__init__.py` — `static_folder`
  points at `frontend/`, `/` returns `index.html`)

**Tested locally**: real Gemini replies confirmed working (curl + browser),
weather/crypto/search tool routing confirmed, voice loop confirmed working in
Chrome (not supported in Firefox/Safari — browser API limitation, not a bug).

## In Progress

- Phase 2: file upload + RAG, image understanding (starting now — see below)

## Pending / Next Up

- Phase 2 remaining after this session: OCR for scanned docs (may be covered
  by Gemini's native multimodal reading instead of a separate OCR library —
  decide once image upload is in and tested)
- Phase 3: analytics dashboard, conversation export, full history browsing
- Real intent classification to replace the current regex router (flagged
  above, not scheduled to a specific phase yet)
- Per-session/per-user history isolation — right now `/api/chat` reads and
  writes one shared `conv_history.json` for everyone, so two browser tabs (or
  two users) see each other's conversation. Fine for solo local testing, needs
  fixing before Phase 4 (auth) makes this a real multi-user problem.

## Architecture Decisions Log

| Date    | Decision                                                                                     | Reasoning                                                                                                                                                                                                                        |
| ------- | -------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| —       | Backend = Flask (FastAPI as fallback)                                                        | Simpler for a solo intern project; can swap later if async/streaming needs grow                                                                                                                                                  |
| —       | No CSS framework                                                                             | Custom design identity per `Design.md`; avoid generic Bootstrap look                                                                                                                                                             |
| —       | SQLite path kept open, JSON used for Phase 1                                                 | `session_memory.py` is JSON now; interface kept stable so swapping storage later doesn't touch `app/agents/router.py`                                                                                                            |
| Phase 1 | Project renamed AURA AI -> **NIMBUS**                                                        | Chosen name; docs/folder/package names updated throughout                                                                                                                                                                        |
| Phase 1 | Mascot redesigned from an abstract face -> **particle sphere**                               | Avoids any resemblance to Baymax; Fibonacci-lattice sphere is fully original and ties into the "Nimbus" name (cloud/halo)                                                                                                        |
| Phase 1 | `google-generativeai` SDK + `gemini-1.5-flash` -> `google-genai` SDK + `gemini-flash-latest` | Google fully shut down the old SDK and the 1.5 model line (hit a live 404 confirming this). `gemini-flash-latest` is Google's auto-updating alias — chosen specifically so the next model retirement doesn't break the app again |
| Phase 1 | Voice output tied to input method, not a manual toggle                                       | Typed messages never get spoken; only replies to voice-chat-loop turns are spoken. Simpler mental model than a global on/off switch, and it's what was actually asked for                                                        |

## Known Issues

- Shared single `conv_history.json` across all sessions (see Pending, above)
- Router is still keyword/regex-based, not true intent recognition (PRD.md
  commits to this eventually — not urgent while it's a single-user local app)
- No automated tests yet (`tests/` folder from `Architecture.md`'s target
  structure doesn't exist yet)

## Notes for the Next AI Session

- Read `PRD.md` -> `Architecture.md` -> `Rules.md` -> current phase in `Phases.md`
  -> `Design.md`, in that order, before writing code.
- Do not skip ahead of the current phase.
- Update this file before ending the session, even if the milestone isn't fully
  done — note what's mid-flight so the next session can resume cleanly.
