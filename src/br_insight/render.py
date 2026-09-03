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
import hashlib
import re
from collections import Counter
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

from br_insight.articles import extract_toc, load_all, related
from br_insight.config import (
    SiteConfig,
    apply_taxonomy,
    load_taxonomy,
    resolve_archive_picks,
    resolve_featured,
)
from br_insight.images import CoverVariants, generate_cover_variants
from br_insight.search import write_index
from br_insight.textutils import slugify

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = REPO_ROOT / "templates"

# A Contents aside is only worth rendering when there is enough structure
# to navigate; fewer h2/h3 headings than this means no aside.
TOC_MIN_HEADINGS = 3

# Home page: topic-cloud tag cap (archive-row size lives in
# config.ARCHIVE_PICK_COUNT).
TOPIC_TAG_LIMIT = 10

# RSS full-summary feed: newest-N window.
FEED_ITEM_LIMIT = 20


def _toc_heading_count(toc: list[dict]) -> int:
    """Total h2/h3 entries across the TOC tree, children included.

    The build-generated footnotes header ("notes") doesn't count toward
    the aside threshold — it's machinery, not authored structure.
    """
    return sum(
        (entry["id"] != "notes")
        + sum(child["id"] != "notes" for child in entry["children"])
        for entry in toc
    )


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


def library_facets(articles) -> dict[str, dict[str, int]]:
    """Per-value chip counts for the library filter toolbar.

    Mirrors the :func:`facets` vocabularies keyed by the chips' ``data-group``
    names (``category``/``tag``/``author``/``decade``) as ``value → count``;
    multi-tag articles count once per tag.
    """
    counts: dict[str, Counter] = {
        "category": Counter(),
        "tag": Counter(),
        "author": Counter(),
        "decade": Counter(),
    }
    for article in articles:
        counts["category"][article.category] += 1
        counts["author"][article.author] += 1
        counts["decade"][decade(article.date)] += 1
        for tag in article.tags:
            counts["tag"][tag] += 1
    return {group: dict(values) for group, values in counts.items()}


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


def home_context(site: SiteConfig, articles, now: datetime.datetime, variants=None) -> dict:
    """Assemble everything templates/home.html needs from the corpus."""
    featured = resolve_featured(site, articles, now.strftime("%Y%m"))
    iso_cal = now.isocalendar()
    iso_year_week = f"{iso_cal.year}-W{iso_cal.week:02d}"
    picks = resolve_archive_picks(articles, iso_year_week, featured.slug)
    # Minimal per-article payload for the client-side weekly carousel:
    # JS re-applies the same digest pick with the *visitor's* current ISO
    # week so the row rotates by time, independent of rebuild cadence.
    # ``crop`` carries each article's actual 16:9 crop-width ladder (from
    # its CoverVariants plan) so client-built srcsets never cite a
    # missing candidate.
    payload = [
        {
            "slug": a.slug,
            "title": a.title,
            "author": a.author,
            "minutes": a.minutes,
            "date": a.date.strftime("%Y-%m-%d"),
            "category": a.category,
            "tags": a.tags,
            "crop": list(plan.crop) if (plan := (variants or {}).get(a.slug)) and plan.crop else [],
        }
        for a in sorted(articles, key=lambda x: x.slug)
    ]
    return {
        "featured": featured,
        "featured_month": now.strftime("%B"),
        "stats": archive_stats(articles),
        "topics": topic_cloud(articles),
        "archive_picks": picks,
        "iso_year_week": iso_year_week,
        "archive_payload": payload,
        # Slug list for main.js's random-essay action; rendered into the
        # home-only <script type="application/json" id="essay-slugs"> hook.
        "essay_slugs": [article.slug for article in articles],
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


def topic_title_size(name: str) -> str:
    """Font tier for a topic page h1 rendered in Sixtyfour.

    Sixtyfour advances exactly 1em per glyph (monospace pixel grid), so on a
    320px phone fs-3xl fits only ~8 characters per line. The global
    ``overflow-wrap: break-word`` would split a too-long word mid-word
    ("Adaptatio / n"), so each name drops to a tier whose size fits its
    longest whitespace-separated word: lg ≤7 chars, md ≤9, sm ≤11, xs ≥12
    (fs-3xl/2xl/xl/lg fit ~8/10/12/16 chars at 320px).
    """
    longest = max(len(word) for word in name.split())
    if longest <= 7:
        return "lg"
    if longest <= 9:
        return "md"
    if longest <= 11:
        return "sm"
    return "xs"


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
                    "title_size": topic_title_size(name),
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


def fx_config(site: SiteConfig) -> dict | None:
    """Client FX payload for ``window.__FX__`` (Task 13).

    Mirrors ``site.fx`` effect-by-effect as plain JSON-able data; the
    master switch never travels to the client (when off, the whole
    payload is omitted and the runtime module stays inert).
    """
    if not site.fx.enabled:
        return None
    return {
        "enabled": site.fx.enabled,
        "rain": {
            "enabled": site.fx.rain.enabled,
            "density": site.fx.rain.density,
            "speed": site.fx.rain.speed,
            "tier_auto": site.fx.rain.tier_auto,
        },
        "flicker": {
            "enabled": site.fx.flicker.enabled,
            "welcome": site.fx.flicker.welcome,
        },
        "scanlines": {"enabled": site.fx.scanlines.enabled},
        "grain": {"enabled": site.fx.grain.enabled},
    }


@functools.lru_cache(maxsize=64)
def _asset_ver(root_str: str, relpath: str) -> str:
    """``?v=<hash8>`` suffix for a repo asset, or ``""`` if it is missing.

    Cached per process — a build reads each asset once, and the CLI runs
    are fresh processes, so staleness across builds is not a concern.
    """
    path = Path(root_str) / relpath
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:8]
    except OSError:
        return ""
    return f"?v={digest}"


def asset_ver(relpath: str) -> str:
    """Jinja global: version-query suffix for a repo-root asset path."""
    return _asset_ver(str(REPO_ROOT), relpath)


def get_env() -> Environment:
    """Shared Jinja2 environment loading ``templates/`` from the repo root."""
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(("html", "xml")),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.globals["now"] = _Clock()
    env.globals["fx_config"] = fx_config
    env.globals["asset_ver"] = asset_ver
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

    # Task 15: compact search index (records + stripped bodies) for the
    # lazy client overlay; fetched on first search open, never render-blocking.
    write_index(out, articles)


    # Task 14: generate responsive cover variants (WebP + JPEG fallbacks,
    # 16:9 card crops) next to each page's output so built
    # pages can cite them. Sources stay read-only; existing-current
    # outputs are skipped, keeping in-tree rebuilds idempotent.
    variants: dict[str, CoverVariants | None] = {
        article.slug: generate_cover_variants(
            root / "library" / article.slug,
            dest=out / "library" / article.slug,
        )
        for article in articles
    }

    written: list[Path] = []
    for article in articles:
        toc = extract_toc(article.html)
        html = render_template(
            "article.html",
            site=site,
            article=article,
            related=related(article, articles),
            toc=toc if _toc_heading_count(toc) >= TOC_MIN_HEADINGS else [],
            og_cover=_og_cover(root, article, out),
            cover_variants=variants.get(article.slug),
            variants=variants,
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
            variants=variants,
            **facets(articles),
            chip_counts=library_facets(articles),
            current_path="library/",
            now=now,
        ),
        encoding="utf-8",
    )
    written.append(library_page)

    home_page = out / "index.html"
    home_page.parent.mkdir(parents=True, exist_ok=True)
    home_page.write_text(
        render_template(
            "home.html",
            site=site,
            now=now,
            variants=variants,
            **home_context(site, articles, now, variants),
        ),
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
            current_path="/topics/",
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
                variants=variants,
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


def _og_cover(root: Path, article, out: Path | None = None) -> str:
    """Social-image filename for ``article`` (Task 14 upgrade path).

    Preference order:
    1. the largest generated JPEG hero variant (``cover-<max>.jpg``) when
       it exists in the output tree — crawlers do not decode WebP;
    2. the front-matter ``cover`` when that file exists on disk under
       ``library/<slug>/`` (Task 8 ruling preserved as fallback);
    3. the physically guaranteed ``cover.jpg``.
    """
    base = out if out is not None else root
    declared_cover = base / "library" / article.slug / article.cover
    if og_cover := _og_variant(base / "library" / article.slug):
        return og_cover
    if article.cover and declared_cover.is_file():
        return article.cover
    return "cover.jpg"


def _og_variant(variant_dir: Path) -> str | None:
    """Largest bare ``cover-<W>.jpg`` hero variant present, if any.

    Only bare hero names match (``cover-crop-*`` names carry an extra stem
    and are not social-card candidates).
    """
    hero_re = re.compile(r"^cover-(\d+)\.jpg$")
    widths = sorted(
        int(m.group(1))
        for p in variant_dir.glob("cover-*.jpg")
        if (m := hero_re.match(p.name))
    )
    if not widths:
        return None
    return f"cover-{widths[-1]}.jpg"
