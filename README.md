# Blade Runner Insight Website

This repository contains all static files for the [Blade Runner Insight](https://www.br-insight.com) website. Articles are updated and revised here; the rendered tree at the repo root is the deployable site.

## Quickstart

```
uv sync                    # set up the Python environment (3.14)
uv run br-insight build    # render Markdown articles → static tree at the repo root
uv run br-insight serve    # serve the built site at http://localhost:8000
uv run br-insight check    # audit asset budgets + internal link integrity
```

Run the test suite with `uv run pytest -q` — the built tree must stay pristine against it.

## How the site is built

The site is plain HTML/CSS/JS with no web framework and no Node toolchain. A small Python pipeline (`src/br_insight/`) turns Jinja2 sources + site data into the static tree:

| Source | → Output |
| --- | --- |
| `templates/` (`base.html`, `home.html`, `library.html`, `article.html`, topic pages) + `_data/` (`site.yaml`, `taxonomy.yaml`, `topics.yaml`) | `index.html`, `about.html`, `library/index.html`, `topics/…` |
| `library/<slug>/article.md` (Markdown + YAML front matter) | `library/<slug>/index.html` |
| `library/<slug>/cover.jpg\|png` | `cover-{W}` / `cover-crop-{W}` responsive variants in WebP + JPEG |
| article metadata | `feed.xml`, `sitemap.xml` |
| 404 template | `404.html` + byte-identical `error.html` (map your host's 404 config to it) |

Article sources live next to their rendered pages: edit `library/<slug>/article.md`, rebuild, and never hand-edit the generated HTML. Article URLs (`/library/<slug>/`) are stable — don't rename slugs casually.

Pages load minified CSS (`assets/css/main.min.css`). After editing a source `.css`, regenerate its `.min.css` sibling with `uv run python scripts/minify_css.py`.

**Deployment:** the entire repo root is a self-contained static tree — drop it on any static host (S3 + CloudFront-style). `robots.txt` allows all crawlers and points to `sitemap.xml`.

## Tuning the atmosphere

The cinematic FX (rain, neon flicker, scanlines, grain) are configured by design: every knob is data — YAML keys flip effects on/off at build time, CSS custom properties tune their look, and the runtime module adds user / accessibility gating on top. Retuning never requires touching JS.

| Knob | Where | Effect |
| --- | --- | --- |
| `fx.enabled` | `_data/site.yaml` | Master switch; off omits the `window.__FX__` payload and all `data-fx-*` flags — the runtime stays inert |
| `fx.atmosphere_toggle` | `_data/site.yaml` | Shows/hides the header **Atmosphere** button |
| `fx.rain.enabled` / `.density` / `.speed` / `.tier_auto` | `_data/site.yaml` | Canvas rain; density ≈ drop count at desktop widths (scales down below 1280 px), speed multiplies fall velocity, `tier_auto` enables the FPS watchdog |
| `fx.flicker.enabled` / `.welcome` | `_data/site.yaml` | Neon flicker on `.neon` accents; `welcome` is the one-shot hero flicker-in |
| `fx.scanlines.enabled` / `fx.grain.enabled` | `_data/site.yaml` | Static CSS overlays behind their `html[data-fx-*]` flags |
| `--fx-rain-opacity`, `--fx-scanline-opacity`, `--fx-grain-opacity` | `assets/css/main.css` | Overlay intensity per effect |
| `--fx-flicker-strength` | `assets/css/main.css` | Neon dip depth + glow radius (drives both keyframes and text-shadow math) |
| Atmosphere button | User preference | Persists to `localStorage["bri:atmosphere"]`; off sets `html[data-fx-off]` and kills every effect regardless of YAML |

Known cosmetic behavior: the welcome flicker replays on every full page load of the home page (it is intentionally one-shot per page load, not per session).

### Degradation behavior

- Focus mode (`<html data-focus>`) and `prefers-reduced-motion` force-disable everything, overriding even an enabled config (reduced motion is also neutralized in CSS as a second layer).
- The rain canvas caps itself at ~30 fps via timestamp accumulation (never `setInterval`), pauses completely while the tab is hidden, re-seeds its buffer on debounced resize (DPR-aware, capped at 2x), and honours `document.hidden`.
- FPS watchdog (`rain.tier_auto`): rolling 2 s frame average > 24 ms halves the drop density once; still slow after that → rain pauses permanently with a `console.info` note.
- Zero-JS visitors simply get the page content without any atmosphere runtime (no canvas, overlays, or button behavior); broken modules never take the rest of the page down.

## Search

The build emits a compact search index to `assets/js/search-index.json`: one record per essay (slug, root-relative URL, title, author, ISO date, category, tags, summary, and the full stripped body text). The overlay (`assets/js/modules/search.js` + vendored MiniSearch v6) fetches it lazily on first open — header Search button, `⌘K`, or `/` — and never blocks page render. The index stays under a 200 KB gzipped budget, enforced by `uv run br-insight check`; a plain content edit refreshes it via `uv run br-insight build --out .`. Zero-JS visitors see a noscript pointer to the library filters instead of the modal.

## Hosting

A Cloudflare Worker is building the page, and deploy to Cloudflare Pages, triggered by pushing/PR to master or dev branches.

Worker settings:
```
Build command: pip install uv && uv sync --frozen && uv run br-insight build && env | grep -iE 'branch|CI_' | sort
Deploy command: npx wrangler pages project create br-insight --production-branch=master 2>/dev/null; npx wrangler pages deploy . --project-name=br-insight --branch="$WORKERS_CI_BRANCH"
Version command: npx wrangler pages project create br-insight --production-branch=master 2>/dev/null; npx wrangler pages deploy . --project-name=br-insight --branch="$WORKERS_CI_BRANCH"
```

master -> https://br-insight.pages.dev/
dev -> https://dev.br-insight.pages.dev/

Other branches goes to the alias with the same name as the branch.
