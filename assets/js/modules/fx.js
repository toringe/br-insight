/**
 * Cinematic FX orchestrator (Task 13).
 *
 * Reads window.__FX__ (build-time serialization of SiteConfig.fx) and owns
 * what actually runs: the persisted atmosphere toggle and
 * prefers-reduced-motion both blanket-disable every effect. Effect visuals
 * themselves live in CSS behind data-fx-* presence flags on <html>; this
 * module only syncs those flags and manages the rain canvas lifecycle.
 *
 * Gating precedence (any one kill = everything off):
 *   1. no window.__FX__              -> nothing configured
 *   2. localStorage bri:atmosphere=0 -> html[data-fx-off]
 *   3. prefers-reduced-motion: reduce-> html[data-fx-off]
 *
 * Exports pure helpers for tests; exposes init() as the only runtime entry.
 */

const STORAGE_KEY = "bri:atmosphere";
const EFFECTS = ["rain", "scanlines", "grain", "flicker"];

export function loadPref(store) {
  if (!store) return true;
  try {
    const raw = store.getItem(STORAGE_KEY);
    return raw === null || raw === undefined ? true : raw === "1";
  } catch {
    return true;
  }
}

export function savePref(store, on) {
  if (!store) return;
  try {
    store.setItem(STORAGE_KEY, on ? "1" : "0");
  } catch {}
}

/** Pure gating matrix: config (null/full/partial) x user environment. */
export function resolve(config, env = {}) {
  const active = {
    rain: false,
    scanlines: false,
    grain: false,
    flicker: false,
    welcome: false,
  };
  if (!config || config.enabled !== true) {
    return { configured: false, blanketOff: true, active };
  }
  const blanketOff =
    env.reduced === true || env.atmosphere === false;
  if (blanketOff) return { configured: true, blanketOff: true, active };
  active.rain = config.rain?.enabled === true;
  active.scanlines = config.scanlines?.enabled === true;
  active.grain = config.grain?.enabled === true;
  active.flicker = config.flicker?.enabled === true;
  active.welcome = active.flicker && config.flicker.welcome === true;
  return { configured: true, blanketOff: false, active };
}

/** Sync the data-fx-* contract on <html>. Idempotent; also strips stale
 * build-time attributes when the effective state turns them off. */
export function applyFx(htmlEl, resolved) {
  for (const name of EFFECTS) {
    setFlag(htmlEl, `data-fx-${name}`, resolved.active[name]);
  }
  setFlag(htmlEl, "data-fx-welcome", resolved.active.welcome);
  // Blanket off only means something when FX was configured at all.
  setFlag(htmlEl, "data-fx-off", resolved.configured && resolved.blanketOff);
}

function setFlag(htmlEl, name, on) {
  if (on) htmlEl.setAttribute(name, "");
  else htmlEl.removeAttribute(name);
}

/** Static overlays live only while their effect is effectively on: fx.js
 * mounts/removes the shells; CSS owns all visuals behind the html flags. */
function syncStaticLayer(doc, cls, wanted) {
  const existing = doc.querySelector("." + cls);
  if (wanted && !existing) {
    const el = doc.createElement("div");
    el.className = "fx-layer " + cls;
    el.setAttribute("aria-hidden", "true");
    (doc.body || doc.documentElement).appendChild(el);
  } else if (!wanted && existing) {
    existing.remove();
  }
}

function storage(doc) {
  try {
    return doc.defaultView.localStorage || null;
  } catch {
    return null;
  }
}

export function init(doc = document) {
  const win = doc.defaultView || {};
  const config = win.__FX__;
  if (!config || config.enabled !== true) return; // fx disabled at build

  const htmlEl = doc.documentElement;
  const btns = doc.querySelectorAll("[data-fx-toggle]");
  const store = storage(doc);
  const media =
    typeof win.matchMedia === "function"
      ? win.matchMedia("(prefers-reduced-motion: reduce)")
      : null;

  let rainHandle = null;
  let rainGeneration = 0;

  const startRain = () => {
    const gen = ++rainGeneration;
    import("./rain.js")
      .then(({ createRain }) => {
        if (gen !== rainGeneration || rainHandle) return; // superseded
        rainHandle = createRain(doc, {
          density: config.rain.density,
          speed: config.rain.speed,
          tierAuto: config.rain.tier_auto,
        });
      })
      .catch((error) => {
        // Enhancement only — but never fully silent while debugging is hard.
        console.warn("[bri] fx rain unavailable", error);
      });
  };

  const stopRain = () => {
    rainGeneration += 1;
    if (rainHandle) {
      rainHandle.stop();
      rainHandle = null;
    }
  };

  const sync = () => {
    const atmosphereOn = loadPref(store);
    const resolved = resolve(config, {
      atmosphere: atmosphereOn,
      reduced: media ? media.matches : false,
    });
    applyFx(htmlEl, resolved);
    try {
      syncStaticLayer(doc, "fx-layer--scanlines", resolved.active.scanlines);
      syncStaticLayer(doc, "fx-layer--grain", resolved.active.grain);
    } catch {} // enhancement only
    for (const btn of btns) btn.setAttribute("aria-pressed", String(atmosphereOn));
    if (config.rain?.enabled === true && !htmlEl.hasAttribute("data-fx-rain")) {
      stopRain();
    } else if (
      config.rain?.enabled === true &&
      htmlEl.hasAttribute("data-fx-rain") &&
      !rainHandle
    ) {
      startRain();
    } else if (config.rain?.enabled !== true) {
      stopRain();
    }
  };

  const toggleAtmosphere = () => {
    savePref(store, !loadPref(store));
    sync();
  };

  for (const btn of btns) btn.addEventListener("click", toggleAtmosphere);

  if (media && typeof media.addEventListener === "function") {
    media.addEventListener("change", sync);
  }

  sync();
}
