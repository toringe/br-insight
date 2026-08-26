"""Jinja2 rendering environment + static-site build pipeline.

Task 7 scope: environment setup + ``render_template`` helper.
Task 8 scope: ``build()`` fans the corpus out to
``library/<slug>/index.html`` pages with relative asset depth.
"""

from __future__ import annotations

import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from PIL import Image

from br_insight.articles import extract_toc, load_all, related
from br_insight.config import SiteConfig, apply_taxonomy, load_taxonomy

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = REPO_ROOT / "templates"


class _Clock:
    """Live ``now`` global: ``year`` always reads the current wall clock.

    A cached environment therefore never serves a frozen timestamp;
    callers who need determinism (``build``) inject a concrete datetime
    via the context, which overrides this global.
    """

    @property
    def year(self) -> int:
        return datetime.datetime.now().year


def get_env() -> Environment:
    """Shared Jinja2 environment loading ``templates/`` from the repo root."""
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(("html", "xml")),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.globals["now"] = _Clock()
    return env


_env: Environment | None = None


def _shared_env() -> Environment:
    global _env
    if _env is None:
        _env = get_env()
    return _env


def render_template(name: str, **ctx):
    """Render ``templates/<name>`` with the given context.

    The clock is injectable per call (``now``) so a cached environment
    never serves a stale year across midnight builds.
    """
    ctx.setdefault("now", datetime.datetime.now())
    template = _shared_env().get_template(name)
    return template.render(**ctx)


def build(root: Path, out: Path) -> list[Path]:
    """Render every article page into ``<out>/library/<slug>/index.html``.

    Returns the list of written paths. Only article pages are written;
    sources, covers and legacy assets are read-only inputs. The wall
    clock is sampled once so a single run stays self-consistent.
    """
    now = datetime.datetime.now()
    site = SiteConfig.load(root)
    taxonomy = load_taxonomy(root)
    articles = apply_taxonomy(load_all(root), taxonomy)

    cover_sizes: dict[str, tuple[int, int]] = {}
    written: list[Path] = []
    for index, article in enumerate(articles):
        newer = articles[index - 1] if index > 0 else None
        older = articles[index + 1] if index + 1 < len(articles) else None
        width, height = _cover_size(root, article.slug, cover_sizes)
        html = render_template(
            "article.html",
            site=site,
            article=article,
            newer=newer,
            older=older,
            related=related(article, articles),
            toc=extract_toc(article.html),
            cover_width=width,
            cover_height=height,
            now=now,
        )
        destination = out / "library" / article.slug / "index.html"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(html, encoding="utf-8")
        written.append(destination)
    return written


def _cover_size(
    root: Path, slug: str, cache: dict[str, tuple[int, int]]
) -> tuple[int, int]:
    if slug not in cache:
        with Image.open(root / "library" / slug / "cover.jpg") as image:
            cache[slug] = image.size
    return cache[slug]
