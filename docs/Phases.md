# Phases.md — Build Roadmap

Each phase should end in a working, demoable state. Don't start the next phase
until the current one's acceptance criteria are met and `Memory.md` is updated.

---

## Phase 1 — Core Chat Experience ✅ COMPLETE

**Goal:** A working chatbot with memory, Gemini responses, voice, and the
animated face — the minimum "this feels alive" demo.

Tasks:

- [x] Flask app skeleton (`app/api`, `app/config`, `run.py`)
- [x] Gemini API integration in `app/ai/` with streaming responses (built on
      `google-genai`, not the originally-assumed `google-generativeai` — see
      `Memory.md`)
- [x] Session-based short-term memory in `app/memory/` — **JSON, not SQLite**
      (interface kept stable so this can swap later without touching callers)
- [x] Chat UI: composer, message list, streaming render
- [x] Animated identity: **particle sphere, not a face** — idle / listening /
      thinking / speaking states wired to stream lifecycle (see `Design.md`
      for why the identity changed)
- [x] Voice input (speech-to-text) and voice output (text-to-speech) — full
      turn-based voice chat loop, not just basic version
- [x] Left sidebar: new chat, chat history list
- [x] Bonus, done ahead of schedule: weather, crypto, and web search tools
      (originally planned for Phase 2 — see below)

Acceptance criteria: all met and confirmed working locally (real Gemini
responses, streaming, voice loop, tool routing).

Not done in Phase 1 (deferred, see `Memory.md`): basic SQLite schema (JSON
works fine for single-user local use so far); per-session memory isolation.

---

## Phase 2 — Understanding & Tools (IN PROGRESS)

**Goal:** NIMBUS can see, read, and look things up.

Already done in Phase 1 (moved up):

- [x] ~~Web search tool integration~~
- [x] ~~Weather lookup tool~~

Remaining tasks:

- [ ] Image upload + vision understanding
- [ ] File upload: PDF, TXT, DOCX parsing → RAG pipeline (chunk + embed + retrieve)
- [ ] OCR for scanned documents/images
- [ ] "Searching"/"reading" sphere state wired to tool-use events (partial —
      sphere already has a "thinking" state during tool calls; a distinct
      visual for "actively reading a document" is still open)

Acceptance criteria:

- User can upload a PDF and ask questions about its content
- User can ask a live question ("what's the weather in X") and get a real
  answer — already true since Phase 1
- Tool calls are visible somewhere in the UI (right-side info panel from the
  original mockup was dropped in favor of the simpler landing/chat layout —
  revisit if this becomes a real gap)

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
