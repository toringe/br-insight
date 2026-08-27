"""Tests for Task 11 about + 404/error pages."""

import re
from pathlib import Path

import pytest

from br_insight.render import REPO_ROOT

# The legacy about.html carries SEVEN revision screenshots (rev1–rev7);
# the brief's "six" is stale — all seven are preserved faithfully.
SCREENSHOTS = (
    ("/assets/img/site_rev1.jpg", "Screenshot of 1st revision"),
    ("/assets/img/site_rev2.jpg", "Screenshot of 2nd revision"),
    ("/assets/img/site_rev3.jpg", "Screenshot of 3rd revision"),
    ("/assets/img/site_rev4.jpg", "Screenshot of 4th revision"),
    ("/assets/img/site_rev5.jpg", "Screenshot of 5th revision"),
    ("/assets/img/site_rev6.png", "Screenshot of 6th revision"),
    ("/assets/img/site_rev7.png", "Screenshot of 7th revision"),
)

HISTORY_FACTS = (
    "Blade Runner Insight started as a project in November 1995",
    "went online in July 1996",
    "The Unofficial In-Depth Analysis of Blade Runner",
    "In 1999 the name of the site was changed",
    "br-insight.com</strong>",
    "In May 2002, the Blade Runner Insight Forum was created",
    "Radomir Balint",
    'href="https://en.wikipedia.org/wiki/Yahoo!_GeoCities">GeoCities</a>',
    'href="https://en.wikipedia.org/wiki/PhpBB">phpBB</a>',
    "Amazon Web Services",
)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    from br_insight.render import build

    out = tmp_path_factory.mktemp("page_build")
    build(REPO_ROOT, out)
    return out


@pytest.fixture
def about(built):
    return (built / "about.html").read_text(encoding="utf-8")


class TestAboutPage:
    def test_built_with_new_design_chrome(self, about):
        assert "<!DOCTYPE html>" in about
        assert '<nav' in about and 'aria-label="Primary"' in about
        assert 'href="/assets/css/main.min.css"' in about

    def test_title_and_canonical(self, about):
        assert "<title>About — Blade Runner Insight</title>" in about
        assert "https://www.br-insight.com/about.html" in about

    def test_history_narrative_preserved(self, about):
        for fact in HISTORY_FACTS:
            assert fact in about, fact

    def test_all_revision_screenshots_carried_over(self, about):
        for src, alt in SCREENSHOTS:
            assert f'src="{src}"' in about, src
            assert f'alt="{alt}"' in about, alt

    def test_legacy_chrome_gone(self, about):
        legacy = ("jquery", "skel.min.js", "about.min.css", "id=\"menu\"")
        for marker in legacy:
            assert marker not in about, marker


class TestNavCurrentPage:
    """Exactly the page's own nav item carries aria-current="page"."""

    NAV_HREFS = ("/", "/library/", "/topics/", "/about.html")

    @staticmethod
    def _nav_current(html: str) -> list[str]:
        return re.findall(
            r'href="([^"]+)"[^>]*aria-current="page"', html
        )

    def test_home_marks_only_home(self, built):
        html = (built / "index.html").read_text(encoding="utf-8")
        assert self._nav_current(html) == ["/"]

    def test_library_marks_only_library(self, built):
        html = (built / "library" / "index.html").read_text(encoding="utf-8")
        assert self._nav_current(html) == ["/library/"]

    def _topic_hub(self, built):
        return (built / "topics" / "index.html").read_text(encoding="utf-8")

    def test_topics_hub_marks_only_topics(self, built):
        assert self._nav_current(self._topic_hub(built)) == ["/topics/"]

    def test_article_page_carries_no_nav_aria_current(self, built):
        html = (
            built / "library" / "deckards-identity-debate" / "index.html"
        ).read_text(encoding="utf-8")
        assert self._nav_current(html) == []


class Test404AndError:
    @pytest.fixture
    def html404(self, built):
        return (built / "404.html").read_text(encoding="utf-8")

    def test_error_is_byte_identical_copy_of_404(self, built):
        data_404 = (built / "404.html").read_bytes()
        data_error = (built / "error.html").read_bytes()
        assert data_404 == data_error

    def test_headline_and_helpful_copy(self, html404):
        assert ">404</h1>" in html404
        assert "This deck no longer exists." in html404

    def test_links_home_library_and_search_hint(self, html404):
        home = html404.index('href="/"')
        library = html404.index('href="/library/"')
        assert home < library
        assert "⌘K" in html404 or "Search" in html404

    def test_no_eyebrow_on_404(self, html404):
        assert 'class="eyebrow' not in html404

    def test_new_design_chrome(self, html404):
        assert 'aria-label="Primary"' in html404
        assert "/assets/css/main.min.css" in html404
