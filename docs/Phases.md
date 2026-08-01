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

## Phase 3 — Insight Layer ✅ COMPLETE
**Goal:** Make usage visible and exportable.

Tasks:
- [x] Analytics event logging (`app/analytics/events.py`) — every chat turn
      logs tool used, latency, message length
- [x] Analytics dashboard: modal in the sidebar (Analytics button) showing
      total messages, average latency, tool-usage breakdown (bar chart), and
      messages-per-day (bar chart) — hand-rolled with divs, not a charting
      library, consistent with the rest of the project's approach
- [x] Full conversation history browsing — this required a real architecture
      change: replaced the single shared `conv_history.json` with proper
      per-conversation storage (`app/memory/conversation_store.py`, one JSON
      file per conversation under `data/conversations/`). The sidebar
      "Recent" list is now real and clicking an entry loads that
      conversation. `session_memory.py` is superseded by this — kept in the
      repo as reference, not used by any route anymore.
- [x] Conversation export — Markdown and JSON, via
      `/api/conversations/<id>/export?format=md|json`, downloadable from the
      topbar export button

Not done (search within history — "browsing" shipped, full-text search
across past conversations did not; small enough to add later if it turns out
to matter).

Acceptance criteria: both met — dashboard shows real accumulated data,
export works for any conversation.

---

## Phase 4 — Accounts & Scale-readiness ✅ COMPLETE
**Goal:** Multi-user ready, model-flexible.

Tasks:
- [x] Authentication (signup/login/session) — session-based via Flask's
      signed-cookie session, not tokens; simplest fit for a same-origin SPA
- [x] Per-user conversation history and memory isolation — conversations
      and attachments both moved from single/global storage to
      `data/conversations/<user_id>/` and `data/embeddings/_attachments/<user_id>.json`.
      Not logging in still works — everything falls into a shared `guest`
      bucket, same behavior the whole app had before Phase 4, now just one
      bucket among many instead of the only one.
- [x] Admin panel (basic) — user list with per-user conversation/message
      counts, gated by an `is_admin` flag (first account ever created is
      auto-flagged admin — simplest possible bootstrap, no separate setup step)
- [x] Model selector UI wired to a real provider abstraction — three actual,
      verified-current Gemini model IDs (`gemini-flash-latest`,
      `gemini-3.6-flash`, `gemini-3.5-flash-lite`), not fabricated
      multi-provider options. Switching it changes which model answers,
      end-to-end. Server-side validates the model id against the allowed
      list before it ever reaches the Gemini API call — an unexpected string
      from the client can't reach the API as a model name.
- [x] Personal long-term memory — satisfied by the per-user conversation
      history itself; no separate memory system was needed

Also built (not originally scoped, but flagged as broken buttons and fixed
alongside Phase 4 since profile/settings are inherently account features):
- Real Settings page: display name, change password
- Real Profile page: account info, join date, admin badge, logout

Acceptance criteria: both met — verified live with two real accounts
(neither could see the other's conversations), and a model override was
confirmed to actually change which model answered (visible in the stub
response during testing).

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