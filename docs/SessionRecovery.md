# Session Recovery — Verified Project State

**Purpose of this file:** the existing docs in this repo may be stale or
out of sync with real code — a prior chat-based agent session did real
work but had no persistent file access, so its changes never landed on
disk and are lost. This file is a verified, honest summary of what's
actually confirmed working vs. still broken, based on direct testing
(not agent claims). Read this FIRST, then cross-check it against the
real current file contents before trusting any other doc's claims.

Project: **Cindrix** — personal voice-enabled RAG assistant, solo-built,
submitted to HHGoa's #RAGInGoa hackathon (Task #2). Deadline: Aug 22 2026
11:59 PM IST. Repo: github.com/Jiten28/Cindrix — Live:
cindrix-ai.onrender.com

---

## ✅ Confirmed working (verified via real testing, not just claimed)

- **STT (Sarvam):** `app/ai/stt.py`, `STT_PROVIDER` config flag
  (default `webspeech`, set to `sarvam` for compliance). Frontend has a
  MediaRecorder + Web Audio silence-detection path for Sarvam alongside
  the original Web Speech API path.
- **Chunking:** `app/rag/chunking.py` — fixed-size, semantic, and
  metadata-aware strategies, tested against the real MSMARCO-XI schema.
- **Vector store:** `app/rag/vector_store.py` — FAISS-backed, numpy
  fallback.
- **Guardrails:** `app/rag/guardrails.py` — off-topic/unsafe/grounding
  checks. Confirmed live via multiple real chat examples correctly
  declining ungrounded questions (e.g. "Golkonda Fort" — not in corpus
  — declined; Taj Mahal location — in corpus — answered correctly).
- **Groq-primary / Gemini-fallback generation chain:** `app/ai/retry.py`
  (`stream_generation()`), `app/ai/groq_client.py` (hand-rolled, uses
  `openai/gpt-oss-120b` — `llama-3.3-70b-versatile` is deprecated,
  confirmed via Groq's live docs). Confirmed via real benchmark run:
  `served_by: "Groq (primary)"` for all test queries.
- **UTF-8 streaming fix (CONFIRMED, manually applied and tested):**
  `groq_client.py`'s `stream_groq()` — changed
  `response.iter_lines(decode_unicode=True)` to
  `response.iter_lines(decode_unicode=False)` + explicit
  `line.decode("utf-8")`. Fixes garbled/mojibake Hindi text. Verified
  live — Hindi responses now render correct Devanagari.
- **General chat / web-search / weather.py error leaking:** all three
  routed through the shared Groq/Gemini fallback chain (was previously
  leaking raw Gemini 503 errors to users). Confirmed fixed.
- **CSS scrollbar bug:** `frontend/css/style.css` — `.app`'s
  `width: 100vw` was causing a spurious horizontal scrollbar (100vw
  counts the vertical scrollbar's own width). Removed. Confirmed fixed.
- **Frontend theme work (Agent 2 track — DONE):**
  - "Lavender Dusk" light-theme palette: `#E9E4F0` bg, `#F6F3FA` cards,
    `#7440E0` accent, `#1D1830` text.
  - Sphere + starfield made theme-aware (read CSS vars, no hardcoded
    dark-only colors).
  - Sphere mouse-interactivity: parallax tilt + local repulsion, layered
    on the existing 4-state system, respects `prefers-reduced-motion`.
  - Light-theme starfield: "Soft Bokeh Motes" (fewer, larger, soft-edged
    violet/amber drifting circles), theme-branched in `starfield.js` —
    dark theme byte-for-byte unchanged.
- **Repo/deployment links:** GitHub `github.com/Jiten28/Cindrix`, live
  `cindrix-ai.onrender.com` — confirmed correct, no stale references.
- **Project framing:** confirmed corrected everywhere — this is a solo
  personal project, NOT an internship/organization-affiliated one.
- **`.gitignore`:** updated to exclude `data/rag_index/` (FAISS index,
  meta.json, latency_report.json — regenerable) and `data/users.json`
  (sensitive — real signup data). NOTE: these files were already
  tracked in git before the ignore rule was added — `git rm --cached`
  was needed to actually untrack them; confirm this was done.

## ❌ Confirmed still broken / NOT done (do not trust other docs' claims otherwise)

1. **Real ingest still fails.** Last confirmed state: dataset.py still
   imports the `datasets` library directly (`import datasets as
   _hf_datasets`) and streams via it — no bypass applied. Known failure
   history, in order: (a) `BuilderConfig 'hi' not found` — fixed by
   loading `train/hintrain.parquet` shard directly; (b)
   `ArrowNotImplementedError: Nested data conversions not implemented`
   — attempted fix via `streaming=False`; (c) vague swallowed "An error
   occurred while generating the dataset" even with streaming=False,
   after successfully downloading the full 3.72GB Hindi shard. A
   chat-based agent session claimed to have fixed this via
   `huggingface_hub.hf_hub_download()` + `pyarrow.parquet.read_table()
   .to_pylist()` bypassing `datasets` entirely — **but this session had
   no persistent file access and its changes were lost. This fix is
   NOT actually applied.** Needs to be redone for real.
2. **Benchmark has never run against real data.** Every benchmark run
   so far loaded a stale 5-chunk FIXTURE index (`data/rag_index/
   msmarco_xi_hi`) from an early session, not real Hindi MSMARCO-XI
   content, because real ingest has never succeeded. Real P50/P70/P100
   numbers against real data do not exist yet.
3. **Generation latency (from the fixture-based benchmark that did
   run):** Groq generation measured ~788-1599ms across two runs — NOT
   fast, contrary to general published Groq benchmarks. P70 end-to-end
   ~1676-1776ms, far above the 200ms target. Worth knowing but not
   blocking — honest reporting is what's graded, not hitting the number.
4. **Weather: still 100% OpenWeatherMap, narrow regex.** Confirmed via
   direct file inspection: `app/tools/weather.py` still has
   `get_weather_openweather()` calling `api.openweathermap.org`, and
   `app/agents/router.py`'s `_WEATHER_RE` still only matches
   `weather.*in <city>` phrasing (fails on "Hyderabad weather" or Hindi
   phrasing without "in"). A chat-based agent session claimed to have
   broadened the regex and switched to Open-Meteo (keyless, free,
   10,000 calls/day) — **this was also lost, same as ingest. NOT
   applied.** Needs to be redone.
5. **Model selector: still Gemini-only, not wired to real provider
   chain.** `GET /api/models` only lists Gemini variants
   (Gemini Flash, 3.5 Flash-Lite, 3.6 Flash), defaults to Gemini, and
   there's an open question whether selecting a model in the dropdown
   actually changes which provider `retry.py` calls, or is purely
   cosmetic. Confirmed via live testing: the dropdown showed only
   Gemini options despite Groq being primary in the real chain. NOT
   fixed.
6. **Known deliberate gap, documented not fixed:** image-vision path
   (`stream_gemini_vision`) still calls Gemini directly, unprotected —
   would need a different client shape for Groq vision support. Out of
   scope unless explicitly revisited.

## 🔧 What to actually do (in priority order)

> **STATUS UPDATE (2026-08-21):** All five items below are now COMPLETE, and
> the "❌ still broken" items #1 (ingest), #2 (benchmark), #4 (weather), and
> #5 (model selector) above have been fixed and verified against a real
> environment. The ❌ section is retained as the historical starting point,
> not current state. Authoritative current state: `docs/Memory.md`'s
> "Hackathon Phase 6" entry + `docs/Testing.md` §17b. In brief: real
> 904-vector Hindi FAISS index built; benchmark real (retrieval ~1 ms, Groq
> generation P70 ~1.08 s, 5/5 Groq-primary, `meets_target` false because
> end-to-end is generation-bound); ingest bypass, Open-Meteo weather, and
> provider routing all confirmed. Only #6 (image-vision, deliberate gap)
> remains untouched by design. Remaining §17b items are live Q&A/STT checks
> and the one benchmark stage (query embedding) awaiting the daily-quota reset.


1. **Ingest bypass** — rewrite `app/rag/dataset.py`'s real-load path to
   use `huggingface_hub.hf_hub_download()` + `pyarrow.parquet
   .read_table().to_pylist()`, bypassing `datasets` entirely. Don't
   swallow real errors — `logger.exception()` + re-raise. Update
   `requirements.txt` (drop `datasets`, add `huggingface_hub`+`pyarrow`
   if missing).
2. **Weather fix** — broaden `_WEATHER_RE`/`_extract_city` in
   `router.py` for city-first and Hindi phrasing; replace
   `weather.py`'s OpenWeatherMap calls with Open-Meteo (geocoding API +
   forecast API, both keyless). Remove `OPENWEATHER_API_KEY` from
   settings/`.env.example`/`render.yaml`. Add WMO weather-code → text
   mapping. Keep the existing Gemini-estimate fallback contract.
3. **Model selector rework** — add a `provider` field to
   `AVAILABLE_MODELS`, Groq listed first/default; scope
   `gemini_client.py`'s model validation to Gemini ids only; make
   `retry.py` actually route by the SELECTED model's provider, not
   always default to Groq regardless of dropdown state.
4. Once 1–3 are done, run `python -m app.rag.ingest` for real, then
   `python -m app.rag.benchmark` for real numbers — this is the actual
   unblock for a demo-able submission.
5. Update `Architecture.md`, `Memory.md`, `Testing.md`, `Phases.md` to
   reflect real, verified state — not agent claims. Cross-reference
   against direct file inspection, not memory of prior sessions.

## Submission checklist reminder

- [x] Real ingest succeeds, real benchmark numbers recorded — **done
      2026-08-21** (904-vector index; retrieval ~1 ms, Groq gen P70 ~1.08 s;
      one benchmark stage — query embedding — awaits daily-quota reset)
- [ ] Weather works for varied phrasing, no API key required
- [ ] Model selector reflects/controls the real provider
- [ ] Live deployed link uses the compliant STT (Sarvam) + real chain
- [ ] Process video (90s) + demo video recorded
- [ ] Both videos posted to Instagram/X/LinkedIn tagged #RAGInGoa, one
      public Instagram account
- [ ] Submission form filled (GitHub link + live link)
- [ ] Deadline: Aug 22 2026, 11:59 PM IST
