"""Tests for Task 11 sitemap.xml and feed.xml (RSS 2.0)."""

import datetime
import re
import xml.etree.ElementTree as ET

import pytest

from br_insight.config import SiteConfig, apply_taxonomy, load_taxonomy
from br_insight.render import REPO_ROOT


def corpus():
    from br_insight.articles import load_all

    return apply_taxonomy(load_all(REPO_ROOT), load_taxonomy(REPO_ROOT))


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    from br_insight.render import build

    out = tmp_path_factory.mktemp("syndication_build")
    build(REPO_ROOT, out)
    return out


@pytest.fixture(scope="module")
def feed(built):
    return (built / "feed.xml").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sitemap(built):
    return (built / "sitemap.xml").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Sitemap
# ---------------------------------------------------------------------------


class TestSitemap:
    def test_namespaces_and_root(self, sitemap):
        assert '<?xml version="1.0" encoding="UTF-8"?>' in sitemap
        assert 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"' in sitemap
        root = ET.fromstring(sitemap)
        assert root.tag == "{http://www.sitemaps.org/schemas/sitemap/0.9}urlset"

    def test_well_formed_xml(self, sitemap):
        ET.fromstring(sitemap)

    def test_contains_every_article_url_exactly_once(self, sitemap):
        articles = corpus()
        locs = re.findall(r"<loc>(.*?)</loc>", sitemap)
        for a in articles:
            url = f"https://www.br-insight.com/library/{a.slug}/"
            assert locs.count(url) == 1, url

    def test_article_lastmod_matches_article_date(self, sitemap):
        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        root = ET.fromstring(sitemap)
        lastmods = {
            u.find("s:loc", ns).text: u.find("s:lastmod", ns).text
            for u in root.findall("s:url", ns)
        }
        for a in corpus():
            expected = a.date.strftime("%Y-%m-%d")
            actual = lastmods[f"https://www.br-insight.com/library/{a.slug}/"]
            assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", actual)
            assert actual == expected, a.slug

    def test_static_and_topic_routes_present(self, sitemap):
        from br_insight.render import topic_pages

        locs = set(re.findall(r"<loc>(.*?)</loc>", sitemap))
        today = datetime.date.today().strftime("%Y-%m-%d")
        base = SiteConfig.load(REPO_ROOT).base_url
        assert f"{base}/" in locs
        assert f"{base}/library/" in locs
        assert f"{base}/about.html" in locs
        for topic in topic_pages(corpus()):
            assert f"{base}{topic['href']}" in locs

    def test_404_error_sitemap_feed_excluded(self, sitemap):
        assert "404.html" not in sitemap
        assert "/error.html" not in sitemap
        assert "/sitemap.xml" not in sitemap
        assert "/feed.xml" not in sitemap


# ---------------------------------------------------------------------------
# RSS 2.0 feed
# ---------------------------------------------------------------------------

_RFC822 = re.compile(
    r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun), \d{2} "
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) "
    r"\d{4} \d{2}:\d{2}:\d{2} [+-]\d{4}$"
)

# Any ampersand outside a proper XML entity is a leak.
_RAW_AMP = re.compile(r"&(?!amp;|lt;|gt;|quot;|apos;|#\d+|#x[0-9a-fA-F]+;)")


class TestFeed:
    def test_channel_metadata(self, feed):
        from html import unescape

        site = SiteConfig.load(REPO_ROOT)
        assert '<rss version="2.0"' in feed
        ET.fromstring(feed)  # well-formed despite raw & in titles
        assert f"<title>{site.name}</title>" in unescape(feed)
        assert f"<link>{site.base_url}/</link>" in feed
        assert site.tagline in unescape(feed)
        assert "<lastBuildDate>" in feed

    def test_latest_twenty_articles_newest_first(self, feed):
        items = re.findall(r"<item>(.*?)</item>", feed, re.DOTALL)
        assert len(items) == 20
        newest = {a.slug for a in corpus()[:20]}
        linked = {
            m for item in items
            for m in re.findall(
                r"<link>https://www\.br-insight\.com/library/([^/]+)/</link>",
                item,
            )
        }
        assert linked == newest

    def test_pub_dates_are_rfc822(self, feed):
        pub_dates = re.findall(r"<pubDate>(.*?)</pubDate>", feed)
        assert len(pub_dates) == 20
        for stamp in pub_dates:
            assert _RFC822.match(stamp), stamp

    def test_links_absolute_with_base_url(self, feed):
        base = SiteConfig.load(REPO_ROOT).base_url
        links = re.findall(r"<item>.*?<link>(.*?)</link>", feed, re.DOTALL)
        assert links
        for link in links:
            assert link.startswith(f"{base}/library/")

    def test_description_carries_summary_and_author(self, feed):
        from html import unescape

        third_newest = corpus()[2]
        item = next(
            i for i in re.findall(r"<item>(.*?)</item>", feed, re.DOTALL)
            if f"/library/{third_newest.slug}/</link>" in i
        )
        plain = unescape(item)
        assert third_newest.summary[:40] in plain
        assert third_newest.author in plain

    def test_xml_escapes_ampersands_in_titles(self, feed):
        titles = [a.title for a in corpus() if "&" in a.title]
        assert titles  # corpus actually contains &-titles
        body = "\n".join(
            l for l in feed.splitlines()
            if "<title>" in l or "<description>" in l
        )
        # every ampersand must be part of a valid XML entity
        leaked = _RAW_AMP.findall(body)
        assert not leaked
        assert "&amp;" in body

    def test_every_item_has_title_link_description(self, feed):
        items = re.findall(r"<item>(.*?)</item>", feed, re.DOTALL)
        for item in items:
            assert "<title>" in item and "<link>" in item
            assert "<pubDate>" in item and "<description>" in item
