"""Jinja2 rendering environment + static-site build pipeline.

Task 7 scope: environment setup + ``render_template`` helper.
Task 8 scope: ``build()`` fans the corpus out to
``library/<slug>/index.html`` pages with relative asset depth.
Task 9 scope: ``decade``/``facets`` helpers and the
``library/index.html`` listing page (server-rendered cards + chips).
Task 10 scope: ``archive_stats``/``topic_cloud``/``home_context``
helpers and the root ``index.html`` home page.
Task 11 scope: ``topic_pages`` + ``templates/topic.html`` fan-out to
``/topics/<cat-slug>/`` and ``/topics/tag/<tag-slug>/`` pages, the new
``about.html``, byte-twin ``404.html``/``error.html``, ``sitemap.xml``
and ``feed.xml``.
"""

from __future__ import annotations

import datetime
import email.utils
import functools
from collections import Counter
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from PIL import Image

from br_insight.articles import extract_toc, load_all, related
from br_insight.config import SiteConfig, apply_taxonomy, load_taxonomy, resolve_featured
from br_insight.textutils import slugify

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = REPO_ROOT / "templates"

# A Contents aside is only worth rendering when there is enough structure
# to navigate; fewer h2/h3 headings than this means no aside.
TOC_MIN_HEADINGS = 3

# Home page: recent-additions row size and topic-cloud tag cap.
RECENT_COUNT = 4
TOPIC_TAG_LIMIT = 10

# RSS full-summary feed: newest-N window.
FEED_ITEM_LIMIT = 20


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


def archive_stats(articles) -> dict[str, int]:
    """Build-time totals for the home stats band."""
    return {
        "essays": len(articles),
        "authors": len({article.author for article in articles}),
        "words": sum(article.words for article in articles),
    }


def topic_cloud(articles) -> list[dict]:
    """Home topic links: every category (A-Z), then the most-used tags.

    Each entry is ``{"label", "href"}`` with canonical slugified URLs
    (``/topics/<cat-slug>/`` and ``/topics/tag/<tag-slug>/``); the tag
    cap keeps the cloud to the highest-count vocabulary.
    """
    topics = [
        {"label": category, "href": f"/topics/{slugify(category)}/"}
        for category in sorted({article.category for article in articles})
    ]
    counts = Counter(tag for article in articles for tag in article.tags)
    top_tags = sorted(counts, key=lambda tag: (-counts[tag], tag))[:TOPIC_TAG_LIMIT]
    topics.extend(
        {"label": tag, "href": f"/topics/tag/{slugify(tag)}/"} for tag in top_tags
    )
    return topics


def home_context(site: SiteConfig, articles, now: datetime.datetime) -> dict:
    """Assemble everything templates/home.html needs from the corpus."""
    return {
        "featured": resolve_featured(site, articles, now.strftime("%Y%m")),
        "featured_month": now.strftime("%B"),
        "stats": archive_stats(articles),
        "topics": topic_cloud(articles),
        "recent": articles[:RECENT_COUNT],
        "current_path": "/",
    }


# ---------------------------------------------------------------------------
# Task 11: topic pages
# ---------------------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def load_topic_intros() -> dict[str, dict[str, str]]:
    """Curated one-line topic intros from ``_data/topics.yaml``.

    Missing keys fall back to generic lines rendered by
    :func:`topic_pages`, so newly added categories/tags never 404 on
    their own copy.
    """
    path = REPO_ROOT / "_data" / "topics.yaml"
    if not path.is_file():
        return {"category": {}, "tag": {}}
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return {
        "category": dict(data.get("categories") or {}),
        "tag": dict(data.get("tags") or {}),
    }


def _generic_intro(kind: str, name: str) -> str:
    filed_by = "filed under" if kind == "category" else "tagged"
    return f"A running thread through the archive: essays {filed_by} “{name}”."


def topic_pages(
    articles, intros: dict[str, dict[str, str]] | None = None
) -> list[dict]:
    """Category + tag topic descriptors derived from the corpus itself.

    Vocabularies are never read directly — only categories/tags actually
    carried by ``articles`` become topics, so an empty topic page is
    structurally impossible. Each entry carries ``kind``, ``name``,
    ``slug``, ``href``, ``count``, its articles (newest-first), and an
    ``intro`` line (curated copy when available, generic otherwise).
    """
    if intros is None:
        intros = load_topic_intros()
    by_kind = {"category": {}, "tag": {}}
    for article in articles:
        by_kind["category"].setdefault(article.category, []).append(article)
        for tag in article.tags:
            by_kind["tag"].setdefault(tag, []).append(article)

    topics: list[dict] = []
    for kind in ("category", "tag"):
        prefix = "" if kind == "category" else "tag/"
        for name, members in sorted(by_kind[kind].items()):
            slug = slugify(name)
            topics.append(
                {
                    "kind": kind,
                    "name": name,
                    "slug": slug,
                    "href": f"/topics/{prefix}{slug}/",
                    "count": len(members),
                    "articles": members,
                    "intro": intros.get(kind, {}).get(name)
                    or _generic_intro(kind, name),
                }
            )
    return topics


# ---------------------------------------------------------------------------
# Task 11: sitemap + RSS syndication helpers
# ---------------------------------------------------------------------------


def sitemap_entries(
    site: SiteConfig, articles, now: datetime.datetime
) -> list[dict]:
    """All indexable routes as ``{"loc", "lastmod"}``.

    Articles carry their own publish date as ``lastmod``; every index
    route (home, library, topics hub, about) gets the build date.
    """
    today = now.date().isoformat()

    def entry(path: str, lastmod: str) -> dict:
        return {"loc": f"{site.base_url}{path}", "lastmod": lastmod}

    entries = [
        entry(p, today)
        for p in ("/", "/library/", "/topics/", "/about.html")
    ]
    entries += [entry(t["href"], today) for t in topic_pages(articles)]
    entries += [
        entry(f"/library/{article.slug}/", article.date.date().isoformat())
        for article in articles
    ]
    return entries


def feed_items(base_url: str, articles) -> list[dict]:
    """Newest ``FEED_ITEM_LIMIT`` essays as RSS 2.0 ``<item>`` fields.

    ``pubdate`` is RFC-822 (UTC-naive article dates pinned to UTC);
    ``description`` is the front-matter summary credited to the author.
    """
    items = []
    for article in articles[:FEED_ITEM_LIMIT]:
        pubdate = email.utils.format_datetime(
            article.date.replace(tzinfo=datetime.timezone.utc)
        )
        items.append(
            {
                "title": article.title,
                "link": f"{base_url}/library/{article.slug}/",
                "pubdate": pubdate,
                "description": f"{article.summary} — {article.author}",
            }
        )
    return items


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
    """Render every article page plus the site's index surfaces.

    Returns the list of written paths: ``library/<slug>/index.html``,
    ``library/index.html``, the root ``index.html``, the ``topics/``
    hub, one page per used category/tag under ``topics/``,
    ``about.html``, byte-twin ``404.html`` + ``error.html``,
    ``sitemap.xml``, and ``feed.xml``.
    Sources, covers and legacy assets are read-only inputs. The wall
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

    home_page = out / "index.html"
    home_page.parent.mkdir(parents=True, exist_ok=True)
    home_page.write_text(
        render_template("home.html", site=site, now=now, **home_context(site, articles, now)),
        encoding="utf-8",
    )
    written.append(home_page)

    # Topic pages: derive routes from the enriched corpus (never the raw
    # vocabularies) so an empty topic can't exist. Category pages sit at
    # depth 2; tag pages at depth 3. The same descriptors feed the hub
    # page at /topics/ (the primary-nav "Topics" target).
    topics = topic_pages(articles)
    hub_page = out / "topics" / "index.html"
    hub_page.parent.mkdir(parents=True, exist_ok=True)
    hub_page.write_text(
        render_template(
            "topics.html",
            site=site,
            categories=[t for t in topics if t["kind"] == "category"],
            tags=[t for t in topics if t["kind"] == "tag"],
            now=now,
        ),
        encoding="utf-8",
    )
    written.append(hub_page)

    for topic in topics:
        parts = ["topics"] + (["tag"] if topic["kind"] == "tag" else []) + [topic["slug"]]
        topic_page = out.joinpath(*parts, "index.html")
        topic_page.parent.mkdir(parents=True, exist_ok=True)
        asset_prefix = "../../" if topic["kind"] == "category" else "../../../"
        topic_page.write_text(
            render_template(
                "topic.html",
                site=site,
                topic=topic,
                asset_prefix=asset_prefix,
                now=now,
            ),
            encoding="utf-8",
        )
        written.append(topic_page)

    about_page = out / "about.html"
    about_page.write_text(
        render_template("about.html", site=site, current_path="/about.html", now=now),
        encoding="utf-8",
    )
    written.append(about_page)

    not_found = render_template("404.html", site=site, current_path="/404.html", now=now)
    written.append(out / "404.html")
    (out / "404.html").write_text(not_found, encoding="utf-8")
    error_twin = out / "error.html"
    error_twin.write_text(not_found, encoding="utf-8")  # byte-identical copy
    written.append(error_twin)

    sitemap = out / "sitemap.xml"
    sitemap.write_text(
        render_template(
            "sitemap.xml",
            entries=sitemap_entries(site, articles, now),
            now=now,
        ),
        encoding="utf-8",
    )
    written.append(sitemap)

    feed = out / "feed.xml"
    feed.write_text(
        render_template(
            "feed.xml",
            site=site,
            items=feed_items(site.base_url, articles),
            rfc_now=email.utils.format_datetime(now.replace(tzinfo=datetime.timezone.utc)),
            now=now,
        ),
        encoding="utf-8",
    )
    written.append(feed)
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
