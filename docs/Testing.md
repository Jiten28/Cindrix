# Testing.md — Manual QA Checklist (through Phase 4)

Not one of the original six planning docs — an extra one, added because the
feature surface got big enough to need a real checklist before Phase 5.
Work through this top to bottom; each section is mostly independent, but
Authentication should be tested before Admin/Model-scoping since those build
on having a real account.

## Before you start

1. `.env` has a real `GOOGLE_API_KEY` (required for anything to respond)
   and `GROQ_API_KEY` (primary generation provider — Gemini is the fallback)
2. Optional but worth having for full coverage: `TAVILY_API_KEY` (web and
   image search), `ADMIN_EMAILS` (set to your own email if you want to test
   admin without relying on "first account created"). Weather needs **no**
   key — it uses Open-Meteo (keyless); there is no `OPENWEATHER_API_KEY`
   anymore.
3. `python run.py`, open `http://127.0.0.1:5000/`
4. Use **Chrome or Edge** for the voice sections — Firefox/Safari don't
   support the Web Speech API at all, that's a browser limitation, not a bug

---

## 1. Landing & identity

- [ ] Page loads to the centered landing view — orb, "Intelligent. Creative.
      Limitless.", subtitle, 5 suggestion chips
- [ ] Particle sphere is visibly animating (slow rotation + gentle pulse) at
      idle, not static
- [ ] Starfield background is visible and very subtle (dim, sparse, slow
      twinkle) — should not be distracting
- [ ] Click a suggestion chip (e.g. "Code Generation") — composer fills with
      `Code Generation: ` and focuses

## 2. Core chat

- [ ] Type a message, send — landing fades out, chat view takes over, orb
      moves/fades to the right-docked position
- [ ] Reply streams in token by token (not all at once)
- [ ] Send a second message in the same conversation — reply should show
      awareness of the first message (context carried over)
- [ ] Markdown renders correctly: ask for something with a numbered list, a
      bold term, and a code block — check all three render as real HTML
      (not literal `**`/` ``` `/`1.`)
- [ ] Ask for something that would include a `#` heading and a `---`
      divider — both should render as an actual heading and a horizontal
      rule, not literal characters
- [ ] Code blocks are syntax-highlighted (color, not plain white text) —
      requires internet access, since highlight.js loads from a CDN

## 3. Message actions

- [ ] Hover an assistant message — copy (⧉) and regenerate (↻) icons appear
- [ ] Click copy — paste somewhere, confirm it matches the raw reply text
      (not the rendered HTML)
- [ ] Click regenerate — that specific reply re-generates in place
- [ ] Hover a user message — edit (✎) icon appears; click it — composer
      fills with that message's text (note: this refills the composer for
      you to resend, it does not truncate/replace history — documented
      simplification, see Memory.md)

## 4. Voice (Chrome/Edge only)

- [ ] Click the mic once — it starts listening (icon gets a persistent glow,
      not just a flash)
- [ ] Speak a question — it sends automatically, sphere goes
      thinking → speaking, reply is read aloud
- [ ] After the reply finishes speaking, it should **automatically start
      listening again** without you clicking anything — this is the
      continuous voice-chat loop
- [ ] Click the mic again mid-loop — it stops immediately (cancels any
      speech, back to text-only)
- [ ] Type and send a message instead of using the mic — confirm the reply
      is **not** spoken (text in → text out only)
- [ ] Topbar voice dropdown — pick a different voice, do another voice turn,
      confirm the new voice is used **and stays selected** on the next turn
      (this was a bug — used to silently reset)

## 5. Tools (weather / crypto / search)

- [ ] Ask "what's the weather in <city>" — real data from Open-Meteo
      (keyless); a Gemini estimate labeled approximate only if Open-Meteo
      can't resolve the city. Also try city-first ("Hyderabad weather") and
      Hindi ("दिल्ली का मौसम") phrasing — all should route to the weather tool
- [ ] Ask "price of bitcoin" — real live price from CoinGecko
- [ ] Ask "search for <topic>" — real results if `TAVILY_API_KEY` is set,
      otherwise a graceful "No search results found (or search isn't
      configured)" message
- [ ] With a document or image attached (see §6), ask a weather question —
      confirm weather still answers correctly rather than the attachment
      hijacking the reply (tool intent should always win over an attachment)

## 6. File upload & RAG

- [ ] Click **+** on the landing page (before first message) — file picker
      opens directly
- [ ] Upload a PDF, TXT, or DOCX with real text content — chip appears above
      composer showing 📄 + filename
- [ ] Ask a question whose answer is actually in that document — reply
      should reference the document's content specifically, not a generic
      answer
- [ ] Upload something with no extractable text (e.g. a blank/scanned-image
      PDF) — should get a clear error, not a crash
- [ ] Try an unsupported file type (e.g. `.exe`) — clear rejection message
      listing allowed types
- [ ] Click ✕ on the attachment chip — chip disappears; ask a follow-up
      question — should no longer reference the removed document

## 7. Image understanding

- [ ] Upload a PNG/JPG — chip shows 🖼️ + filename
- [ ] Ask "what's in this image" or similar — reply should describe the
      actual image content (this also covers OCR — try an image with text
      in it, Gemini should read the text natively)

## 8. Layout & responsiveness

- [ ] Resize the browser narrow (tablet width) — sidebar collapses to
      overlay behavior, orb shrinks
- [ ] Resize very narrow (mobile width) — orb shrinks to a small badge near
      the bottom-right, never overlapping messages or the composer
- [ ] Scroll through a long conversation — the **whole page** scrolls (check
      for a browser-level scrollbar), not a boxed-in chat area; topbar and
      composer stay pinned (sticky) while content scrolls underneath
  - [ ] No horizontal scrollbar should appear at any width — if one does,
        that's a regression of a bug that was already fixed once

## 9. Conversations & history

- [ ] Send a message, click **+ New Chat**, send a different message —
      sidebar "Recent" list should show both as separate entries
- [ ] Click an older entry in "Recent" — that full past conversation loads
      back into view correctly
- [ ] Open two conversations in sequence and confirm messages from one never
      appear inside the other

## 10. Export

- [ ] With an active conversation, click the topbar ⬇ export button —
      small menu with Markdown/JSON options
- [ ] Export as Markdown — downloads a readable `.md` transcript
- [ ] Export as JSON — downloads the raw structured conversation data
- [ ] Click export with **no** conversation started yet — should get a
      brief "nothing to export yet" message, not an error or a broken file

## 11. Analytics

- [ ] Sidebar → Analytics — modal opens showing total messages, average
      latency, a tool-usage bar chart, and a messages-per-day bar chart
- [ ] Send a few more messages of different types (a weather question, a
      general question), reopen Analytics — numbers should have gone up and
      the tool-usage breakdown should reflect the new message types

## 12. Authentication

- [ ] Sidebar → Profile while logged out — should prompt to sign in, not
      show a blank/broken panel
- [ ] Create an account — check the live password-requirements checklist
      fills in green as you type a valid password; try a weak password
      first and confirm it's rejected with a specific reason
- [ ] Click the 👁 icon on a password field — text becomes visible, icon
      changes to 🙈; click again to re-hide
- [ ] After signup, Profile should now show your real account info (name,
      email, join date)
- [ ] Log out via Profile — Profile should go back to the "please sign in"
      state
- [ ] Log back in with the same credentials — should succeed
- [ ] Try logging in with the wrong password — clear error, no crash
- [ ] **Isolation check** (the important one): create a second account in a
      different browser (or incognito window), send messages on both —
      confirm neither account's "Recent" list or conversations ever show
      the other account's data

## 13. Settings

- [ ] Sidebar → Settings while logged out — should prompt sign-in, same as
      Profile
- [ ] While logged in: change your display name, save — Profile should
      reflect the new name
- [ ] Change your password (correct current password + a new strong one) —
      should succeed; log out and log back in with the **new** password to
      confirm it actually took effect
- [ ] Try changing password with the **wrong** current password — clear
      rejection, no crash
- [ ] Try setting a new password that's too weak — rejected with the
      specific missing requirement

## 14. Admin panel

- [ ] Log in as whichever account is admin (first account ever created, or
      whatever email you put in `ADMIN_EMAILS`) — sidebar should show an
      **Admin** button that's hidden for everyone else
- [ ] Log in as a non-admin account — confirm the Admin button is not
      visible, and that directly hitting the admin API is denied (not
      strictly testable from the UI, but the button hiding is the visible
      signal)
- [ ] Open Admin as the admin account — table of all users with
      conversation/message counts per user

## 15. Model selector

- [ ] Topbar model dropdown — four real options across two providers, Groq
      listed first and default: **Groq GPT-OSS 120B (recommended)**, Gemini
      Flash, Gemini 3.6 Flash, Gemini 3.5 Flash-Lite
- [ ] Switch models mid-session, send a message — should still get a normal
      reply (confirms the switch didn't break anything); exact wording
      differences between models are expected and not a bug signal either
      way. Selecting a Gemini option should make Gemini the **primary** for
      that turn (with Groq as its fallback) — the reverse of the default —
      confirmed in `app/ai/retry.py`'s provider routing and by unit test

## 16. Things that were bugs and got fixed — worth specifically re-checking

- [ ] Favicon loads in the browser tab (no 404 in dev tools console)
- [ ] Select/highlight text inside any modal (try dragging a selection
      across a password field or form text) — modal should **not** close
      mid-selection
- [ ] No leftover "Idle / Thinking / Listening / Speaking" text label
      constantly visible under the orb — it should stay blank except for
      brief transient messages (mic errors, "Reading file…")
- [ ] A transient Gemini `503`/`429` no longer shows raw error JSON in the
      chat (e.g. `(Gemini error: 503 UNAVAILABLE. {'error': ...})`) for a
      RAG-path answer (document upload or knowledge-base query) — it
      should either quietly recover after a retry or show the friendly
      "Cindrix hit a temporary issue…" message, never the raw text

## 17. Retrieval track — STT provider, RAG, guardrails, retry, latency

This section splits into what the automated suite covers (every provider
mocked, so it runs anywhere) and what can only be verified against live
services and real keys. Run §17b before any demo or release.

### 17a. Automated coverage (no manual re-check needed)
- [x] `app/rag/chunking.py` — all four strategies tested against the
      real MSMARCO-XI row schema (verified against the live HF dataset
      card, not assumed): fixed-size sizing/overlap and its invalid-overlap
      guard, semantic never splitting mid-sentence (Devanagari danda
      included) and its boundary-sentence overlap, metadata-aware
      preserving the `is_selected` link and skipping empty passages, and
      the hybrid router's length-based routing with metadata surviving into
      sub-chunks
- [x] `app/rag/dataset.py` — fixture fallback tested (yields the
      documented example rows, loudly logged as a fixture, and ONLY when
      `huggingface_hub`/`pyarrow` are absent — never as a silent cover for a
      real load that failed); shard-path construction for the confirmed
      train/validation patterns, rejection of an unconfirmed split, and (via
      a mocked `hf_hub_download` + `pyarrow.ParquetFile`) that the real path
      downloads one language's shard file directly (`train/hintrain.parquet`,
      `repo_type="dataset"`, projecting only the columns chunking needs) and
      reads it with pyarrow — bypassing the HuggingFace `datasets` library
      entirely, which is what crashed with `ArrowNotImplementedError` on the
      nested `passages` struct in real runs before this fix. A separate test
      asserts a real load failure is **re-raised**, never swapped for the
      fixture
- [x] `app/rag/vector_store.py` — exact-search correctness, save/load
      round-trip, and rejection of mismatched vector/text lengths. The tests
      are backend-agnostic: they assert the same behavior whether FAISS is
      installed or the numpy fallback is in use
- [x] `app/ai/embeddings.py`'s `top_k_chunks()` — confirmed it now goes
      through `VectorStore` and still returns correctly-ranked results
- [x] `app/rag/ingest.py` — full pipeline (dataset → chunk → embed →
      vector store → save) tested end-to-end against fixture data
- [x] `app/rag/guardrails.py` — unsafe-input detection (including a
      false-positive check: a legitimate safety question doesn't trip it),
      off-topic screening for greetings, tool intent, and self/user meta
      questions, the relevance-floor check itself, and `kb_decision()`
      separating all three bands (answer / decline / fall through) — plus a
      test asserting the shipped 0.75/0.70 defaults are actually calibrated
      rather than permissive enough to let anything ground
- [x] `app/ai/retry.py` — all four single-provider retry scenarios
      tested: transient-error recovery, retry exhaustion → friendly
      message, non-transient error → no wasted retry, mid-stream failure
      → graceful close (not hung) — plus, separately, the provider-routed
      fallback chain: with no model (or a Groq model) selected, Groq is
      primary and Gemini is the fallback (Groq succeeds → Gemini never
      called; Groq exhausts retries → Gemini called and used; both fail →
      clean error, no raw leak; non-transient Groq error still falls back
      without wasting a retry). Selecting a **Gemini** model flips the
      order — Gemini primary, Groq fallback — verified by test
      (`test_stream_generation_gemini_selection_makes_gemini_primary` and
      its still-falls-back-to-Groq sibling). A regression test also
      confirms the original single-provider `stream_with_retry()` is
      byte-for-byte unaffected by the refactor that added the chain on top.
- [x] `app/agents/router.py`'s new `knowledge_base_rag` path — unsafe
      decline, pre-ingest fallback to old behavior, correct
      `detect_tool()` labeling, a well-grounded query answering from
      retrieved KB context (confirmed the prompt actually contained the
      retrieved passage, not just that *some* answer came back), and a
      weak-grounding query declining **with Gemini never called at all**
      (confirmed via mock assertion, not just output inspection)
- [x] `app/rag/benchmark.py` — confirmed it correctly marks itself
      `is_self_test` and refuses to claim `meets_target` when no real
      `GOOGLE_API_KEY` is available, rather than reporting misleadingly
      fast near-zero numbers as if they meant something
- [x] `app/ai/retry.py`'s `call_generation()` (non-streaming chain) and
      `app/tools/weather.py`'s use of it — Groq succeeds/Gemini never
      called, Groq fails/Gemini used, both fail/clean error not leaked —
      plus a direct regression test reproducing the exact reported bug
      (a weather question with both providers failing) confirming no raw
      `503`/`UNAVAILABLE` text reaches the returned string
- [x] `app/tools/weather.py`'s Open-Meteo path — `get_weather_open_meteo()`
      formats current conditions into a natural sentence from a mocked
      geocode+forecast response (temp, WMO-code description, humidity,
      wind), and returns `None` (so the caller falls back to Gemini) when
      the city can't be geocoded — both via mocked `requests`, no live call
- [x] `app/agents/router.py`'s weather routing — `_WEATHER_RE` matches
      city-first ("Hyderabad weather") and Hindi ("दिल्ली का मौसम")
      phrasing, and `_extract_city()` pulls the right city out of varied
      phrasings (prepositional "in/for/at/of", city-first, Hindi
      "<city> का मौसम") while stripping noise words, falling back to a
      default when no city is present
- [x] `app/config/settings.py`'s `model_provider()` + `AVAILABLE_MODELS` —
      each id maps to the right provider ("groq"/"gemini"), an unknown/absent
      id defaults to Groq, and `GEMINI_MODEL_IDS` contains only the Gemini
      entries (so a Groq id selected in the UI is never handed to the Gemini
      API — it resolves to `GEMINI_MODEL` there instead)

### 17b. Manual verification against a real environment (network + real API keys)

Automated tests mock every provider. These are the checks that require live
keys and a real network, with their recorded outcomes.

**Dependencies and dataset loading — verified.**
`pip install -r requirements.txt` with network access installs `faiss-cpu`,
`huggingface_hub`, and `pyarrow`; the startup warnings about missing
faiss/huggingface_hub/pyarrow stop appearing. (`datasets` is not a
dependency — the loader reads the parquet shard directly.)

**Real-dataset ingest — verified.** `python -m app.rag.ingest` against the
real `ai4bharat/MSMARCO-XI` dataset (not the fixture) logs
`[rag.dataset] downloading/opening shard train/hintrain.parquet
(target_lang='hin_Deva')` and reaches its row cap after scanning exactly that
many rows — i.e. every row in the shard's leading block is `hin_Deva`, so
**`hin_Deva` for Hindi is confirmed against real rows**, not just convention
or filename. No `MemoryError`/`WinError 10038`, no "falling back to FIXTURE"
line, no streaming of the combined "default" config.

The binding constraint is the Gemini free-tier embedding quota, and there are
**two** limits, not one: a per-minute cap (~100 requests/min) *and* a hard
**1000 requests/day** cap
(`EmbedContentRequestsPerDayPerUserPerProjectPerModel-FreeTier`), each text
in a batch counting individually. `embed_texts`' opt-in 429-retry budget
rides out the per-minute windows; the daily cap cannot be beaten by retrying
(it does not reset for hours). `RAG_INGEST_MAX_ROWS` is therefore tuned to
land under the daily ceiling. The shipped index holds **868 vectors (dim
3072)**. Any chunk that fails to embed is logged explicitly
(`N/M chunks failed to embed (empty vector) — skipped`) rather than dropped
silently, so a partial index is an honest one.

**Grounded retrieval on a real index — verified locally.** An in-corpus
Hindi query returns a top cosine score above `RAG_MIN_RELEVANCE` (measured
0.8147 on `"स्नातक छात्र कक्षा में क्या पहनते हैं"`) and the answer uses the
retrieved passage content rather than general knowledge.

**Guardrail bands on a real index — verified locally.** Out-of-corpus queries
score below the bands and are answered conversationally rather than
declined; the narrow middle band produces `DECLINE_MESSAGE` with no model
call at all. Measured score distribution: true matches 0.65–0.82,
out-of-domain Hindi 0.60–0.72, out-of-domain English 0.57–0.60 — the
calibration the 0.75/0.70 thresholds come from.

**Latency benchmark with both keys real — verified.**
`python -m app.rag.benchmark --queries 28` reports `is_self_test: false`,
`provider_config_note: null`, and **18/28** in-corpus queries grounded — 17
served by **Groq (primary)** and one by the **Gemini fallback**
(`served_by_breakdown: {"Groq (primary)": 17, "Gemini (fallback, after Groq
failed)": 1}`), so both the primary routing and the fallback path are
confirmed against live services in a single run. All five stages are measured
live, including query embedding. Full per-stage table in
[`Architecture.md`](Architecture.md) → Latency harness; the raw report is
`rag_index/latency_report.json`.

`retrieval_meets_target` is `false`, and the `stages_ms` breakdown shows
exactly why: FAISS vector search is **0.83 ms P70** while the single
`gemini-embedding-001` call to embed the query is **475.6 ms P70**. The
target is missed entirely on network round-trip to a remote embedding API,
not on anything the index or search does. Full generation adds **1817.7 ms
P70** on top — its P100 is a ~31 s outlier, the single query that fell back
to Gemini (whose retry budget elapsed first), not representative inference
time. So: local retrieval clears 200 ms by more than two orders of magnitude;
anything involving a remote call does not, and no retrieval tuning changes
that.

Note: `benchmark.py` measures the knowledge-base RAG path's generation stage
only, not general chat's. Use the analytics panel's average-latency figure to
sanity-check general chat specifically.

**Provider fallback with a real key missing — verified.** With only
`GOOGLE_API_KEY` set (no or invalid `GROQ_API_KEY`), responses still come
back via the Gemini fallback and the log records why Groq was skipped.

**Live deployment checks (https://cindrix-ai.onrender.com/).**

- Generation works, served by Groq primary.
- Identity: asked who created it, the assistant answers as Cindrix rather
  than naming the underlying model's provider — confirming the shared
  `_PERSONA` preamble is live.
- Weather returns real Open-Meteo data for a resolvable city.
- Cold start on Render's free tier is ~25 s for the first request after
  idle; subsequent requests are normal. This is a free-plan characteristic,
  not an application one.
- `/api/config` reports what the running instance actually resolved — check
  this before any demo. It returns
  `{"sttProvider": ..., "knowledgeBase": {"loaded": ..., "chunks": ...}}`.
  `sttProvider: "webspeech"` means `SARVAM_API_KEY` never reached the host's
  environment; `render.yaml` declares the key `sync: false`, so it must be
  filled in manually in the Render dashboard, and if it is absent the app
  silently and correctly falls back to `webspeech`.
- The knowledge-base RAG path needs two things to work in the container: the
  index has to load, and `embed_query` has to succeed. `/api/config`'s
  `knowledgeBase.loaded` answers the first — `false` there means
  `VectorStore.load` failed (most likely `faiss` unavailable, since the index
  is saved with `backend: "faiss"` and refuses to load without it). If it
  reports `loaded: true` with a non-zero chunk count and grounded answers
  still don't appear, the failure is the embedding call: a `GOOGLE_API_KEY`
  that is missing, different from the local one, or out of daily embedding
  quota causes retrieval to be skipped and the turn answered conversationally.
  `router.py` logs a distinct warning for that case (`query embedding
  unavailable — skipping knowledge-base retrieval`) precisely so it can't be
  mistaken for "the corpus wasn't relevant." Check the host logs for that line.

**Voice paths.** `STT_PROVIDER=sarvam` with a real `SARVAM_API_KEY`: record a
voice question, confirm it transcribes and that the sphere states (listening
→ thinking → speaking) behave as on the WebSpeech path. `STT_PROVIDER=webspeech`:
confirm the keyless fallback still works (Chrome/Edge only).

**Weather fallback.** Ask for a made-up city name to force the model-estimate
path — a normal weather description should come back, not raw error text.
Temporarily invalidating both keys should still produce the clean
both-providers-failed message. (There is no `OPENWEATHER_API_KEY` anymore;
the real-data path is keyless Open-Meteo.)

---
