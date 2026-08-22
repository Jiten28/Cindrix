# Technical Decisions & Project History

This document records the significant engineering decisions behind Cindrix and
the reasoning for each — the context that isn't obvious from reading the code.
It is organized by area, not chronologically.

---

## Naming and identity

The project was renamed twice during development: AURA AI → Nimbus → Cindrix.
The particle-sphere identity (rather than a humanoid face or mascot) was chosen
deliberately to be an original design with no resemblance to existing IP.

Canonical references: the GitHub repository is
`https://github.com/Jiten28/Cindrix` and the live deployment is
`https://cindrix-ai.onrender.com/`. Older names (`Nimbus`, `Nimbus-AI`,
`AURA`) may survive in historical commit messages but are not current.

## Backend and storage

- **Flask with JSON-file storage, not SQLite.** Conversations, users,
  attachments, and analytics are stored as JSON files. This keeps the stack
  simple; the storage interface is deliberately kept stable so a database can be
  swapped in later without changing callers.
- **Per-conversation storage.** Each conversation is one JSON file under
  `data/conversations/<user_id>/`, with an index file for fast listing. This
  replaced an earlier single shared `conv_history.json` written by a
  `session_memory.py` module, since one flat file couldn't express per-user
  scoping or list conversations without loading everything.
- **Streaming response metadata via header.** `/api/chat` returns its reply as a
  streaming plain-text body and carries the (possibly newly created)
  conversation id in an `X-Conversation-Id` response header, rather than
  wrapping the stream in JSON — which keeps the frontend reader simple.
- **Per-user isolation with a guest fallback.** Conversations and attachments
  are stored per user. Using the app without an account still works; everything
  falls into a shared `guest` bucket.
- **Attachments are keyed per (user, conversation).** A document or image
  uploaded in one conversation does not bleed into another. An upload made
  before a conversation exists attaches to it once it is created.

## AI and generation stack

- **`google-genai` SDK, not `google-generativeai`.** The older SDK and its
  `gemini-1.5-flash` model were retired and returned live 404s; the current SDK
  with the `gemini-flash-latest` alias avoids repeating that.
- **Groq `openai/gpt-oss-120b`, not `llama-3.3-70b-versatile`.** The latter was
  deprecated by Groq; model ids are verified against live provider docs rather
  than trusted from examples.
- **Groq primary, Gemini fallback.** The generation path (`app/ai/retry.py`)
  tries the primary provider with its own retry budget, falls back to the other
  provider with a fresh retry budget on exhaustion, and returns a clean
  user-facing error only if both fail. Which provider served each response is
  logged. Selecting a model in the UI changes which provider is primary for that
  turn — it changes the order, not the resilience.
- **Model-override validation.** A Gemini model id from the client is validated
  against a Gemini-only allow-list (`GEMINI_MODEL_IDS`) before it can reach the
  API, so a stray string or a Groq id can never be sent as a Gemini model name.
- **Non-streaming path reuses the same machinery.** `call_generation()` is built
  on the same fallback logic as `stream_generation()` (a non-streaming call is a
  one-chunk stream), so there is one retry/fallback implementation, not two.
- **No separate OCR library.** Gemini's vision endpoint reads text in images
  natively, so image understanding and any text-in-image reading share one path.
  The image-vision path calls Gemini directly and is not covered by the
  Groq/Gemini fallback chain (a Groq vision equivalent would need a different
  client and message format).

## RAG pipeline

- **Dataset:** ai4bharat/MSMARCO-XI, Hindi shard (`hin_Deva`).
- **Direct parquet ingest, not the `datasets` library.** The HuggingFace
  `datasets` library raised `ArrowNotImplementedError` decoding the nested
  `passages` struct even with the shard fully downloaded. Ingest instead fetches
  the shard with `huggingface_hub.hf_hub_download()` and reads it with
  `pyarrow`. `datasets` is no longer a dependency, and a genuine load failure
  re-raises rather than being masked by a fixture.
- **Four chunking strategies.** Fixed-size with overlap, semantic
  sentence-packing (aware of the Devanagari danda `।`), metadata-aware passage
  units, and a hybrid router that indexes short passages whole and sub-splits
  only the long tail — with a fixed-size fallback for long passages that have no
  sentence boundary at all.
- **FAISS `IndexFlatIP` over L2-normalized vectors**, so inner product equals
  cosine similarity, with a numpy exact-search fallback when FAISS is
  unavailable. Embeddings are Gemini `gemini-embedding-001` (3072-dim),
  asymmetric between document (`RETRIEVAL_DOCUMENT`) and query
  (`RETRIEVAL_QUERY`) task types.
- **Calibrated three-band grounding decision.** Because same-language
  `gemini-embedding-001` similarity compresses into a narrow range (measured:
  true matches 0.65–0.82, out-of-domain Hindi 0.60–0.72, out-of-domain English
  0.57–0.60), a single threshold cannot separate "in the corpus" from "merely
  looks like it." So there are two bands: at or above `RAG_MIN_RELEVANCE` (0.75)
  the answer comes strictly from retrieved excerpts; between that and
  `RAG_DECLINE_FLOOR` (0.70) the system declines rather than answer from a weak
  match; below the floor the corpus isn't about the question, so it is answered
  conversationally. The decline band is deliberately narrow — it covers genuine
  ambiguity, not everything that fails to ground.
- **The index ships in the image, outside `data/`.** `rag_index/` is read-only
  build output. Keeping it out of `data/` means a hosted persistent disk mounted
  at `data/` cannot shadow the index baked into the deployed image. The shipped
  index holds 868 vectors.
- **Two Gemini free-tier embedding quotas.** There are two limits, not one: a
  per-minute cap (~100 requests/min) and a hard per-day cap (~1000 requests/day),
  each text in a batch counting individually. Batch ingest opts into a 429-retry
  budget so it can ride out the per-minute window and build a complete index;
  live query embedding deliberately does not retry, so a query never hangs
  mid-request. Chunks that cannot be embedded are logged explicitly and skipped,
  producing an honest partial index rather than a silent drop.
- **`detect_tool()` is pure classification.** The same function labels the
  analytics event and drives which path answers a turn, so the two cannot drift
  apart.

## Voice

- **Sarvam `saaras:v3` for speech-to-text**, chosen over ElevenLabs for its
  Indic-language focus, matching the corpus. The browser's Web Speech API
  remains a keyless fallback so a fresh clone has working voice input with no
  account; `STT_PROVIDER` selects between them and defaults to Sarvam whenever a
  key is present.
- **Two front-end capture paths.** The Sarvam path uses `MediaRecorder` plus a
  Web Audio silence detector for end-of-speech detection (which the Web Speech
  API provides for free); both feed the same downstream send path.
- **Text-to-speech** uses the browser's `speechSynthesis`, preferring a
  higher-quality neural voice when one is available without overriding a user's
  manual pick. A user's chosen default voice persists to their profile.
- **Sphere state and audio are decoupled.** The sphere stays in its "thinking"
  state through generation and only enters "speaking" once TTS playback actually
  begins, so a typed reply (which plays no audio) never triggers the speaking
  animation.

## Frontend and visual identity

- **Two sphere instances, not one moved element.** The landing sphere and the
  docked chat sphere are separate instances of a factory (`particle-sphere.js`).
  A single canvas cannot be smoothly animated between `position: static` and
  `position: fixed`, so the transition is a crossfade between two instances that
  reads as continuous motion.
- **Canvas reads theme colors from CSS.** The sphere and starfield read accent,
  text, and glow colors from CSS custom properties via `getComputedStyle` and
  re-read them on a `cindrix:themechange` event, so toggling the theme recolors
  them live without a reload.
- **Two themes: "Ember Violet" (dark) and "Lavender Dusk" (light).** The light
  palette was chosen to read as the same product as the dark theme (a shared
  cool violet-gray undertone), not a different mood. The saved theme is applied
  synchronously in `<head>` before first paint to avoid a flash of the wrong
  theme.
- **Hand-rolled analytics UI.** The dashboard's bar charts are plain elements,
  not a charting library — consistent with the project's preference for small
  hand-built UI over dependencies for simple needs.
- **Message editing refills the composer** rather than truly branching or
  truncating history. Per-message structure now exists in
  `conversation_store.py`, so true edit-with-truncation is feasible but not
  built.

## Key decisions at a glance

| Decision | Rationale |
|---|---|
| Flask + JSON storage over SQLite | Simplest fit; storage interface kept stable for a later swap |
| Particle sphere as the identity | Original design, no resemblance to existing IP |
| `google-genai` + `gemini-flash-latest` | Old SDK/model were retired and returned live 404s |
| Groq `gpt-oss-120b` primary, Gemini fallback | Fast primary with a resilient fallback; model ids verified against live docs |
| Validate Gemini overrides against an allow-list | A client string or Groq id must never become an arbitrary Gemini model name |
| Direct parquet ingest via `huggingface_hub` + `pyarrow` | `datasets` crashed decoding the nested `passages` struct |
| No separate OCR library | Gemini vision reads text in images natively |
| Three-band grounding (0.75 / 0.70) | Embedding similarity is too compressed for a single threshold to separate in-corpus from lookalike |
| Index shipped outside `data/` | A runtime volume mounted at `data/` would otherwise shadow the baked-in index |
| Ingest retries on 429; live query does not | Ingest must build a complete index; a live query must never hang mid-request |
| Per-conversation JSON files + `X-Conversation-Id` header | Real history browsing; keeps the streaming body plain text |
| Session-cookie auth, not tokens | Same-origin single-page app with no external API consumers |
| First account is auto-admin | Simplest admin bootstrap, no separate setup step |
| Two sphere instances with a crossfade | CSS can't smoothly animate `static` → `fixed` position |

## Known limitations

- The router classifies intent with keyword/regex matching, not a learned intent
  model.
- The image-vision path calls Gemini directly and is not protected by the
  Groq/Gemini fallback chain.
- Code blocks use a dark `highlight.js` theme in both light and dark modes; a
  light-theme code style would need a second stylesheet swapped in on theme
  change.
- Syntax highlighting loads `highlight.js` from a CDN, so it is unavailable in a
  fully offline environment.
- If `FLASK_SECRET_KEY` is unset, a random key is generated per run and sessions
  do not survive a restart; set a fixed value before deploying.
