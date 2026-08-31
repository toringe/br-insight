/**
 * Focus mode — hides every [data-focus-hide] element (primary nav, menu/
 * atmosphere buttons' extras, footer, article end-block extras) plus fx layers
 * by toggling data-focus on <html>. No header button; toggled by the `f`
 * shortcut (which dispatches "bri:focus-toggle"), exited with Esc.
 *
 * Preference persists in localStorage key "bri:focus" ("1"/"0"); storage is
 * optional — private-mode failures degrade to session-only state.
 */

const STORAGE_KEY = "bri:focus";

export function loadPref(store) {
  if (!store) return false;
  try {
    return store.getItem(STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

export function savePref(store, on) {
  if (!store) return;
  try {
    store.setItem(STORAGE_KEY, on ? "1" : "0");
  } catch {}
}

export function isActive(htmlEl) {
  return htmlEl.hasAttribute("data-focus");
}

export function applyFocus(htmlEl, on) {
  if (on) htmlEl.setAttribute("data-focus", "");
  else htmlEl.removeAttribute("data-focus");
  return isActive(htmlEl);
}

function storage(doc) {
  try {
    return doc.defaultView.localStorage || null;
  } catch {
    return null;
  }
}

export function init(doc = document) {
  const htmlEl = doc.documentElement;
  const btn = doc.querySelector("[data-focus-toggle]");
  const store = storage(doc);

  const syncButton = () => {
    if (btn) btn.setAttribute("aria-pressed", String(isActive(htmlEl)));
  };

  const setOn = (on) => {
    applyFocus(htmlEl, on);
    savePref(store, on);
    syncButton();
  };
  const toggle = () => setOn(!isActive(htmlEl));

  if (btn) btn.addEventListener("click", toggle);
  // Shortcut wiring: `f` dispatches this event; focus mode needs no button.
  doc.addEventListener("bri:focus-toggle", toggle);
  doc.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && isActive(htmlEl)) setOn(false);
  });

  // Restore previous preference; button state stays honest either way.
  setOn(loadPref(store));
}
