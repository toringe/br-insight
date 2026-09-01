"""Article domain model and loaders for the br-insight static site."""

from __future__ import annotations

import datetime
import math
import re
from dataclasses import dataclass
from pathlib import Path

from markdown_it import MarkdownIt
from mdit_py_plugins.footnote import footnote_plugin

from br_insight import frontmatter
from br_insight.textutils import slugify

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_LEGACY_DATE = re.compile(r"^\d{2}-\d{2}-\d{4}$")
_BOLD = re.compile(r"(\*\*|__)(.+?)\1", re.DOTALL)
_ITALIC = re.compile(r"(\*|_)(.+?)\1", re.DOTALL)
_HEADING = re.compile(r"<h([1-6])>(.*?)</h\1>", re.DOTALL)
_HEADING_WITH_ID = re.compile(r"<h([1-6]) id=\"([^\"]*)\">(.*?)</h\1>", re.DOTALL)
_ANCHOR_TAG = re.compile(r'<a class="anchor"[^>]*>.*?</a>', re.DOTALL)
_INLINE_TAGS = re.compile(r"<[^>]+>")
_ATX_HEADING = re.compile(r"^\s{0,3}#{1,6}(?:\s|$)")

_MARKDOWN = MarkdownIt().use(footnote_plugin)

# Inline footnote refs render as "[1]"; the brackets are noise — keep the
# number only.
_FOOTNOTE_REF_BRACKETS = re.compile(
    r'(<sup class="footnote-ref"><a[^>]*>)\[(\d+)\](</a></sup>)'
)
# The plugin emits <section class="footnotes"> bare; a heading is injected
# inside it so the notes get their own TOC-visible section header.
_FOOTNOTE_SECTION = '<section class="footnotes">'
_FOOTNOTES_HEADER = '<section class="footnotes">\n<h2>Notes</h2>'


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
    """First ``size`` words of the body's first prose paragraph, stripped.

    Pure ATX-heading blocks are skipped so a heading-led body yields real
    summary text. Emphasis markers are stripped and an ellipsis is appended
    when the paragraph is truncated.
    """
    paragraph = next(
        (
            p.strip()
            for p in body.split("\n\n")
            if p.strip()
            and not all(
                _ATX_HEADING.match(line)
                for line in p.splitlines()
                if line.strip()
            )
        ),
        "",
    )
    words = _ITALIC.sub(r"\2", _BOLD.sub(r"\2", paragraph)).split()
    if len(words) <= size:
        return " ".join(words)
    return " ".join(words[:size]) + "…"


def render_markdown(body: str) -> str:
    """Render markdown to HTML with anchored headings.

    Every heading gets a slugified ``id``; duplicates are suffixed
    ``-2``, ``-3``, … and slugless headings fall back to ``section`` so
    an empty id is never emitted. H2/H3 additionally carry a trailing
    ``<a class="anchor">`` link targeting their own id.

    Footnotes (``[^1]`` refs / ``[^1]: text`` defs) render via the
    markdown-it footnote plugin; the notes section gains an injected
    ``<h2>Notes`` header so extract_toc lists it.
    """
    html = _MARKDOWN.render(body)
    if _FOOTNOTE_SECTION in html:
        html = _FOOTNOTES_HEADER.join(html.split(_FOOTNOTE_SECTION, 1))
        html = _FOOTNOTE_REF_BRACKETS.sub(r"\1\2\3", html)
    used: set[str] = set()
    counts: dict[str, int] = {}

    def unique_id(base: str) -> str:
        if not base:
            base = "section"
        candidate = base
        while candidate in used:
            counts[base] = counts.get(base, 1) + 1
            candidate = f"{base}-{counts[base]}"
        used.add(candidate)
        return candidate

    def add_id(match: re.Match[str]) -> str:
        level, inner = match.group(1), match.group(2)
        plain = _INLINE_TAGS.sub("", inner)
        hid = unique_id(slugify(plain))
        if level in ("2", "3"):
            anchor = f' <a class="anchor" href="#{hid}">#</a>'
        else:
            anchor = ""
        return f'<h{level} id="{hid}">{inner}{anchor}</h{level}>'

    return _HEADING.sub(add_id, html)


def extract_toc(html: str) -> list[dict]:
    """TOC tree from rendered article HTML: nested h2 → h3 entries.

    Returns a list of ``{"level", "id", "text", "children"}`` dicts;
    consecutive h3s nest under the preceding h2, orphan h3s surface at
    the top level. Empty when the document has no h2/h3.
    """
    def plain_text(inner: str) -> str:
        without_anchor = _ANCHOR_TAG.sub("", inner)
        return re.sub(
            r"\s+", " ", _INLINE_TAGS.sub("", without_anchor)
        ).strip()

    tree: list[dict] = []
    current_h2: dict | None = None
    for match in _HEADING_WITH_ID.finditer(html):
        level, hid, inner = (
            int(match.group(1)),
            match.group(2),
            match.group(3),
        )
        if level not in (2, 3):
            continue
        entry = {
            "level": level,
            "id": hid,
            "text": plain_text(inner),
            "children": [],
        }
        if level == 2:
            tree.append(entry)
            current_h2 = entry
        elif current_h2 is not None:
            current_h2["children"].append(entry)
        else:
            tree.append(entry)
    return tree


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
