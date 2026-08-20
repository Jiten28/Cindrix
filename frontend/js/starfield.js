/**
 * Starfield background — sparse, dim, slow. Per docs/Design.md: stars stay
 * colorless and low-opacity so they never compete with the accent-colored
 * particle sphere, which is the only thing on screen that should draw the eye.
 *
 * Theme-aware: star color was hardcoded white, which reads fine on the dark
 * background but disappears (or worse, looks like dust) on the light theme.
 * Reads --star-rgb from style.css (255,255,255 in dark, a near-black tint in
 * light) instead of a literal white, and re-reads it whenever app.js's theme
 * toggle fires "cindrix:themechange" — no restart needed to see it switch.
 */
(function () {
  const canvas = document.getElementById("starfield");
  const ctx = canvas.getContext("2d");

  let stars = [];
  let w = 0, h = 0, dpr = 1;

  function readStarRGB() {
    const raw = getComputedStyle(document.documentElement).getPropertyValue("--star-rgb").trim();
    // Expected format: "r,g,b" (see style.css). Falls back to white if the
    // custom property is ever missing/malformed rather than drawing nothing.
    const parts = raw.split(",").map((n) => parseInt(n, 10));
    return parts.length === 3 && parts.every((n) => !Number.isNaN(n)) ? parts : [255, 255, 255];
  }
  let starRGB = readStarRGB();
  window.addEventListener("cindrix:themechange", () => { starRGB = readStarRGB(); });

  const STAR_COUNT_PER_1000PX2 = 0.09; // sparse on purpose
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
    const count = Math.round((w * h) / 1000 * STAR_COUNT_PER_1000PX2);
    stars = [];
    for (let i = 0; i < count; i++) {
      stars.push({
        x: Math.random() * w,
        y: Math.random() * h,
        r: Math.random() * 1.1 + 0.3,
        baseAlpha: Math.random() * 0.35 + 0.15,
        phase: Math.random() * Math.PI * 2,
        speed: Math.random() * 0.4 + 0.15,
      });
    }
  }

  let t = 0;
  function draw() {
    ctx.clearRect(0, 0, w, h);
    for (const s of stars) {
      const twinkle = reduceMotion ? 0 : Math.sin(t * s.speed + s.phase) * 0.15;
      const alpha = Math.max(0, Math.min(1, s.baseAlpha + twinkle));
      ctx.beginPath();
      ctx.fillStyle = `rgba(${starRGB[0]},${starRGB[1]},${starRGB[2]},${alpha.toFixed(3)})`;
      ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
      ctx.fill();
    }
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
