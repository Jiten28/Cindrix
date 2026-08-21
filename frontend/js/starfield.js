/**
 * Starfield background — sparse, dim, slow. Per docs/Design.md: stars stay
 * colorless and low-opacity so they never compete with the accent-colored
 * particle sphere, which is the only thing on screen that should draw the eye.
 *
 * Theme-aware: dark theme is untouched — same sparse white twinkling dots
 * as always. Light theme used to just recolor those same dots dark, which
 * read as dust/specks on paper rather than a "living particle" background
 * (user feedback). Light theme now runs a distinct "Soft Bokeh Motes" mode
 * instead: fewer, larger, soft-edged (blurred) circles that drift slowly,
 * mixing the violet accent and amber glow — reads as warm ambient light
 * rather than pinpoint stars. Picked from 3 live-animated options (Violet
 * Sparkle / Soft Bokeh Motes / Sparse Glints + Grain) — see Memory.md's
 * dated "Starfield — Light Theme Finalized" entry for the other two.
 *
 * Both modes share one draw loop and one resize/generate lifecycle; only
 * the per-particle shape/motion/color differs, picked once per
 * generateStars() call (on resize and on theme change) via isLightTheme().
 */
(function () {
  const canvas = document.getElementById("starfield");
  const ctx = canvas.getContext("2d");

  let stars = [];
  let w = 0, h = 0, dpr = 1;

  function isLightTheme() {
    return document.documentElement.getAttribute("data-theme") === "light";
  }

  function readRGBVar(name, fallback) {
    const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    const parts = raw.split(",").map((n) => parseInt(n, 10));
    return parts.length === 3 && parts.every((n) => !Number.isNaN(n)) ? parts : fallback;
  }

  // Dark-theme colors (unchanged behavior: flat white dots).
  let starRGB = readRGBVar("--star-rgb", [255, 255, 255]);
  // Light-theme mote colors: violet accent + amber glow, mixed per-particle.
  let accentRGB = readRGBVar("--accent-rgb", [116, 64, 224]);
  let glowRGB = readRGBVar("--glow-rgb", [240, 163, 78]);

  window.addEventListener("cindrix:themechange", () => {
    starRGB = readRGBVar("--star-rgb", [255, 255, 255]);
    accentRGB = readRGBVar("--accent-rgb", [116, 64, 224]);
    glowRGB = readRGBVar("--glow-rgb", [240, 163, 78]);
    // Density/size/motion differ between the two modes, so a plain color
    // refresh isn't enough on theme change — regenerate the particle set.
    generateStars();
  });

  // Dark theme — pinpoint stars, unchanged from before this session.
  const STAR_COUNT_PER_1000PX2 = 0.09; // sparse on purpose
  const STAR_RADIUS_MIN = 0.3, STAR_RADIUS_MAX = 1.4;
  const STAR_ALPHA_MIN = 0.15, STAR_ALPHA_MAX = 0.5;

  // Light theme — Soft Bokeh Motes: fewer and bigger, soft-edged (blur),
  // gently drifting rather than fixed-in-place-and-twinkling, ~30% amber.
  const MOTE_COUNT_PER_1000PX2 = 0.03;
  const MOTE_RADIUS_MIN = 1.8, MOTE_RADIUS_MAX = 4.2;
  const MOTE_ALPHA_MIN = 0.08, MOTE_ALPHA_MAX = 0.22;
  const MOTE_BLUR_PX = 6;
  const MOTE_AMBER_CHANCE = 0.3;
  const MOTE_DRIFT_PX = 6; // max drift radius from each mote's anchor point

  // Below this width (phones in portrait), the starfield is switched off
  // entirely rather than just thinned — it's pure background decoration,
  // and a continuous full-viewport canvas rAF loop is a real battery/frame
  // -rate cost on mid-range phones for something that competes with, not
  // supports, the particle sphere anyway (see the file header note).
  const DISABLE_BELOW_WIDTH = 480;
  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const disabled = window.innerWidth < DISABLE_BELOW_WIDTH;

  if (disabled) {
    canvas.hidden = true;
    return;
  }

  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    w = window.innerWidth;
    h = window.innerHeight;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    canvas.style.width = w + "px";
    canvas.style.height = h + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    generateStars();
  }

  function generateStars() {
    if (w === 0 || h === 0) return; // resize() hasn't run yet on first themechange
    const light = isLightTheme();
    const density = light ? MOTE_COUNT_PER_1000PX2 : STAR_COUNT_PER_1000PX2;
    const rMin = light ? MOTE_RADIUS_MIN : STAR_RADIUS_MIN;
    const rMax = light ? MOTE_RADIUS_MAX : STAR_RADIUS_MAX;
    const aMin = light ? MOTE_ALPHA_MIN : STAR_ALPHA_MIN;
    const aMax = light ? MOTE_ALPHA_MAX : STAR_ALPHA_MAX;
    const count = Math.round((w * h) / 1000 * density);
    stars = [];
    for (let i = 0; i < count; i++) {
      stars.push({
        x: Math.random() * w,
        y: Math.random() * h,
        r: Math.random() * (rMax - rMin) + rMin,
        baseAlpha: Math.random() * (aMax - aMin) + aMin,
        phase: Math.random() * Math.PI * 2,
        speed: Math.random() * 0.4 + 0.15,
        // Only used in mote mode; harmless to compute unconditionally.
        amber: Math.random() < MOTE_AMBER_CHANCE,
        driftPhaseX: Math.random() * Math.PI * 2,
        driftPhaseY: Math.random() * Math.PI * 2,
        driftSpeed: Math.random() * 0.3 + 0.1,
      });
    }
  }

  let t = 0;
  function draw() {
    ctx.clearRect(0, 0, w, h);
    const light = isLightTheme();

    if (!light) {
      // Dark theme — exactly the original draw path, untouched.
      for (const s of stars) {
        const twinkle = reduceMotion ? 0 : Math.sin(t * s.speed + s.phase) * 0.15;
        const alpha = Math.max(0, Math.min(1, s.baseAlpha + twinkle));
        ctx.beginPath();
        ctx.fillStyle = `rgba(${starRGB[0]},${starRGB[1]},${starRGB[2]},${alpha.toFixed(3)})`;
        ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
        ctx.fill();
      }
      return;
    }

    // Light theme — Soft Bokeh Motes: gentle drift + soft-edged glow instead
    // of fixed-position twinkle. shadowBlur gives the blurred/soft edge
    // cheaply without a separate offscreen blur pass.
    for (const s of stars) {
      const twinkle = reduceMotion ? 0 : Math.sin(t * s.speed + s.phase) * 0.5 + 0.5;
      const alpha = Math.max(0, Math.min(1, s.baseAlpha * (0.6 + twinkle * 0.5)));
      let x = s.x, y = s.y;
      if (!reduceMotion) {
        x += Math.sin(t * s.driftSpeed + s.driftPhaseX) * MOTE_DRIFT_PX;
        y += Math.cos(t * s.driftSpeed * 0.85 + s.driftPhaseY) * MOTE_DRIFT_PX;
      }
      const c = s.amber ? glowRGB : accentRGB;
      const rgba = `rgba(${c[0]},${c[1]},${c[2]},${alpha.toFixed(3)})`;
      ctx.beginPath();
      ctx.shadowBlur = MOTE_BLUR_PX;
      ctx.shadowColor = rgba;
      ctx.fillStyle = rgba;
      ctx.arc(x, y, s.r, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.shadowBlur = 0; // don't leak the blur setting into any other canvas draw
  }

  let last = performance.now();
  function loop(now) {
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    t += dt;
    draw();
    requestAnimationFrame(loop);
  }

  window.addEventListener("resize", resize);
  resize();
  if (!reduceMotion) {
    requestAnimationFrame(loop);
  } else {
    draw();
  }
})();
