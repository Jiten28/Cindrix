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
 */
window.createCindrixSphere = function (canvasId, labelId) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return { setState() {}, getState() { return "idle"; }, setPaused() {}, resize() {} };
  const ctx = canvas.getContext("2d");

  const ACCENT = [155, 110, 247]; // --accent  #9B6EF7
  const MUTED = [245, 240, 250];  // --text base color #F5F0FA (--text-secondary's base hue before its .6 alpha)

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

    const breathing = state === "idle" ? 1 + Math.sin(t * 1.2) * 0.04 : 1;
    const R = baseRadius() * breathing;
    const cosR = Math.cos(rotY), sinR = Math.sin(rotY);
    const cx = w / 2, cy = h / 2;

    const drawList = [];
    for (const p of particles) {
      const rx = p.bx * cosR + p.bz * sinR;
      const rz = -p.bx * sinR + p.bz * cosR;
      const ry = p.by;

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
      const px = cx + sx * scale;
      const py = cy + sy * scale;
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
