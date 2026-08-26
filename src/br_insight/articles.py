"""Article domain model and loaders for the br-insight static site."""

from __future__ import annotations

import datetime
import math
import re
from dataclasses import dataclass
from pathlib import Path

from markdown_it import MarkdownIt

from br_insight import frontmatter

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_LEGACY_DATE = re.compile(r"^\d{2}-\d{2}-\d{4}$")
_BOLD = re.compile(r"(\*\*|__)(.+?)\1", re.DOTALL)
_ITALIC = re.compile(r"(\*|_)(.+?)\1", re.DOTALL)
_HEADING = re.compile(r"<h([1-6])>(.*?)</h\1>", re.DOTALL)
_INLINE_TAGS = re.compile(r"<[^>]+>")
_NON_SLUG = re.compile(r"[^a-z0-9]+")

_MARKDOWN = MarkdownIt()


@dataclass(frozen=True)
class Article:
    slug: str
    title: str
    author: str
    cover: str
    cover_artist: str | None
    date: datetime.datetime
    words: int
    minutes: int
    summary: str
    copyright: str | None
    source: str | None
    category: str
    tags: list[str]
    html: str  # rendered markdown


def reading_time(words: int) -> int:
    """Estimated reading time in minutes: ceil(words/220), minimum 1."""
    return max(1, math.ceil(words / 220))


def parse_date(raw: str | datetime.date | datetime.datetime) -> datetime.datetime:
    """Normalize a front-matter date to a ``datetime``.

    Accepts bare ISO strings (PyYAML resolves them to ``datetime.date``),
    ISO ``YYYY-MM-DD`` strings, and legacy ``DD-MM-YYYY`` strings.
    """
    if isinstance(raw, datetime.datetime):
        return raw
    if isinstance(raw, datetime.date):
        return datetime.datetime(raw.year, raw.month, raw.day)
    text = str(raw).strip()
    if _ISO_DATE.match(text):
        return datetime.datetime.strptime(text, "%Y-%m-%d")
    if _LEGACY_DATE.match(text):
        return datetime.datetime.strptime(text, "%d-%m-%Y")
    raise ValueError(f"Unrecognized date format: {raw!r}")


def extract_summary(body: str, size: int = 100) -> str:
    """First ``size`` words of the body's first paragraph, emphasis-stripped.

    Appends an ellipsis when the paragraph is truncated.
    """
    paragraph = next((p.strip() for p in body.split("\n\n") if p.strip()), "")
    words = _ITALIC.sub(r"\2", _BOLD.sub(r"\2", paragraph)).split()
    if len(words) <= size:
        return " ".join(words)
    return " ".join(words[:size]) + "…"


def _slugify(text: str) -> str:
    return _NON_SLUG.sub("-", text.strip().lower()).strip("-")


def render_markdown(body: str) -> str:
    """Render markdown to HTML; headings get slugified ``id`` attributes."""
    html = _MARKDOWN.render(body)

    def add_id(match: re.Match[str]) -> str:
        level, inner = match.group(1), match.group(2)
        plain = _INLINE_TAGS.sub("", inner)
        return f'<h{level} id="{_slugify(plain)}">{inner}</h{level}>'

    return _HEADING.sub(add_id, html)


def load_all(root: Path) -> list[Article]:
    """Load every library article, sorted newest-first."""
    loaded = [
        _build_article(path.parent.name, *frontmatter.load(path))
        for path in sorted((root / "library").glob("*/article.md"))
    ]
    return sorted(loaded, key=lambda a: a.date, reverse=True)


def related(article: Article, all_articles: list[Article]) -> list[Article]:
    """Top 3 articles sharing the most tags with ``article``, descending."""
    tags = set(article.tags)
    scored = []
    for other in all_articles:
        if other is article:
            continue
        shared = len(tags & set(other.tags))
        if shared:
            scored.append((shared, other))
    scored.sort(key=lambda pair: -pair[0])
    return [other for _, other in scored[:3]]


def _build_article(slug: str, data: dict, body: str) -> Article:
    words = len(body.split())
    summary_block = data.get("summary") or {}
    taxonomy = data.get("taxonomy") or {}
    summary = ""
    if summary_block.get("enabled", True):
        size = int(summary_block.get("size", 100))
        summary = extract_summary(body, size=size)
    return Article(
        slug=slug,
        title=data.get("title", ""),
        author=data.get("author", ""),
        cover=data.get("cover", ""),
        cover_artist=data.get("cauthor"),
        date=parse_date(data["date"]),
        words=words,
        minutes=reading_time(words),
        summary=summary,
        copyright=data.get("copyright"),
        source=data.get("source"),
        category=taxonomy.get("category", ""),
        tags=list(data.get("tags") or []),
        html=render_markdown(body),
    )
