/**
 * Search (Task 15) — modal overlay over a lazily-built MiniSearch engine.
 *
 * Lazy contract: nothing network-y happens until the first open — the
 * vendored ESM bundle (`../vendor/minisearch.esm.min.js`) and the build-time
 * index (`../search-index.json`) are dynamic-import/fetch'd once, then cached.
 *
 * Safety contract: every rendered string lands as DOM text nodes
 * (highlightInto/buildResult never touch innerHTML), so hostile-looking
 * corpus text can't become markup.
 *
 * A11y contract: native <dialog> showModal() gives the focus trap + Esc;
 * close always restores focus to the invoker. Results are plain anchors,
 * so Enter follows them natively; ↑/↓ move through results.
 *
 * Exports pure helpers (highlightSegments, highlightInto, buildResult,
 * createEngine, nextIndex) for testing; init() wires the live page.
 */

const FIELDS = ["title", "author", "tags", "category", "summary", "body"];
const BOOSTS = {
  title: 3,
  author: 2,
  tags: 1.5,
  category: 1.5,
  summary: 1,
  body: 0.4,
};
const SEARCH_OPTIONS = { prefix: true, fuzzy: 0.2 };
const MAX_RESULTS = 12;

/** Split text into [{text, hit}] segments marking case-insensitive term hits. */
export function highlightSegments(text, terms) {
  const list = (Array.isArray(terms) ? terms : []).filter(
    (term) => typeof term === "string" && term.length > 0
  );
  if (!list.length || !text) return [{ text: String(text ?? ""), hit: false }];
  const escaped = [...new Set(list.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")))]
    .sort((a, b) => b.length - a.length);
  const pattern = new RegExp(`(${escaped.join("|")})`, "gi");
  const segments = [];
  let last = 0;
  for (const match of String(text).matchAll(pattern)) {
    const start = match.index;
    if (start > last) segments.push({ text: text.slice(last, start), hit: false });
    segments.push({ text: match[0], hit: true });
    last = start + match[0].length;
  }
  if (!segments.length || last < text.length)
    segments.push({ text: text.slice(last), hit: false });
  return segments;
}

/** Append safe text/mark nodes for each segment (never innerHTML). */
export function highlightInto(parent, text, terms, doc) {
  for (const segment of highlightSegments(text, terms)) {
    if (segment.hit) {
      const mark = doc.createElement("mark");
      mark.appendChild(doc.createTextNode(segment.text));
      parent.appendChild(mark);
    } else {
      parent.appendChild(doc.createTextNode(segment.text));
    }
  }
  return parent;
}

/** One result row: anchor wrapping highlighted title, meta line, summary. */
export function buildResult(record, terms, doc) {
  const li = doc.createElement("li");
  const link = doc.createElement("a");
  link.href = record.url;

  const title = doc.createElement("span");
  title.className = "search-result__title";
  highlightInto(title, record.title, terms, doc);
  link.appendChild(title);

  const meta = doc.createElement("span");
  meta.className = "search-result__meta";
  meta.appendChild(
    doc.createTextNode(
      `${record.author} · ${String(record.date).slice(0, 4)} · ${record.category}`
    )
  );
  link.appendChild(meta);

  if (record.summary) {
    const summary = doc.createElement("p");
    summary.className = "search-result__summary";
    highlightInto(summary, record.summary, terms, doc);
    link.appendChild(summary);
  }

  li.appendChild(link);
  return li;
}

/**
 * Wrap-around cursor math for ↑/↓ navigation over `length` items from
 * `current` (-1 = none focused) by `delta`. Returns -1 when there is
 * nothing to navigate into; callers may special-case that.
 */
export function nextIndex(length, current, delta) {
  if (length <= 0) return -1;
  const index = current < 0 ? (delta > 0 ? 0 : length - 1) : current + delta;
  return ((index % length) + length) % length;
}

/**
 * Resolve a MiniSearch hit back to its source record. Hits carry ``id`` =
 * the ``idField`` value ("slug"), so records must be re-matched by slug.
 */
export function recordFor(result, records) {
  const id = result?.id;
  const key = typeof id === "string" ? id : id?.slug;
  return records.find((record) => record.slug === key) ?? null;
}

export function createEngine(records, MiniSearchClass) {
  const engine = new MiniSearchClass({
    fields: FIELDS,
    storeFields: ["slug"],
    idField: "slug",
    searchOptions: { ...SEARCH_OPTIONS, boost: BOOSTS },
    extractField(record, field) {
      const value = record[field];
      return Array.isArray(value) ? value.join(" ") : value ?? "";
    },
  });
  engine.addAll(records);
  return engine;
}

let enginePromise = null;

/** Memoized vendor import + index fetch → { engine, records }. */
export function loadEngine({
  importVendor = () => import("../vendor/minisearch.esm.min.js"),
  fetchIndex = () =>
    fetch(new URL("../search-index.json", import.meta.url)).then((res) => res.json()),
} = {}) {
  enginePromise ??= Promise.all([importVendor(), fetchIndex()]).then(
    ([mod, records]) => ({
      records,
      engine: createEngine(records, mod.MiniSearch ?? mod.default),
    })
  );
  return enginePromise;
}

export function init(doc = document, { engineLoader = loadEngine } = {}) {
  const dialog = doc.querySelector("[data-search-dialog]");
  if (!dialog || typeof dialog.showModal !== "function") return null;
  const input = dialog.querySelector("[data-search-input]");
  const list = dialog.querySelector("[data-search-results]");
  const hint = dialog.querySelector("[data-search-hint]");
  const emptyNote = dialog.querySelector("[data-search-empty]");

  let invoker = null;
  let state = null; // { engine, records } once loaded

  async function open(trigger) {
    invoker =
      trigger && trigger.closest ? trigger.closest("[data-search-open]") : trigger;
    dialog.showModal();
    if (input) input.focus();
    try {
      state ??= await engineLoader();
    } catch {
      setHint("Search is unavailable right now.", true);
      return;
    }
    runQuery(input ? input.value.trim() : "");
  }

  function close() {
    if (dialog.open) dialog.close();
  }

  function setHint(text, visible) {
    if (!hint) return;
    hint.textContent = text;
    hint.hidden = !visible;
  }

  function runQuery(query) {
    if (!state || !list) return;
    while (list.firstChild) list.removeChild(list.firstChild);
    const results = query ? state.engine.search(query).slice(0, MAX_RESULTS) : [];
    for (const result of results) {
      const record = recordFor(result, state.records);
      if (record) list.appendChild(buildResult(record, result.terms || [], doc));
    }
    if (emptyNote) emptyNote.hidden = !query || results.length > 0;
    setHint(query ? "" : `Search ${state.records.length} essays…`, !query);
  }

  for (const opener of doc.querySelectorAll("[data-search-open]")) {
    opener.addEventListener("click", () => open(opener));
  }

  const closeBtn = dialog.querySelector("[data-search-close]");
  if (closeBtn) closeBtn.addEventListener("click", close);
  // click on the ::backdrop surfaces as a click on <dialog> itself
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) close();
  });
  // native Esc-close also fires this; always hand focus back to the opener
  dialog.addEventListener("close", () => {
    if (invoker && typeof invoker.focus === "function") invoker.focus();
    invoker = null;
  });

  input?.addEventListener("input", () => runQuery(input.value.trim()));
  dialog.addEventListener("keydown", (event) => {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    event.preventDefault();
    const links = [...list.querySelectorAll("a")];
    const active = links.indexOf(doc.activeElement);
    const delta = event.key === "ArrowDown" ? 1 : -1;
    let target =
      active === -1
        ? delta > 0
          ? links[0]
          : links[links.length - 1]
        : links[nextIndex(links.length, active, delta)];
    // ArrowUp past the first result parks focus back on the input
    (target || input)?.focus();
  });

  return { open, close }; // test seam
}
