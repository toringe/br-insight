"""Build-time search index (Task 15).

One compact JSON document per build: a record per essay with slug, root-
absolute URL, metadata, and full stripped body text, emitted to
``assets/js/search-index.json``. The client overlay
(``assets/js/modules/search.js``) fetches it lazily on first open and feeds
it to vendored MiniSearch; ``cli.py check`` enforces the ≤ 200 KB gz budget
whenever the file is present.
"""

from __future__ import annotations

import json
import re
from html import unescape as _unescape
from pathlib import Path

# Checks budget (mirrors checks.BUDGET_SEARCH_GZ; declared here so the
# writer's docstring contract stays self-contained).
INDEX_BUDGET_GZ = 200 * 1024

_ANCHOR_TAG = re.compile(r'<a class="anchor"[^>]*>.*?</a>', re.DOTALL)
_TAGS = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")


def strip_html(html: str) -> str:
    """Rendered article HTML → single-line plain text.

    Anchor decoration is dropped first (the ``#`` glyphs would pollute the
    index), then every tag becomes one space so adjacent block text never
    concatenates mid-word. Entities are decoded after tag stripping (a
    single pass: a double-encoded ``&amp;lt;`` stays literal text and can
    never reintroduce markup).
    """
    plain = _unescape(_TAGS.sub(" ", _ANCHOR_TAG.sub("", html)))
    return _WHITESPACE.sub(" ", plain).strip()


def build_record(article) -> dict:
    """One indexable record for an :class:`~br_insight.articles.Article`."""
    return {
        "slug": article.slug,
        "url": f"/library/{article.slug}/",
        "title": article.title,
        "author": article.author,
        "date": article.date.date().isoformat(),
        "category": article.category,
        "tags": list(article.tags),
        "summary": article.summary,
        "body": strip_html(article.html),
    }


def build_index(articles) -> list[dict]:
    """Records for every article, newest-first (input order preserved)."""
    return [build_record(article) for article in articles]


def write_index(out: Path, articles) -> Path:
    """Emit the compact index JSON under ``out/assets/js/``.

    ``ensure_ascii=False`` keeps Unicode as UTF-8 (smaller gzip), compact
    separators keep it single-line. Returns the written path.
    """
    records = build_index(articles)
    blob = json.dumps(records, ensure_ascii=False, separators=(",", ":"))
    target = out / "assets" / "js" / "search-index.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(blob, encoding="utf-8")
    return target
