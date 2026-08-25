# Blade Runner Insight — 2026 Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended)
> or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Rebuild br-insight.com as a fast, modern, fully responsive static site with a configurable
cinematic Blade Runner aesthetic, client-side search, curated taxonomy, and reader-focused features —
with zero runtime backend and zero URL changes.

**Architecture:** A small Python package (`src/br_insight`, uv-managed) renders Markdown sources +
Jinja2 templates into pure static HTML/CSS/JS directly into the repo root (the deploy root today).
Article sources stay at `library/<slug>/article.md`; the generator rewrites `library/<slug>/index.html`.
Client enhancements are vanilla ES modules — no framework, no jQuery.

**Tech Stack:** Python 3.14 + uv · jinja2 · markdown-it-py · PyYAML · Pillow (image variants) ·
pytest (dev) · vanilla ES-module JS · MiniSearch (vendored, lazy-loaded) · self-hosted subset WOFF2 fonts.

**Verified current state:** 29 article directories, 79,357 words total, longest 11,307 words;
every article has `author`; 26/29 have `cauthor` (missing: `editors-article`, `parting-of-the-mist`,
`significance-of-the-unicorn`); dates `DD-MM-YYYY` spanning 1995–2018; front matter is malformed
in places (tab-indented YAML, inconsistent fields); site went online July 1996 (about.html) → 2026 =
30th anniversary.

## Global Constraints

- Output is 100% static files; no database, no server-side runtime, no Node toolchain.
- **URL preservation:** every existing URL keeps working byte-for-byte in structure:
  `/`, `/library/`, `/library/<slug>/`, `/about.html`. New pages only ADD routes (`/topics/…`, `/search/`).
- Pages load the minified stylesheet convention where applicable; repo-root stays deployable as-is.
- JS budget: ≤ 25 KB gzipped total shipped JS. CSS ≤ 35 KB gzipped. No layout-shifting animations.
- All animations respect `prefers-reduced-motion`; every cinematic effect is individually
  switchable via `_data/site.yaml` + CSS custom properties (see Task 13).
- WCAG AA contrast for text; visible keyboard focus everywhere.
- Cover art always credited from `cauthor`; uncredited covers show an invitation to identify the artist.
- Anniversary marker discreet on every page: small mono-type footer line `EST. 1996 · 30 YEARS ONLINE`.
- Commits after each task; conventional-commit style (`feat:`, `chore:`, `perf:`, `docs:`).

---

## Target File Structure

```
src/br_insight/
  __init__.py        # main() console entry -> cli.run()
  cli.py             # argparse: build | serve | check
  config.py          # loads _data/site.yaml + _data/taxonomy.yaml, exposes SiteConfig
  frontmatter.py     # lenient YAML-front-matter parser (handles legacy quirks)
  articles.py        # Article dataclass, load_all(), reading_time(), related(), sorting
  render.py          # Jinja2 env; build(): pages -> repo root, idempotent
  search.py          # emits assets/js/search-index.json
  images.py          # Pillow: cover variants (webp+jpg, 480/800/1280w)
templates/
  base.html  home.html  library.html  article.html  topic.html  about.html  404.html
  partials/{header,footer,card,byline,credit}.html
_data/
  site.yaml          # featured slug, anniversary copy, FX config, nav, social
  taxonomy.yaml      # categories, tags, per-slug assignment (owner-reviewed)
assets/css/main.css (+ .min.css)     assets/js/modules/*.js     assets/js/search-index.json
tests/test_frontmatter.py test_articles.py test_render.py test_search.py
scripts/normalize_frontmatter.py     # one-time migration, kept for provenance
```

Legacy removals (final phase): `assets/js/jquery*.js`, `skel.min.js`, `util.js`, old `main.js`,
`assets/js/ie/*`, superseded `assets/css/*` and `assets/sass/*`, `assets/templates/*`.

---

## Phase 1 — Build pipeline foundation

### Task 1: Package scaffold + tooling

**Files:** Modify `pyproject.toml`; Create `src/br_insight/__init__.py`, `src/br_insight/cli.py`,
`tests/conftest.py`.

- [ ] Add deps: `jinja2`, `markdown-it-py`, `PyYAML`, `Pillow`; dev-deps: `pytest`.
- [ ] `cli.py`: subcommands `build --out .` (default repo root), `serve` (http.server wrapper),
  `check` (link/integrity checks used by Task 15). Exit codes non-zero on failure.
- [ ] Step: `uv sync && uv run br-insight --help` prints usage.
- [ ] Commit `chore: scaffold br_insight build package`.

### Task 2: Front-matter normalization (one-time)

**Files:** Create `scripts/normalize_frontmatter.py`, `tests/test_frontmatter.py`;
Modify all 29 `library/*/article.md`.

- [ ] Normalizer: tabs→2 spaces inside front matter; strip trailing whitespace; coerce `date`
  to ISO `YYYY-MM-DD`; ensure `taxonomy.category: article`; ensure `summary.enabled/size`
  defaults (`true`/`100`) when absent; preserve `copyright:`/`source:` fields untouched.
  Idempotent (running twice = no diff).
- [ ] Test: parse every `library/*/article.md` with strict PyYAML post-normalization — 29/29 pass;
  second run produces empty git diff.
- [ ] Run once; commit `chore: normalize article front matter`.

### Task 3: Article model + loaders

**Files:** Create `src/br_insight/frontmatter.py`, `src/br_insight/articles.py`, `tests/test_articles.py`.

Interfaces produced (used by Tasks 5–12):
```python
@dataclass(frozen=True)
class Article:
    slug: str; title: str; author: str; cover: str; cover_artist: str | None
    date: datetime; words: int; minutes: int; summary: str
    copyright: str | None; source: str | None
    category: str; tags: list[str]; html: str   # rendered markdown

def load_all(root: Path) -> list[Article]: ...        # sorted newest-first
def reading_time(words: int) -> int: ...              # ceil(words/220), min 1
def related(a: Article, all: list[Article]) -> list[Article]: ...  # shared tags desc, top 3
def parse_date(raw: str) -> datetime: ...             # accepts DD-MM-YYYY and ISO
```

- [ ] Tests first: reading_time edges (0 words→1, 220→1, 441→3); parse_date both formats;
  load_all returns 29 articles; unknown-author passthrough; missing cover_artist → None.
- [ ] Implement; `uv run pytest -q` green.
- [ ] Commit `feat: article model, lenient front matter, reading time`.

---

## Phase 2 — Data: taxonomy, site config

### Task 4: Taxonomy curation (OWNER REVIEW GATE)

**Files:** Create `_data/taxonomy.yaml`.

Schema:
```yaml
categories: [Film Analysis, Themes & Humanity, Characters, Religion & Symbolism,
             Technology & Society, World & Setting, Novel & Adaptation, Creative Works]
tag_vocab: [noir, visual-style, cinematography, genre, director's-cut, special-effects,
            postmodernism, tears-in-rain, deckard, roy-batty, rachael, replicant-or-human,
            empathy, personhood, philosophy, eyes, unicorn, dreams, christ-figure, tyrell,
            philip-k-dick, adaptation, cloning-genetics, creator-creation, dystopia,
            los-angeles-2019, race, fan-fiction, editorial]
assignments:
  a-study-of-blade-runner: {category: Film Analysis, tags: [cinematography, noir, tears-in-rain]}
  aboutfilm-analysis: {category: Film Analysis, tags: [noir, visual-style]}
  an-analysis-of-blade-runner: {category: Film Analysis, tags: [visual-style]}
  analysis-of-a-sf-movie: {category: Film Analysis, tags: [genre]}
  analysis-of-an-itch: {category: Characters, tags: [deckard]}
  appreciation-assessment-of-dircut: {category: Film Analysis, tags: [director's-cut, noir]}
  br-a-sf-movie: {category: Film Analysis, tags: [genre]}
  br-an-analysis: {category: Film Analysis, tags: [special-effects]}
  br-demystified: {category: World & Setting, tags: [dystopia]}
  christian-symbolism: {category: Religion & Symbolism, tags: [christ-figure, tyrell]}
  city-eyes-and-christ: {category: Religion & Symbolism, tags: [eyes, christ-figure, visual-style]}
  deckards-identity-debate: {category: Characters, tags: [deckard, unicorn, replicant-or-human]}
  do-androids-dream: {category: Novel & Adaptation, tags: [philip-k-dick, empathy]}
  editors-article: {category: Themes & Humanity, tags: [editorial, eyes]}
  genealogy-of-abdul-ben-hassan: {category: World & Setting, tags: [race]}
  how-and-why-movie-is-different: {category: Novel & Adaptation, tags: [adaptation]}
  how-science-became-god: {category: Technology & Society, tags: [tyrell]}
  humans-and-technology: {category: Technology & Society, tags: [creator-creation, roy-batty]}
  least-scary-option: {category: Technology & Society, tags: [dystopia]}
  love-letter: {category: Creative Works, tags: [fan-fiction, rachael]}
  measure-of-a-man: {category: Themes & Humanity, tags: [personhood, replicant-or-human]}
  parting-of-the-mist: {category: Religion & Symbolism, tags: [dreams]}
  picturing-the-human: {category: Themes & Humanity, tags: [philosophy, personhood]}
  postmodernist-view: {category: Film Analysis, tags: [postmodernism, tears-in-rain]}
  replicant-i-used-to-know: {category: Characters, tags: [empathy, deckard]}
  sf-with-an-angle: {category: Technology & Society, tags: [cloning-genetics]}
  significance-of-the-unicorn: {category: Religion & Symbolism, tags: [unicorn, dreams]}
  what-defines-human: {category: Themes & Humanity, tags: [philip-k-dick, personhood]}
  worn-down-hell: {category: World & Setting, tags: [los-angeles-2019, dystopia]}
```

> **STOP: present this mapping to the owner; apply corrections before continuing.**

- [ ] Loader in `config.py` validates: every slug exists on disk; every tag ∈ tag_vocab;
  every article assigned exactly one category. Test each rule.
- [ ] Commit `feat: curated taxonomy (owner-reviewed)`.

### Task 5: Site config

**Files:** Create `_data/site.yaml`, `src/br_insight/config.py`, `tests/test_config.py`.

Contents: `name`, `tagline`, `base_url: https://www.br-insight.com`, `established: 1996`,
`featured: {slug: postmodernist-view, fallback: monthly-rotation}`, `social`, `nav`,
and the FX block consumed by Task 13 (see Task 13 for exact shape). Loader merges owner overrides
over defaults; unknown keys warn loudly.

---

## Phase 3 — Design system & templates

### Task 6: Design tokens + core CSS

**Files:** Create `assets/css/main.css` (+ regenerate `.min.css`; minify via
`uv run python -c` with `rcssmin` dev-dep — decided: add `rcssmin` to dev deps).

Tokens (CSS custom properties, single source of truth):
```css
:root{
  --bg-0:#0a0e14; --bg-1:#10161f; --surface:#141c28;
  --text:#c9d4e0; --muted:#8494ab; --line:rgba(0,229,255,.14);
  --cyan:#00e5ff; --pink:#ff2e88; --amber:#ffb347;
  /* FX knobs — all cinematic values live here (Task 13 consumes these) */
  --fx-rain-opacity:.5; --fx-flicker-strength:.06; --fx-scanline-opacity:.04;
  --fx-grain-opacity:.05;
}
```
Type: headings `"Chakra Petch"` (self-hosted latin WOFF2, subset via `pyftsubset`, preloaded),
body `system-ui` stack (zero-cost). Fluid type scale `clamp()`. Components: `.btn`, `.card`,
`.chip`, `.byline`, `.progress`, `.toc`, focus-visible rings, skip-link. Breakpoints:
360 / 768 / 1024 / 1440. Verify: contrast AA pairs documented inline; no px-fonts below 16px body.

### Task 7: Base template + chrome

**Files:** Create `templates/base.html`, `partials/header.html`, `partials/footer.html`.

- Semantic landmarks; `<header>` sticky, translucent blur; nav: Home/Library/Topics/About +
  search button (`⌘K` hint) + atmosphere toggle (Task 13).
- Footer: copyright, cover-art blanket credit, discreet anniversary line
  `<span class="est">EST. 1996 · 30 YEARS ONLINE</span>` (mono, muted, 0.75rem).
- Head partial: charset, viewport, description, canonical, OG/Twitter (cover image),
  JSON-LD `Article` on article pages, `speculationsrules` JSON prefetch (Task 14),
  inline critical CSS ≤ 8 KB, deferred `main.min.css`.

### Task 8: Render engine + article pages

**Files:** Create `src/br_insight/render.py`, `templates/article.html`, `partials/byline.html`,
`partials/credit.html`, `tests/test_render.py`.

Article page anatomy (top→bottom): progress bar (fixed) · hero `cover.webp` `<picture>` with
`fetchpriority=high` + credit caption `Cover art © {cauthor}` (or artist-invite line) ·
byline `By {author} · {date} · {minutes} min read` · optional TOC aside (≥3 H2/H3) ·
prose (markdown-it-py, heading anchors) · end-block: prev/next + “← Back to Library” +
related (shared tags) · focus-mode target hooks (`data-focus-hide` on chrome/decor).

- [ ] Test: build idempotency — two consecutive `build`s produce identical tree hashes;
  every `/library/<slug>/` written; relative asset depth correct (`../../assets/…`).
- [ ] Commit `feat: render engine + article template`.

### Task 9: Library page + filters

**Files:** Create `templates/library.html`, `assets/js/modules/filter.js`.

Server-rendered cards (cover-crop webp lazy, title, byline chip, reading time, category chip,
tags). Client JS: chip rows for Category / Tag / Decade / Author; sort (newest, oldest,
longest, shortest, A–Z); state synced to query params (`?tag=noir` etc.) so filtered views are
shareable; author chip links here with `?author=`. Zero-JS fallback: full list still browsable.

### Task 10: Home page

**Files:** Create `templates/home.html`.

Hero: logo/title, tagline, subtle anniversary line, CTA buttons (Library / Random essay).
Featured-of-month card from `site.featured` (fallback: deterministic rotation
`hash(YYYY-MM) % pool`). Stats band computed at build: `29 essays · {N} authors · 79,000+ words · est. 1996`.
Topic cloud (categories + top tags → `/topics/<slug>/`). Recent additions row (latest 4).

### Task 11: Topics, About, 404, sitemap, RSS

**Files:** Create `templates/topic.html`, updated `about.html`, `404.html` (+ keep `error.html`
as symlink-equivalent copy for existing host config), `sitemap.xml`, `feed.xml`.

- `/topics/<cat-slug>/index.html` per category + `/topics/tag/<tag-slug>/index.html` per tag;
  each = intro line + card grid.
- About: restyle in place, history/screenshots preserved.
- RSS: full-item feed, newest 20. Sitemap: all routes with `lastmod` from git mtime.

---

## Phase 4 — Client features

### Task 12: Reading UX modules

**Files:** Create `assets/js/modules/{progress.js,toc.js,endnav.js,focus.js,memory.js,shortcuts.js}`
+ tiny `main.js` orchestrator (import map, `type=module`, deferred).

- `progress.js`: fixed bar, `transform: scaleX()` on rAF-throttled scroll; `role="progressbar"`
  with aria-valuenow.
- `toc.js`: IntersectionObserver scrollspy.
- `endnav.js`: floating ↑ top button appears past 600px; end-of-article actions are plain links.
- `focus.js`: toggles `<html data-focus>` hiding `[data-focus-hide]` (header decor, rain, grain,
  end-block extras); persists localStorage; Esc exits.
- `memory.js`: restore per-article scroll position (sessionStorage, keyed by slug, only if <30d).
- `shortcuts.js`: `/` or `⌘K`→search, `f`→focus, `t`→top; ignore when typing in inputs.

Budget check: all modules together ≤ 12 KB gz.

### Task 13: Cinematic FX module — configurable by design

**Files:** Create `assets/js/modules/fx.js`, `assets/js/modules/rain.js`; extend `_data/site.yaml`.

Config shape (build injects as `window.__FX__`, single source of truth):
```yaml
fx:
  enabled: true            # master switch — flips everything off
  atmosphere_toggle: true  # show user-facing toggle in header
  rain:    {enabled: true, density: 120, speed: 1.0, tier_auto: true}
  flicker: {enabled: true}
  scanlines: {enabled: true}
  grain:   {enabled: true}
```

- Each effect registers behind its flag; removing one = flip YAML, rebuild. All visual values
  flow through the `--fx-*` CSS vars (Task 6) — retuning never touches JS.
- `rain.js`: single fixed `<canvas>` behind content, pointer-events:none; capped 30fps;
  `visibilitychange` pauses; density knob = drop count; **FPS watchdog**: rolling 2s average
  frame > 24ms ⇒ downgrade tier (density×0.5, then pause) — automatic performance safety net.
- Flicker = CSS keyframe opacity/text-shadow on `.neon` accents only. Scanlines/grain =
  static CSS overlays (repeating-gradient / SVG noise, opacity via vars).
- Atmosphere toggle (persisted) + focus mode force-disable FX + `prefers-reduced-motion`
  disables all regardless of config.
- Document a "Tuning the atmosphere" subsection in README (which knob does what, perf tiers).

### Task 14: Performance pass

- [ ] `images.py` (Pillow): covers → WebP 480/800/1280w (q80) + JPG fallback; regenerate
  `cover-crop` (16:9) and `cover-sq` (1:1) variants; explicit width/height everywhere (CLS 0).
  Verify: largest article-page payload (excluding lazily loaded) < 350 KB.
- [ ] Speculation Rules `<script type=speculationrules>` prerender/prefetch same-site links;
  `<link rel=preload>` for font + LCP cover only.
- [ ] Budget script in `cli.py check`: gzip sizes of css/js vs Global Constraints; fails build
  when exceeded.
- [ ] Lighthouse (local): ≥95 perf/a11y/bp/seo on Home, Library, one long article, mobile profile.

### Task 15: Search

**Files:** Create `src/br_insight/search.py`, `assets/js/modules/search.js`,
`templates/search.html`, vendor `assets/js/vendor/minisearch.min.js` (~10 KB gz).

- Build emits `search-index.json`: title, author, summary, category, tags, date, url,
  body text (stripped). Estimated ≤ 150 KB gz — fetched lazily on first search open, cached.
- Overlay UI: modal with input, fuzzy + prefix match, grouped results, highlighted matches,
  arrow-key navigation, Enter opens; `/search/?q=` fallback page for no-JS.
- Test: `search.py` unit tests (index fields present, JSON loads, size budget asserted).

### Task 16: Legacy cleanup + docs

- Delete: jQuery/skel/util/old main.js, `assets/js/ie/`, superseded CSS/Sass,
  `assets/templates/`. Update `robots.txt` (allow all + sitemap). Rewrite README quickstart
  (`uv run br-insight build && uv run br-insight serve`). Update AGENTS.md: new layout,
  build commands, "regenerate min.css", FX tuning pointer.
- Full-tree grep for dead references (`jquery|skel|ie8|ie9|templates/`) → zero hits.

---

## Phase 5 — Verification & release prep

### Task 17: QA sweep

- [ ] `uv run br-insight check`: zero broken internal links; idempotent rebuild (clean git tree).
- [ ] `pytest -q` all green.
- [ ] Browser smoke (OpenCode browser tools, `serve`): iPhone SE / iPad / 1440 desktop widths —
  home, library + filters, search, one short + one long article, focus mode, atmosphere toggle,
  reduced-motion emulation, back-to-top, progress bar, 404.
- [ ] Owner walkthrough checklist in PR description; screenshots at 3 breakpoints.
- [ ] Final commit sequence tidy-up; tag `v2.0.0-site-redesign`.

---

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Malformed legacy front matter breaks builds | Task 2 normalization + strict tests thereafter |
| Rain/FX hurts low-end devices | Config flags + CSS-var knobs + FPS watchdog auto-degrade + user toggle |
| Search index too large | Body-only-on-demand sizing test in Task 15; trim to summaries if > 200 KB gz |
| Host ignores `404.html` (uses `error.html`) | Ship both files, identical content |
| Owner disagrees with taxonomy | Hard STOP review gate at Task 4 before any topic pages build |

## Owner decisions needed during execution
1. Approve/correct Task 4 taxonomy mapping (blocking gate).
2. Confirm featured-article default (`postmodernist-view`) or supply preferred slug/monthly picks.
3. Optional: author bios or external links for an Authors section (YAGNI unless supplied).
