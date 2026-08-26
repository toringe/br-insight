"""Tests for br_insight.render: Jinja2 environment and base template chrome."""

import datetime
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
        assert ">EST. 1996 · 30 YEARS ONLINE</span>" in html
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
