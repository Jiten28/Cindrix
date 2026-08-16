# PRD.md — Product Requirements Document

## Project Name

**CINDRIX** — _A calm, ever-present AI companion_

## Context

Final-month internship deliverable (Amdocs). Built as an industry-grade AI chatbot
product, not a toy demo — intended to double as a portfolio piece for AI/ML and
software engineering roles.

## Problem Statement

Most internship chatbot projects are barebones Q&A wrappers around an LLM API with
no memory, no personality, and no real UX design. CINDRIX aims to feel like a real
AI companion: it remembers context across sessions, understands intent and
sentiment, responds through an expressive animated face, and gives the user a
professional dashboard to see what it's doing (which model, which tools, memory
status).

## Target Users

- **Primary (internship reviewers / evaluators):** judging technical depth,
  architecture quality, and UI polish.
- **Secondary (end users of the deployed demo):** anyone chatting with CINDRIX for
  general assistance, Q&A, document understanding, and voice interaction.

## Goals

1. Deliver a working, deployable chatbot with a distinctive visual identity (not a
   ChatGPT/Gemini/Baymax clone).
2. Demonstrate real NLP/AI engineering: intent recognition, contextual memory,
   sentiment-aware responses — not just a raw API passthrough.
3. Ship incrementally across 5 phases with a working demo at the end of each.
4. Produce a resume-worthy codebase: modular architecture, RAG, tool-calling,
   streaming responses, Docker support.

## Non-Goals (explicitly out of scope for now)

- Native mobile apps (Phase 5, stretch only)
- Multi-tenant SaaS billing/auth-at-scale
- Training a custom LLM from scratch (we use Gemini API, not a custom model)
- Full WhatsApp/Telegram/Slack integrations (nice-to-have, not core)

## Key Features

### Conversational Core

- Intent recognition and Named Entity Recognition (NER) for extracting key info
  from user queries
- Persistent contextual memory across a session and across sessions (long-term
  memory)
- Multi-intent handling within a single query (intent prioritization)
- Sentiment/emotion detection that adjusts response tone
- Fallback and error-handling flows when intent confidence is low

### Interaction Modes

- Text chat with streaming responses
- Voice input (speech-to-text) and voice output (text-to-speech)
- Image upload and understanding (vision)
- File upload: PDF, TXT, DOCX (parsed and made queryable via RAG)
- Web search tool and weather lookup tool

### Experience Layer

- Animated minimalist AI face (idle / thinking / talking / happy / listening /
  searching / blink states) — see `Design.md`
- Dark, glassmorphic, premium desktop-first UI
- Left sidebar: chat history, search chats, AI tools, settings, profile
- Right-side collapsible panel: current model, memory status, active tools,
  conversation stats
- Dark/light theme toggle

### Platform & Ops

- Multiple selectable AI models (architecture ready even if only Gemini is wired
  up in Phase 1)
- Analytics dashboard: usage trends, response effectiveness, conversation stats
- Conversation export
- Authentication + admin panel (Phase 4)
- Dockerized, CI-ready structure for deployment (Render/Railway)

## Success Metrics

- All Phase 1–3 features demoable end-to-end without manual intervention
- Chatbot maintains context correctly across at least 10 conversational turns
- Response latency acceptable for streaming UX (first token < ~2s on typical query)
- Zero unhandled exceptions surfaced to the UI (all errors caught and shown as
  friendly messages)
- Codebase passes a basic review for modularity: business logic fully separated
  from routes/UI

## Constraints

- Backend: Python (Flask, or FastAPI if switched — see `Architecture.md`)
- No CSS frameworks (Bootstrap/Tailwind) — custom CSS only, per design brief
- AI provider: Gemini API, architected to support additional models later
- Storage: SQLite for development, PostgreSQL path kept open for later
- Must not visually or functionally clone ChatGPT, Gemini, or Baymax

## Stakeholders

- You (developer / intern)
- Amdocs internship reviewers/mentors
- (Optional) end users of the public demo, if deployed

## Hackathon Submission Requirement (formal, added — see Memory.md)

Separate from the internship deliverable above, this build is also being
submitted to the HHGoa "Voice-Enabled RAG" hackathon (deadline Aug 22,
2026). That task has one hard, formal requirement this PRD is now
explicit about rather than leaving implied by the code: **a user must be
able to ask a question by voice and receive a spoken answer that is
grounded in retrieved document content (RAG), not a generic response.**
Concretely: voice input (speech-to-text) → the same retrieval-augmented
query pipeline used for typed input → voice output (text-to-speech) of
the grounded answer, end to end, with no separate/lesser voice-only code
path. The existing "Voice input/output" and "File upload... RAG" bullets
above already cover the underlying capabilities — this section exists to
state plainly that their combination (voice question → RAG-grounded
voice answer) is the literal judged requirement, not just two adjacent
features.
