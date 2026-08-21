# Design.md

## Identity

CINDRIX is not a ChatGPT/Gemini clone, not the Baymax character, and not a
JARVIS-style reactor/HUD. There is no face, no head, no body. The mascot is a
sphere made of individual particles arranged on a Fibonacci lattice (evenly
distributed points on a sphere, no clumping) rendered with perspective
projection and depth-based color/opacity. It reads as a living data-presence
rather than a character — "a cloud of thought."

## Color Palette

Ember Violet (replaces the original indigo/violet palette — see `Memory.md`
for the rename/palette log entry):

| Role             | Hex / value              |
| ---------------- | ------------------------- |
| Background       | `#0A0A0C`                 |
| Cards            | `#1A1620`                 |
| Card border      | `rgba(255,255,255,.08)`   |
| Accent           | `#9B6EF7`                 |
| Glow             | `#F0A34E` (amber)         |
| Text (primary)   | `#F5F0FA`                 |
| Text (secondary) | `rgba(245,240,250,.6)`    |

Glow is amber, not a second violet — it's reserved for the sphere's
`speaking`-adjacent presence (the ambient halo behind the docked orb) and
the mic's listening/active states, not used as a general secondary color
everywhere accent already is. General UI chrome (buttons, bars, avatars,
the brand mark) uses solid accent instead — see `frontend/css/style.css`
for the specific spots this was audited.

Style direction: dark theme first, glassmorphism (translucent blurred panels),
soft gradients, subtle shadows, rounded corners, floating particles in the
background at low opacity (see "Starfield" below for how this differs
between themes).

### Light theme

No light-mode values existed anywhere in this project before the
sphere-interactivity/theme-toggle session — checked this file, `Memory.md`,
`PRD.md`, and full git history; `PRD.md` only ever listed "Dark/light theme
toggle" as an unspecified requirement bullet. Named **"Lavender Dusk"**,
picked from 4 candidates (Warm Parchment, Lavender Dusk, Champagne Violet,
Slate Orchid) shown as a live-rendered preview against real UI chrome —
picked specifically for reading as the same product as the dark theme
(cool violet-gray undertone, not a warm/neutral swap to a different mood)
rather than an unrelated palette:

| Role             | Hex / value                |
| ---------------- | --------------------------- |
| Background       | `#E9E4F0`                   |
| Cards            | `#F6F3FA`                   |
| Card border      | `rgba(28,22,40,.14)`        |
| Accent           | `#7440E0`                   |
| Glow             | `#F0A34E` (amber, unchanged) |
| Text (primary)   | `#1D1830`                   |
| Text (secondary) | `rgba(29,24,48,.62)`        |

Glow stays the same amber in both themes — it's the sphere/mic-state color,
not a surface token, so it doesn't need to invert. Accent is deepened from
the dark theme's `#9B6EF7` to `#7440E0` for AA contrast on a light surface
— same violet family, not a different hue. Implemented via
`html[data-theme="light"]` in `frontend/css/style.css`, toggled and
persisted (`localStorage`) by `frontend/js/app.js`. Known gap: code-block
syntax highlighting (`highlight.js`'s `atom-one-dark` CDN theme) stays dark
in both themes — a light hljs theme swap wasn't attempted as part of this
pass.

### Starfield

The full-viewport canvas background (`frontend/js/starfield.js`) is
deliberately colorless and low-opacity in the dark theme so it never
competes with the accent-colored particle sphere — sparse white dots,
gentle fixed-position twinkle, unchanged since it was first built.

The light theme does **not** use the same dots recolored dark — that
literal approach was tried first and read as dust/specks on paper rather
than a "living particle" background (user feedback). Light theme instead
runs a distinct mode, **Soft Bokeh Motes**: fewer, larger (1.8–4.2px vs.
0.3–1.4px), soft-edged (blurred) circles that drift slowly around an
anchor point rather than twinkling in place, mixing the violet accent
(~70%) and amber glow (~30%) instead of a single flat color. Reads as
warm ambient light rather than pinpoint stars. Picked from 3 live-animated
options (Violet Sparkle — same dots just recolored; Soft Bokeh Motes —
chosen; Sparse Glints + Grain — a near-static paper-grain texture) shown
side by side before deciding; see `Memory.md`'s dated "Starfield — Light
Theme Finalized" entry for the other two and why they weren't picked.

Both modes share one draw loop, generation lifecycle, and the
`prefers-reduced-motion`/sub-480px-disable handling already documented
above for the sphere — only per-particle shape/motion/color branches on
the active theme, decided once per `generateStars()` call (page load,
window resize, and on the `cindrix:themechange` event `app.js`'s theme
toggle dispatches).

## Typography

- Clean geometric sans-serif (e.g. Inter or similar) for UI text
- Slightly larger, confident weight for headers ("CINDRIX", section titles)
- Monospace accent font reserved for code blocks / technical panels only

## Layout

### Header

`CINDRIX` — connection status — current model name

### Left Sidebar

Logo · New Chat · Chat History · Search Chats · AI Tools · Settings · User Profile

### Main Section

Top-center: the animated particle sphere. Below it: the chat stream. Bottom:
composer bar with microphone, attachment, and send controls.

### Right Panel (collapsible)

Current model · memory status · active tools · conversation statistics

## Particle Sphere States

Base geometry: ~220 particles on a Fibonacci-lattice sphere. Each state changes
radius, rotation speed, and per-particle offset — the lattice itself never
changes.

| State     | Radius                                              | Rotation       | Per-particle motion                                                                                                                                       |
| --------- | --------------------------------------------------- | -------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Idle      | Compressed (~80% of normal), gentle breathing pulse | Slow, constant | None — points hold their lattice position                                                                                                                 |
| Listening | Normal                                              | Slow           | Organic wander: each particle offsets on sine waves with a unique per-particle phase, so points drift outward and back individually rather than in unison |
| Thinking  | Normal                                              | Fast           | None beyond rotation — the speed of rotation itself reads as "processing"                                                                                 |
| Speaking  | Normal                                              | Medium         | Vertical ripple: a sine wave keyed to each particle's angle around the sphere, so a wave visibly travels around the form in sync with audio amplitude     |

Depth handling: particles are projected with simple perspective (closer =
larger, brighter, more opaque via interpolation between a muted color and the
accent color); farther particles are smaller, dimmer, and drawn first
(painter's algorithm) so the sphere reads with real depth instead of a flat
scatter.

## Voice Mode

- On mic activation: transition from Idle to Listening — sphere expands from
  compressed to normal radius, particle wander begins.
- While AI speaks: transition to Speaking — the vertical ripple wave scales in
  amplitude and frequency with live audio output amplitude, so louder/sharper
  speech produces a more pronounced ripple.
- All state transitions animate smoothly (see Motion Principles) — no hard cuts
  between radius/rotation/offset values.

## Animation Toolkit

Three.js (or a lightweight Canvas 2D particle system if Three.js proves
unnecessary overhead) drives the sphere itself — this is the one place a
heavier rendering approach is justified. GSAP for surrounding UI state
transitions and micro-interactions · Lottie for supplementary pre-built
animations (loading, success states) · CSS transitions for hover/focus states.

## Motion Principles

- Every state transition should be smooth (200–400ms ease for UI chrome; sphere
  transitions can run slightly longer, ~500–800ms, so the shift in radius/
  rotation reads clearly rather than snapping).
- Glow/color intensity maps to AI "activity" — particles trend toward the
  accent color and higher opacity when actively generating/searching, and
  toward the muted color at idle.
- Hover states on interactive elements: soft glow + slight scale (1.02–1.05x),
  no jarring movement.
- Typing indicator: three animated dots, distinct from the sphere itself —
  used in the message stream, not on the sphere.

## Responsive Behavior

Desktop-first. On tablet widths, the right info panel collapses behind a toggle;
the left sidebar collapses to icons-only. Mobile is out of scope until Phase 5.

## Implementation Status (Phase 1)

What actually shipped vs. what's still just planned, since a couple of things
drifted during the build:

- **Right info panel** (model/memory/sentiment/tools-used/stats from the
  original mockup) — **not built**. The simpler landing→chat layout took
  priority. Revisit in Phase 2/3 if tool-use visibility becomes a real gap.
- **Message formatting** — assistant replies render basic markdown (bold,
  inline code, code fences) via a small hand-rolled parser in `app.js`, not a
  library. Not in the original spec, added because Gemini's output needed it.
- **Voice mode UI** — implemented as a single mic button that starts/stops a
  full turn-based conversation loop, not a separate "voice mode" toggle
  layered on top of always-available text chat. Simpler than what was
  originally sketched, and matches what was actually asked for during the
  build.
- **Ambient glow behind the sphere** — added (soft radial gradient, not in
  the original palette/motion spec) to keep the chat view from feeling empty
  once the sphere shrinks down from its landing-page size. Now uses the
  amber Ember Violet glow value — see Color Palette above.
- **Sphere mouse-interactivity** — **built**. A parallax tilt (whole
  sphere leans gently toward the cursor's page position) plus a local
  screen-space repulsion (particles near the actual cursor nudge away),
  both layered additively on top of the existing idle/listening/thinking/
  speaking state math in `particle-sphere.js` — no per-state radius/
  rotation/offset logic changed. Skipped under `prefers-reduced-motion`,
  same as the rest of that file's motion. See Memory.md's dated entry for
  the session this shipped in.
