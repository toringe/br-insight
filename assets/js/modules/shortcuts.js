/**
 * Keyboard shortcuts — `/` or Cmd/Ctrl-K → search, `f` → focus mode,
 * `t` → back to top. Plain letters are ignored while typing in inputs/
 * textareas/selects/contenteditable and while any modifier besides Shift is
 * held; Cmd/Ctrl-K deliberately works everywhere (it's a command chord, not
 * text entry).
 *
 * Exports pure router for testing; init() wires the live page.
 */

export function isTyping(target) {
  if (!target || !target.tagName) return false;
  const tag = target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  return !!target.isContentEditable;
}

/** Action name ("search"|"focus"|"top") for a key event, else null. */
export function route(key, mods = {}, target = null) {
  const meta = !!(mods.meta || mods.ctrl);
  if ((key === "k" || key === "K") && meta) return "search";
  if (meta || mods.alt || isTyping(target)) return null;
  if (key === "/") return "search";
  if (key === "f" || key === "F") return "focus";
  if (key === "t" || key === "T") return "top";
  return null;
}

function openSearch(doc) {
  const trigger = doc.querySelector("[data-search-open]");
  if (!trigger) return; // search UI lands in Task 15; no-op until then
  if (typeof trigger.click === "function") trigger.click();
  else trigger.focus();
}

export function init(doc = document) {
  doc.addEventListener("keydown", (event) => {
    const action = route(
      event.key,
      { meta: event.metaKey, ctrl: event.ctrlKey, alt: event.altKey },
      event.target
    );
    if (!action) return;
    event.preventDefault();

    if (action === "search") {
      openSearch(doc);
    } else if (action === "focus") {
      const btn = doc.querySelector("[data-focus-toggle]");
      if (btn) btn.click();
    } else if (action === "top") {
      const win = doc.defaultView;
      if (!win) return;
      let reduced = false;
      try {
        reduced = !!win.matchMedia("(prefers-reduced-motion: reduce)").matches;
      } catch {}
      win.scrollTo({ top: 0, behavior: reduced ? "auto" : "smooth" });
    }
  });
}
