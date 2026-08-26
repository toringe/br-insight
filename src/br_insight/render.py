"""Jinja2 rendering environment + static-site build pipeline.

Task 7 scope: environment setup + ``render_template`` helper.
Task 8 scope: ``build()`` fans the corpus out to
``library/<slug>/index.html`` pages with relative asset depth.
Task 9 scope: ``decade``/``facets`` helpers and the
``library/index.html`` listing page (server-rendered cards + chips).
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

# A Contents aside is only worth rendering when there is enough structure
# to navigate; fewer h2/h3 headings than this means no aside.
TOC_MIN_HEADINGS = 3


def _toc_heading_count(toc: list[dict]) -> int:
    """Total h2/h3 entries across the TOC tree, children included."""
    return sum(1 + len(entry["children"]) for entry in toc)


def decade(date: datetime.date) -> str:
    """Decade label for a date: ``1996-11-30`` → ``"1990s"``."""
    return f"{date.year // 10 * 10}s"


def facets(articles) -> dict[str, list[str]]:
    """Distinct filter vocabularies for the library page.

    Categories/tags/authors sort A-Z; decades stay chronological
    (``1990s`` before ``2000s``, which plain string sort would break).
    """
    decades = {decade(article.date) for article in articles}
    return {
        "categories": sorted({a.category for a in articles}),
        "tags": sorted({tag for a in articles for tag in a.tags}),
        "authors": sorted({a.author for a in articles}),
        "decades": sorted(decades, key=lambda d: int(d[:-1])),
    }


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
    env.filters["decade"] = decade
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
        toc = extract_toc(article.html)
        html = render_template(
            "article.html",
            site=site,
            article=article,
            newer=newer,
            older=older,
            related=related(article, articles),
            toc=toc if _toc_heading_count(toc) >= TOC_MIN_HEADINGS else [],
            og_cover=_og_cover(root, article),
            cover_width=width,
            cover_height=height,
            now=now,
        )
        destination = out / "library" / article.slug / "index.html"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(html, encoding="utf-8")
        written.append(destination)

    library_page = out / "library" / "index.html"
    library_page.parent.mkdir(parents=True, exist_ok=True)
    library_page.write_text(
        render_template(
            "library.html",
            site=site,
            articles=articles,
            **facets(articles),
            current_path="library/",
            now=now,
        ),
        encoding="utf-8",
    )
    written.append(library_page)
    return written


def _cover_size(
    root: Path, slug: str, cache: dict[str, tuple[int, int]]
) -> tuple[int, int]:
    if slug not in cache:
        with Image.open(root / "library" / slug / "cover.jpg") as image:
            cache[slug] = image.size
    return cache[slug]


def _og_cover(root: Path, article) -> str:
    """Social-image filename for ``article``.

    The front-matter ``cover`` when it exists on disk under
    ``library/<slug>/``, else the physically guaranteed ``cover.jpg``
    (social cards must never point at a 404).
    """
    declared = root / "library" / article.slug / article.cover
    return article.cover if declared.is_file() else "cover.jpg"
