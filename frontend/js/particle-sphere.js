/**
 * NimbusSphere — the particle-sphere identity from docs/Design.md.
 * ~220 points on a Fibonacci lattice; state changes radius, rotation speed,
 * and per-particle offset only — the lattice itself never changes.
 *
 * Public API: window.NimbusSphere.setState("idle" | "listening" | "thinking" | "speaking")
 */
window.NimbusSphere = (function () {
  const canvas = document.getElementById("sphere");
  const ctx = canvas.getContext("2d");

  const ACCENT = [99, 102, 241];   // --accent  #6366F1
  const MUTED = [161, 161, 170];   // --text-secondary #A1A1AA

  const N = 220;
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
  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    const rect = canvas.getBoundingClientRect();
    w = rect.width;
    h = rect.height;
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
  // sphere size changes on chat-active (see CSS) — observe it directly
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
        const label = document.getElementById("sphereState");
        if (label) label.textContent = next.charAt(0).toUpperCase() + next.slice(1);
      }
    },
    getState() {
      return state;
    },
  };
})();
