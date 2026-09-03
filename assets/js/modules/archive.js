/**
 * Weekly "From the archive" carousel (home only).
 *
 * The no-JS fallback is the build-time pick (same FNV-1a digest logic,
 * same key format) rendered server-side into [data-archive-grid]. At
 * load this module re-applies the pick with the *visitor's* current ISO
 * week, so the row rotates by time without any rebuild. When the
 * visitor's week equals the build week the computed picks are identical
 * to the server's, and the swap is skipped — no flicker, no relayout.
 */

const CARD_SIZES = "(min-width: 64em) 340px, (min-width: 48em) 45vw, calc(100vw - 2rem)";

export function cyrb53(text) {
  // Mirrors br_insight.config.cyrb53 exactly (32-bit ops, 53-bit output);
  // slugs are ASCII so charCodeAt == Python's code-point loop.
  let h1 = 0xdeadbeef;
  let h2 = 0x41c6ce57;
  for (let i = 0; i < text.length; i++) {
    const c = text.charCodeAt(i);
    h1 = Math.imul(h1 ^ c, 2654435761) >>> 0;
    h2 = Math.imul(h2 ^ c, 1597334677) >>> 0;
  }
  h1 = (Math.imul(h1 ^ (h1 >>> 16), 2246822507) >>> 0)
    ^ (Math.imul(h2 ^ (h2 >>> 13), 3266489909) >>> 0);
  h1 = h1 >>> 0;
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) >>> 0;
  h2 = (h2 ^ (Math.imul(h1 ^ (h1 >>> 13), 3266489909) >>> 0)) >>> 0;
  return (2097151 & h2) * 4294967296 + h1;
}

export function cyrb53Hex(text) {
  return cyrb53(text).toString(16).padStart(13, "0");
}

export function fnv1a32(text) {
  // Retained only for the Python-parity test vectors in tests;
  // weekly picks use cyrb53Hex (see pick()).
  let h = 0x811c9dc5;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h.toString(16).padStart(8, "0");
}

export function isoYearWeek(date = new Date()) {
  // Monday-based ISO week, matching Python's date.isocalendar().
  const d = new Date(
    Date.UTC(date.getFullYear(), date.getMonth(), date.getDate())
  );
  const day = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - day);
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  const week = Math.ceil(((d - yearStart) / 86400000 + 1) / 7);
  return `${d.getUTCFullYear()}-W${String(week).padStart(2, "0")}`;
}

export function pick(items, week, excludeSlug, count = 3) {
  return items
    .filter((item) => item.slug !== excludeSlug)
    .map((item) => ({
      item,
      key: cyrb53Hex(`${item.slug}:${week}`) + item.slug,
    }))
    .sort((a, b) => (a.key < b.key ? -1 : a.key > b.key ? 1 : 0))
    .slice(0, count)
    .map(({ item }) => item)
    .sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0));
}

function srcset(base, widths, ext) {
  return widths
    .map((w, i) => `${base}${w}.${ext} ${w}w${i < widths.length - 1 ? ", " : ""}`)
    .join("");
}

function coverMarkup(item) {
  const base = `/library/${item.slug}/cover-crop-`;
  const last = item.crop[item.crop.length - 1];
  const source = item.crop.length
    ? `<source type="image/webp" srcset="${srcset(base, item.crop, "webp")}" sizes="${CARD_SIZES}">`
    : "";
  const src = item.crop.length
    ? `${base}${last}.jpg`
    : `/library/${item.slug}/cover-crop.jpg`;
  const srcsetAttr = item.crop.length
    ? ` srcset="${srcset(base, item.crop, "jpg")}" sizes="${CARD_SIZES}"`
    : "";
  return `<picture>${source}<img src="${src}"${srcsetAttr} alt="" loading="lazy" decoding="async" width="505" height="295"></picture>`;
}

function cardMarkup(item) {
  const href = `/library/${item.slug}/`;
  const chips = [
    `<a class="chip chip--sm chip--category" data-link="category" href="/library/?category=${encodeURIComponent(item.category)}">${item.category}</a>`,
    ...item.tags.map(
      (tag) =>
        `<a class="chip chip--sm chip--tag" data-link="tag" href="/library/?tag=${encodeURIComponent(tag)}">${tag}</a>`
    ),
  ].join("\n      ");
  return `<article class="card"
    data-category="${item.category}"
    data-tags="${item.tags.join(" ")}"
    data-author="${item.author}"
    data-minutes="${item.minutes}"
    data-date="${item.date}">
    <a class="card__cover" href="${href}" tabindex="-1" aria-hidden="true">${coverMarkup(item)}</a>
    <div class="card__body">
      <h3 class="card__title"><a href="${href}">${item.title}</a></h3>
      <p class="card__meta">
        <a class="card__author" data-link="author" href="/library/?author=${encodeURIComponent(item.author)}">by ${item.author}</a>
        <span class="card__reading-time">${item.minutes} min read</span>
      </p>
      <p class="card__tax">
        ${chips}
      </p>
    </div>
  </article>`;
}

export function init(doc = document) {
  const grid = doc.querySelector("[data-archive-grid]");
  const payloadEl = doc.getElementById("archive-payload");
  if (!grid || !payloadEl) return;
  let items;
  try {
    items = JSON.parse(payloadEl.textContent);
  } catch {
    return;
  }
  if (!Array.isArray(items) || !items.length) return;

  const week = isoYearWeek();
  if (week === grid.dataset.buildWeek) return; // server DOM is already this week's pick
  const picks = pick(items, week, grid.dataset.featuredSlug || "");
  if (!picks.length) return;
  grid.innerHTML = picks.map(cardMarkup).join("\n");
}
