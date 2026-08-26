"""Tests for the Task 10 home page: template anatomy, home ctx helpers,
and build pipeline output at the root index.html."""

import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from br_insight.config import SiteConfig, apply_taxonomy, load_taxonomy
from br_insight.render import REPO_ROOT


def corpus():
    """Real taxonomy-enriched corpus, newest-first."""
    from br_insight.articles import load_all

    return apply_taxonomy(load_all(REPO_ROOT), load_taxonomy(REPO_ROOT))


def taxonomy_categories():
    """Category vocabulary from the curated taxonomy."""
    return sorted(set(load_taxonomy(REPO_ROOT).categories))


def _cloud_hrefs(cloud_html: str) -> list[str]:
    """Ordered ``href="…"`` attributes inside a rendered topic-cloud fragment."""
    import re

    return [
        f'href="{match}"'
        for match in re.findall(r'href="(/topics/[^"]+)"', cloud_html)
    ]


# ---------------------------------------------------------------------------
# Pure helpers: archive stats + topic cloud
# ---------------------------------------------------------------------------


class TestArchiveStats:
    def test_stats_computed_from_corpus(self):
        from br_insight.articles import load_all
        from br_insight.render import archive_stats

        raw = load_all(REPO_ROOT)
        assert archive_stats(corpus()) == {
            "essays": len(raw),
            "authors": len({a.author for a in raw}),
            "words": sum(a.words for a in raw),
        }


class TestTopicCloud:
    def test_categories_first_then_top_tags(self):
        from collections import Counter

        from br_insight.render import topic_cloud

        topics = topic_cloud(corpus())
        categories = [t for t in topics if "/topics/tag/" not in t["href"]]
        tags = [t for t in topics if "/topics/tag/" in t["href"]]

        assert [t["label"] for t in categories] == taxonomy_categories()
        assert len(categories) == 8  # every taxonomy category surfaces
        # top tags: ordered by article count desc, ties alphabetical, capped
        counts = Counter(tag for a in corpus() for tag in a.tags)
        expected_order = sorted(counts, key=lambda t: (-counts[t], t))
        assert [t["label"] for t in tags] == expected_order[:10]
        # and every tag link comes after every category link
        assert len(topics) == len(categories) + len(tags)

    def test_hrefs_use_canonical_slugify(self):
        from br_insight.textutils import slugify

        from br_insight.render import topic_cloud

        by_label = {t["label"]: t["href"] for t in topic_cloud(corpus())}
        assert by_label["Film Analysis"] == "/topics/film-analysis/"
        assert by_label["Themes & Humanity"] == "/topics/themes-humanity/"
        assert "director's-cut" not in by_label  # count 1: outside the top-10 cap
        for label, href in by_label.items():
            if "/topics/tag/" in href:
                assert href == f"/topics/tag/{slugify(label)}/"
            else:
                assert href == f"/topics/{slugify(label)}/"

    def test_apostrophe_slugifies_like_the_shared_rule(self):
        """Slug rule proven end-to-end on a synthetic tag with an apostrophe
        (the real corpus's ``director's-cut`` sits below the top-10 cap)."""
        from br_insight.render import topic_cloud

        synthetic = [_ns_article(tags=["director's-cut", "noir"], author=f"A{i}")
                     for i in range(10)]
        by_label = {t["label"]: t["href"] for t in topic_cloud(synthetic)}
        assert by_label["director's-cut"] == "/topics/tag/director-s-cut/"


class TestHomeContext:
    def test_featured_recent_and_month_resolved_from_injected_now(self):
        from br_insight.render import home_context

        articles = corpus()
        ctx = home_context(
            SiteConfig.load(REPO_ROOT), articles,
            datetime.datetime(2026, 8, 26, 14, 30),
        )
        # config slug wins over monthly rotation
        assert ctx["featured"].slug == "postmodernist-view"
        assert ctx["featured_month"] == "August"
        assert ctx["recent"] == articles[:4]
        assert ctx["stats"]["essays"] == len(articles)

    def test_rotation_fallback_is_deterministic_per_month(self):
        from dataclasses import replace

        from br_insight.config import FeaturedConfig, resolve_featured
        from br_insight.render import home_context

        site = replace(
            SiteConfig.load(REPO_ROOT),
            featured=FeaturedConfig(slug="", fallback="monthly-rotation"),
        )
        articles = corpus()
        july = home_context(site, articles, datetime.datetime(2026, 7, 1))
        july_again = home_context(site, articles, datetime.datetime(2026, 7, 28))
        august = home_context(site, articles, datetime.datetime(2026, 8, 1))
        assert july["featured"].slug == resolve_featured(
            site, articles, "202607"
        ).slug
        assert july_again["featured"].slug == july["featured"].slug
        assert august["featured"].slug != july["featured"].slug


# ---------------------------------------------------------------------------
# Template-level: home page anatomy
# ---------------------------------------------------------------------------


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
        tags=["noir", "empathy"],
        html="<p>prose</p>",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


RECENT_ARTICLES = [
    _ns_article(
        slug=f"recent-{i}",
        title=f"Recent {i}",
        date=datetime.datetime(2024, 5, i + 1),
    )
    for i in range(4)
]

HOME_TOPICS = [
    {"label": "Characters", "href": "/topics/characters/"},
    {"label": "Film Analysis", "href": "/topics/film-analysis/"},
    {"label": "Themes & Humanity", "href": "/topics/themes-humanity/"},
    {"label": "noir", "href": "/topics/tag/noir/"},
    {"label": "eyes", "href": "/topics/tag/eyes/"},
]


def _ctx(**overrides):
    ctx = dict(
        featured=_ns_article(slug="postmodernist-view", title="Postmodernist View"),
        featured_month="August",
        stats={"essays": 29, "authors": 12, "words": 79321},
        topics=HOME_TOPICS,
        recent=RECENT_ARTICLES,
        current_path="/",
    )
    ctx.update(overrides)
    return ctx


@pytest.fixture
def html():
    from br_insight.render import render_template

    return render_template("home.html", site=SiteConfig.load(REPO_ROOT), **_ctx())


class TestHomeAnatomy:
    def test_title_and_chrome_defaults(self, html):
        assert "<!DOCTYPE html>" in html
        assert 'href="/assets/css/main.min.css"' in html  # root asset depth
        assert 'href="/library/"' in html

    @pytest.mark.parametrize(
        "snippet",
        [
            ">Browse the Library</a>",
            'data-random-link href="/library/">Random essay</a>',
            "Thirty years of Blade Runner analysis — online since 1996.",
        ],
    )
    def test_hero_ctas_and_anniversary_line(self, html, snippet):
        assert snippet in html

    def test_hero_shows_site_name_and_tagline(self):
        from html import unescape

        from br_insight.render import render_template

        plain = unescape(render_template(
            "home.html", site=SiteConfig.load(REPO_ROOT), **_ctx()
        ))
        assert '<h1 class="hero__title">Blade Runner Insight</h1>' in plain
        assert "In-depth analytical perspectives on Ridley Scott's Blade Runner</p>" in plain

    def test_featured_section_contract(self, html):
        cover_at = html.index('src="/library/postmodernist-view/cover-crop.jpg"')
        title_at = html.index('href="/library/postmodernist-view/">Postmodernist View</a>')
        author_at = html.index("K. Deckard")
        reading_at = html.index("min read")
        summary_at = html.index("A machine to measure empathy.")
        read_at = html.index(">Read essay</a>")
        assert -1 < cover_at < title_at < author_at < reading_at < summary_at < read_at
        assert "Featured analysis · August" in html

    def test_featured_skips_when_absent(self):
        from br_insight.render import render_template

        plain = render_template(
            "home.html", site=SiteConfig.load(REPO_ROOT), **_ctx(featured=None)
        )
        assert "Featured analysis" not in plain
        assert "Read essay" not in plain

    def test_stats_band_text(self, html):
        assert ">29 essays · 12 authors · 79,321 words · est. 1996</" in html

    def test_topic_cloud_links_categories_then_tags(self, html):
        cloud = html[html.index('aria-label="Topics"'):]
        joined = "\n".join(_cloud_hrefs(cloud))
        assert 'href="/topics/characters/"' in joined
        assert 'href="/topics/themes-humanity/"' in joined
        assert 'href="/topics/tag/noir/"' in joined
        last_category = joined.index("/topics/themes-humanity/")
        first_tag = joined.index("/topics/tag/")
        assert last_category < first_tag
        assert len(_cloud_hrefs(cloud)) == len(HOME_TOPICS)

    def test_topic_cloud_escapes_ampersands(self, html):
        assert "Themes &amp; Humanity" in html

    def test_recent_row_four_cards_newest_first(self, html):
        recent = html[html.index('aria-labelledby="recent-title"'):]
        positions = [recent.index(f'/library/recent-{i}/">') for i in range(4)]
        assert positions == sorted(positions)
        assert html.count('class="card"') == 4
        assert 'src="/library/recent-0/cover-crop.jpg"' in recent

    def test_zero_js_no_script_tags(self, html):
        # graceful degradation only: Random essay stays an inert <a>
        assert "<script" not in html

    def test_section_order_hero_stats_topics_recent(self, html):
        hero = html.index('class="hero"')
        featured = html.index('class="featured"')
        stats = html.index('class="home-stats"')
        topics = html.index('aria-label="Topics"')
        recent = html.index('aria-labelledby="recent-title"')
        assert hero < featured < stats < topics < recent

    def test_home_nav_marks_current_page(self, html):
        nav = html[html.index("<nav"):html.index("</nav>")]
        home_line = next(line for line in nav.split("\n") if '>Home</a>' in line)
        assert 'href="/" aria-current="page"' in home_line


class TestEyebrowSignature:
    """Task 10b: exactly five "Esper scan" eyebrows on the home page."""

    def test_all_five_eyebrows_with_labels(self, html):
        assert html.count('class="eyebrow') == 5
        for label in (
            ">The Archive<",
            ">Featured analysis · August<",
            ">Thirty years online<",
            ">Browse by topic<",
            ">Recent additions<",
        ):
            assert label in html

    def test_hero_kicker_precedes_site_name(self, html):
        assert html.index("hero__kicker") < html.index('class="hero__title"')

    def test_stats_label_precedes_essay_counts(self, html):
        assert (
            html.index("stats-band__label")
            < html.index('class="home-stats"')
        )

    def test_no_legacy_headings_remain(self, html):
        assert "home-heading" not in html


# ---------------------------------------------------------------------------
# Build pipeline writes the root index.html
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def built_home(tmp_path_factory):
    from br_insight.render import build

    out = tmp_path_factory.mktemp("home_build")
    build(REPO_ROOT, out)
    return out


class TestBuildHomePage:
    def test_root_index_written(self, built_home):
        assert (built_home / "index.html").is_file()

    def test_written_paths_include_root_index(self, tmp_path):
        from br_insight.articles import load_all
        from br_insight.render import build

        out = tmp_path / "out"
        written = build(REPO_ROOT, out)
        expected = {
            Path("library") / slug / "index.html"
            for slug in {a.slug for a in load_all(REPO_ROOT)}
        } | {Path("library") / "index.html", Path("index.html")}
        actual = {p.relative_to(out) for p in written}
        assert actual == expected

    def test_built_featured_matches_config_slug(self, built_home):
        title = next(
            a.title for a in corpus() if a.slug == "postmodernist-view"
        )
        text = (built_home / "index.html").read_text(encoding="utf-8")
        assert f'href="/library/postmodernist-view/">{title}</a>' in text

    def test_built_stats_band_matches_corpus(self, built_home):
        from br_insight.articles import load_all

        raw = load_all(REPO_ROOT)
        n_authors = len({a.author for a in raw})
        words = sum(a.words for a in raw)
        text = (built_home / "index.html").read_text(encoding="utf-8")
        expected = (
            f">{len(raw)} essays · {n_authors} authors · "
            f"{words:,} words · est. 1996</"
        )
        assert expected in text

    def test_built_topic_cloud_has_eight_category_links(self, built_home):
        from br_insight.textutils import slugify

        text = (built_home / "index.html").read_text(encoding="utf-8")
        cloud = text[text.index('aria-label="Topics"'):text.index("Recent additions")]
        hrefs = {h.removeprefix('href="').removesuffix('"') for h in _cloud_hrefs(cloud)}
        expected_cats = {
            f"/topics/{slugify(c)}/" for c in taxonomy_categories()
        }
        assert len(hrefs & expected_cats) == 8
        assert "/topics/film-analysis/" in hrefs
        assert "/topics/themes-humanity/" in hrefs
        assert "/topics/tag/noir/" in hrefs

    def test_built_recent_row_is_four_newest(self, built_home):
        articles = corpus()
        text = (built_home / "index.html").read_text(encoding="utf-8")
        recent = text[text.index('aria-labelledby="recent-title"'):]
        positions = [recent.index(f'/library/{a.slug}/">') for a in articles[:4]]
        assert positions == sorted(positions)  # newest-first card order
        assert recent.count('class="card"') == 4
        # nothing else from the corpus leaks past the four-card grid
        fifth_newest_onwards = {a.slug for a in articles[4:]}
        row_slugs = {
            slug for slug in fifth_newest_onwards
            if f"/library/{slug}/" in recent
        }
        assert not row_slugs

    def test_built_month_name_present(self, built_home):
        text = (built_home / "index.html").read_text(encoding="utf-8")
        current_month = datetime.date.today().strftime("%B")
        assert current_month in text

    def test_built_home_carries_five_eyebrows_and_welcome_attr(self, built_home):
        text = (built_home / "index.html").read_text(encoding="utf-8")
        assert text.count('class="eyebrow') == 5
        # real site config has the full fx chain on: root attr emitted
        assert "<html lang=\"en\" data-fx-welcome>" in text
