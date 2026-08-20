# Memory.md — Living Development Log

> Update this file at the end of every milestone/session. Any AI assistant
> picking up this project should read this file FIRST, before touching code.
> Purpose: avoid re-reading the whole codebase or re-deriving decisions already
> made.

> **Canonical URLs (as of Hackathon Phase 3 — see that entry below for
> when/why these were fixed):** GitHub repo is
> `https://github.com/Jiten28/Cindrix` — NOT `Nimbus-AI`, an earlier
> project name from before the CINDRIX rename. Live deployment is
> `https://cindrix-ai.onrender.com/`. If any doc, comment, or generated
> output reintroduces `Nimbus-AI` or a different Render URL, that's stale
> — fix it back to these two values rather than trusting what's already
> written elsewhere as a source of truth.

Last updated: Interface polish, core (sphere mouse-interactivity + light/dark theme toggle) — see entry immediately below. Hackathon Phase 5 (dataset/fallback fixes) still the most recent *hackathon-track* entry; this session's work was frontend-only and doesn't affect it.

---

## Interface Polish, Core — Sphere Mouse-Interactivity + Light/Dark Theme Toggle

New. Frontend-only session (CSS/JS under `frontend/` only — `app/`,
router.py, and anything RAG/STT/Groq/Gemini-related were explicitly out of
scope and untouched). Picks up the two Phase-1-deferred items named in
`Design.md`'s Implementation Status section and `Phases.md`'s Hackathon
Track "Interface polish, core" line.

**Important sequencing note:** `Phases.md`'s Hackathon Track status said
this work should stay paused until Hackathon Phase 2 passes real-environment
verification (`Testing.md` §17b), and that verification still hasn't
happened — nothing in §17b is checked off, and this session didn't touch
the RAG/STT/Groq backend at all, so that gate is unaffected either way.
This work was done anyway, on explicit instruction this session, out of the
sequence `Phases.md` otherwise documents. Flagging this rather than quietly
rewriting the Hackathon Phase 2 status to look like the gate was cleared —
it wasn't. See `Phases.md`'s updated status line for the honest phrasing.

**1. Sphere mouse-interactivity (`frontend/js/particle-sphere.js`).**
`Design.md` explicitly said this was "not built... states are driven purely
by voice/chat lifecycle, not pointer input" — confirmed true by reading the
file before starting. Built as two effects, both layered additively on top
of the existing idle/listening/thinking/speaking state math (radius,
rotation speed, per-particle wander/ripple formulas — none of it changed):
- **Parallax tilt** — the whole sphere leans gently (~10° max) toward
  wherever the cursor is on the page, not just when hovering the canvas
  itself, eased frame-to-frame so it never snaps. Implemented as two small
  additional single-axis rotations composed with the existing Y-axis
  autonomous spin, applied before any per-state offset so listening's
  wander and speaking's ripple still layer on top of it exactly as before.
- **Local repulsion** — particles within a small radius of the actual
  cursor (screen-space, post-projection) nudge away from it, falling off
  to nothing past that radius. Applied last, after the 3D state motion and
  projection, so it can't distort the state-driven shape.
- Both skip entirely under `prefers-reduced-motion`, matching this file's
  existing motion-sensitivity handling elsewhere.
- Constants (`MAX_TILT`, `TILT_EASE`, `REPEL_RADIUS_FRAC`,
  `REPEL_STRENGTH_FRAC`) were picked for "subtle" per Design.md's motion
  principles but not tuned against a real cursor in a real browser — no
  browser in this session's sandbox. Worth a quick live eyeball before
  trusting the feel is right.

**2. Light/dark theme toggle (`frontend/css/style.css`,
`frontend/index.html`, `frontend/js/app.js`).** No light-mode hex values
existed anywhere before this session — checked `Design.md`, `PRD.md`, and
the full git log/diff history for a previously-chosen palette; `PRD.md`
only ever listed "Dark/light theme toggle" as an unspecified requirement
bullet. Chose new values in the same Ember Violet family (same accent hue,
`#7C4DEF` — deepened slightly from `#9B6EF7` for AA contrast on a light
surface; glow stays the amber `#F0A34E` unchanged in both themes) rather
than inventing an unrelated palette — full table now in `Design.md`'s new
"Light theme" subsection.
- `style.css`: new `--*-rgb` triplet tokens (`--bg-rgb`, `--card-rgb`,
  `--text-rgb`, `--star-rgb`) alongside the existing hex tokens, plus a
  `html[data-theme="light"]` override block. Every hardcoded
  `rgba(255,255,255,…)` / `rgba(26,22,32,…)` / `rgba(10,10,12,…)` surface
  or hover color in the file was converted to read `rgba(var(--text-rgb),
  …)` / `rgba(var(--card-rgb), …)` / `rgba(var(--bg-rgb), …)` instead, so
  every one of those spots (sidebar, modals, dropdowns, form inputs, hover
  states — audited line by line) follows the active theme automatically.
  Deliberately left alone: drop shadows and modal scrims (stay dark in
  both themes, standard pattern), and the accent/glow-based glows (violet/
  amber rgba values) — those are theme-invariant identity colors, not
  surface tokens.
- **Known gap, not fixed**: `.msg pre`/inline-code-block styling still
  reads from the `highlight.js` `atom-one-dark` CDN stylesheet
  (`index.html`'s `<link>`), which stays dark regardless of theme — a
  light hljs theme swap would need its own pass (a second CDN stylesheet
  swapped in via the same `data-theme` attribute) and wasn't attempted
  here to keep this session scoped to what was asked.
- `index.html`: a small inline script in `<head>`, before any stylesheet
  or the rest of the page loads, applies a saved `localStorage` theme to
  `<html data-theme="…">` synchronously — avoids a flash-of-wrong-theme on
  reload. A toggle button (🌙/☀️) was added to the topbar controls, next
  to the existing voice/model/language selectors.
- `app.js`: owns the actual toggle behavior — flips `data-theme`, persists
  to `localStorage` (`cindrix-theme`), updates the button's icon/label
  (via the existing `CindrixI18n.t()` helper, not a new i18n mechanism),
  and dispatches a `cindrix:themechange` `CustomEvent` on `window` so other
  modules can react without polling.
- `particle-sphere.js` / `starfield.js`: both used to have hardcoded dark-
  only RGB triplets (`ACCENT`/`MUTED` in the sphere, plain white stars).
  Both now read the relevant CSS custom property (`--accent`/`--text` for
  the sphere, `--star-rgb` for the starfield) via `getComputedStyle` at
  creation time, and re-read it on `cindrix:themechange` — so toggling
  the theme re-colors the sphere and starfield live, no reload needed.
- **i18n note**: added `topbar.switchToLight` / `topbar.switchToDark` keys
  to all four locale files (`en`/`es`/`fr`/`hi`) so the new toggle button's
  label/tooltip translates like its sibling topbar controls do. This is
  filling in one key on an *already-shipped* i18n system, not new i18n
  feature work — Phase 4's i18n/mobile-responsiveness push itself is still
  untouched and still paused per `Phases.md`.

**Verified:** all four touched/added-to frontend JS files
(`particle-sphere.js`, `starfield.js`, `app.js`, `i18n.js`) pass
`node --check`. **Not verified:** no live browser in this session's
sandbox, so the actual visual result (light theme, tilt/repel feel) hasn't
been eyeballed — flagged above per-item where it matters most.

**Not done:** `.msg pre`/hljs light-theme support (see gap above);
tuning the mouse-interactivity constants against a real cursor.

---

## Hackathon Track — Hackathon Phase 5 (Dataset Shard Fix + General-Chat Fallback Coverage)

New. Two real crashes/bugs, both confirmed via live testing rather than
inferred:

**1. Dataset loader crash #2 (`app/rag/dataset.py`).** The Hackathon
Phase 3 fix (per-language configs don't exist, switch to `"default"` +
filter by `target_lang`) was directionally right but incomplete: it
crashed differently on the real second run — `MemoryError` + `WinError
10038` downloading `train/asmtrain.parquet` (Assamese) before ever
reaching a Hindi row. Root cause: `"default"` is per-language parquet
shards concatenated by the loader, and streaming-then-filtering still has
to fetch each shard in full first. Fixed by loading the target language's
shard file directly (`data_files={"train": "train/hintrain.parquet"}`)
instead of streaming the combined config. Confirmed the shard naming
pattern (`{split}/{iso3}{suffix}.parquet`) against three real files in
the repo's tree while fixing this (`train/hintrain.parquet`,
`train/asmtrain.parquet`, `validation/telval.parquet`) — see
`Architecture.md`'s rewritten Dataset section for the full before/after.
Side effect worth noting: this also makes `hin_Deva`'s correctness (still
not confirmed against a literal fetched row — see Hackathon Phase 3's
entry) much cheaper to disprove if wrong, since a mismatch now surfaces
on the shard's first few rows instead of after scanning millions of rows
from other languages.

**2. General chat still leaking raw Gemini errors (`app/agents/router.py`,
`app/tools/weather.py`).** Confirmed via live testing: `stream_generation()`
(the Groq/Gemini fallback chain from Hackathon Phase 4) only got wired
into the two RAG-serving call sites, not the web-search-synthesis path or
the final plain-conversational fallback — which is the highest-traffic
path in the whole router (everything that isn't a tool/attachment/KB
match lands there). Weather questions specifically hit a second, separate
bug: `app/tools/weather.py`'s Gemini fallback (`call_gemini(...)`) is a
non-streaming call with no fallback-chain equivalent to route through at
all. Both fixed:
- `router.py`'s web-search-synthesis and plain-conversational paths now
  call `stream_generation()` — same as the RAG paths.
- Added `call_generation()` to `retry.py` (non-streaming equivalent,
  built by reusing `stream_with_fallback` — a non-streaming call is just
  a one-chunk "stream" from that machinery's point of view — not a
  second parallel retry implementation) and `call_groq()` to
  `groq_client.py` (Groq's non-streaming endpoint, mirrors `call_gemini`'s
  error-sentinel shape). `weather.py`'s plain-text Gemini fallback now
  goes through `call_generation()`.
- A regression test reproduces the exact reported scenario (both
  providers failing on a weather question) and confirms no raw `503`/
  `UNAVAILABLE` text reaches the returned string.

**Known gap, explicitly not fixed:** the image-vision path
(`stream_gemini_vision`) still calls Gemini directly, unprotected by any
fallback chain. Would need a distinct Groq vision client (different
message format, unconfirmed whether a suitable vision model exists on
Groq) — flagged in `Architecture.md` rather than silently built beyond
what was asked (the reported bug was specifically about text generation:
weather, factual questions) or silently left undocumented.

**Tests:** 7 new (3 for the dataset shard fix — path construction, an
unconfirmed-split rejection, and a mocked `load_dataset` call verifying
the actual `data_files` argument; 4 for `call_generation` including the
weather-specific regression test). All 27 tests (20 prior + 7 new)
verified passing.

**Not done yet:** re-running ingest/benchmark for real against the fixed
dataset loader and the now-fully-wired fallback chain — still the
critical remaining gap, `Testing.md` §17b.

## Hackathon Track — Hackathon Phase 4 (Groq-Primary Generation Provider Chain)

New. Built entirely fresh — a prior message assumed Groq-as-fallback
already existed from "Task 3" and asked to reverse its order; that
turned out to be a false premise (confirmed by grep: zero mentions of
"groq" anywhere in the codebase before this entry). Flagged that
mismatch rather than trying to "reverse" code that didn't exist, then
built the real target state directly: **Groq primary, Gemini fallback**.

**Why Groq primary:** based on Groq's generally-published LPU-hardware
inference speed vs. Gemini Flash (independent third-party benchmarks) —
explicitly NOT based on this project's own `benchmark.py`, which has
only ever produced `is_self_test` placeholder output so far (no real
`GROQ_API_KEY`/`GOOGLE_API_KEY` in any sandboxed session yet). Confirming
this holds for the actual pipeline (small Indic-text prompts, this exact
retrieval-then-generate shape) is explicit follow-up, not assumed true —
see `Testing.md` §17b.

**What was built:**
- `app/ai/groq_client.py` — new. Groq's OpenAI-compatible
  `/chat/completions` endpoint, hand-rolled via `requests` (no new SDK
  dependency, same pattern as `app/ai/stt.py`'s Sarvam call). Default
  model is `openai/gpt-oss-120b`, **not** `llama-3.3-70b-versatile` as
  originally suggested — checked Groq's live deprecations page/changelog
  while building this and found that model deprecated (announced June 17
  2026, shutdown Aug 16 2026 — already past). Same class of trap this
  project already got burned by once with `gemini-1.5-flash` — verify
  current model IDs against live docs, don't trust a suggested example
  model name at face value.
- `app/ai/retry.py` — restructured, not just extended. The old
  single-provider retry mechanic got factored into a reusable internal
  helper (`_attempt_with_retry`) so it's shared, not duplicated, between
  the still-present, still-unchanged-behavior `stream_with_retry()`
  (kept for anything that wants retry without fallback — verified via a
  regression test that its behavior is bit-for-bit identical to before)
  and the new `stream_with_fallback()`/`stream_generation()` — Groq with
  its own retry budget, then Gemini with its own retry budget if Groq's
  is exhausted, then a clean user-facing error if both fail. Which
  provider actually served each response is always logged.
- `app/agents/router.py` — both RAG-serving call sites
  (`document_rag`, `knowledge_base_rag`) swapped from
  `stream_with_retry(lambda: stream_gemini(...))` to
  `stream_generation(prompt, gemini_model=model)`. This is the one place
  "don't touch router logic" needed a judgment call: the actual routing
  decisions (which path, guardrail checks, prompt construction) are
  byte-for-byte unchanged — only which retry-layer function serves the
  generation changed, which is squarely "the generation provider chain"
  this task was about, not routing logic. Flagging the interpretation
  rather than silently making it.
- `app/rag/benchmark.py` — also updated (not explicitly listed in the
  task, but necessary for the task to mean anything): it was calling
  `stream_gemini` directly, bypassing the new fallback chain entirely.
  Re-running it without this fix would have measured Gemini-only
  performance, not what the app actually serves. Now goes through
  `stream_generation()` and captures which provider served each
  benchmark query (via a temporary log handler on `app.ai.retry`'s
  logger, not a change to that function's production return signature)
  for a per-provider breakdown in the report.
- `settings.py`/`.env.example`/`render.yaml` — `GROQ_API_KEY`,
  `GROQ_MODEL` added, same `sync: false` pattern as the other keys.
  `GOOGLE_API_KEY` unchanged (still required, now documented as the
  fallback rather than primary).
- `tests/test_rag.py` — 4 new tests for the fallback chain (Groq
  succeeds/Gemini never called, Groq exhausts retries/Gemini used and
  returned, both fail/clean error, non-transient Groq error still falls
  back without wasting a retry) plus a regression check that the old
  `stream_with_retry` is unaffected. All 20 tests (16 prior + 4 new)
  verified passing.
- `Architecture.md` — "Generation Provider Chain" section (replaces the
  old "Retry & structured error recovery" section) documents the full
  chain, the model-deprecation catch, and the honest
  published-benchmark-vs-own-benchmark caveat.

**Not done yet:** the actual re-run of `benchmark.py` with real
`GROQ_API_KEY`/`GOOGLE_API_KEY` to confirm Groq-primary actually helps
*this* pipeline hit the 200ms target — still pending, still the single
most important remaining verification gap alongside the rest of
`Testing.md` §17b (real Sarvam call, real MSMARCO-XI ingest).

## Hackathon Track — Hackathon Phase 2 (Compliance: STT, RAG, Guardrails, Hardening)

New, separate from the Phase 1–5 roadmap below (this project's original
solo development roadmap, not tied to any organization) and from
Hackathon Phase 1 above. Triggered by finally obtaining the hackathon's
official task brief (#RAGInGoa Task #2, deadline Aug 22 2026 11:59 PM
IST), which revealed everything it grades was either unbuilt or
non-compliant. Phase 4 work (i18n, mobile responsiveness) was paused per
explicit instruction to focus entirely on this until the deadline.

**Five priorities, all built and unit-tested this session** (see
`docs/Testing.md`'s new section 17 for exactly what "tested" means here —
short version: real logic tested against real schemas/scenarios with
mocked network calls, since this session had neither a `GOOGLE_API_KEY`
nor general network access; section 17b lists what still needs a real
environment before the submission is actually verified end-to-end):

**Priority 1 — STT provider compliance.** Web Speech API doesn't qualify
for the hackathon (Sarvam or ElevenLabs required); it stays as the
default dev/fallback path rather than being ripped out.
`STT_PROVIDER=sarvam` (+ a real `SARVAM_API_KEY`) switches to
`app/ai/stt.py`, calling Sarvam's `/speech-to-text` REST endpoint
(`saaras:v3`). Sarvam picked over ElevenLabs for its Indic-language
focus, matching the MSMARCO-XI corpus. Endpoint/auth/param details were
looked up directly against Sarvam's live docs while building this, not
recalled from training data. Frontend (`app.js`) got a full second voice-
input implementation (MediaRecorder + a Web Audio silence-detector, since
raw audio recording doesn't get free end-of-speech detection the way
Web Speech API does) behind a provider switch fetched from a new
`/api/config` endpoint — both providers feed the exact same
`sendMessage(transcript, true)` call downstream.

**Priority 2 — Chunking + vector DB.** `app/rag/chunking.py`: three
strategies (fixed-size, semantic/sentence-packed, metadata-aware — the
last one is what's actually used for MSMARCO-XI, since its passages
arrive pre-segmented). `app/rag/dataset.py`: streams the real dataset via
HF `datasets`, capped/disclosed scope (`RAG_INGEST_MAX_ROWS`, default
2000 — ingesting all 10M+ rows/language isn't a realistic hackathon-
timeline operation), with a fixture fallback (built from the dataset
card's own documented example) when `datasets` isn't installed.
`app/rag/vector_store.py`: FAISS-backed (numpy exact-search fallback when
`faiss` isn't installed), replaces the old brute-force loop in
`embeddings.py`'s `top_k_chunks()`. `app/rag/ingest.py`: ties it together,
runnable via `python -m app.rag.ingest`. Wired into
`app/agents/router.py` as a new `knowledge_base_rag` path — see
`Architecture.md`'s new section for the full writeup, including a
product-behavior tradeoff worth reading before demoing this outside the
hackathon context (once
the KB index exists, general queries that don't ground well now decline
rather than falling back to generic chat — flagged there, not buried).

**Priority 3 — Latency harness.** `app/rag/benchmark.py`: P50/P70/P100
across embed-query/vector-retrieval/generation stages plus end-to-end,
target <200ms. Deliberately excludes ingest-time chunking from the
per-query number (that's a one-time cost, not something a live query
pays — see Architecture.md for why a literal reading would be bad
engineering). **Honest, not fabricated**: with no `GOOGLE_API_KEY` in
this session's sandbox, the harness marks its own output
`"is_self_test": true` and refuses to claim `meets_target` — real numbers
need `python -m app.rag.benchmark` run with a real key, not done yet.

**Priority 4 — Guardrails.** `app/rag/guardrails.py`: unsafe-input
blocking (tested for false positives too — a legitimate safety question
doesn't trip it), off-topic screening (tool-intent/greetings skip KB
retrieval entirely rather than getting force-declined), and a grounding
check (`RAG_MIN_RELEVANCE`, default 0.55 cosine) that — verified by
test, not just by reading the code — actually prevents Gemini from being
called at all when retrieval comes back weak, rather than just hoping a
prompt instruction stops it from improvising.

**Priority 5 — Harness hardening.** `app/ai/retry.py`: wraps both
RAG-serving Gemini calls (`document_rag`, `knowledge_base_rag`) with
retry + structured recovery — scoped to the RAG path specifically, not
every Gemini call site, per the instruction ("that's what's graded").
Built directly against a real production bug: a transient `503
UNAVAILABLE` was leaking as raw `(Gemini error: 503 UNAVAILABLE.
{'error': ...})` text in the chat (this was caught live, in a screenshot
of the deployed app, not hypothetically). Tested all four shapes this
needs to handle: recovers transparently on a transient error, gives up
gracefully after exhausting retries, doesn't waste a retry on a
non-transient error, and closes cleanly (no hang, no duplicate content)
if a failure happens mid-stream after real content already went out.

**Docs touched this session:** this entry; `Architecture.md` (new
"Retrieval, Vector Store & Guardrails" section — dataset, all three
chunking strategies, vector store choice, router wiring including the
flagged product tradeoff, guardrails, retry, latency harness; Voice I/O
section updated for the STT provider switch); `Testing.md` (new section
17, split into what's automated-tested vs. what needs a real environment
before trusting the submission); `.env.example` (new STT/RAG config vars,
`GOOGLE_CSE_ID` deliberately left untouched per explicit instruction).

**What's NOT done yet, going into the next session:**
- Nothing in section 17b of `Testing.md` has been run against a real
  environment — no real Sarvam call, no real MSMARCO-XI ingest (only the
  2-row fixture), no real Gemini-backed latency numbers. This is the
  single most important gap before the Aug 22 submission — the code is
  real and tested, but "tested against mocks in a sandbox with no
  network" is not the same claim as "verified against the live
  hackathon stack."
- `faiss-cpu` and `datasets` need `pip install -r requirements.txt` run
  somewhere with network access — both are soft-imported with working
  fallbacks, but the fallbacks are explicitly not what "real vector
  store"/"the mandated dataset" mean for grading purposes.
- Once section 17b passes for real: resume the paused Phase 4 work
  (i18n, mobile responsiveness) and the still-earlier-paused Phase 3
  interface polish (sphere mouse-interactivity, light/dark theme) — see
  `Phases.md`'s Hackathon Track section for the current phase order.

## Hackathon Track — Hackathon Phase 1 (Rename + Core Voice Pipeline)

New, separate from the Phase 1–5 roadmap below (this project's original
solo development roadmap) — logged here
per this file's own "dated entry per milestone" convention. See
`Phases.md`'s "Hackathon Track" section for how this relates to the
original roadmap; short version: it doesn't replace it, it's a parallel
submission push.

**Reason:** submitting to the HHGoa "Voice-Enabled RAG" hackathon,
deadline Aug 22, 2026. Structured as 4 phases; this is Phase 1.

**Done in Hackathon Phase 1:**
- **Rename NIMBUS → CINDRIX** across every user-facing and developer-facing
  reference: frontend (`index.html`, `app.js`, `style.css` header comment,
  `favicon.svg` gradient/background colors), backend (the LLM system
  prompt in `app/agents/router.py` — this is what the model was literally
  told to call itself, so it mattered beyond just UI text — plus
  `app/__init__.py`'s health payload, `app/api/routes.py`'s transcript
  speaker label, `app/config/settings.py`), deploy config (`render.yaml`,
  `docker-compose.yml`, `Dockerfile`), `tests/test_health.py` (updated to
  assert the new title so this doesn't start failing), `run.py`, and
  `Readme.md`. The GitHub repo itself is deliberately still named
  `Nimbus-AI` — that's a manual rename step, not part of this pass, so the
  README's clone instructions still point at that real URL. (Since
  renamed for real — see the canonical-URLs note at the top of this file.)
- **Ember Violet palette** applied to `frontend/css/style.css`'s `:root`
  variables. Audited every existing `--glow` usage first: kept amber glow
  on the sphere's ambient halo (`.orb-dock::before`) and the mic
  listening/active states (both genuinely voice/sphere-adjacent), switched
  everything else that was blending `--glow` in as a generic second color
  — `.brand-mark`, `.new-chat-btn`, `.composer-send`, `.form-submit`,
  `.profile-avatar`, the analytics bar-fill/daily-bar gradients — over to
  solid `--accent`, so amber doesn't bleed into unrelated UI chrome that
  was never meant to sit next to a violet accent in the first place.
- **Found and fixed a real gap the palette swap alone would have missed**:
  `particle-sphere.js`'s canvas rendering never read the CSS variables at
  all — `ACCENT`/`MUTED` were hardcoded RGB triplets matching the *old*
  palette. Updated them to the new accent/text values so the sphere itself
  actually reflects Ember Violet, not just the surrounding chrome.
- **Voice pipeline — verified, not rebuilt.** Contrary to an earlier
  assumption that no STT/TTS existed yet, a full voice pipeline was
  already implemented (`SpeechRecognition` for input, `speechSynthesis`
  for output, mic button wired to sphere states, error handling for
  no-mic-permission/unsupported-browser). Verified against four criteria
  and fixed the two real gaps found:
  - Same code path as typed input for both directions — already correct.
  - Sphere state transitions — **had a real bug**: a leftover line in
    `streamInto()` flipped the sphere into the `speaking` animation the
    moment the first streamed chunk arrived, including for typed (non-
    voice) replies, which never play audio. Fixed — the sphere now stays
    in `thinking` through the whole generation for both input modes, and
    only enters `speaking` once `speak()` actually starts TTS playback.
  - Edge "Natural"/"Online" neural voice preference — **was missing**,
    added (`pickPreferredVoiceName()` in `app.js`): defaults the voice
    selector to a Natural/Online voice matching the page language when one
    exists, without overriding a user's manual pick, and falls back
    silently to the browser default otherwise (Edge never hard-required).
    Documented in `Readme.md` and `Architecture.md`.
  - Mic-permission-denied / unsupported-browser handling — already
    correct (resets sphere to `idle`, shows a visible error message via
    `flashStateMessage`, disables the mic button with a tooltip when
    `SpeechRecognition` doesn't exist at all).
- Updated all six planning docs (this entry; `PRD.md`'s new formal
  hackathon-requirement section; `Architecture.md`'s new Voice I/O
  section; `Design.md`'s palette table, header renames, and new
  sphere-mouse-interactivity-deferred bullet; `Rules.md` and `Phases.md`
  renames; `Phases.md`'s new Hackathon Track section).

**Pending / not done in Hackathon Phase 1:**
- Whether to actually tint the sphere amber during the `speaking` state on
  the canvas itself (vs. just the CSS ambient halo around it) — flagged as
  an open design decision, not built, since `Design.md`'s existing state
  table doesn't specify per-state color and this would be a real behavior
  change beyond a token swap.
- A pre-existing doc inconsistency was noticed but left untouched (out of
  scope for this pass): `Phases.md`'s Phase 2 checklist still shows image
  upload/RAG/OCR as unchecked "remaining tasks," while `Memory.md`'s own
  Phase 2 log below says all of that shipped. Worth reconciling at some
  point, but not part of the rename/palette/voice work above.

## Current Status
Phases 1–4 are complete and tested end-to-end locally. Real backend, real
frontend, multi-conversation storage now scoped per-user, analytics, export,
authentication, admin panel, working model selector, and real Settings/
Profile pages (they were sidebar buttons that did nothing before this
session — now fully functional). Next up: Phase 5 (Docker, deployment,
stretch goals) — not started.

## Completed Work

**Phase 1 (backend + frontend foundation)** — see prior log entries in git
history / earlier docs if needed; short version: `gemini_retrieval.py` split
into `app/`, Flask serving a real particle-sphere frontend, streaming chat,
voice loop, weather/crypto/search tools.

**Phase 2 (understanding & tools)**:
- `app/tools/documents.py` — PDF/TXT/DOCX text extraction + chunking
- `app/ai/embeddings.py` — Gemini embeddings (`gemini-embedding-001`,
  configurable) + cosine similarity for RAG retrieval
- `app/ai/gemini_client.py` — added `stream_gemini_vision()` for image
  understanding (also covers OCR — Gemini reads text in images natively, no
  separate OCR library needed)
- `app/memory/attachment_store.py` — single active-attachment slot (document
  or image), shared across the session — see Known Issues
- `app/api/routes.py` — `/api/upload`, `/api/attachment` (GET/DELETE)
- Frontend: real attach button (file picker → upload → chip shown above
  composer), attachment feeds into the next chat turn automatically

**Phase 2b (ChatGPT/Claude-style redesign, per user's spec doc)**:
- Page-level scroll instead of a boxed chat window — `.messages` no longer
  has its own `overflow-y`, whole page scrolls
- Orb repositioned: docked fixed at right-center in chat mode instead of
  shrinking to the top. Required refactoring `particle-sphere.js` into a
  factory (`createNimbusSphere(canvasId, labelId)` — renamed to
  `createCindrixSphere` in the Cindrix rename, see below) so the landing orb and
  the docked chat orb are independent instances — a single canvas can't be
  smoothly CSS-animated between `position:static` and `position:fixed`, so
  the "movement" is actually a crossfade between two orbs, not one orb
  physically translating. Looks continuous, isn't literally one element.
- Quick-action chips move into a `+` attach-menu popover once chat starts
  (landing keeps them inline, per spec)
- Sticky composer, sticky topbar, extended markdown (tables, lists, images,
  **headings, horizontal rules** — these were missing in the first pass and
  showed as literal `###`/`---` text until fixed), syntax highlighting via
  highlight.js (CDN — can't verify rendering in this sandbox, no internet
  access there; wiring confirmed correct)
- Copy + regenerate buttons work fully. **Edit message is simplified** — it
  refills the composer rather than truly branching/truncating conversation
  history, because the backend had no message IDs at the time. Phase 3's
  conversation_store.py now has per-message structure, so real edit-with-
  truncation is feasible if it's ever worth doing — not done yet.
- Fixed two real bugs post-launch: (1) `.attachment-chip{display:flex}` was
  overriding the browser's `[hidden]{display:none}` default — added a global
  `[hidden]{display:none !important}` rule so `el.hidden=true` always works
  regardless of a component's own `display`; (2) orb size/message padding
  were tuned too small for high-res displays — increased both, with a
  `min-width:1600px` tier for very large screens.
- Removed the persistent Idle/Thinking/Listening/Speaking text label per
  user feedback — the orb's motion communicates state now; the label is
  reserved for transient messages only (mic errors, "Reading file…").

**Phase 3 (insight layer)**:
- **Real multi-conversation storage** — `app/memory/conversation_store.py`,
  one JSON file per conversation under `data/conversations/`, plus an index
  file for fast listing. This replaces the single shared
  `conv_history.json` that Phase 1/2 used — that was flagged as a known
  issue and is now actually fixed. `session_memory.py` is superseded, still
  in the repo as reference, not imported by any route.
- `/api/chat` now takes a `conversation_id` in the request body and returns
  the (possibly newly-created) id via an `X-Conversation-Id` response
  header, since the response body itself is a streaming plain-text reply and
  can't carry JSON metadata inline.
- `app/analytics/events.py` — logs every chat turn (tool used, latency,
  message length) to `data/analytics_events.json`; `/api/analytics/summary`
  aggregates it (total messages, average latency, tool-usage breakdown,
  daily counts). `detect_tool()` in `router.py` is a pure classification
  function used both to answer the message AND to label the analytics event,
  specifically so the two can't drift out of sync.
- Analytics dashboard is a modal (sidebar "Analytics" button) — stat cards +
  hand-rolled bar charts (divs, not a charting library).
- Export: `/api/conversations/<id>/export?format=md|json`, downloadable from
  a topbar button.
- Sidebar "Recent" list is now real — fetched from `/api/conversations` on
  load, clicking an entry loads that full conversation via
  `GET /api/conversations/<id>`.

**Tested locally** (sandboxed — no real internet, so Gemini/embeddings/CDN
libraries tested via a stand-in SDK, not the real API): full chat flow,
weather/crypto/search tool routing, RAG over uploaded PDF/DOCX/TXT
(extraction, chunking, embedding, retrieval all confirmed), image vision
path, multi-conversation isolation (two conversations confirmed NOT to leak
messages into each other), analytics accumulation across turns, markdown
export, JSON export, conversation deletion, the `[hidden]` CSS fix, header/hr
markdown parsing against the exact structure that was broken.

**Phase 4 (accounts & scale-readiness)**:
- `app/auth/users_store.py` — JSON-based user storage (consistent with the
  rest of the project), passwords hashed with werkzeug's built-in helpers
  (already a Flask dependency, nothing new added). First user ever created
  is auto-flagged `is_admin` — simplest bootstrap, no separate setup step.
- `app/auth/current_user.py` — `current_user_id()` helper used everywhere
  data needs to be scoped; returns the session's user_id or `"guest"`. Not
  logging in still works, on purpose — everything just lands in a shared
  guest bucket, same as the whole app's behavior before this phase.
- `app/api/auth_routes.py` — `/api/auth/signup`, `/login`, `/logout`, `/me`
  (GET + PATCH for display name), `/change-password`
- `app/api/admin_routes.py` — `/api/admin/users` (list + per-user
  conversation/message counts), `/api/admin/stats`, both gated by `is_admin`
- **Real architectural change**: `conversation_store.py` and
  `attachment_store.py` both now take a `user_id` parameter and store under
  per-user subdirectories/files instead of one global location. Every route
  in `routes.py` that touches conversations, attachments, or analytics now
  calls `current_user_id()` first.
- **Model selector**: `settings.AVAILABLE_MODELS` lists three real,
  verified-current Gemini model ids. `gemini_client.py`'s `call_gemini()`/
  `stream_gemini()`/`stream_gemini_vision()` all accept an optional `model`
  param, validated against the allowed list (`_resolve_model()`) before it
  can reach the actual API call — an unexpected string from the client
  can't become an arbitrary model name in the request.
- **Settings and Profile pages** — these were sidebar buttons that did
  nothing (flagged directly by the user). Now real modals: Profile shows
  account info + join date + admin badge + logout; Settings has display
  name editing and password change, both wired to the backend and tested.
  Both gracefully handle the guest (not-logged-in) case by prompting sign-in
  instead of erroring.

**Tested locally** (same sandboxed caveat as before — stand-in SDK, not real
Gemini): signup, login, logout, login-with-wrong-password (correctly
rejected), two-account conversation isolation (verified neither account's
messages leak into the other's conversation list), admin access control
(non-admin correctly gets 403, admin gets the full user list), display name
update, password change (old password correctly rejected after the change,
new password correctly accepted), and model override (valid id changes which
model answers, invalid id safely falls back to the default instead of
erroring or reaching the API with a bad value).

## Pending / Next Up
- Phase 5: Docker, CI, deployment, stretch goals (not started)
- Real intent classification to replace the regex-based router (still open,
  not scheduled to a specific phase)
- True edit-message (branch/truncate conversation history) — feasible given
  conversation_store.py's structure, not yet built
- Search within conversation history (Phase 3 shipped browsing, not search)
- Attachments are scoped per-user now (Phase 4), but still a single slot per
  user rather than per-conversation — a user with two open conversations
  shares one active attachment between them
- Sessions use a randomly-generated secret key if `FLASK_SECRET_KEY` isn't
  set in `.env`, which means sessions don't survive a server restart — fine
  for local dev, needs a real fixed secret before deploying anywhere

## Architecture Decisions Log
| Date | Decision | Reasoning |
|---|---|---|
| Phase 1 | Backend = Flask, JSON storage over SQLite (for now) | Simpler for a solo intern project |
| Phase 1 | Project renamed AURA AI -> NIMBUS, mascot -> particle sphere | Avoid Baymax/JARVIS IP resemblance; original design |
| Phase 1 | `google-generativeai` SDK + `gemini-1.5-flash` -> `google-genai` SDK + `gemini-flash-latest` | Old SDK/model fully shut down (hit a live 404); `-latest` alias avoids repeating this |
| Phase 2 | No separate OCR library | Gemini's vision endpoint reads text in images natively |
| Phase 2b | Two orb instances (factory-based `particle-sphere.js`) instead of one moved element | CSS can't animate `position:static` -> `position:fixed` smoothly; crossfade between two instances achieves the same visual effect |
| Phase 2b | Edit-message simplified to composer-refill | No message IDs existed yet for true history branching |
| Phase 3 | Replaced shared `conv_history.json` with per-conversation JSON files | This was Phase 1/2's biggest known issue — real conversation history browsing required it |
| Phase 3 | `X-Conversation-Id` response header instead of restructuring the streaming response format | Keeps `/api/chat`'s body a plain text stream (simple for the frontend reader) while still returning the id |
| Phase 3 | Hand-rolled bar-chart analytics UI, no charting library | Consistent with the project's existing pattern of hand-rolling small UI pieces rather than adding dependencies for simple needs |
| Phase 4 | Session-based auth (Flask signed cookies), not tokens/JWT | Same-origin SPA talking to its own backend — no cross-origin API consumers to justify token complexity |
| Phase 4 | Not logging in still works (falls into a shared "guest" bucket) | Didn't want to force an account just to try the app; matches how the whole project behaved before this phase |
| Phase 4 | First user ever created is auto-flagged admin | Simplest possible bootstrap for the admin panel — no separate seed script or manual DB edit needed |
| Phase 4 | Model selector offers 3 real Gemini model ids, not fabricated multi-provider options | Honest to what's actually implemented; `gemini_client.py`'s structure is still ready for a genuinely different provider later |
| Phase 4 | Server validates the model id against an allow-list before it reaches the Gemini API call | An unexpected string from the client should never become an arbitrary model name in a live API request |

## Post-Launch Fixes (after Phase 3 testing in the browser)
- **Topbar border gap + horizontal scrollbar** — `.app.chat-active .main { padding-right: 260px/320px }` (added to reserve visual space for the docked orb) was adding to total page width, causing a horizontal scrollbar and shortening the topbar's border since the topbar sits inside that padded box. Removed entirely — the centered `.messages` column already leaves enough natural gap from the orb at normal widths without it.
- **Voice kept resetting to the default system voice** — `loadVoices()` rebuilt the voice `<select>` from scratch every time the browser fired `onvoiceschanged` (which can fire more than once), silently resetting the selection to whatever ended up first in the list. Fixed by capturing the previously-selected voice name before rebuilding and restoring it afterward if it still exists.
- **Sandbox filesystem corruption incident** — mid-session, a filesystem issue silently zeroed out most backend `.py` files and all frontend JS/CSS files across several `cp -r` directory copies. The zip handed over at that point (`nimbus-phase2b-full.zip`) was corrupted — it passed `unzip -t` but most files inside were empty. Full rebuild from scratch was required, verified by exact byte-size matches to pre-corruption sizes, Python compile checks, JS syntax checks, HTML/JS id cross-referencing, and a live server test from an independently re-extracted copy. If anything seems to be missing or behaving like an earlier version, a full re-extraction (not a merge) is the safest fix.

## Known Issues
- Attachments (documents/images) are now per-user (Phase 4 fixed the global
  slot) but still not per-conversation — one user's two open conversations
  share the same active attachment
- Router is still keyword/regex-based, not true intent recognition
- No automated tests yet
- highlight.js loads from a CDN — untested in a fully offline environment;
  fine for normal local dev with internet access
- Session secret key is randomly generated per-run if `FLASK_SECRET_KEY`
  isn't set — sessions won't survive a server restart until that's set in
  `.env`

## Notes for the Next AI Session
- Read `PRD.md` -> `Architecture.md` -> `Rules.md` -> current phase in `Phases.md`
  -> `Design.md`, in that order, before writing code.
- Do not skip ahead of the current phase (Phase 4 is next).
- Update this file before ending the session, even if the milestone isn't fully
  done — note what's mid-flight so the next session can resume cleanly.