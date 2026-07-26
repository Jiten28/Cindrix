# Phases.md — Build Roadmap

Each phase should end in a working, demoable state. Don't start the next phase
until the current one's acceptance criteria are met and `Memory.md` is updated.

---

## Phase 1 — Core Chat Experience

**Goal:** A working chatbot with memory, Gemini responses, voice, and the
animated face — the minimum "this feels alive" demo.

Tasks:

- Flask app skeleton (`app/api`, `app/config`, `run.py`)
- Gemini API integration in `app/ai/` with streaming responses
- Session-based short-term memory in `app/memory/`
- Basic SQLite schema: `conversations`, `messages`
- Chat UI: composer, message list, streaming render
- Animated face: idle / thinking / talking / blink states wired to stream
  lifecycle
- Voice input (speech-to-text) and voice output (text-to-speech), basic version
- Left sidebar: new chat, chat history list

Acceptance criteria:

- User can hold a multi-turn conversation that remembers earlier context
- Face visibly changes state between idle → thinking → talking
- Voice input transcribes correctly and voice output speaks the reply

---

## Phase 2 — Understanding & Tools

**Goal:** NIMBUS can see, read, and look things up.

Tasks:

- Image upload + vision understanding
- File upload: PDF, TXT, DOCX parsing → RAG pipeline (chunk + embed + retrieve)
- OCR for scanned documents/images
- Web search tool integration
- Weather lookup tool
- Face "searching" state wired to tool-use events

Acceptance criteria:

- User can upload a PDF and ask questions about its content
- User can ask a live question ("what's the weather in X") and get a real answer
- Tool calls are visible in the right-side info panel (active tools)

---

## Phase 3 — Insight Layer

**Goal:** Make usage visible and exportable.

Tasks:

- Analytics event logging (`app/analytics/`)
- Analytics dashboard page: usage trends, response effectiveness, latency
- Full conversation history browsing + search
- Conversation export (e.g. Markdown/JSON download)

Acceptance criteria:

- Dashboard shows real data from actual chat sessions
- User can export any past conversation

---

## Phase 4 — Accounts & Scale-readiness

**Goal:** Multi-user ready, model-flexible.

Tasks:

- Authentication (signup/login/session)
- Per-user conversation history and memory isolation
- Admin panel (basic: view users, usage stats)
- Model selector UI wired to a real provider abstraction in `app/ai/` (even if
  only Gemini is live, the switch should work end-to-end)
- Personal long-term memory (persisted across sessions per user)

Acceptance criteria:

- Two different accounts have fully isolated chat history and memory
- Switching the model selector changes which provider handles the request

---

## Phase 5 — Stretch Goals

**Goal:** Portfolio polish, only after 1–4 are solid.

Tasks:

- Docker + docker-compose, CI-ready structure
- Deployment to Render or Railway
- Offline mode / plugin architecture (exploratory)
- Smart recommendations (proactive suggestions based on conversation history)
- Mobile app (only if time remains — lowest priority)

Acceptance criteria:

- App runs via `docker compose up` with no manual setup
- Live deployed demo URL works end-to-end
