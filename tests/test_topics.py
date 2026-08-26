"""Tests for Task 11 topic pages: pure ctx helpers + built /topics/ routes."""

import datetime
from types import SimpleNamespace

import pytest

from br_insight.config import SiteConfig, apply_taxonomy, load_taxonomy
from br_insight.render import REPO_ROOT


def corpus():
    """Real taxonomy-enriched corpus, newest-first."""
    from br_insight.articles import load_all

    return apply_taxonomy(load_all(REPO_ROOT), load_taxonomy(REPO_ROOT))


# ---------------------------------------------------------------------------
# Pure helper: topic_pages()
# ---------------------------------------------------------------------------


class TestTopicPages:
    def test_eight_categories_plus_every_used_tag(self):
        from br_insight.render import topic_pages

        articles = corpus()
        topics = topic_pages(articles)
        categories = [t for t in topics if t["kind"] == "category"]
        tags = [t for t in topics if t["kind"] == "tag"]

        assert len(categories) == 8
        used_tags = {tag for a in articles for tag in a.tags}
        assert {t["name"] for t in tags} == used_tags
        assert len(topics) == len(categories) + len(tags)

    def test_hrefs_match_home_topic_cloud_exactly(self):
        from br_insight.render import topic_cloud, topic_pages

        pages_hrefs = {t["href"] for t in topic_pages(corpus())}
        cloud_hrefs = {t["href"] for t in topic_cloud(corpus())}
        # every cloud link (8 cats + top-10 tags) must have a real page,
        # and both use identical href forms (/topics/<slug>/ vs /topics/tag/<slug>/)
        assert cloud_hrefs <= pages_hrefs
        # both use identical href forms (/topics/<slug>/ vs /topics/tag/<slug>/)
        assert all(h.startswith("/topics/") for h in pages_hrefs)
        assert "/topics/film-analysis/" in pages_hrefs
        assert "/topics/tag/noir/" in pages_hrefs

    def test_slugs_use_shared_slugify_rule(self):
        from br_insight.textutils import slugify

        from br_insight.render import topic_pages

        by_href = {t["href"]: t for t in topic_pages(corpus())}
        cat = next(
            t for t in by_href.values() if t["name"] == "Themes & Humanity"
        )
        assert cat["slug"] == slugify(cat["name"])
        assert cat["href"] == f"/topics/{cat['slug']}/"
        # ledger ruling: director-s-cut style slugs accepted as-is
        apostrophe = next(t for t in by_href.values() if "'" in t["name"])
        assert apostrophe["slug"] == slugify(apostrophe["name"])
        assert apostrophe["href"].startswith("/topics/tag/")

    def test_no_empty_topic_is_possible(self):
        """Topics derive from the enriched corpus itself — never the raw
        vocabularies — so an unused category/tag can never yield a page."""
        from collections import Counter
        from dataclasses import replace

        from br_insight.render import topic_pages

        # synthetic: vocab mentions a tag no article carries
        ghosts = [
            _ns_article(slug="synthetic-a", category="Real", tags=["used"]),
            _ns_article(slug="synthetic-b", category="Real", tags=["unused-tag"]),
        ]
        topics = topic_pages(ghosts)
        assert [(t["name"], t["count"]) for t in topics] == [
            ("Real", 2),
            ("unused-tag", 1),
            ("used", 1),
        ]
        # both ghosts surface exactly once per membership (category + tag)
        assert Counter(a.slug for t in topics for a in t["articles"]) == {
            "synthetic-a": 2,
            "synthetic-b": 2,
        }

    def test_intro_is_real_copy(self):
        from br_insight.render import topic_pages

        for topic in topic_pages(corpus()):
            text = topic["intro"]
            assert isinstance(text, str) and len(text) >= 40, topic["name"]
            assert "lorem" not in text.lower() and "TODO" not in text

    def test_curated_intros_load_from_data_file(self):
        """Regression: _data/topics.yaml copy must actually reach pages
        (loader returns kind-keyed map; no silent generic fallback)."""
        from br_insight.render import load_topic_intros, topic_pages

        intros = load_topic_intros()
        by_name = {t["name"]: t for t in topic_pages(corpus())}
        assert (
            by_name["Film Analysis"]["intro"]
            == intros["category"]["Film Analysis"]
        )
        assert "Scene-by-scene" in by_name["Film Analysis"]["intro"]
        assert by_name["noir"]["intro"] == intros["tag"]["noir"]

    def test_articles_newest_first_within_topic(self):
        from br_insight.render import topic_pages

        articles = corpus()
        film = next(
            t
            for t in topic_pages(articles)
            if t["name"] == "Film Analysis"
        )
        dates = [a.date for a in film["articles"]]
        assert dates == sorted(dates, reverse=True)


def _ns_article(**overrides):
    base = dict(
        title="Voight-Kampff Test",
        author="K. Deckard",
        summary="A machine to measure empathy.",
        slug="voight-kampff-test",
        date=datetime.datetime(2024, 5, 1),
        minutes=6,
        words=1300,
        cover="cover.jpg",
        cover_artist=None,
        copyright=None,
        source=None,
        category="Film Analysis",
        tags=["noir"],
        html="<p>prose</p>",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


# ---------------------------------------------------------------------------
# Template-level anatomy
# ---------------------------------------------------------------------------


class TestTopicTemplateAnatomy:
    @pytest.fixture(scope="class")
    def real_corpus(self):
        return corpus()

    def _render(self, name="Film Analysis", kind="category"):
        from br_insight.render import render_template, topic_pages

        topics = {t["name"]: t for t in topic_pages(corpus())}
        topic = dict(topics[name], kind=kind)
        return render_template(
            "topic.html",
            site=SiteConfig.load(REPO_ROOT),
            topic=topic,
            asset_prefix="../../" if kind == "category" else "../../../",
        )

    def test_header_eyebrow_name_intro_count(self):
        html = self._render("Film Analysis", kind="category")
        assert '<p class="eyebrow">Category</p>' in html
        assert "<h1>Film Analysis</h1>" in html
        assert 'class="page-head__lead"' in html
        assert ">8 essays</" in html

    def test_tag_eyebrow_and_count(self):
        from br_insight.render import topic_pages

        html = self._render("noir", kind="tag")
        assert '<p class="eyebrow">Tag</p>' in html
        count = next(t["count"] for t in topic_pages(corpus()) if t["name"] == "noir")
        assert f">{count} essays</" in html
        assert '<p class="page-head__meta">' in html

    def test_cards_sorted_newest_first_with_card_partial(self):
        html = self._render("Film Analysis", kind="category")
        grid = html[html.index('class="grid grid--cards"'):]
        positions = []
        for a in corpus():
            needle = f'href="/library/{a.slug}/"'
            if needle in grid:
                positions.append(grid.index(needle))
        assert len(positions) == 8
        assert positions == sorted(positions)

    def test_relative_asset_depth_via_context(self):
        html = self._render("Film Analysis", kind="category")
        assert 'href="../../assets/css/main.min.css"' in html
        assert 'src="../../library/' in html

    def test_html_escapes_names(self):
        html = self._render("Themes & Humanity", kind="category")
        assert "Themes &amp; Humanity" in html


# ---------------------------------------------------------------------------
# Build pipeline output
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def built_topics(tmp_path_factory):
    from br_insight.render import build

    out = tmp_path_factory.mktemp("topic_build")
    build(REPO_ROOT, out)
    return out


class TestBuiltTopicRoutes:
    def test_every_category_and_tag_page_written(self, built_topics):
        from pathlib import Path

        from br_insight.render import topic_pages

        topics = topic_pages(corpus())
        expected = set()
        for t in topics:
            parts = ["topics"]
            if t["kind"] == "tag":
                parts.append("tag")
            parts += [t["slug"], "index.html"]
            expected.add(Path(*parts))
        actual = {
            p.relative_to(built_topics)
            for p in (built_topics / "topics").rglob("*.html")
        }
        assert actual == expected

    def test_apostrophe_tag_gets_director_s_cut_route(self, built_topics):
        from br_insight.render import topic_pages

        page = built_topics / "topics" / "tag" / "director-s-cut" / "index.html"
        assert page.is_file()
        text = page.read_text(encoding="utf-8")
        # slug route is canonical; the raw apostrophe form is escaped as text
        assert "/topics/tag/director-s-cut/" in text
        expected = next(
            t for t in topic_pages(corpus()) if t["slug"] == "director-s-cut"
        )
        assert expected["kind"] == "tag"

    def test_built_topic_pages_link_home_cloud_targets(self, built_topics):
        text = (built_topics / "index.html").read_text(encoding="utf-8")
        cloud = text[text.index('aria-label="Topics"'):]
        assert 'href="/topics/tag/noir/"' in cloud
        hrefs = [
            h[len('href="'):-1]
            for h in __import__("re").findall(r'href="/topics/[^"]+"', cloud)
        ]
        for href in hrefs:
            path = built_topics / href.lstrip("/") / "index.html"
            assert path.is_file(), href
