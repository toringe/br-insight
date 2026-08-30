/**
 * Library filter/sort — progressive enhancement over the server-rendered
 * grid. Zero-JS keeps the full list browsable; with JS, chips toggle
 * filters (AND across groups, OR within a group), the select reorders,
 * and state syncs to ?category=&tag=&author=&decade=&sort= so filtered
 * views are shareable. Incoming params are applied on load too, so
 * author/tag chip links elsewhere deep-link straight into a filtered view.
 * A Clear filters action resets chips, sort, and params to the full list.
 *
 * Exports pure helpers (parseParams, toSearch, matches, compareCards)
 * for testing; init() wires the prerendered DOM. Active filters also
 * render as removable pills with an active-count badge on the toolbar;
 * incoming params auto-open the disclosure panel.
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
  for (const [key, value] of new URLSearchParams(search)) {
    if (key === "sort") {
      sort = SORTS.has(value) ? value : null;
    } else if (key in state && value) {
      state[key].push(value);
    }
  }
  const sets = {};
  for (const g of GROUPS) sets[g] = new Set(state[g]);
  return { state: sets, sort };
}

export function toSearch(state, sort) {
  const params = new URLSearchParams();
  for (const g of GROUPS) {
    for (const value of [...(state[g] || [])].sort()) params.append(g, value);
  }
  if (SORTS.has(sort)) params.append("sort", sort);
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
  const originalOrder = new Map(
    [...grid.querySelectorAll(".card")].map((card, i) => [card, i])
  );

  const incoming = parseParams(doc.defaultView.location.search);
  const state = incoming.state;
  let sort = incoming.sort || "";
  if (select && SORTS.has(sort)) select.value = sort;

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

  if (clearBtn) clearBtn.addEventListener("click", reset);

  function reset() {
    for (const g of GROUPS) state[g].clear();
    sort = "";
    if (select) select.value = "";
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
    if (clearBtn) clearBtn.hidden = total === 0;
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
    let ordered = [...originalOrder.keys()];
    ordered.sort(compareOrder);
    function compareOrder(a, b) {
      if (!sort) return originalOrder.get(a) - originalOrder.get(b);
      return compareCards(a, b, sort) || originalOrder.get(a) - originalOrder.get(b);
    }
    let visibleCount = 0;
    for (const card of ordered) {
      const visible = matches(card, state);
      card.hidden = !visible;
      if (visible) visibleCount++;
      grid.appendChild(card);
    }
    if (emptyMessage) emptyMessage.hidden = visibleCount > 0;
    doc.defaultView.history.replaceState(
      null,
      "",
      doc.defaultView.location.pathname +
        toSearch(state, sort) +
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
