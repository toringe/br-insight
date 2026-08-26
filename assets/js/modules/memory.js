/**
 * Reading memory — per-article scroll restore. Entries live in sessionStorage
 * under "bri:scroll:<path>" as timestamped JSON ({y, t}); an entry only
 * restores when the revisit is inside TTL (30 days) and the saved offset
 * clears the RESTORE_MIN threshold (never yank a reader back for a stray
 * two-line scroll).
 *
 * Exports pure helpers for testing; init() wires the live page.
 */

const PREFIX = "bri:scroll:";
export const TTL_MS = 30 * 24 * 60 * 60 * 1000; // 30 days
const RESTORE_MIN = 120;

/** Canonical cache key: strip trailing slash / index.html so one path never
 *  stores twice ("/library/x/" === "/library/x"). */
export function makeKey(pathname) {
  let path = String(pathname || "/");
  path = path.replace(/\/index\.html$/, "").replace(/\/+$/, "");
  return PREFIX + (path || "/");
}

export function encodeEntry(y, ts) {
  return JSON.stringify({ y, t: ts });
}

/** Saved offset or null. Rejects missing/corrupt/malformed and expired. */
export function decodeEntry(raw, now, ttl = TTL_MS) {
  if (!raw) return null;
  let entry;
  try {
    entry = JSON.parse(raw);
  } catch {
    return null;
  }
  const { y, t } = entry || {};
  if (typeof y !== "number" || !Number.isFinite(y)) return null;
  if (typeof t !== "number" || !Number.isFinite(t)) return null;
  if (!(now >= t) || now - t > ttl) return null;
  return y;
}

export function shouldRestore(y) {
  return Number.isFinite(y) && y > RESTORE_MIN;
}

export function init(doc = document) {
  const win = doc.defaultView;
  if (!win || typeof win.requestAnimationFrame !== "function") return;

  let store;
  try {
    store = win.sessionStorage;
  } catch {
    return; // storage access can throw in hardened privacy modes
  }
  if (!store) return;

  let key;
  try {
    key = makeKey(win.location.pathname);
    store.getItem(key); // probe once so security errors surface before we wire
  } catch {
    return;
  }

  const save = () => {
    try {
      store.setItem(key, encodeEntry(win.scrollY | 0, Date.now()));
    } catch {}
  };

  let queued = false;
  win.addEventListener(
    "scroll",
    () => {
      if (!queued) {
        queued = true;
        win.requestAnimationFrame(() => {
          queued = false;
          save();
        });
      }
    },
    { passive: true }
  );
  // pagehide covers tab close/navigate without the deprecated unload event.
  win.addEventListener("pagehide", save);

  const saved = decodeEntry(store.getItem(key), Date.now());
  if (shouldRestore(saved)) win.scrollTo(0, saved);
}
