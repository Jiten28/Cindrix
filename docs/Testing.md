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

---

## If something fails

Note which numbered item failed and what you saw vs. expected — that's
enough for a fast fix. Screenshots help most for anything visual (layout,
orb, modals).
