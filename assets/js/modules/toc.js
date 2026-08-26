/**
 * TOC scrollspy — IntersectionObserver over the headings linked from the
 * server-rendered .toc aside. The first visible heading (in TOC order) gets
 * aria-current="true"; CSS keys on [aria-current="true"].
 *
 * Exports pure helper(s) for testing; init() wires the live page.
 */

/** Mark `id`'s link current among `links`, clearing the rest. Returns the id
 *  made current, or null when no link matches (caller keeps its previous). */
export function activate(links, id) {
  links = [...links];
  if (!links.some((link) => link.hash === `#${id}`)) return null;
  for (const link of links) {
    if (link.hash === `#${id}`) link.setAttribute("aria-current", "true");
    else link.removeAttribute("aria-current");
  }
  return id;
}

function clearAll(links) {
  for (const link of links) link.removeAttribute("aria-current");
}

export function init(doc = document) {
  const aside = doc.querySelector(".toc");
  const win = doc.defaultView;
  if (!aside || !win || typeof win.IntersectionObserver !== "function") return;

  const links = [...aside.querySelectorAll('a[href^="#"]')];
  const targets = [];
  for (const link of links) {
    const el = doc.getElementById(link.hash.slice(1));
    if (el) targets.push(el);
  }
  if (!targets.length) return;

  let currentId = null;
  const visible = new Set();
  const io = new win.IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) visible.add(entry.target.id);
        else visible.delete(entry.target.id);
      }
      const next = targets.find((t) => visible.has(t.id));
      if (next) {
        currentId = activate(links, next.id) ?? currentId;
      } else {
        // Nothing inside the observation band: only clear when the reader has
        // scrolled back above the first heading; otherwise keep the last one.
        if ((win.scrollY || 0) < targets[0].offsetTop - 80 && currentId) {
          clearAll(links);
          currentId = null;
        }
      }
    },
    { rootMargin: "-15% 0px -60% 0px" }
  );
  for (const target of targets) io.observe(target);
}
