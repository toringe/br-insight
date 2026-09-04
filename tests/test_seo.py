"""SEO/AEO head-tag contract: metadata, structured data, and syndication
discoverability across every page type (single build, module-scoped)."""

import json
import re

import pytest

from br_insight.articles import meta_description
from br_insight.config import SiteConfig, apply_taxonomy, load_taxonomy
from br_insight.render import REPO_ROOT


def corpus():
    return apply_taxonomy(load_all_articles(), load_taxonomy(REPO_ROOT))


def load_all_articles():
    from br_insight.articles import load_all

    return load_all(REPO_ROOT)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    from br_insight.render import build

    out = tmp_path_factory.mktemp("seo_build")
    build(REPO_ROOT, out)
    return out


def head(page: str, built) -> str:
    html = (built / page).read_text(encoding="utf-8")
    return html.split("</head>", 1)[0]


def json_ld(head_html: str) -> list[dict]:
    blobs = re.findall(
        r'<script type="application/ld\+json">(.*?)</script>',
        head_html,
        re.DOTALL,
    )
    return [json.loads(b) for b in blobs]


class TestSiteWideHead:
    @pytest.mark.parametrize(
        "page", ["index.html", "about.html", "library/index.html"]
    )
    def test_rss_autodiscovery_and_twitter_site(self, built, page):
        h = head(page, built)
        site = SiteConfig.load(REPO_ROOT)
        assert re.search(
            r'<link rel="alternate" type="application/rss\+xml"'
            r' title="[^"]+" href="https://www\.br-insight\.com/feed\.xml">',
            h,
        )
        assert f'<meta name="twitter:site" content="@{site.social.twitter}">' in h
        assert 'property="og:image:alt"' in h

    def test_secondary_pages_never_carry_article_jsonld(self, built):
        for page in ("index.html", "about.html", "library/index.html"):
            types = [d.get("@type") for d in json_ld(head(page, built))]
            assert "Article" not in types, page


class TestHomeHead:
    def test_title_is_brand_first_and_not_the_full_tagline(self, built):
        h = head("index.html", built)
        title = re.search(r"<title>(.*?)</title>", h).group(1)
        assert title == "In-depth Blade Runner analysis — Blade Runner Insight"

    def test_website_schema_with_search_action(self, built):
        site = SiteConfig.load(REPO_ROOT)
        website = next(
            d for d in json_ld(head("index.html", built)) if d["@type"] == "WebSite"
        )
        assert website["name"] == site.name
        action = website["potentialAction"]
        assert action["@type"] == "SearchAction"
        assert (
            action["target"]["urlTemplate"]
            == f"{site.base_url}/library/?q={{search_term_string}}"
        )
        assert action["query-input"] == "required name=search_term_string"


@pytest.fixture(scope="module")
def measure_head(built):
    return head("library/measure-of-a-man/index.html", built)


class TestArticleHead:
    def test_meta_description_is_serp_sized(self, measure_head):
        desc = re.search(
            r'<meta name="description" content="(.*?)">', measure_head
        ).group(1)
        assert len(desc) <= 160
        assert desc == meta_description(desc)

    def test_published_time_and_og_image_alt(self, measure_head):
        assert re.search(
            r'<meta property="article:published_time" content="\d{4}-\d{2}-\d{2}">',
            measure_head,
        )
        assert (
            'property="og:image:alt" content="Cover art for'
            in measure_head
        )

    def test_article_schema_is_rich_result_complete(self, measure_head):
        site = SiteConfig.load(REPO_ROOT)
        article = next(
            d for d in json_ld(measure_head) if d["@type"] == "Article"
        )
        assert len(article["description"]) <= 160
        assert article["publisher"]["@type"] == "Organization"
        assert article["publisher"]["logo"]["url"].endswith(".png")
        assert article["datePublished"] == article["dateModified"]
        assert isinstance(article["wordCount"], int) and article["wordCount"] > 0
        assert article["inLanguage"] == "en"
        assert article["mainEntityOfPage"].startswith(site.base_url)

    def test_breadcrumb_schema(self, measure_head):
        crumbs = next(
            d for d in json_ld(measure_head) if d["@type"] == "BreadcrumbList"
        )
        positions = [i["position"] for i in crumbs["itemListElement"]]
        assert positions == [1, 2, 3]
        names = [i["name"] for i in crumbs["itemListElement"]]
        assert names[:2] == ["Home", "Library"]

    def test_every_article_gets_serp_description_and_schemas(self, built):
        from html import unescape

        for a in corpus():
            h = head(f"library/{a.slug}/index.html", built)
            desc = unescape(
                re.search(r'<meta name="description" content="(.*?)">', h).group(1)
            )
            assert len(desc) <= 160, a.slug
            types = {d["@type"] for d in json_ld(h)}
            assert {"Article", "BreadcrumbList"} <= types, a.slug


class Test404Head:
    def test_noindex_guard(self, built):
        h = head("404.html", built)
        assert '<meta name="robots" content="noindex">' in h


class TestTopicHead:
    def test_tag_titles_are_prettified(self, built):
        h = head("topics/tag/deckard/index.html", built)
        assert "<title>Deckard — Blade Runner Insight</title>" in h

    def test_hyphenated_tag_titles_prettified(self, built):
        h = head("topics/tag/philip-k-dick/index.html", built)
        assert "<title>Philip K Dick — Blade Runner Insight</title>" in h
