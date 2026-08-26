/**
 * Reading progress bar — fixed .progress strip driven by transform:scaleX()
 * (compositor-only, origin left so it fills like a tape counter). Accessibility
 * contract is server-rendered (role="progressbar" + aria values in base.html);
 * this module only repaints on rAF-throttled scroll.
 *
 * Exports pure helpers for testing; init() wires the live page.
 */

export function clamp01(value) {
  return value < 0 ? 0 : value > 1 ? 1 : value;
}

/** Scrolled fraction 0..1 from viewport metrics. Short pages read as full. */
export function progressRatio(scrollY, innerHeight, scrollHeight) {
  const span = scrollHeight - innerHeight;
  if (!(span > 0)) return 1;
  return clamp01(scrollY / span);
}

export function init(doc = document) {
  const bar = doc.querySelector(".progress");
  const win = doc.defaultView;
  if (!bar || !win || typeof win.requestAnimationFrame !== "function") return;

  let queued = false;
  const paint = () => {
    queued = false;
    const ratio = progressRatio(
      win.scrollY || 0,
      win.innerHeight,
      doc.documentElement.scrollHeight
    );
    bar.style.transform = `scaleX(${ratio})`;
    bar.setAttribute("aria-valuenow", String(Math.round(ratio * 100)));
  };
  const schedule = () => {
    if (!queued) {
      queued = true;
      win.requestAnimationFrame(paint);
    }
  };

  win.addEventListener("scroll", schedule, { passive: true });
  win.addEventListener("resize", schedule);
  paint();
}
