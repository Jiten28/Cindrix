# Testing.md — Manual QA Checklist (through Phase 4)

Not one of the original six planning docs — an extra one, added because the
feature surface got big enough to need a real checklist before Phase 5.
Work through this top to bottom; each section is mostly independent, but
Authentication should be tested before Admin/Model-scoping since those build
on having a real account.

## Before you start

1. `.env` has a real `GOOGLE_API_KEY` (required for anything to respond)
2. Optional but worth having for full coverage: `GOOGLE_CSE_ID` (web/image
   search), `OPENWEATHER_API_KEY` (real weather instead of the Gemini
   estimate), `ADMIN_EMAILS` (set to your own email if you want to test
   admin without relying on "first account created")
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

- [ ] Ask "what's the weather in <city>" — real data if `OPENWEATHER_API_KEY`
      is set, otherwise a Gemini estimate labeled as approximate
- [ ] Ask "price of bitcoin" — real live price from CoinGecko
- [ ] Ask "search for <topic>" — real results if `GOOGLE_CSE_ID` is set,
      otherwise a graceful "search isn't configured" message
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

- [ ] Topbar model dropdown — three real options (Gemini Flash, Gemini 3.6
      Flash, Gemini 3.5 Flash-Lite)
- [ ] Switch models mid-session, send a message — should still get a normal
      reply (confirms the switch didn't break anything); exact wording
      differences between models are expected and not a bug signal either
      way

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

## 17. Hackathon track — STT provider, RAG, guardrails, retry, latency

Everything here is new — automated-tested during development (see below
for what "tested" means without a live `GOOGLE_API_KEY`/network in the
sandbox this was built in), but not yet manually re-verified against the
real Sarvam API, the real MSMARCO-XI dataset, or real Gemini traffic.
**Do this section before relying on the hackathon submission.**

### 17a. Automated coverage already done (no manual re-check needed)
- [x] `app/rag/chunking.py` — all three strategies tested against the
      real MSMARCO-XI row schema (verified against the live HF dataset
      card, not assumed), including Devanagari sentence boundaries
- [x] `app/rag/dataset.py` — fixture fallback tested (yields the
      documented example rows, loudly logged as a fixture)
- [x] `app/rag/vector_store.py` — exact search correctness + save/load
      round-trip tested (numpy fallback backend — `faiss` isn't
      installed in the sandbox this was built in)
- [x] `app/ai/embeddings.py`'s `top_k_chunks()` — confirmed it now goes
      through `VectorStore` and still returns correctly-ranked results
- [x] `app/rag/ingest.py` — full pipeline (dataset → chunk → embed →
      vector store → save) tested end-to-end against fixture data
- [x] `app/rag/guardrails.py` — unsafe-input detection (including a
      false-positive check: a legitimate safety question doesn't trip
      it), off-topic screening, and the relevance-floor grounding check
- [x] `app/ai/retry.py` — all four scenarios tested: transient-error
      recovery, retry exhaustion → friendly message, non-transient error
      → no wasted retry, mid-stream failure → graceful close (not hung)
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

### 17b. Needs a real environment (network + real API keys) — not done yet
- [ ] Run `pip install -r requirements.txt` somewhere with network access
      so `faiss-cpu` and `datasets` are actually installed — confirm the
      log warnings about missing faiss/datasets *stop* appearing
- [ ] `python -m app.rag.ingest` against the real `ai4bharat/MSMARCO-XI`
      dataset (not the fixture) — confirm it streams real rows and
      produces a real-sized index under `data/rag_index/`
- [ ] Ask a question the indexed corpus should cover — confirm a grounded
      answer citing/using retrieved passage content, not a generic one
- [ ] Ask something clearly outside the corpus — confirm the honest
      decline message, not a hallucinated answer
- [ ] Set `STT_PROVIDER=sarvam` and a real `SARVAM_API_KEY` — record a
      voice question, confirm it transcribes correctly and the sphere
      states (listening → thinking → speaking) still work exactly as
      they do on the WebSpeech path
- [ ] Set `STT_PROVIDER=webspeech` (or leave unset) — confirm voice input
      still works exactly as it did before this priority (regression
      check for the dev/fallback path)
- [ ] `python -m app.rag.benchmark` with a real `GOOGLE_API_KEY` — confirm
      `is_self_test` is `false` and record the actual P50/P70/P100; if
      P70 is over the 200ms target, note where the `stages_ms` breakdown
      says the time is going (this is expected to need real tuning, not
      something the harness itself can fix)

---
