/**
 * Rain — cinematic canvas streaks (Task 13, depth pass).
 *
 * Fixed full-viewport shell (.fx-layer--rain, z-index 80, pointer-events
 * none) holding THREE canvases behind content: .fx-rain--far (slow, dim,
 * CSS-blurred focus falloff), .fx-rain--near (foreground), and
 * .fx-rain--glass (stick-slip window droplets from a pre-rendered sprite).
 * All painted in one rAF loop. Config flows from window.__FX__ (density /
 * speed / tier_auto); visual tuning lives in --fx-* CSS vars + PLANES here.
 *
 * Runtime discipline:
 *   - ~30fps cap via timestamp accumulation inside one rAF loop (no setInterval)
 *   - visibilitychange pauses completely (loop cancelled, timers dropped)
 *   - debounced resize re-seeds the buffer (DPR-aware, capped at 2x)
 *   - FPS watchdog (tier_auto): rolling 2s frame average > 24ms halves the
 *     drop density once, then pauses rain permanently with a console.info
 *
 * Pure helpers are exported for the test harness; importing this module
 * never touches the DOM — createRain() must be called explicitly.
 */

const REFERENCE_WIDTH = 1280;
const MIN_SCALE = 0.4;
const MIN_DROPS = 12;
export const FRAME_BUDGET_MS = 24;
const TIER_FLOOR = 8;
const TIER_DOWNGRADE_DIVISOR = 2;

const TARGET_INTERVAL_MS = 1000 / 30;
const WATCHDOG_WINDOW_MS = 2000;
const WATCHDOG_MIN_SAMPLES = 30;
const DPR_CAP = 2;
const WIND_ANGLE = -0.06; // radians (~-3.4°): slight diagonal lean
const RESIZE_DEBOUNCE_MS = 150;

// Glass droplets: count scaling + stick-slip lifecycle bounds.
const DROPLET_REF = 24;
const DROPLET_MAX = 28;
const DROPLET_MIN = 6;
const WOBBLE_AMP = 0.35; // px of idle jitter while stuck
export const STUCK = "stuck";
export const SLIDING = "sliding";

/** Drop count for a viewport width: linear scale below REFERENCE_WIDTH,
 * clamped so thin viewports never fall under an atmospheric minimum. */
export function dropsForWidth(density, width) {
  const scale = Math.min(1, width / REFERENCE_WIDTH);
  return Math.max(MIN_DROPS, Math.round(density * Math.max(scale, MIN_SCALE)));
}

/** Watchdog tier step: halve the density, floored so tiers terminate. */
export function downgradeTier(density) {
  return Math.max(TIER_FLOOR, Math.round(density / TIER_DOWNGRADE_DIVISOR));
}

/** Depth split of the total drop budget into [far, near]. Near carries the
 * majority (60%) since it reads as the foreground plane; both layers keep
 * at least one drop so thin viewports never lose a depth plane. */
export function splitDrops(density) {
  const total = Math.max(2, Math.round(density));
  const near = Math.max(1, Math.round(total * 0.6));
  const far = Math.max(1, total - near);
  return [far, near];
}

/** Glass droplet count for a viewport width: linear from DROPLET_REF at the
 * reference width, capped at DROPLET_MAX, floored at DROPLET_MIN. */
export function dropletsForWidth(width) {
  const scale = width / REFERENCE_WIDTH;
  return Math.round(
    Math.min(DROPLET_MAX, Math.max(DROPLET_MIN, DROPLET_REF * Math.max(scale, MIN_SCALE))),
  );
}

/** One stick-slip step for a glass droplet. Stuck droplets hold position
 * (tiny wobble) while `hold` counts down; firing picks a burst speed and
 * slides (with wind lean) until `slide` expires, then sticks again.
 * Pure: mutates and returns the droplet. */
export function stepDroplet(droplet, seconds, rand = Math.random) {
  const d = droplet;
  if (d.state === STUCK) {
    d.hold -= seconds;
    d.x += (rand() - 0.5) * WOBBLE_AMP * seconds * 60 * 0.05;
    if (d.hold <= 0) {
      d.state = SLIDING;
      d.vy = 24 + rand() * 90;
      d.slide = 0.4 + rand() * 2.4;
    }
    return d;
  }
  d.slide -= seconds;
  d.y += d.vy * seconds;
  d.x += UX * d.vy * seconds;
  if (d.slide <= 0) {
    d.state = STUCK;
    d.vy = 0;
    d.hold = 1.5 + rand() * 7;
  }
  return d;
}

/** Ladder: hold -> downgrade (once) -> pause permanently. */
export function watchdogVerdict(avgFrameMs, downgradesDone) {
  if (!(avgFrameMs > FRAME_BUDGET_MS)) return "hold";
  return downgradesDone < 1 ? "downgrade" : "pause";
}

const UX = Math.sin(WIND_ANGLE); // unit wind vector components
const UY = Math.cos(WIND_ANGLE);

export function createRain(doc, opts = {}) {
  try {
    return buildRain(doc, opts);
  } catch {
    return { stop() {} };
  }
}

function buildRain(doc, opts = {}) {
  const win = doc.defaultView;
  if (!win) return { stop() {} };

  const speed = Number(opts.speed) > 0 ? Number(opts.speed) : 1;
  const tierAuto = opts.tierAuto !== false;
  let density = Math.max(1, Math.round(Number(opts.density) || 0));

  const shell = doc.createElement("div");
  shell.className = "fx-layer fx-layer--rain";

  // Depth planes: far reads soft/slow (CSS blur sells the focus falloff),
  // near keeps the original foreground look. Third canvas: glass droplets.
  const canvases = [];
  const ctxs = [];
  for (const plane of ["far", "near", "glass"]) {
    const canvas = doc.createElement("canvas");
    canvas.id = `fx-rain--${plane}`;
    canvas.className = `fx-rain fx-rain--${plane}`;
    canvas.setAttribute("aria-hidden", "true");
    shell.appendChild(canvas);
    canvases.push(canvas);
    ctxs.push(canvas.getContext("2d", { alpha: true }));
  }
  const [ctxFar, ctxNear, ctxGlass] = ctxs;
  doc.body.appendChild(shell);

  if (ctxs.some((c) => !c)) {
    shell.remove();
    return { stop() {} };
  }

  let cssWidth = 0;
  let cssHeight = 0;
  let layers = [[], []]; // [far, near] drop arrays
  let droplets = [];
  let tierDowns = 0;
  let glassPaused = false; // watchdog freezes the priciest garnish first

  // Per-plane look: far is slower, dimmer, thinner — parallax depth.
  const PLANES = [
    { speedScale: 0.55, alphaBase: 0.08, alphaRange: 0.3, thickBias: 0.95 },
    { speedScale: 1.0, alphaBase: 0.14, alphaRange: 0.5, thickBias: 0.86 },
  ];

  // Pre-rendered droplet sprite: one radial-gradient teardrop blob with a
  // highlight; per-frame work is a single drawImage per droplet.
  const sprite = doc.createElement("canvas");
  sprite.width = 64;
  sprite.height = 64;
  {
    const sctx = sprite.getContext("2d");
    if (sctx) {
      const g = sctx.createRadialGradient(26, 24, 2, 32, 32, 30);
      g.addColorStop(0, "rgba(235,248,255,.95)");
      g.addColorStop(0.45, "rgba(207,233,245,.38)");
      g.addColorStop(1, "rgba(207,233,245,0)");
      sctx.fillStyle = g;
      sctx.beginPath();
      sctx.arc(32, 32, 30, 0, Math.PI * 2);
      sctx.fill();
      sctx.fillStyle = "rgba(255,255,255,.85)";
      sctx.beginPath();
      sctx.ellipse(24, 22, 5, 3.4, -0.6, 0, Math.PI * 2);
      sctx.fill();
    }
  }

  function newDrop(planeIx, fromTop) {
    const p = PLANES[planeIx];
    const len = 8 + Math.random() * 18;
    return {
      x: Math.random() * (cssWidth + 40) - 40,
      y: fromTop ? -len : Math.random() * cssHeight,
      len: planeIx === 0 ? len * 0.75 : len,
      vy: (280 + Math.random() * 240) * speed * p.speedScale,
      alpha: p.alphaBase + Math.random() * p.alphaRange,
      thick: Math.random() < p.thickBias ? 1 : 2,
    };
  }

  function newDroplet() {
    return {
      state: STUCK,
      x: Math.random() * cssWidth,
      y: Math.random() * cssHeight * 0.9,
      r: 2 + Math.random() * 3.5,
      vy: 0,
      hold: Math.random() * 8,
      slide: 0,
    };
  }

  function makeLayers(counts) {
    return layers.map((old, ix) => {
      const next = old.slice(0, counts[ix]);
      while (next.length < counts[ix]) next.push(newDrop(ix, false));
      return next;
    });
  }

  function makeDroplets(count) {
    const next = droplets.slice(0, count);
    while (next.length < count) next.push(newDroplet());
    return next;
  }

  function reseed() {
    layers = makeLayers(splitDrops(density));
    droplets = makeDroplets(dropletsForWidth(cssWidth));
  }

  function resize() {
    cssWidth = win.innerWidth;
    cssHeight = win.innerHeight;
  const dpr = Math.min(DPR_CAP, win.devicePixelRatio || 1);
    for (const canvas of canvases) {
      canvas.width = Math.round(cssWidth * dpr);
      canvas.height = Math.round(cssHeight * dpr);
    }
    for (const ctx of ctxs) ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    reseed();
  }

  // --- Frame loop -----------------------------------------------------------

  let rafId = 0;
  let running = false;
  let pausedForPerf = false;
  let lastTime = 0;
  let acc = 0;
  let samples = [];

  function pruneSamples(now) {
    while (samples.length && now - samples[0].t > WATCHDOG_WINDOW_MS) {
      samples.shift();
    }
  }

  function watchdog(now) {
    if (!tierAuto || pausedForPerf) return;
    pruneSamples(now);
    if (samples.length < WATCHDOG_MIN_SAMPLES) return;
    const avg =
      samples.reduce((total, s) => total + s.dt, 0) / samples.length;
    const verdict = watchdogVerdict(avg, tierDowns);
    if (verdict === "downgrade") {
      tierDowns += 1;
      glassPaused = true; // garnish goes first; rain planes persist
      density = downgradeTier(density);
      reseed();
      samples = [];
    } else if (verdict === "pause") {
      pausedForPerf = true;
      stopLoop();
      console.info(
        "[bri] rain paused: sustained frame average over budget",
      );
    }
  }

  function paint(stepMs) {
    const seconds = Math.min(stepMs, 100) / 1000;
    for (let ix = 0; ix < ctxs.length; ix += 1) {
      const ctx = ctxs[ix];
      const drops = layers[ix];
      ctx.clearRect(0, 0, cssWidth, cssHeight);
      ctx.lineCap = "round";
      for (const drop of drops) {
        drop.y += drop.vy * seconds;
        drop.x += UX * drop.vy * seconds;
        if (drop.y - drop.len > cssHeight || drop.x < -drop.len * 2) {
          Object.assign(drop, newDrop(ix, true));
          continue;
        }
        ctx.globalAlpha = drop.alpha;
        ctx.strokeStyle = "#cfe9f5";
        ctx.lineWidth = drop.thick;
        ctx.beginPath();
        ctx.moveTo(drop.x, drop.y);
        ctx.lineTo(drop.x - UX * drop.len, drop.y - UY * drop.len);
        ctx.stroke();
      }
      ctx.globalAlpha = 1;
    }
  }

  /** Glass plane: step each droplet's stick-slip lifecycle and stamp the
   * pre-rendered sprite (scaled to droplet radius); sliding droplets pull a
   * short fading trail. Droplets that reach the floor re-stick near the top
   * of their run instead of leaving the glass. */
  function paintGlass(seconds) {
    if (glassPaused) return;
    const ctx = ctxGlass;
    ctx.clearRect(0, 0, cssWidth, cssHeight);
    for (const d of droplets) {
      stepDroplet(d, seconds);
      if (d.y > cssHeight) {
        d.y = -4 - Math.random() * 20;
        d.x = Math.random() * cssWidth;
        d.state = STUCK;
        d.vy = 0;
        d.hold = 0.5 + Math.random() * 4;
      }
      const size = d.r * 2;
      if (d.state === SLIDING) {
        ctx.globalAlpha = 0.16;
        ctx.strokeStyle = "#cfe9f5";
        ctx.lineWidth = Math.max(1, d.r * 0.7);
        ctx.lineCap = "round";
        ctx.beginPath();
        ctx.moveTo(d.x, d.y - d.vy * 0.12);
        ctx.lineTo(d.x, d.y);
        ctx.stroke();
      }
      ctx.globalAlpha = 0.9;
      ctx.drawImage(sprite, d.x - d.r, d.y - d.r, size, size);
    }
    ctx.globalAlpha = 1;
  }

  function frame(now) {
    if (!running) return;
    rafId = win.requestAnimationFrame(frame);
    if (!lastTime) {
      lastTime = now;
      return;
    }
    const dt = now - lastTime;
    lastTime = now;
    if (dt > 1000) { // long tab stall: resync instead of a giant step
      acc = 0;
      samples = [];
      return;
    }
    acc += dt;
    samples.push({ t: now, dt });
    if (acc >= TARGET_INTERVAL_MS) {
      acc %= TARGET_INTERVAL_MS;
      watchdog(now);
      if (!running) return; // watchdog may have paused us
      paintGlass(dt);
      paint(dt);
    }
  }

  function startLoop() {
    if (running || pausedForPerf) return;
    running = true;
    lastTime = 0;
    acc = 0;
    rafId = win.requestAnimationFrame(frame);
  }

  function stopLoop() {
    running = false;
    win.cancelAnimationFrame(rafId);
  }

  // --- Lifecycle ------------------------------------------------------------

  let resizeTimer = 0;
  function onResize() {
    win.clearTimeout(resizeTimer);
    resizeTimer = win.setTimeout(resize, RESIZE_DEBOUNCE_MS);
  }

  function onVisibility() {
    if (doc.hidden) stopLoop();
    else startLoop();
  }

  resize();
  doc.addEventListener("visibilitychange", onVisibility);
  win.addEventListener("resize", onResize);
  startLoop();

  return {
    stop() {
      stopLoop();
      doc.removeEventListener("visibilitychange", onVisibility);
      win.removeEventListener("resize", onResize);
      win.clearTimeout(resizeTimer);
      shell.remove();
    },
  };
}

