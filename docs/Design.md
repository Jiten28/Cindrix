# Design.md

## Identity

NIMBUS is not a ChatGPT/Gemini clone, not the Baymax character, and not a
JARVIS-style reactor/HUD. There is no face, no head, no body. The mascot is a
sphere made of individual particles arranged on a Fibonacci lattice (evenly
distributed points on a sphere, no clumping) rendered with perspective
projection and depth-based color/opacity. It reads as a living data-presence
rather than a character — "a cloud of thought," fitting the name Nimbus.

## Color Palette

| Role             | Hex       |
| ---------------- | --------- |
| Background       | `#09090B` |
| Cards            | `#18181B` |
| Accent           | `#6366F1` |
| Glow             | `#8B5CF6` |
| Text (primary)   | `#FFFFFF` |
| Text (secondary) | `#A1A1AA` |

Style direction: dark theme first, glassmorphism (translucent blurred panels),
soft gradients, subtle shadows, rounded corners, floating particles in the
background at low opacity.

## Typography

- Clean geometric sans-serif (e.g. Inter or similar) for UI text
- Slightly larger, confident weight for headers ("NIMBUS", section titles)
- Monospace accent font reserved for code blocks / technical panels only

## Layout

### Header

`NIMBUS` — connection status — current model name

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
