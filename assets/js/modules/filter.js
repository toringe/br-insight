/**
 * Library filter/sort/search — progressive enhancement over the
 * server-rendered grid. Zero-JS keeps the full list browsable; with JS,
 * chips toggle filters (AND across groups, OR within a group), the
 * select reorders, and the search input live-filters cards by
 * title/author/category/tag substring. State syncs to
 * ?category=&tag=&author=&decade=&q=&sort= so filtered views are
 * shareable. Incoming params are applied on load too, so author/tag chip
 * links elsewhere deep-link straight into a filtered view.
 * A Clear filters action resets chips, search, sort, and params to the
 * full list.
 *
 * Exports pure helpers (parseParams, toSearch, matches, matchesQuery,
 * compareCards) for testing; init() wires the prerendered DOM. Active
 * filters also render as removable pills with an active-count badge on
 * the toolbar; incoming params auto-open the disclosure panel. Card
 * chips mirror the active state via aria-current so a clicked facet
 * highlights in place.
 */

const GROUPS = ["category", "tag", "author", "decade"];
const SORTS = new Set(["newest", "oldest", "longest", "shortest", "az"]);

/** data-* attribute backing each group ("tag" cards use space-separated
 *  slugs via data-tags; slugs never contain spaces, unlike facet labels). */
function attrFor(group) {
  return group === "tag" ? "tags" : group;
}

export function parseParams(search) {
  const state = {};
  for (const g of GROUPS) state[g] = [];
  let sort = null;
  let q = "";
  for (const [key, value] of new URLSearchParams(search)) {
    if (key === "sort") {
      sort = SORTS.has(value) ? value : null;
    } else if (key === "q") {
      if (value) q = value;
    } else if (key in state && value) {
      state[key].push(value);
    }
  }
  const sets = {};
  for (const g of GROUPS) sets[g] = new Set(state[g]);
  return { state: sets, sort, q };
}

export function toSearch(state, sort, q = "") {
  const params = new URLSearchParams();
  for (const g of GROUPS) {
    for (const value of [...(state[g] || [])].sort()) params.append(g, value);
  }
  if (SORTS.has(sort)) params.append("sort", sort);
  if (q) params.append("q", q);
  const query = params.toString();
  return query ? `?${query}` : "";
}

export function matches(card, state) {
  for (const g of GROUPS) {
    const selected = state[g];
    if (!selected || !selected.size) continue;
    const values =
      g === "tag"
        ? String(card.dataset.tags || "").split(" ")
        : [String(card.dataset[attrFor(g)] ?? "")];
    if (!values.some((v) => selected.has(v))) return false;
  }
  return true;
}

function cardTitle(card) {
  const el = card.querySelector && card.querySelector(".card__title");
  return String(el ? el.textContent : card.dataset.title || "")
    .trim()
    .toLowerCase();
}

/** Live-search: case-insensitive substring over title, author, category,
 *  and tag slugs. Empty query matches everything. ANDs with matches(). */
export function matchesQuery(card, q) {
  const needle = String(q ?? "").trim().toLowerCase();
  if (!needle) return true;
  const d = card.dataset;
  return (
    cardTitle(card).includes(needle) ||
    String(d.author ?? "").toLowerCase().includes(needle) ||
    String(d.category ?? "").toLowerCase().includes(needle) ||
    String(d.tags ?? "").toLowerCase().includes(needle)
  );
}

/** Comparator honoring dataset strings (dates are ISO, minutes numeric). */
export function compareCards(a, b, sort) {
  switch (sort) {
    case "newest":
      return b.dataset.date.localeCompare(a.dataset.date);
    case "oldest":
      return a.dataset.date.localeCompare(b.dataset.date);
    case "longest":
      return +b.dataset.minutes - +a.dataset.minutes;
    case "shortest":
      return +a.dataset.minutes - +b.dataset.minutes;
    case "az":
      return cardTitle(a).localeCompare(cardTitle(b));
    default:
      return 0; // server order (newest-first) is already correct
  }
}

export function init(doc = document) {
  const grid = doc.querySelector("[data-grid]");
  if (!grid) return;
  const bar = doc.querySelector("[data-filter-bar]");
  const emptyMessage = doc.querySelector("[data-empty]");
  const select = doc.querySelector("[data-sort]");
  const clearBtn = doc.querySelector("[data-clear-filters]");
  const pills = doc.querySelector("[data-pills]");
  const badge = doc.querySelector("[data-filter-badge]");
  const searchInput = doc.querySelector("[data-library-search]");
  const originalOrder = new Map(
    [...grid.querySelectorAll(".card")].map((card, i) => [card, i])
  );

  // Card chip deep links: parse each href once so render() can cheaply
  // toggle aria-current on the chips whose facet is active. Non-filter
  // or unparseable hrefs are ignored.
  const cardLinks = [...grid.querySelectorAll("[data-link]")]
    .flatMap((link) => {
      const group = link.dataset.link;
      if (!GROUPS.includes(group)) return [];
      let value = null;
      try {
        value = new URL(link.getAttribute("href") || "", doc.baseURI)
          .searchParams.get(group);
      } catch {
        value = null;
      }
      return value === null ? [] : [{ link, group, value }];
    });

  const incoming = parseParams(doc.defaultView.location.search);
  const state = incoming.state;
  let sort = incoming.sort || "";
  let q = incoming.q || "";
  if (select && SORTS.has(sort)) select.value = sort;
  if (searchInput) searchInput.value = q;

  // Deep link: incoming filter params open the disclosure panel so the
  // pressed chips are visible without a second click.
  const details = bar && bar.querySelector("details");
  if (details && GROUPS.some((g) => state[g].size)) details.open = true;

  // Pill removal: the × button deletes exactly that group/value pair.
  if (pills) {
    pills.addEventListener("click", (event) => {
      const btn = event.target.closest && event.target.closest("button");
      if (!btn) return;
      const pill = btn.closest("[data-group]");
      if (!pill || !state[pill.dataset.group]) return;
      state[pill.dataset.group].delete(pill.dataset.value);
      render();
    });
  }

  render();

  if (bar) {
    bar.addEventListener("click", (event) => {
      const chip = event.target.closest("button[data-group]");
      if (!chip) return;
      toggle(chip.dataset.group, chip.dataset.value);
    });
  }

  // Click anywhere outside the disclosure panel closes it — native
  // <details> ignores outside clicks, so this adds the expected dismiss
  // behavior. Clicks inside the panel (chips, counts) keep it open, and
  // the summary toggle still handles open/close itself.
  if (details) {
    doc.addEventListener("click", (event) => {
      const target = event.target;
      if (target.closest && target.closest("details.filterbar__details")) {
        return;
      }
      details.open = false;
    });
  }

  // Card chip anchors: intercept same-page deep links for instant filtering.
  // Anchor elements expose no searchParams (that's URL-only) — parse href.
  doc.addEventListener("click", (event) => {
    const link = event.target.closest("[data-link]");
    if (!link) return;
    let url;
    try {
      url = new URL(link.href, doc.baseURI);
    } catch {
      return; // unparseable href — fall through to native navigation
    }
    if (url.protocol !== "http:" && url.protocol !== "https:") return;
    if (url.origin !== doc.defaultView.location.origin) return;
    const value = url.searchParams.get(link.dataset.link);
    if (value === null) return;
    event.preventDefault();
    replace(link.dataset.link, value);
  });

  if (select) {
    select.addEventListener("change", () => {
      sort = select.value;
      render();
    });
  }

  if (searchInput) {
    searchInput.addEventListener("input", () => {
      q = searchInput.value.trim();
      render();
    });
  }

  if (clearBtn) clearBtn.addEventListener("click", reset);

  function reset() {
    for (const g of GROUPS) state[g].clear();
    sort = "";
    q = "";
    if (select) select.value = "";
    if (searchInput) searchInput.value = "";
    render();
  }

  function toggle(group, value) {
    const values = state[group];
    if (values.has(value)) values.delete(value);
    else values.add(value);
    render();
  }

  /** Exactly-one-value semantics for card chip links; re-click clears. */
  function replace(group, value) {
    const only = state[group].size === 1 && state[group].has(value);
    state[group].clear();
    if (!only) state[group].add(value);
    render();
  }

  function activeTotal() {
    let total = 0;
    for (const g of GROUPS) total += state[g].size;
    return total;
  }

  /** One .pill per active value (createElement/textContent only — no HTML
   *  parsing), ordered like toSearch(); badge + Clear track the total. */
  function renderPills() {
    if (pills) {
      pills.textContent = ""; // clears the container
      for (const g of GROUPS) {
        for (const value of [...state[g]].sort()) {
          const pill = doc.createElement("span");
          pill.className = "pill";
          pill.dataset.group = g;
          pill.dataset.value = value;
          const label = doc.createElement("span");
          label.className = "pill__label";
          label.textContent = value;
          pill.appendChild(label);
          const remove = doc.createElement("button");
          remove.type = "button";
          remove.className = "pill__remove";
          remove.setAttribute("aria-label", `Remove ${value} filter`);
          remove.textContent = "×";
          pill.appendChild(remove);
          pills.appendChild(pill);
        }
      }
    }
    const total = activeTotal();
    if (badge) {
      badge.textContent = String(total);
      badge.hidden = total === 0;
    }
    if (clearBtn) clearBtn.hidden = total === 0 && !q;
  }

  function render() {
    renderPills();
    if (bar) {
      for (const chip of bar.querySelectorAll("button[data-group]")) {
        chip.setAttribute(
          "aria-pressed",
          String(state[chip.dataset.group].has(chip.dataset.value))
        );
      }
    }
    for (const { link, group, value } of cardLinks) {
      const active = value !== null && !!state[group] && state[group].has(value);
      if (active) link.setAttribute("aria-current", "true");
      else link.removeAttribute("aria-current");
    }
    let ordered = [...originalOrder.keys()];
    ordered.sort(compareOrder);
    function compareOrder(a, b) {
      if (!sort) return originalOrder.get(a) - originalOrder.get(b);
      return compareCards(a, b, sort) || originalOrder.get(a) - originalOrder.get(b);
    }
    let visibleCount = 0;
    for (const card of ordered) {
      const visible = matches(card, state) && matchesQuery(card, q);
      card.hidden = !visible;
      if (visible) visibleCount++;
      grid.appendChild(card);
    }
    if (emptyMessage) emptyMessage.hidden = visibleCount > 0;
    doc.defaultView.history.replaceState(
      null,
      "",
      doc.defaultView.location.pathname +
        toSearch(state, sort, q) +
        doc.defaultView.location.hash
    );
  }
}

if (
  typeof document !== "undefined" &&
  typeof window !== "undefined" &&
  document.querySelector("[data-grid]")
) {
  init();
}
