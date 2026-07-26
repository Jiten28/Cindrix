# Memory.md — Living Development Log

> Update this file at the end of every milestone/session. Any AI assistant
> picking up this project should read this file FIRST, before touching code.
> Purpose: avoid re-reading the whole codebase or re-deriving decisions already
> made.

Last updated: _(not started — update on first coding session)_

---

## Current Status

Project is in the planning/documentation stage. `PRD.md`, `Architecture.md`,
`Rules.md`, `Phases.md`, and `Design.md` are complete. No code has been written
yet. Next step: begin Phase 1 (see `Phases.md`).

## Completed Work

- (none yet)

## In Progress

- (none yet)

## Pending / Next Up

- Phase 1: Flask skeleton, Gemini integration, session memory, chat UI, face
  animation states, voice I/O (see `Phases.md` for full task list)

## Architecture Decisions Log

| Date | Decision                                | Reasoning                                                                       |
| ---- | --------------------------------------- | ------------------------------------------------------------------------------- |
| —    | Backend = Flask (FastAPI as fallback)   | Simpler for a solo intern project; can swap later if async/streaming needs grow |
| —    | No CSS framework                        | Custom design identity per `Design.md`; avoid generic Bootstrap look            |
| —    | SQLite for dev, Postgres path kept open | Fast local iteration, clear upgrade path                                        |

## Known Issues

- (none yet)

## Notes for the Next AI Session

- Read `PRD.md` → `Architecture.md` → `Rules.md` → current phase in `Phases.md`
  → `Design.md`, in that order, before writing code.
- Do not skip ahead of the current phase.
- Update this file before ending the session, even if the milestone isn't fully
  done — note what's mid-flight so the next session can resume cleanly.
