/**
 * createCindrixSphere — factory for the particle-sphere identity from
 * docs/Design.md. ~220 points on a Fibonacci lattice on desktop, fewer
 * (110) below a 640px viewport width for mobile performance — state
 * changes radius, rotation speed, and per-particle offset only; the
 * lattice itself never changes shape mid-session.
 *
 * Refactored into a factory (Phase 2b) so the landing orb and the docked
 * chat-mode orb can each run their own independent instance/canvas — needed
 * for a smooth crossfade transition between them, since a single canvas
 * element can't be smoothly animated between position:static and
 * position:fixed.
 *
 * Usage: const orb = window.createCindrixSphere("sphere", "sphereState");
 * orb.setState("idle" | "listening" | "thinking" | "speaking")
 *
 * Theme-aware color: ACCENT/MUTED used to be hardcoded RGB triplets tied to
 * the dark palette. Now read from --accent/--text (style.css) at creation
 * time and refreshed on app.js's "cindrix:themechange" event, so switching
 * theme re-colors the sphere without a reload.
 *
 * Mouse-interactivity (new): layered additively on top of the existing
 * state system per docs/Design.md's "not built yet" note — none of the
 * per-state math below (radius/rotation/wander/ripple) changed. Two
 * effects, both subtle by design:
 *   1. Whole-sphere parallax tilt toward the cursor's position anywhere on
 *      the page (a gentle "aware presence" read), eased so it never snaps.
 *   2. Local screen-space repulsion: particles within a small radius of
 *      the actual cursor nudge away from it, applied after projection so
 *      it can't distort the state-driven 3D motion above it.
 * Both are skipped entirely under prefers-reduced-motion, same as the rest
 * of this file's motion.
 */
window.createCindrixSphere = function (canvasId, labelId) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return { setState() {}, getState() { return "idle"; }, setPaused() {}, resize() {} };
  const ctx = canvas.getContext("2d");

  function hexToRGB(hex) {
    const m = hex.trim().replace("#", "");
    const n = parseInt(m.length === 3 ? m.split("").map((c) => c + c).join("") : m, 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  function readThemeColors() {
    const cs = getComputedStyle(document.documentElement);
    const accentHex = cs.getPropertyValue("--accent").trim() || "#9B6EF7";
    const textHex = cs.getPropertyValue("--text").trim() || "#F5F0FA";
    return { ACCENT: hexToRGB(accentHex), MUTED: hexToRGB(textHex) };
  }
  let { ACCENT, MUTED } = readThemeColors();
  window.addEventListener("cindrix:themechange", () => {
    ({ ACCENT, MUTED } = readThemeColors());
  });

  // Fewer points on narrow viewports — mid-range phones can visibly drop
  // frames animating ~220 canvas particles every frame, and it's pure
  // decoration, not something that needs the full desktop density to read
  // as "a sphere." Checked once at creation time, not on resize/rotate,
  // since going from a 220-particle to a 110-particle lattice mid-animation
  // would be a visible pop, not a smooth transition.
  const N = window.innerWidth < 640 ? 110 : 220;
  const golden = Math.PI * (3 - Math.sqrt(5));
  const particles = [];
  for (let i = 0; i < N; i++) {
    const y = 1 - (i / (N - 1)) * 2;
    const r = Math.sqrt(Math.max(0, 1 - y * y));
    const theta = golden * i;
    particles.push({
      bx: Math.cos(theta) * r,
      by: y,
      bz: Math.sin(theta) * r,
      seed: (i * 12.9898) % (Math.PI * 2),
      seed2: (i * 78.233) % (Math.PI * 2),
    });
  }

  let state = "idle";
  let t = 0;
  let rotY = 0;
  let w = 0, h = 0, dpr = 1;
  let paused = false;
  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ---------- mouse-interactivity (additive layer) ----------
  const MAX_TILT = 0.18;       // radians, ~10° — subtle, per Design.md motion principles
  const TILT_EASE = 3.2;       // higher = snappier follow, lower = lazier drift
  const REPEL_RADIUS_FRAC = 0.16; // fraction of canvas short side
  const REPEL_STRENGTH_FRAC = 0.05;
  let targetTiltX = 0, targetTiltY = 0; // where the sphere wants to tilt toward
  let tiltX = 0, tiltY = 0;             // eased current tilt actually applied
  let cursorLocalX = null, cursorLocalY = null; // cursor pos in this canvas's local coords, null = far away/unknown

  if (!reduceMotion) {
    window.addEventListener("mousemove", (e) => {
      // Page-wide parallax target — the sphere reads the cursor's position
      // anywhere on the page, not just when hovering the orb itself, so it
      // feels like a presence tracking the user rather than a hover effect.
      const nx = Math.max(-1, Math.min(1, (e.clientX / window.innerWidth) * 2 - 1));
      const ny = Math.max(-1, Math.min(1, (e.clientY / window.innerHeight) * 2 - 1));
      targetTiltY = nx * MAX_TILT;
      targetTiltX = ny * MAX_TILT;

      // Local repulsion only needs the cursor's position relative to THIS
      // canvas — recomputed per move since layout can shift (sidebar
      // collapse, orb dock crossfade) without a resize event firing.
      const rect = canvas.getBoundingClientRect();
      cursorLocalX = e.clientX - rect.left;
      cursorLocalY = e.clientY - rect.top;
    }, { passive: true });
  }

  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    const rect = canvas.getBoundingClientRect();
    w = rect.width;
    h = rect.height;
    if (w === 0 || h === 0) return;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function baseRadius() {
    const short = Math.min(w, h);
    const norm = short * 0.34;
    return state === "idle" ? norm * 0.8 : norm;
  }

  function rotSpeed() {
    if (state === "idle") return 0.15;
    if (state === "thinking") return 0.9;
    if (state === "listening") return 0.2;
    return 0.35; // speaking
  }

  function tick(dt) {
    if (paused || w === 0 || h === 0) return;
    t += dt;
    rotY += rotSpeed() * dt;

    // Ease the mouse-parallax tilt toward its target rather than snapping —
    // additive layer, doesn't touch rotY/the state-driven spin above it.
    if (!reduceMotion) {
      const ease = Math.min(1, dt * TILT_EASE);
      tiltX += (targetTiltX - tiltX) * ease;
      tiltY += (targetTiltY - tiltY) * ease;
    }

    const breathing = state === "idle" ? 1 + Math.sin(t * 1.2) * 0.04 : 1;
    const R = baseRadius() * breathing;
    const cosR = Math.cos(rotY), sinR = Math.sin(rotY);
    const cx = w / 2, cy = h / 2;
    const hasTilt = tiltX !== 0 || tiltY !== 0;
    const ctX = Math.cos(tiltX), stX = Math.sin(tiltX);
    const ctY = Math.cos(tiltY), stY = Math.sin(tiltY);

    // Local repulsion radius/strength scale with the canvas, and fade to
    // zero once the cursor is far enough away that it shouldn't be null
    // (still tracked) but has no visible effect — computed once per tick.
    const repelRadius = Math.min(w, h) * REPEL_RADIUS_FRAC;
    const repelStrength = Math.min(w, h) * REPEL_STRENGTH_FRAC;

    const drawList = [];
    for (const p of particles) {
      const rx0 = p.bx * cosR + p.bz * sinR;
      const rz0 = -p.bx * sinR + p.bz * cosR;
      const ry0 = p.by;

      // Mouse-parallax tilt — an additive rotation applied on top of the
      // state-driven spin above, before any per-state offset below, so
      // idle/listening/thinking/speaking motion still layers on top of it
      // exactly as it did with no mouse involved at all. Two composed
      // single-axis rotations (X then Y) rather than a full matrix, since
      // the tilt amounts are small and this keeps it cheap per-particle.
      let rx = rx0, ry = ry0, rz = rz0;
      if (hasTilt) {
        const ry1 = ry0 * ctX - rz0 * stX;
        const rz1 = ry0 * stX + rz0 * ctX;
        rx = rx0 * ctY + rz1 * stY;
        ry = ry1;
        rz = -rx0 * stY + rz1 * ctY;
      }

      let sx = rx * R, sy = ry * R, sz = rz * R;

      if (state === "listening") {
        const wv = 10;
        sx += Math.sin(t * wv + p.seed) * (R * 0.11);
        sy += Math.sin(t * wv * 0.8 + p.seed2) * (R * 0.11);
        sz += Math.cos(t * wv * 1.1 + p.seed) * (R * 0.11);
      }

      if (state === "speaking") {
        const angle = Math.atan2(rz, rx);
        sy += Math.sin(t * 7 + angle * 3) * (R * 0.16);
      }

      const focal = w * 0.6;
      const scale = focal / (focal + sz + w * 0.45);
      let px = cx + sx * scale;
      let py = cy + sy * scale;

      // Local cursor repulsion — screen-space, applied last so it can't
      // distort the 3D state motion above; particles near the actual
      // cursor nudge away from it, falling off to nothing past repelRadius.
      if (cursorLocalX !== null) {
        const dx = px - cursorLocalX, dy = py - cursorLocalY;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist > 0.001 && dist < repelRadius) {
          const push = (1 - dist / repelRadius) * repelStrength;
          px += (dx / dist) * push;
          py += (dy / dist) * push;
        }
      }

      drawList.push({ px, py, scale, z: sz });
    }

    drawList.sort((a, b) => a.z - b.z);

    ctx.clearRect(0, 0, w, h);
    for (const d of drawList) {
      const depthT = Math.max(0, Math.min(1, (d.z + R) / (R * 2)));
      const rC = MUTED[0] + (ACCENT[0] - MUTED[0]) * depthT;
      const gC = MUTED[1] + (ACCENT[1] - MUTED[1]) * depthT;
      const bC = MUTED[2] + (ACCENT[2] - MUTED[2]) * depthT;
      const alpha = 0.35 + depthT * 0.65;
      const size = Math.max(0.5, d.scale * (w * 0.012));
      ctx.beginPath();
      ctx.fillStyle = `rgba(${rC | 0},${gC | 0},${bC | 0},${alpha})`;
      ctx.arc(d.px, d.py, size, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  let last = performance.now();
  function loop(now) {
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    tick(dt);
    requestAnimationFrame(loop);
  }

  window.addEventListener("resize", resize);
  new ResizeObserver(resize).observe(canvas);
  resize();

  if (!reduceMotion) {
    requestAnimationFrame(loop);
  } else {
    tick(0.016);
  }

  return {
    setState(next) {
      if (["idle", "listening", "thinking", "speaking"].includes(next)) {
        state = next;
        // Label is intentionally not updated with the routine state name
        // anymore — the orb's motion communicates state, and the label is
        // reserved for transient messages (mic errors, "Reading file…") via
        // app.js's flashStateMessage. See docs/Memory.md.
      }
    },
    getState() {
      return state;
    },
    setPaused(next) {
      paused = next;
    },
    resize,
  };
};
