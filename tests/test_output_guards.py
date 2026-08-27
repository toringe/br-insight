"""Output-level guards: shipped artifacts must never leak raw markdown.

Regression for the stale feed-description wave: a `git checkout` reverted
regenerated <description> blocks, shipping raw ATX headings in the feed.
These tests scan the built tree at repo root (not a fresh tmp build) so
stale committed outputs fail loudly.
"""

import json
import re

from br_insight.render import REPO_ROOT

# An ATX heading marker anywhere in rendered prose is a markdown leak:
# optional leading whitespace, 1-6 hashes, then whitespace.
_ATX = re.compile(r"^\s{0,3}#{1,6}\s", re.MULTILINE)


class TestNoRawMarkdownInOutputs:
    def test_feed_descriptions_have_no_atx_headings(self):
        feed = (REPO_ROOT / "feed.xml").read_text(encoding="utf-8")
        descs = re.findall(r"<description>(.*?)</description>", feed, re.DOTALL)
        assert descs, "feed.xml must carry item descriptions"
        leaked = [d for d in descs if _ATX.search(d)]
        assert not leaked, (
            f"{len(leaked)} feed description(s) contain raw ATX headings; "
            "run `uv run br-insight build` and stage feed.xml"
        )

    def test_search_index_summary_body_have_no_atx_headings(self):
        idx = json.loads(
            (REPO_ROOT / "assets/js/search-index.json").read_text(encoding="utf-8")
        )
        assert idx, "search index must not be empty"
        leaked = [
            e["url"]
            for e in idx
            if _ATX.search(e.get("summary") or "")
            or _ATX.search(e.get("body") or "")
        ]
        assert not leaked, (
            f"search-index.json entries with raw ATX headings: {leaked}"
        )

    def test_built_pages_meta_description_have_no_atx_headings(self):
        pages = [
            REPO_ROOT / name
            for name in ("index.html", "about.html", "404.html")
        ] + list((REPO_ROOT / "library").glob("*/index.html")) + list(
            (REPO_ROOT / "topics").rglob("*.html")
        )
        assert len(pages) >= 40
        meta_re = re.compile(
            r'<meta\s+name="description"\s+content="([^"]*)"', re.DOTALL
        )
        leaked = []
        scanned = 0
        for page in pages:
            html = page.read_text(encoding="utf-8")
            m = meta_re.search(html)
            if m is None:
                continue
            scanned += 1
            if _ATX.search(m.group(1)):
                leaked.append(page.relative_to(REPO_ROOT).as_posix())
        assert scanned, "no built pages expose a meta description"
        assert not leaked, (
            f"meta description(s) with raw ATX headings: {leaked}"
        )
