# Rules.md — Boundaries for AI-assisted development

These rules apply to any AI coding assistant (Claude Code, Cursor, ChatGPT, Gemini)
working on this repo. They exist so multiple tools/sessions produce consistent,
predictable code.

## Do

- Build strictly according to `PRD.md`, `Architecture.md`, `Design.md`, and the
  current phase in `Phases.md`. Do not jump ahead to a later phase's features.
- Keep business logic in `app/services/` or the relevant module — never inline in
  route handlers.
- Use type hints on all function signatures.
- Write docstrings for public functions/classes; inline comments only where the
  code isn't self-explanatory.
- Handle errors explicitly — no bare `except:`; always return a friendly UI-facing
  message plus a logged technical detail.
- Update `Memory.md` at the end of every milestone (see template in `Memory.md`).
- Ask before making an architectural decision that isn't already specified in
  `Architecture.md` (e.g. switching Flask → FastAPI, adding a new major dependency).
- Keep frontend and backend concerns separated — no business logic in templates/JS
  beyond UI state.
- Prefer small, reviewable diffs over large rewrites.

## Don't

- Don't use Bootstrap or Tailwind — custom CSS only, per `Design.md`.
- Don't render a full humanoid robot or reproduce the Baymax character — the
  mascot is only the minimal floating face described in `Design.md`.
- Don't copy ChatGPT/Gemini UI patterns wholesale — this is a distinct product.
- Don't hardcode API keys or secrets — use `app/config/` + environment variables.
- Don't silently swallow exceptions.
- Don't introduce a new major library (ORM, task queue, etc.) without checking it
  against `Architecture.md` first.
- Don't invent features not listed in `PRD.md`/`Phases.md` — flag ideas instead of
  building them unprompted.
- Don't remove or rewrite unrelated code while implementing a feature.

## Libraries — approved / avoid

| Category          | Approved                             | Avoid                                                                   |
| ----------------- | ------------------------------------ | ----------------------------------------------------------------------- |
| Backend framework | Flask (FastAPI if formally switched) | Django (too heavy for this scope)                                       |
| CSS               | Hand-written CSS                     | Bootstrap, Tailwind                                                     |
| Animation         | GSAP, Lottie, CSS transitions        | Full animation frameworks that fight vanilla JS                         |
| DB (dev)          | SQLite via SQLAlchemy                | Raw SQL strings without parameterization                                |
| AI                | Gemini API SDK                       | Mixing multiple providers without the provider abstraction in `app/ai/` |

## Error Handling Policy

- Every route wraps external calls (LLM, search, weather, file parsing) in
  try/except with a specific fallback.
- User-facing errors: short, friendly, non-technical ("CINDRIX couldn't reach the
  weather service — try again in a moment").
- Technical detail goes to logs (`app/utils/logging` or equivalent), never to the
  client.
- Streaming responses must gracefully close the stream on error, not hang the UI.

## AI Behavior / Ethics

- No fabricated data in responses presented as fact — if the model is unsure, say so.
- Sentiment/emotion detection informs tone only, never used to manipulate or
  exploit user emotional state.
- Bias checks: avoid training/prompting patterns that produce discriminatory
  outputs; flag if a fix requires design input.

## Git & Commit Conventions

- One logical change per commit.
- Commit message format: `[phase-N] short description` (e.g. `[phase-1] add
session memory persistence`).
- No committing `data/uploads/`, `data/cache/`, `.env`, or embeddings to version
  control — keep `.gitignore` current.

## When the AI Should Stop and Ask

- Before deleting or significantly restructuring existing files.
- Before adding authentication/security-sensitive code without explicit direction.
- Before any decision affecting cost (model choice, external paid API).
- Whenever a request conflicts with `PRD.md` or the current phase scope.
