# AGENTS.md

Static site for [Blade Runner Insight](https://www.br-insight.com) (br-insight.com). Plain HTML/CSS/JS based on the HTML5 UP "Solid State" template (CCA 3.0 license) — no web framework or JS build tooling.

## Layout

- `index.html`, `about.html`, `error.html` — top-level pages.
- `library/<article-slug>/` — one directory per article. Each contains:
  - `article.md` — Markdown source with YAML front matter (`title`, `author`, `cover`, `date`, `taxonomy.category: article`, `summary.enabled/size`).
  - `index.html` — rendered HTML version of the article (this is what serves).
  - `article.css` / `article.min.css`, cover images.
  - When updating an article, keep `article.md` and `index.html` content in sync.
- `assets/templates/` — canonical page skeletons (`home.html`, `library.html`, `article.html`, `article.css`). Base new/edited pages on these rather than inventing markup.
- `library/index.html` — library listing; add new articles here ("re-indexed" commits do this).
- `assets/css/*.min.css` — pages load the **minified** CSS (`main.min.css`, `<page>.min.css`). If you change a `.css` file, regenerate/update the matching `.min.css` too.
- `assets/sass/` — Sass sources for the base template; compiled output lives in `assets/css/`.
- Relative paths differ by depth: root pages use `assets/...`, library articles use `../../assets/...`.

## Python tooling (in progress)

Repo is being scaffolded as a Python package via [uv](https://docs.astral.sh/uv/) (`.python-version` = 3.14, `uv_build` backend), intended entry point `br-insight = br_insight:main`. No Python source exists yet — don't assume it runs. Use `uv` for env/deps.

## Commands

No test, lint, or CI configuration exists. To preview the site locally:

```
python3 -m http.server 8000   # from repo root
```
