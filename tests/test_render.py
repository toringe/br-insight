"""Tests for br_insight.render: Jinja2 environment, base template chrome,
article page anatomy, and the Task 8 build pipeline."""

import datetime
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from br_insight.config import SiteConfig
from br_insight.render import REPO_ROOT, get_env, render_template


@pytest.fixture
def site() -> SiteConfig:
    return SiteConfig.load(REPO_ROOT)


@pytest.fixture
def article():
    return SimpleNamespace(
        title="Voight-Kampff Test",
        author="K. Deckard",
        summary="A machine to measure empathy.",
        slug="voight-kampff-test",
        date=datetime.datetime(2024, 5, 1),
        minutes=6,
        cover="cover.jpg",
    )


class TestEnvironment:
    def test_templates_compile(self):
        env = get_env()
        for name in ("base.html", "partials/header.html", "partials/footer.html"):
            assert env.get_template(name) is not None

    def test_render_template_returns_html_string(self, site):
        html = render_template("base.html", site=site)
        assert isinstance(html, str)
        assert "<!DOCTYPE html>" in html

    def test_render_template_injects_current_year(self, site):
        year = str(datetime.date.today().year)
        assert f"© 1996–{year}" in render_template("base.html", site=site)


class TestBaseChrome:
    @pytest.fixture
    def html(self, site):
        return render_template("base.html", site=site)

    def test_semantic_landmarks(self, html):
        assert '<main id="main"' in html
        assert "<nav" in html and 'aria-label="Primary"' in html
        assert "<header" in html and "<footer" in html

    def test_skip_link_and_progress_bar(self, html):
        assert 'class="skip-link"' in html
        assert 'href="#main"' in html
        assert 'class="progress"' in html

    def test_header_buttons_are_hooked_but_inert(self, html):
        assert "data-search-open" in html
        assert "⌘K" in html
        assert "data-fx-toggle" in html
        assert 'aria-pressed="true"' in html
        assert "data-menu-toggle" in html
        assert 'aria-expanded="false"' in html

    def test_nav_renders_config_entries(self, html, site):
        for item in site.nav:
            assert f'>{item.label}</a>' in html
            assert f'href="{item.href}"' in html

    def test_footer_lines(self, html):
        assert "Cover art © their respective artists" in html
        established = SiteConfig.load(REPO_ROOT).established
        current = datetime.date.today().year
        assert f">EST. {established} · {current - established} YEARS ONLINE</span>" in html
        assert "est" in html  # anniversary span carries the .est class hook

    def test_head_essentials(self, html):
        assert 'charset="utf-8"' in html
        assert 'name="viewport"' in html
        assert "/assets/css/main.min.css" in html
        assert "/assets/img/favicon.png" in html
        assert html.count("chakra-petch-latin-") == 2  # both weights preloaded

    def test_meta_defaults_from_site_config(self, site):
        from html import unescape

        plain = unescape(render_template("base.html", site=site))
        assert f'href="{site.base_url}/"' in plain  # canonical
        assert site.tagline in plain
        assert 'property="og:title"' in plain
        assert 'property="og:type" content="website"' in plain
        assert 'name="twitter:card" content="summary_large_image"' in plain

    def test_no_jsonld_without_article_context(self, html):
        assert "application/ld+json" not in html


class TestArticleContext:
    def test_jsonld_emitted_with_article(self, site, article):
        html = render_template("base.html", site=site, article=article)
        assert "application/ld+json" in html
        assert '"@type": "Article"' in html
        assert article.title in html
        assert "2024-05-01" in html

    def test_article_title_used_for_og(self, site, article):
        html = render_template("base.html", site=site, article=article)
        og_title = 'property="og:title" content="' + article.title
        assert og_title in html


class TestBlocksHaveDefaults:
    def test_bare_render_does_not_explode(self, site):
        html = render_template("base.html", site=site)
        assert "— Blade Runner Insight" in html  # composed default title

    def test_child_block_override_composes_suffix(self, site):
        child = get_env().from_string(
            "{% extends 'base.html' %}\n"
            "{% block title %}Library{% endblock %}"
            "{% block canonical_path %}library/{% endblock %}"
        )
        html = child.render(site=site)
        assert "<title>Library — Blade Runner Insight</title>" in html
        assert f'href="{site.base_url}/library/"' in html


# ---------------------------------------------------------------------------
# Task 8: injectable clock (stale cached-global fix)
# ---------------------------------------------------------------------------


class TestInjectableNow:
    def test_explicit_now_overrides_footer_year(self, site):
        html = render_template(
            "base.html", site=site, now=datetime.datetime(2030, 6, 1)
        )
        assert "© 1996–2030" in html

    def test_bare_env_render_shows_live_year_not_a_frozen_one(self, site):
        child = get_env().from_string(
            "{% extends 'base.html' %}{% block title %}x{% endblock %}"
        )
        year = datetime.date.today().year
        assert f"© 1996–{year}" in child.render(site=site)


# ---------------------------------------------------------------------------
# Task 8: CSS anchor contract (coarse pointers + minified sync)
# ---------------------------------------------------------------------------


class TestCssAnchorContract:
    def test_anchors_visible_on_coarse_pointers(self):
        css = (REPO_ROOT / "assets/css/main.css").read_text(encoding="utf-8")
        rule = "@media (hover: none)"
        assert rule in css
        after = css[css.index(rule):]
        assert ".prose .anchor" in after[:200]

    def test_min_css_is_regenerated_from_source(self):
        import rcssmin

        source = (REPO_ROOT / "assets/css/main.css").read_text(encoding="utf-8")
        minified = (REPO_ROOT / "assets/css/main.min.css").read_text(encoding="utf-8")
        assert minified == rcssmin.cssmin(source)


# ---------------------------------------------------------------------------
# Task 8: article page anatomy (template-level)
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
        cover_artist="Syd Mead",
        copyright=None,
        source=None,
        category="article",
        tags=["empathy"],
        html="<h2 id=\"one\">One <a class=\"anchor\" href=\"#one\">#</a></h2>"
             "<p>prose</p>",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


ANATOMY_CTX = dict(
    newer=None,
    older=None,
    related=[],
    toc=[],
    cover_width=1167,
    cover_height=700,
)


class TestArticleAnatomy:
    @pytest.fixture
    def html(self, site):
        return render_template(
            "article.html", site=site, article=_ns_article(), **ANATOMY_CTX
        )

    def test_hero_picture_with_high_fetchpriority_and_dimensions(self, html):
        assert "<picture>" in html
        assert 'fetchpriority="high"' in html
        assert re.search(r'<img[^>]+width="1167"[^>]+height="700"', html)
        assert "../../library/voight-kampff-test/cover.jpg" in html
        assert "../../library/voight-kampff-test/cover-crop.jpg" in html

    def test_credit_caption_known_artist(self, html):
        assert "Cover art © Syd Mead" in html

    def test_credit_invite_line_when_artist_unknown(self, site):
        html = render_template(
            "article.html",
            site=site,
            article=_ns_article(cover_artist=None),
            **ANATOMY_CTX,
        )
        assert "Cover art by an unknown artist — know the creator?" in html
        assert '../../about.html">Get in touch</a>' in html

    def test_byline_format(self, html):
        assert 'By <span class="byline__author">K. Deckard</span>' in html
        assert '<time datetime="2024-05-01">May 2024</time>' in html
        assert "6 min read" in html

    def test_relative_asset_depth(self, html):
        assert 'href="../../assets/css/main.min.css"' in html
        assert 'href="../../assets/fonts/chakra-petch-latin-400.woff2"' in html

    def test_jsonld_article_schema(self, html):
        assert '"@type": "Article"' in html
        assert '"datePublished": "2024-05-01"' in html
        assert '"mainEntityOfPage": "https://www.br-insight.com/library/voight-kampff-test/"' in html

    def test_toc_aside_when_entries_exist(self, site):
        toc = [
            {"level": 2, "id": "one", "text": "One", "children": []},
            {"level": 3, "id": "two", "text": "Two", "children": []},
            {"level": 3, "id": "three", "text": "Three", "children": []},
        ]
        html = render_template(
            "article.html", site=site, article=_ns_article(), toc=toc,
            **{k: v for k, v in ANATOMY_CTX.items() if k != "toc"},
        )
        assert '<aside class="toc"' in html
        assert 'href="#two"' in html

    def test_no_toc_aside_when_below_threshold(self, html):
        assert '<aside class="toc"' not in html

    def test_back_to_library_link(self, html):
        assert 'href="/library/">' in html

    def test_pager_slots_newer_then_older(self, site):
        newer = _ns_article(slug="newer-one", title="Newer One")
        older = _ns_article(slug="older-one", title="Older One")
        html = render_template(
            "article.html", site=site, article=_ns_article(),
            newer=newer, older=older, related=[], toc=[], cover_width=1, cover_height=1,
        )
        n = html.index(">Newer</span>")
        o = html.index(">Older</span>")
        assert n < o
        assert html.index('href="/library/newer-one/"', n, o)
        assert html.index('href="/library/older-one/"', o)

    def test_related_cards_with_title_byline_reading_time(self, site):
        rels = [_ns_article(slug=f"rel-{i}", title=f"Rel {i}") for i in range(3)]
        html = render_template(
            "article.html", site=site, article=_ns_article(),
            newer=None, older=None, related=rels, toc=[], cover_width=1, cover_height=1,
        )
        assert html.count('class="card"') == 3
        assert 'href="/library/rel-0/"' in html
        assert "K. Deckard" in html
        assert "min read" in html

    def test_focus_hide_on_chrome_but_not_progress_or_prose(self, html):
        assert html.count("data-focus-hide") >= 3  # header controls, footer, end-block extras
        progress = html[html.index('class="progress"'):html.index('class="progress"') + 60]
        assert "data-focus-hide" not in progress
        prose_at = html.index('class="prose"')
        assert "data-focus-hide" not in html[prose_at - 40:prose_at]


# ---------------------------------------------------------------------------
# Task 8: build pipeline over the real corpus
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    from br_insight.render import build

    out = tmp_path_factory.mktemp("build")
    written = build(REPO_ROOT, out)
    return out, written


def _tree_hash(out: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    for path in sorted((out / "library").glob("*/index.html")):
        digest.update(path.relative_to(out).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


class TestBuildPipeline:
    def test_writes_every_library_index_html(self, built):
        from br_insight.articles import load_all

        out, written = built
        slugs = {a.slug for a in load_all(REPO_ROOT)}
        expected = {Path("library") / slug / "index.html" for slug in slugs}
        actual = {p.relative_to(out) for p in written}
        assert actual == expected
        assert len(written) == 29

    def test_build_is_idempotent(self, tmp_path):
        from br_insight.render import build

        first, second = tmp_path / "a", tmp_path / "b"
        build(REPO_ROOT, first)
        build(REPO_ROOT, second)
        assert _tree_hash(first) == _tree_hash(second)

    def test_sample_page_uses_correct_asset_depth(self, built):
        out, _ = built
        sample = next((out / "library").glob("*/index.html"))
        text = sample.read_text(encoding="utf-8")
        assert 'href="../../assets/css/main.min.css"' in text

    def test_built_pages_carry_jsonld(self, built):
        from br_insight.articles import load_all

        out, _ = built
        article = load_all(REPO_ROOT)[0]
        text = (out / "library" / article.slug / "index.html").read_text(encoding="utf-8")
        assert '"@type": "Article"' in text
        iso = article.date.strftime("%Y-%m-%d")
        assert f'"datePublished": "{iso}"' in text
        assert f'"mainEntityOfPage": "https://www.br-insight.com/library/{article.slug}/"' in text

    def test_toc_threshold_on_real_corpus(self, built):
        from br_insight.articles import load_all, extract_toc

        out, _ = built
        with_toc = [a for a in load_all(REPO_ROOT) if extract_toc(a.html)]
        without = [a for a in load_all(REPO_ROOT) if not extract_toc(a.html)]
        assert with_toc, "expected some articles to clear the TOC threshold"
        assert '<aside class="toc"' in (
            out / "library" / with_toc[0].slug / "index.html"
        ).read_text(encoding="utf-8")
        assert '<aside class="toc"' not in (
            out / "library" / without[0].slug / "index.html"
        ).read_text(encoding="utf-8")

    def test_pager_orders_newer_before_older(self, built):
        from br_insight.articles import load_all

        out, _ = built
        articles = load_all(REPO_ROOT)
        mid = articles[len(articles) // 2]
        newer, older = articles[len(articles) // 2 - 1], articles[len(articles) // 2 + 1]
        text = (out / "library" / mid.slug / "index.html").read_text(encoding="utf-8")
        n = text.index(">Newer</span>")
        o = text.index(">Older</span>")
        assert n < o
        assert text.index(f'href="/library/{newer.slug}/"', n, o)
        assert text.index(f'href="/library/{older.slug}/"', o)

    def test_both_credit_branches_occur_across_corpus(self, built):
        from br_insight.articles import load_all

        out, _ = built
        texts = {
            a.slug: (out / "library" / a.slug / "index.html").read_text(encoding="utf-8")
            for a in load_all(REPO_ROOT)
        }
        credited = [t for t in texts.values() if "Cover art © " in t]
        invited = [t for t in texts.values() if "unknown artist" in t]
        assert credited and invited
        assert all('../../about.html">Get in touch</a>' in t for t in invited)

    def test_focus_hooks_present_progress_untouched(self, built):
        out, _ = built
        sample = next((out / "library").glob("*/index.html"))
        text = sample.read_text(encoding="utf-8")
        assert text.count("data-focus-hide") >= 3
        assert '<div class="progress" aria-hidden="true"></div>' in text


# ---------------------------------------------------------------------------
# Task 8: CLI wiring
# ---------------------------------------------------------------------------


class TestCliBuildWiring:
    def test_build_command_delegates_to_render_build(self, monkeypatch, tmp_path):
        import br_insight.cli as cli

        calls = {}

        def fake_build(root, out):
            calls["root"], calls["out"] = root, out
            return []

        monkeypatch.setattr("br_insight.cli.build", fake_build)
        rc = cli.main(["build", "--out", str(tmp_path)])
        assert rc == 0
        assert calls["out"] == tmp_path
        assert calls["root"] == REPO_ROOT
