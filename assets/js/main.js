/**
 * Global orchestrator — one ES-module entry loaded by base.html on every page.
 * Each reading-UX module is feature-detecting and self-guarding; init() calls
 * are isolated so a failure in one never takes down the rest.
 *
 * Also hosts two small chrome behaviors that don't warrant their own module:
 * the mobile menu toggle ([data-menu-toggle] → [data-menu-open] on the
 * header, matching the CSS contract in main.css) and the random-essay action
 * ([data-random-link] navigates to a slug from the home-only
 * #essay-slugs JSON payload; modifier-click opens it in a new tab).
 */

import { init as initProgress } from "./modules/progress.js";
import { init as initToc } from "./modules/toc.js";
import { init as initEndnav } from "./modules/endnav.js";
import { init as initFocus } from "./modules/focus.js";
import { init as initMemory } from "./modules/memory.js";
import { init as initShortcuts } from "./modules/shortcuts.js";
import { init as initSearch } from "./modules/search.js";
import { init as initFx } from "./modules/fx.js";

function safe(name, fn) {
  try {
    fn();
  } catch (error) {
    // Enhancement only: a broken module must not break the others or the page.
    console.warn(`[bri] ${name} disabled`, error);
  }
}

safe("progress", () => initProgress());
safe("toc", () => initToc());
safe("endnav", () => initEndnav());
safe("focus", () => initFocus());
safe("memory", () => initMemory());
safe("shortcuts", () => initShortcuts());

// Search (Task 15): feature gate is inside init — it no-ops when the
// <dialog> skeleton or showModal() support is missing. The engine itself
// loads lazily on first open (see modules/search.js).
safe("search", () => initSearch());

// Cinematic FX (Task 13): feature-detection gate — the build either embeds
// window.__FX__ or omits it entirely; no payload means nothing to run.
safe("fx", () => {
  if (typeof window === "undefined" || !window.__FX__) return;
  initFx();
});

// --- Mobile menu -----------------------------------------------------------

safe("menu", () => {
  const toggle = document.querySelector("[data-menu-toggle]");
  if (!toggle) return;
  const header = toggle.closest(".site-header");
  if (!header) return;

  const isOpen = () => header.hasAttribute("data-menu-open");
  const setOpen = (open) => {
    if (open) header.setAttribute("data-menu-open", "");
    else header.removeAttribute("data-menu-open");
    toggle.setAttribute("aria-expanded", String(open));
  };

  toggle.addEventListener("click", () => setOpen(!isOpen()));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && isOpen()) setOpen(false);
  });
  header.addEventListener("click", (event) => {
    if (isOpen() && event.target.closest(".site-nav a")) setOpen(false);
  });
});

// --- Random essay (home) ---------------------------------------------------

safe("random", () => {
  const link = document.querySelector("[data-random-link]");
  const payload = document.getElementById("essay-slugs");
  if (!link || !payload) return;
  let slugs;
  try {
    slugs = JSON.parse(payload.textContent);
  } catch {
    return;
  }
  if (!Array.isArray(slugs) || !slugs.length) return;

  link.addEventListener("click", (event) => {
    const slug = slugs[Math.floor(Math.random() * slugs.length)];
    const href = `/library/${slug}/`;
    if (event.metaKey || event.ctrlKey || event.shiftKey) {
      event.preventDefault();
      window.open(href, "_blank", "noopener");
    } else {
      window.location.href = href;
    }
  });
});
