/**
 * End navigation — floating back-to-top button ([data-top]). The button ships
 * `hidden` in markup so zero-JS pages never show it; JS reveals it past
 * ENDNAV_THRESHOLD px of scroll and smooth-scrolls home on click unless the
 * visitor prefers reduced motion.
 *
 * End-of-article pager actions stay plain links by design (no JS).
 */

export function shouldShow(scrollY, threshold = 600) {
  return scrollY > threshold;
}

export function init(doc = document) {
  const btn = doc.querySelector("[data-top]");
  const win = doc.defaultView;
  if (!btn || !win || typeof win.requestAnimationFrame !== "function") return;

  let queued = false;
  const update = () => {
    queued = false;
    btn.hidden = !shouldShow(win.scrollY || 0);
  };
  const schedule = () => {
    if (!queued) {
      queued = true;
      win.requestAnimationFrame(update);
    }
  };

  win.addEventListener("scroll", schedule, { passive: true });
  update();

  btn.addEventListener("click", () => {
    let reduced = false;
    try {
      reduced = !!win.matchMedia("(prefers-reduced-motion: reduce)").matches;
    } catch {}
    win.scrollTo({ top: 0, behavior: reduced ? "auto" : "smooth" });
  });
}
