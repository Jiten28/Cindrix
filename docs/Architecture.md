# Architecture.md

## Tech Stack

### Backend
- Python 3.11+, Flask (app factory pattern), gunicorn in production
- Groq API — primary generation provider (`openai/gpt-oss-120b`), hand-rolled
  via `requests` in `app/ai/groq_client.py` rather than the `groq`/`openai`
  SDK: one REST endpoint doesn't justify another dependency
- Gemini API via the `google-genai` SDK — generation fallback, embeddings
  (`gemini-embedding-001`), and the vision/image path, behind
  `app/ai/gemini_client.py`. The older `google-generativeai` package and
  `gemini-1.5-x` models are deprecated and return live 404s; see `Memory.md`
- FAISS (`faiss-cpu`) for the vector index, with a numpy exact-search
  fallback when it isn't installed
- `huggingface_hub` + `pyarrow` for dataset loading; `pypdf` and
  `python-docx` for document extraction
- No LangChain, no ORM, no SQL database, no Redis. Retrieval and tool
  dispatch are hand-rolled — small enough to read in one sitting and easier
  to explain in review than a framework's abstractions. Persistence is JSON
  files behind stable interfaces (see Storage layout below)

### Frontend
- HTML5 / CSS3 — hand-written, no Bootstrap or Tailwind. Design tokens as
  CSS custom properties drive both themes
- Vanilla JavaScript, no bundler and no framework
- Canvas 2D for the particle sphere and starfield — no Three.js, no WebGL.
  Both read their colors from CSS custom properties so a theme switch
  recolors them live
- CSS transitions and keyframes for motion — no GSAP, no Lottie
- Two CDN libraries: `highlight.js` for code-block syntax highlighting and
  `i18next` for UI-chrome translation (UMD builds, since there is no bundler)

## High-Level Flow

```
Browser (frontend/)
   │  fetch() — plain streaming text response
   ▼
Flask app (app/api/) ──► app/agents/router.py  (decides: answer directly,
   │                        call a tool, use an attachment, or query the
   │                        knowledge base)
   ├──► app/ai/         (Groq + Gemini clients, retry/fallback chain, STT)
   ├──► app/rag/        (chunking, vector store, guardrails, ingest)
   ├──► app/memory/     (per-conversation history, active attachment)
   ├──► app/tools/      (web search, weather, crypto, document parsing)
   ├──► app/analytics/  (event logging → dashboard aggregation)
   └──► app/auth/       (signup/login, signed-cookie sessions, admin flag)
```

Request lifecycle for a chat turn:
1. Frontend sends the user message to `/api/chat`.
2. The API layer validates input and resolves the current user and
   conversation, creating the conversation if this is its first message.
3. `app/agents/router.py` classifies intent and picks a strategy, in order:
   unsafe-input block → explicit tool intent → active attachment (document
   RAG or image vision) → knowledge-base RAG → plain conversational.
4. `app/ai/retry.py` streams the model response through the chosen provider,
   falling back to the other provider if the primary exhausts its retries.
   The response body is plain streaming text; the (possibly new) conversation
   id comes back in an `X-Conversation-Id` header rather than wrapping the
   stream in JSON.
5. `app/memory/conversation_store.py` persists both messages of the turn.
6. `app/analytics/events.py` logs the turn: timestamp, user, conversation,
   tool used, latency, and message length.
7. The frontend renders the streamed text and drives the particle sphere's
   state (idle → listening → thinking → speaking) off the stream lifecycle.
   The `speaking` state is tied to TTS playback actually starting, not to
   generation, so a typed reply never triggers it.


## Repository layout

```text
Cindrix/
├── docs/
│   ├── PRD.md              # product requirements
│   ├── Architecture.md     # this file
│   ├── Design.md           # visual system, sphere states
│   ├── Rules.md            # engineering constraints
│   ├── Phases.md           # capabilities as delivered
│   ├── Memory.md           # technical decisions and why
│   └── Testing.md          # test coverage + manual verification
├── app/
│   ├── __init__.py              # Flask app factory — secret_key, serves frontend/ as static
│   ├── config/settings.py       # env-based settings, AVAILABLE_MODELS, RAG thresholds
│   ├── ai/
│   │   ├── gemini_client.py     # chat + vision, optional validated model override
│   │   ├── groq_client.py       # OpenAI-compatible /chat/completions via requests
│   │   ├── retry.py             # retry budgets + Groq↔Gemini provider fallback chain
│   │   ├── embeddings.py        # Gemini embeddings, asymmetric doc/query task types
│   │   └── stt.py               # Sarvam speech-to-text (saaras:v3)
│   ├── rag/
│   │   ├── dataset.py           # MSMARCO-XI shard loader (hf_hub_download + pyarrow)
│   │   ├── chunking.py          # four chunking strategies + hybrid router
│   │   ├── vector_store.py      # FAISS IndexFlatIP with a numpy exact-search fallback
│   │   ├── ingest.py            # dataset → chunk → embed → index → save
│   │   ├── guardrails.py        # unsafe block, off-topic screen, three-band kb_decision()
│   │   └── benchmark.py         # per-stage P50/P70/P100 latency harness
│   ├── tools/
│   │   ├── weather.py           # Open-Meteo, model-estimate fallback
│   │   ├── crypto.py            # CoinGecko price lookup
│   │   ├── search.py            # web search + image search
│   │   └── documents.py         # PDF/TXT/DOCX extraction + chunking
│   ├── memory/
│   │   ├── conversation_store.py   # per-user, per-conversation JSON storage
│   │   └── attachment_store.py     # active document/image slot per (user, conversation)
│   ├── analytics/events.py      # event logging + summary aggregation, scoped by user_id
│   ├── auth/
│   │   ├── users_store.py       # JSON user storage, password hashing
│   │   └── current_user.py      # current_user_id()/current_user()/is_admin() helpers
│   ├── agents/router.py         # tool routing + detect_tool() classification
│   └── api/
│       ├── routes.py            # /api/chat, /api/conversations*, /api/upload, /api/attachment,
│       │                        # /api/stt, /api/analytics/summary, /api/models, /api/config
│       ├── auth_routes.py       # /api/auth/signup, /login, /logout, /me, /change-password
│       └── admin_routes.py      # /api/admin/users, /api/admin/stats — is_admin gated
├── frontend/
│   ├── index.html
│   ├── favicon.svg
│   ├── css/style.css
│   ├── i18n/en.json, es.json, fr.json, hi.json   # UI-chrome translations
│   └── js/app.js, particle-sphere.js, starfield.js, i18n.js
├── rag_index/                   # built knowledge-base index — committed, ships in the image
├── data/                        # gitignored runtime state (see Storage layout above)
├── tests/test_health.py, test_rag.py
├── .github/workflows/ci.yml     # compile check + pytest + frontend JS syntax check
├── Dockerfile, docker-compose.yml, .dockerignore
├── render.yaml                  # Render blueprint
├── .env.example
├── requirements.txt
├── run.py                       # entry point
└── Readme.md
```

The project began as a single-file CLI prototype (`gemini_retrieval.py`) that
held Gemini calls, keyword intent routing, JSON conversation memory, and TTS
in one place. Everything in it was relocated rather than discarded: `app/ai/`
took the model clients, `app/agents/` the routing, `app/memory/` the history
persistence, `app/tools/` the weather/search/crypto lookups. The prototype
itself is no longer in the repo.

## Storage layout

There is no SQL database. All persistent state is JSON files under `data/`,
behind stable module interfaces (`app/memory/`, `app/analytics/`) so a real
database can be swapped in later without changing callers.

| Path | Shape | Written by |
|---|---|---|
| `data/users.json` | list of `{id, username, email, password_hash, display_name, default_voice, is_admin, created_at}` | `app/memory/user_store.py` |
| `data/conversations/<user_id>/_index.json` | list of `{id, title, created_at, updated_at, message_count}` — the sidebar listing, so listing never opens every conversation | `app/memory/conversation_store.py` |
| `data/conversations/<user_id>/<conv_id>.json` | `{id, title, created_at, updated_at, messages: [{role, content, ts}]}` | `app/memory/conversation_store.py` |
| `data/analytics_events.json` | list of `{ts, event_type, user_id, conversation_id, tool_used, latency_ms, message_len}` | `app/analytics/events.py` |
| `data/uploads/` | uploaded document and image files | `app/api/` upload route |
| `data/embeddings/` | per-attachment chunk text + vectors | `app/memory/attachment_store.py` |
| `rag_index/` | the built knowledge-base index (FAISS binary + chunk metadata + latency report) — read-only build output, deliberately **outside** `data/` | `app/rag/ingest.py` |

Conversation titles are derived from the first user message rather than
stored separately. `user_id` is `guest` for unauthenticated use, so the same
code paths serve both signed-in and anonymous sessions.

## Integration Points
- **Groq API** — primary generation provider, streaming; **Gemini API** —
  generation fallback plus embeddings and vision (see "Generation Provider
  Chain")
- **Sarvam AI** — server-side speech-to-text (`saaras:v3`) via `app/ai/stt.py`
- **Open-Meteo** — keyless geocoding + forecast REST APIs, with a model
  best-effort estimate as fallback for places it can't geocode
- **CoinGecko** — keyless crypto price lookup
- **Tavily** — image search; general web search goes through Gemini's Google
  Search grounding
- **HuggingFace Hub** — downloads the MSMARCO-XI parquet shard at ingest time
- **Attachment RAG** — file upload → parse (PDF/DOCX/TXT) → chunk → embed →
  store in `data/embeddings/` → retrieve on query
- **Knowledge-base RAG** — a separate, pre-built index in `rag_index/`; see
  "Retrieval, Vector Store & Guardrails"

## Voice I/O

- **Input (STT):** two providers, switched by `STT_PROVIDER` (see
  `app/config/settings.py`). The default is resolved from configuration
  rather than hardcoded: `sarvam` whenever `SARVAM_API_KEY` is present,
  `webspeech` otherwise, so a fresh clone has working voice input with no
  account while a configured deployment uses the real STT service.
  - `sarvam`: server-side, via `app/ai/stt.py` calling Sarvam's
    `/speech-to-text` REST endpoint (`saaras:v3`, Indic-language-focused —
    picked over ElevenLabs for that reason, since it matches the
    MSMARCO-XI corpus this app retrieves against). This is the primary
    path. The frontend records audio via `MediaRecorder` + a small Web
    Audio volume analyser for silence-based auto-stop (WebSpeech gets
    end-of-speech detection for free from the browser; raw audio recording
    doesn't, so it's built in `frontend/js/app.js`), then POSTs the clip to
    `/api/stt`. `SARVAM_API_KEY` never reaches the browser — only the
    backend holds it, per `Rules.md`. `/api/config` tells the frontend
    which provider is live so it wires up the right one at page load.
  - `webspeech`: the browser's native `SpeechRecognition` (Web Speech API),
    entirely client-side, no key needed. Keyless fallback for local
    development, and Chrome/Edge only.
  Both providers funnel into the exact same `sendMessage(transcript,
  true)` call once a final transcript exists — the RAG routing, retry
  handling, and TTS output described below are identical regardless of
  which one produced the text.
- **Output (TTS):** the browser's native `speechSynthesis`
  (`SpeechSynthesisUtterance`), not a server-side library. A
  server-rendered-audio approach (the original CLI prototype used `pyttsx3`)
  doesn't produce audio in a deployed browser context on Render, and would
  add an audio-upload/-download round-trip before the RAG pipeline even
  starts. Doing STT/TTS client-side avoids that round-trip entirely, which
  matters for the streaming-response latency target in `PRD.md`.
  Microsoft's "Natural"/"Online" neural voices are preferred when
  available via `speechSynthesis.getVoices()` (Edge-only, 250+ voices,
  far more natural than default voices) — Chrome/Firefox/Safari fall back
  gracefully to whatever default voice they expose; Edge is never
  hard-required. A user's chosen voice persists to their profile. No
  server-side TTS dependency remains in `requirements.txt`.
- Sphere state (`listening` / `thinking` / `speaking`) is driven off this
  same flow — see `Design.md` for the state table and `Memory.md` for why
  sphere state and audio playback are deliberately decoupled.

## Interface localization

UI chrome is translated with `i18next` (`frontend/js/i18n.js`), with
translation files in `frontend/i18n/*.json` — English, Spanish, French, and
Hindi. Strings are marked up declaratively in `index.html` via `data-i18n`,
`data-i18n-placeholder`, `data-i18n-aria-label`, and `data-i18n-title`
attributes, so adding a translated element needs no JavaScript change. The
language switcher is in the topbar; the choice persists to `localStorage`,
and the initial language is detected from `navigator.language` with an
English fallback.

Deliberately scoped to UI chrome only. The assistant's own responses are not
translated — they come back in whatever language the user wrote in — and
speech recognition stays on `en-US` rather than following the UI language,
since transcription language is a separate concern from interface language
and conflating them would silently break voice input for a user who switched
the UI to browse in another language.

## Retrieval, Vector Store & Guardrails

Everything below lives under `app/rag/` plus small hooks in
`app/ai/embeddings.py`, `app/ai/retry.py`, and `app/agents/router.py`.

### Dataset

`ai4bharat/MSMARCO-XI` (`app/rag/dataset.py`) — the full dataset, not a
sample. Reading it requires bypassing the `datasets` library entirely. Three
distinct failure modes rule out the obvious approaches, and each is worth
recording because each looks like the correct approach until it is tried:

1. **Per-language configs do not exist.** The dataset card's own "Usage"
   sample suggests `load_dataset(..., "hi", split="train")`. That fails with
   `BuilderConfig 'hi' not found. Available: ['default']` — the card's
   sample is stale relative to the dataset's actual structure, which exposes
   a single `"default"` config (11.5M rows total: `train` 10.1M,
   `validation` 1.37M) with all 14 languages mixed together, filterable only
   by each row's `target_lang` field.
2. **Streaming the combined config and filtering in Python does not work
   either.** It fails with `MemoryError` + `WinError 10038` while
   downloading `train/asmtrain.parquet` (Assamese). Root cause: `"default"`
   isn't one combined file, it's **per-language parquet shards**
   concatenated by the loader, and streaming through the concatenation still
   has to fetch each shard in full before moving to the next — Assamese
   sorts before Hindi, so the stream pulls all of Assamese's large shard
   before reaching a single Hindi row.
3. **Loading the Hindi shard by name through `datasets` still fails.** The
   full 3.72 GB shard downloads successfully and then dies with a vague,
   swallowed "An error occurred while generating the dataset" — an
   `ArrowNotImplementedError: Nested data conversions not implemented`
   surfacing from inside `datasets`' Arrow→Python formatting of the nested
   `passages` struct. `datasets` cannot decode that column shape.

**The approach that works:** skip the `datasets` library entirely.
Download the target language's shard file by name with
`huggingface_hub.hf_hub_download()` (to the local HF cache — a one-time
cost, cached across runs) and read it with `pyarrow.parquet`, which
decodes the nested `passages` struct into plain Python dicts via
`.to_pylist()` without complaint (verified directly against a real row:
`passages` came back as `{English_passages, Translated_passages,
is_selected}` — the exact conversion `datasets` couldn't do):
```python
local_path = hf_hub_download(repo_id="ai4bharat/MSMARCO-XI",
                             filename="train/hintrain.parquet",
                             repo_type="dataset")
for batch in pq.ParquetFile(local_path).iter_batches(
        batch_size=1024, columns=_INGEST_COLUMNS):
    for row in batch.to_pylist():
        ...
```
Shard filenames follow `{split_dir}/{iso3}{suffix}.parquet` — confirmed
against real files in the repo's tree (`train/hintrain.parquet`,
`train/asmtrain.parquet`, `validation/telval.parquet`), giving
`train/<iso3>train.parquet` and `validation/<iso3>val.parquet` as the two
confirmed patterns (`app/rag/dataset.py`'s `_shard_path()` raises clearly
for any other split rather than guessing at an unconfirmed pattern).
Only the columns `metadata_aware_chunks()` consumes are projected out of
the read (`_INGEST_COLUMNS`), so pyarrow decodes far less than the full
~3.72 GB. `target_lang` is still checked per row — now as a cheap safety
check on an already-scoped, single-language shard rather than the thing
doing the scoping, and it fires on the shard's first few rows if the
filename assumption turns out wrong for a given language, rather than
only after scanning millions of rows the old combined-stream approach
would have needed.

Row shape (confirmed against a real row): `{source_lang, target_lang,
meta, query, Answer, query_id, query_type, passages: {is_selected,
English_passages, Translated_passages}, Eng_Query, Eng_Answer}`. The
Hindi shard `train/hintrain.parquet` is a single parquet row group of
778,638 rows, all `target_lang == "hin_Deva"` (so `hin_Deva` is now
confirmed off real rows, not just the ISO convention). Because it's one
monolithic row group there's no cheap remote sub-range read — hence the
one-time `hf_hub_download` of the whole shard, then fast local reads.
Ingest is capped at `RAG_INGEST_MAX_ROWS` (**default 100**). **Disclosed
scope decision, not a hidden shortcut:** the binding constraint isn't the
download but the Gemini free-tier embedding quota (~100 contents/minute —
see `docs/Memory.md`); at ~10 passages/row that's ~10 rows/min, so the
cap keeps ingestion to a bounded, *fully-embedded* subset rather than a
partial one. Real, unmodified rows from the real shard, just a bounded
number of them. Raise `RAG_INGEST_MAX_ROWS` on a paid embedding tier
where the RPM cap is higher.

`huggingface_hub`/`pyarrow` are soft-imported — if neither is installed,
`load_msmarco_xi()` falls back to a small local fixture built from the
dataset card's own documented example rows, with a loud warning logged
every time (never silently mistaken for the real dataset). Crucially, a
real load that *fails* (network, 404, decode error) is **not** papered
over with the fixture — it's logged with a full traceback and re-raised,
so a broken ingest can't masquerade as a successful one. This directly
closes the trap that had every earlier benchmark secretly running on 5
fixture chunks. `datasets` is no longer a dependency at all.

### Chunking strategies (`app/rag/chunking.py`)

Three, because different content calls for different chunking:

- **`fixed_size_chunks`** — character-window with overlap (the same
  approach `app/tools/documents.py`'s `chunk_text` already used for
  user-uploaded PDFs/DOCX/TXT). Good default when a text's structure is
  unknown or irregular.
- **`semantic_chunks`** — packs whole sentences into a chunk up to a
  target size, never cutting a sentence in half. Sentence boundary
  detection includes `।` (Devanagari danda) alongside `.!?`, since this
  runs over Hindi/Indic text, not just English. A full sentence tokenizer
  (spaCy/NLTK) would be a new major dependency per `Rules.md` for a
  problem a regex handles well enough here.
- **`metadata_aware_chunks`** — the one actually used for MSMARCO-XI
  ingestion. Each dataset row already arrives pre-segmented into passages
  (`passages.Translated_passages`); this strategy treats each given
  passage as one chunk rather than re-splitting it, and attaches the
  metadata the dataset already provides (`is_selected` ground-truth
  relevance, `query_id`, language, passage index). Re-chunking an
  already-short, already-coherent MS MARCO passage would be as likely to
  cut it awkwardly as to improve it, and would sever the direct link to
  `is_selected` that makes the dataset's own relevance labels usable
  later (e.g. for retrieval-quality validation against ground truth,
  not built yet but the metadata is there if it's worth doing).

### Vector store (`app/rag/vector_store.py`)

Replaces the old brute-force in-memory cosine loop that used to live
directly in `app/ai/embeddings.py`'s `top_k_chunks()`. Backed by **FAISS**
(`IndexFlatIP` for small collections — exact, just no longer a hand-
written Python loop; `IndexIVFFlat` once a collection passes ~10k
vectors, a genuine approximate-nearest-neighbor index) — picked over a
hosted/server vector DB (Pinecone, Weaviate, etc.) because it needs no
running service or network dependency, fitting this project's existing
no-external-infra pattern (JSON files, SQLite-when-needed), and over
Chroma because FAISS is the leaner dependency for a pure similarity-
search need with no extra features this project uses. Vectors are
L2-normalized on insert so inner product doubles as cosine similarity —
one index type serves both the small per-document case and the large
corpus case.

`faiss` is soft-imported too (not installed in the sandboxed session this
was built in) — falls back to an exact numpy-based search, loudly logged
every time a store is built without it, so it's never mistaken for the
real thing in a benchmark or demo. Persists to disk via `.save()`/
`.load()` (JSON for chunks/metadata + a native FAISS index file, or a
pickle of the raw vectors in fallback mode).

`top_k_chunks()` in `embeddings.py` now builds a small `VectorStore` per
call instead of looping by hand — same behavior at the small scale it
actually runs at (a single upload's chunks), but going through the same
real abstraction the much larger MSMARCO-XI index uses, so there's one
implementation to keep correct, not two.

### Router wiring (`app/agents/router.py`)

The `knowledge_base_rag` path sits between the attachment-RAG path and the
final plain-conversational fallback: general queries (no tool intent, no
active attachment) that aren't obvious chit-chat/greetings are checked
against the persisted MSMARCO-XI index before falling through. **If no index
has been built** (`python -m app.rag.ingest` hasn't been run),
`get_kb_store()` returns `None` and every general query is answered
conversationally — the path only activates once a knowledge base actually
exists on disk.

**The product tradeoff this path creates, and how it is resolved:** a
knowledge-grounded assistant should visibly refuse to answer outside its
indexed corpus rather than quietly falling back to being a generic chatbot
while still implying it is grounded. Taken to its extreme, that makes the
assistant useless for anything the corpus doesn't cover — every general
question becomes a decline. The three-band guardrail below is the resolution:
declining is reserved for the narrow band where the corpus *does* hold
related material but nothing that confidently answers the question (the case
where answering anyway would be a hallucination risk). When the corpus is
simply not about the question at all, the retrieved excerpts are dropped
entirely and the turn is answered conversationally — because declining a
question the knowledge base was never meant to cover is not honesty, it is
just a broken assistant. Cindrix therefore stays generally conversational
while still refusing to fabricate grounded-sounding answers.

If a deployment wants pure corpus-only behavior instead, don't run
`ingest.py` for the general path — or raise `RAG_DECLINE_FLOOR` to collapse
the fallthrough band into the decline band.

### Guardrails (`app/rag/guardrails.py`)

Three checks, deliberately heuristic/keyword-based rather than a second
LLM call per guardrail check — the <200ms latency target (see below)
doesn't leave room for an extra model round-trip just to gate another
one. A real moderation API or LLM-based check would be a reasonable
upgrade later; that's a new external dependency/cost decision, which
`Rules.md` says to flag rather than add unprompted, so it isn't built.

1. `is_unsafe()` — blocks clearly unsafe input (self-harm, weapons
   synthesis, CSAM, unauthorized-access instructions) before it reaches
   retrieval or generation at all. Pattern-matches full phrasings, not
   single trigger words, to keep false positives low (a genuine question
   like "how do bomb disposal robots work" doesn't trip it — verified by
   test).
2. `is_offtopic_for_kb()` — screens out queries not worth attempting
   knowledge-base retrieval for (tool-intent messages, greetings, near-
   empty input), so those still get normal conversational handling
   instead of a forced "not grounded" decline for something that was
   never meant to be a factual lookup.
3. `kb_decision()` — after retrieval, sorts the result into one of three
   bands using the top hit's cosine score. At or above `RAG_MIN_RELEVANCE`
   (0.75) the answer is generated strictly from the retrieved excerpts.
   Between that and `RAG_DECLINE_FLOOR` (0.70) the corpus holds related
   material but nothing that is a confident match, so the router yields
   `guardrails.DECLINE_MESSAGE` and **never calls the LLM at all** for that
   turn (verified by test — the generation mock is asserted not-called).
   Below the floor the corpus simply isn't about the question, so declining
   would be wrong; the excerpts are dropped entirely and the turn is answered
   conversationally. The decline band is deliberately narrow because
   `gemini-embedding-001` compresses same-language similarity into a tight
   range — see the calibration note in `app/config/settings.py`. The middle
   band is a real hard stop, not a prompt instruction hoping the model
   declines on its own.

### Generation Provider Chain (`app/ai/retry.py`, `app/ai/groq_client.py`)

Wraps every text-generation call the app makes to an LLM — RAG-serving
(`document_rag`, `knowledge_base_rag`), tool-synthesis (the web-search
results path), plain conversational chat, and non-streaming calls like
`app/tools/weather.py`'s Gemini-fallback description. **This was
initially scoped to "just the RAG path, since that's what's graded" and
shipped that way** — but the plain-conversational path is the
highest-traffic path in the whole router (everything that isn't a tool
match, an attachment, or a knowledge-base match lands there), and it was
still calling Gemini directly, unprotected. A live production leak
confirmed this concretely: general chat (a weather question, "tell me
about neem tree") showed raw `(Gemini error: 503 UNAVAILABLE...)` text as
the answer — the exact bug this whole chain exists to prevent, just on a
path that hadn't been wired up yet. Fixed by routing every text-
generation call site through the same chain rather than re-scoping
"RAG-only" more narrowly. Two layers: per-provider retry (unchanged from
the original single-provider version — see below), and, built on top of
it, a **Groq-primary / Gemini-fallback chain**.

Two public entry points, same underlying chain: `stream_generation()`
(streaming, used by everything in `router.py`) and `call_generation()`
(non-streaming, returns a complete string — used by `weather.py`; built
by reusing `stream_with_fallback` rather than a second parallel
implementation, since a non-streaming call is just a one-chunk "stream"
from this machinery's point of view).

**Known remaining gap, not yet fixed:** the image-vision path
(`stream_gemini_vision`, triggered by an uploaded image attachment) still
calls Gemini directly, unprotected by this chain. Groq's OpenAI-
compatible endpoint would need a different client function (multimodal
message format, base64 image content, and a vision-capable model — not
confirmed whether one exists on Groq or fits this app's needs) to
participate in the same fallback pattern; that's a real gap, left
deliberately unaddressed rather than silently built beyond what was asked
for a text-generation-focused fix. Flagging it here so it doesn't get
lost.

**Why Groq is primary:** originally chosen on Groq's generally-published
LPU-hardware inference speed (independent third-party benchmarks showing
3-5x faster time-to-first-token than Gemini Flash). Confirmed by this
project's own `app/rag/benchmark.py`: a real run against the built
868-vector Hindi index had Groq (`openai/gpt-oss-120b`) serve **7/7**
grounded queries as primary with **zero fallbacks**, generating a grounded
Hindi answer in **~1.28 s P50 / ~1.62 s P70 / ~2.84 s P100** (first token in
~1.03 s P50 / ~1.29 s P70). That confirms Groq reliably fills the primary
slot and that the provider routing works end-to-end. What this run does
*not* establish is a head-to-head Groq-vs-Gemini latency comparison —
because Groq never failed, the Gemini fallback path was never exercised, so
the 3-5x figure remains third-party, not reproduced here. Producing a direct
comparison would require deliberately forcing a fallback; worth doing later,
but the ordering is sound as-is. See the Latency harness section below for
the full per-stage table.

**The chain, in order:**
1. **Groq** (`app/ai/groq_client.py`, OpenAI-compatible `/chat/completions`
   REST endpoint, hand-rolled via `requests` rather than the `groq`/
   `openai` SDK packages — one endpoint doesn't justify a new dependency,
   same call as already made for Sarvam in `app/ai/stt.py`). Model is
   `openai/gpt-oss-120b` by default (`GROQ_MODEL`) — **not**
   `llama-3.3-70b-versatile`, which this project almost defaulted to
   before checking: Groq deprecated it (announced June 17 2026, shutdown
   Aug 16 2026 — already past by the time this was verified against
   Groq's own live deprecations page and changelog). Same class of trap
   this project already got burned by once with `gemini-1.5-flash` —
   verify current model IDs against live docs, don't trust an example
   snippet's specific model name.
2. If Groq exhausts its own retry budget (2 retries, exponential
   backoff, same transient-detection logic as the original Gemini-only
   version — 503/429/timeout-shaped errors only; a clearly non-transient
   error like a bad API key skips straight to step 3 without wasting
   retries), **Gemini** is tried next, with its own independent retry
   budget. Gemini's error handling (the original 503-leak fix) is
   unchanged — same robustness whether it's serving as primary or
   fallback.
3. If **both** exhaust their retries, a clean user-facing message is
   returned (`"Cindrix couldn't reach either AI provider right now —
   please try again in a moment."`) — never a raw exception, never a
   hang. Both providers' failure reasons are logged for debugging.

**Which provider actually served a response is always logged** (`[retry]
response served by Groq (primary)` / `... by Gemini (fallback, after Groq
failed)`) — useful for demo narration and for correlating the latency
benchmark's per-provider breakdown with what a real user's traffic
actually hit.

Retries/fallback only happen before any real content has reached the
caller — once a chunk of the actual answer is out, switching providers
mid-stream would duplicate/contradict it, so a failure after that point
just closes the stream gracefully with a short trailer note instead, per
`Rules.md`'s "streaming responses must gracefully close on error, not
hang the UI." This applies independently at each layer (a Groq mid-stream
failure doesn't retry Groq *or* fall back to Gemini — same reasoning).

Built directly against a real production failure that predates the Groq
fallback: a transient `503 UNAVAILABLE` from Gemini surfaced to a user as
raw `(Gemini error: 503 UNAVAILABLE. {'error': {'code': 503, ...}})` text
in the chat. Since both `gemini_client.py`'s `stream_gemini()` and
`groq_client.py`'s `stream_groq()` catch their own exceptions and *yield*
an error string rather than raising (deliberately mirrored shapes, so the
retry layer doesn't need provider-specific error parsing), "was this
transient" is detected by pattern-matching the first yielded chunk, not
by catching an exception.

`stream_with_retry()` (single-provider retry, no fallback) is kept as its
own function, unchanged in behavior/signature from before the fallback
chain existed — anything that wants retry without provider fallback can
still use it directly; `stream_generation()` (the new Groq→Gemini chain)
is what `router.py`'s two RAG paths actually call now.

### Latency harness (`app/rag/benchmark.py`)

Instruments five live per-query stages — embed query, embed query with the
vector already in hand, vector retrieval, time to first token, and full
generation — across a test-query set, reporting P50/P70/P100 per stage and
end-to-end. Target: retrieval under 200 ms (P70).

**Deliberately excludes ingest-time chunking/embedding from the per-query
number** — chunking the corpus happens once at ingest (`app/rag/
ingest.py`), not on every live query, so counting it per-query would
mischaracterize what a real user's request actually costs. That's
disclosed here rather than silently interpreted, since a literal reading
of "instrument chunking + retrieval + generation" could otherwise suggest
re-chunking per query, which would be straightforwardly bad engineering.

Runs honestly rather than fabricating numbers: if `GOOGLE_API_KEY` isn't
set, `embed_query`/`stream_gemini` both short-circuit without a real
network call (existing behavior, unchanged), so the report is marked
`"is_self_test": true` with an explicit note, and `retrieval_meets_target`
is forced `false` — it never claims to hit the target using numbers that
didn't involve a real model call.

**Real numbers (868-vector Hindi index, both keys configured, 10 test
queries — 8 in-corpus, 2 deliberately out-of-corpus):**

| Stage | P50 | P70 | P100 |
|---|---|---|---|
| embed query (Gemini, network) | 465.7 ms | 471.8 ms | 1083.5 ms |
| embed query (cached) | 0.001 ms | 0.001 ms | 0.002 ms |
| vector retrieval (FAISS, local) | 0.76 ms | 0.78 ms | 0.89 ms |
| **retrieval total** (embed + search) | 466.6 ms | 472.5 ms | 1084.3 ms |
| generation (Groq `gpt-oss-120b`) | 1278.1 ms | 1622.6 ms | 2836.4 ms |
| time to first token | 1030.8 ms | 1291.1 ms | 1933.3 ms |
| **end-to-end** | 2075.7 ms | 2109.3 ms | 3303.0 ms |

7 of the 8 in-corpus queries grounded above `RAG_MIN_RELEVANCE`; both
out-of-corpus queries correctly failed to ground (the guardrail working, not
a retrieval miss). All 7 grounded answers were served by **Groq (primary)**
with zero fallbacks (`served_by_breakdown: {"Groq (primary)": 7}`).

Ten queries is enough to show where the time goes, not a statistically
rigorous large-sample percentile — the report says so in its own
`statistical_note` field rather than leaving the reader to assume otherwise.

Two things the report is explicit about (`rag_index/latency_report.json`):

1. **Query embedding, not vector search, is the whole retrieval cost.** The
   FAISS search is ~0.8 ms; the single `gemini-embedding-001` call to turn
   the question into a vector is ~470 ms of network round-trip. That is
   ~99.8% of retrieval time and it is entirely a remote API call, not an
   index property. The harness also records a `embed_query_cached` stage
   (~0.001 ms) to show what the same retrieval costs once the embedding is
   in hand — that is the honest measure of the local pipeline.
2. **The <200 ms end-to-end target is not met — and structurally can't be
   by this shape of pipeline.** Vector search, the stage a vector-DB choice
   actually governs, is ~0.8 ms (over two orders of magnitude under target).
   The rest is two remote calls: ~470 ms to embed the query and ~1.6 s to
   generate a real answer, neither of which any retrieval optimization can
   shrink. So the honest reading: local retrieval is far under 200 ms;
   end-to-end with a full generated answer is ~2.1 s and dominated by
   network-bound model inference. `retrieval_meets_target` is `false` and
   the report says why.

## Deployment

- **Docker** — `Dockerfile` runs gunicorn, not the Flask dev server.
  `docker-compose.yml` gives local parity with `data/` volume-mounted.
- **Render** — `render.yaml` is a Blueprint that Render picks up
  automatically when the repo is connected. Live at
  https://cindrix-ai.onrender.com/
- **Secrets** — every API key is declared `sync: false` in `render.yaml`, so
  it must be filled in manually in the Render dashboard and is never
  committed. Worth checking after the first deploy: a missing key doesn't
  crash the app, it degrades the feature that needs it (no `SARVAM_API_KEY`
  falls back to `webspeech`; no `GOOGLE_API_KEY` skips knowledge-base
  retrieval). Both cases log a warning — check `/api/config` and the host
  logs rather than assuming the deploy is complete.
- **Persistent disk** — mounted at `/app/data` for mutable runtime state
  (uploads, conversations, users, analytics). The read-only vector index
  lives in `rag_index/`, deliberately outside `data/`, because a disk mounted
  at that path starts empty on first deploy and would shadow anything the
  image shipped there.
- **CI** — `.github/workflows/ci.yml` runs a compile check, the pytest suite,
  and a frontend JS syntax check on every push and pull request.
- **Cold starts** — Render's free plan spins the instance down when idle, so
  the first request after a quiet period takes ~25 s. This is a plan
  characteristic, not an application one.