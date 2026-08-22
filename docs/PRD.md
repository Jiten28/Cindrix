# PRD.md — Product Requirements Document

## Project Name

**CINDRIX** — _A calm, ever-present AI companion_

## Context

An independent personal project — built solo, no organizational affiliation
or outside guidance. Built as an industry-grade AI chatbot product rather
than a toy demo, and intended to double as a portfolio piece for AI/ML and
software engineering roles. Its original brief was HHGoa's #RAGInGoa
voice-enabled RAG task, which shaped the retrieval requirements in this
document.

## Problem Statement

Most personal-project chatbots are barebones Q&A wrappers around an LLM API
with no memory, no personality, and no real UX design. CINDRIX aims to feel
like a real AI companion: it remembers context across sessions, understands
intent, responds through an expressive animated particle sphere, and gives
the user a dashboard to see what it's doing (which model, which tools,
usage history).

## Target Users

- **Primary (technical reviewers):** judging technical depth, architecture
  quality, and UI polish.
- **Secondary (end users of the deployed app):** anyone chatting with CINDRIX
  for general assistance, Q&A, document understanding, and voice interaction.

## Goals

1. Deliver a working, deployable chatbot with a distinctive visual identity (not a
   ChatGPT/Gemini/Baymax clone).
2. Demonstrate real AI engineering: intent routing, contextual memory, retrieval
   grounding, and provider resilience — not just a raw API passthrough.
3. Ship incrementally, with a working demo at every step.
4. Produce a resume-worthy codebase: modular architecture, RAG, tool-calling,
   streaming responses, tests, Docker support.

## Non-Goals (explicitly out of scope)

- Native mobile apps (the web UI is responsive; there is no native client)
- Multi-tenant SaaS billing / auth-at-scale
- Training a custom LLM from scratch — this uses hosted provider APIs
- WhatsApp/Telegram/Slack integrations

## Key Features

### Conversational Core

- Intent routing across tool calls, attachment queries, knowledge-base
  retrieval, and plain conversation
- Contextual memory within a conversation, persisted per user so history
  survives across sessions
- Retrieval grounding with an explicit refusal path when the corpus doesn't
  confidently answer
- Error handling and provider fallback so a failed request degrades into a
  friendly message rather than a raw exception

### Interaction Modes

- Text chat with streaming responses
- Voice input (speech-to-text) and voice output (text-to-speech), as a
  turn-based conversation loop
- Image upload and understanding (vision)
- File upload: PDF, TXT, DOCX — parsed, chunked, and made queryable via RAG
- Web search, image search, weather, and crypto price tools

### Experience Layer

- Animated particle-sphere identity with idle / listening / thinking /
  speaking states — see `Design.md`
- Dark-first premium UI, desktop-first but responsive down to phone widths
- Left sidebar: conversation history, tool shortcuts, analytics, settings,
  profile
- Dark/light theme toggle ("Ember Violet" / "Lavender Dusk")
- UI-chrome localization across English, Spanish, French, and Hindi

### Platform & Ops

- Multiple selectable AI models behind a real provider abstraction — selecting
  a model changes which provider is primary and which is the fallback
- Analytics dashboard: message totals, average latency, tool-usage breakdown,
  messages per day
- Conversation export to Markdown or JSON
- Authentication + admin panel
- Automated test suite and CI; Dockerized for deployment (Render)

## Requirements dropped during implementation

Recorded rather than quietly deleted, since each was a deliberate call:

- **Named Entity Recognition as a distinct stage** — the router extracts what
  it actually needs (city names for weather, coin names for crypto) with
  targeted patterns. A general NER layer would have added a dependency and a
  latency cost for entities nothing consumes.
- **Sentiment/emotion detection adjusting response tone** — not built. It
  would need either a second model call per turn (a latency cost on the
  highest-traffic path) or a keyword heuristic too crude to be worth
  claiming. Nothing in the codebase computes sentiment.
- **Multi-intent handling within one query** — the router picks a single
  strategy per turn, in a defined priority order. Genuine multi-intent
  handling needs an orchestration loop, which is a larger change than the
  feature justified.
- **Long-term memory across conversations** — history persists per user and
  every past conversation is browsable, but the assistant's context window
  is scoped to the current conversation. There is no cross-conversation
  summarization or retrieval.
- **Right-side collapsible info panel** — the analytics modal covers the same
  need without a permanent panel competing with the sphere for attention.
  See `Design.md`.

## Success Metrics

- Every listed feature demoable end-to-end without manual intervention
- Context maintained correctly across at least 10 conversational turns
- Response latency acceptable for streaming UX (first token ~1.3s P70 on a
  grounded query — see `Testing.md`)
- Zero unhandled exceptions surfaced to the UI — all errors caught and shown
  as friendly messages
- Business logic fully separated from routes and UI

## Constraints

- Backend: Python / Flask
- No CSS frameworks (Bootstrap/Tailwind) — custom CSS only, per design brief
- AI providers: Groq primary and Gemini fallback, behind an abstraction that
  supports adding more
- Storage: JSON files behind stable interfaces, so a database can be
  introduced later without changing callers
- Must not visually or functionally clone ChatGPT, Gemini, or Baymax

## Stakeholders

- Developer (sole author)
- End users of the public deployment

## Core requirement: voice question → grounded voice answer

The single hard requirement this product is built around, stated explicitly
rather than left implied by the code: **a user must be able to ask a question
by voice and receive a spoken answer that is grounded in retrieved document
content, not a generic response.**

Concretely: voice input (speech-to-text) → the same retrieval-augmented query
pipeline used for typed input → voice output (text-to-speech) of the grounded
answer, end to end, with no separate or lesser voice-only code path. The
"Voice input/output" and "File upload … RAG" capabilities above cover the
underlying pieces; this section exists to state that their *combination* is
the requirement, not two adjacent features that happen to both exist.
