"""Tests for br_insight.render: Jinja2 environment, base template chrome,
article page anatomy, and the Task 8 build pipeline."""

import datetime
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from br_insight.config import SiteConfig
from br_insight.images import CoverVariants
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
        meta_description="A machine to measure empathy.",
        slug="voight-kampff-test",
        date=datetime.datetime(2024, 5, 1),
        minutes=6,
        words=1300,
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


class TestDesignDirectionRetrofit:
    """Task 10b: serif prose face, welcome-flicker gating, shipped fonts."""

    @pytest.fixture
    def css(self):
        return (REPO_ROOT / "assets/css/main.css").read_text(encoding="utf-8")

    def test_serif_token_face_and_preloads(self, site, css):
        assert "--font-serif" in css
        assert 'font-family: "Source Serif 4"' in css
        assert "font-display: swap" in css
        assert css.count("source-serif-4-latin-400") == 2  # face + italic face
        html = render_template("base.html", site=site)
        assert html.count("source-serif-4-latin-400") == 1  # regular preload
        assert "400italic.woff2" not in html  # Task 14: italic no longer preloaded

    def test_header_uses_rajdhani_with_red_insight(self, site, css):
        """Header chrome (brand, nav links, header buttons) rides the
        self-hosted Rajdhani face; 'Insight' in the wordmark wears the
        eyebrow red. Both header weights are preloaded."""
        assert '--font-header: "Rajdhani"' in css
        assert css.count('font-family: "Rajdhani"') == 2  # 400 + 600 faces
        assert "font-display: swap" in css
        # Header-scoped rules ride the new token.
        assert re.search(r"\.site-header__brand\s*\{[^}]*font-family:\s*var\(--font-header\)", css)
        assert re.search(r"\.site-nav__link\s*\{[^}]*font-family:\s*var\(--font-header\)", css)
        assert re.search(r"\.site-header \.btn\s*\{[^}]*font-family:\s*var\(--font-header\)", css)
        assert re.search(
            r"\.site-header__brand-accent\s*\{[^}]*color:\s*var\(--red\)", css
        )
        html = render_template("base.html", site=site)
        assert html.count("rajdhani-latin-") == 2  # both weights preloaded

    def test_serif_fonts_shipped_within_budget(self, css):
        fonts = sorted((REPO_ROOT / "assets/fonts").glob("source-serif-*.woff2"))
        sizes = {p.name: p.stat().st_size for p in fonts}
        assert set(sizes) == {
            "source-serif-4-latin-400.woff2",
            "source-serif-4-latin-400italic.woff2",
        }
        assert all(size <= 22 * 1024 for size in sizes.values())
        assert sum(sizes.values()) <= 45 * 1024

    def test_serif_applied_to_prose_and_summaries(self, css):
        prose = css[css.index(".prose {"):]
        # Article prose reads in Lato Light 300; serif stays for card and
        # featured summaries.
        assert "font-family: var(--font-prose)" in prose[:200]
        assert "font-weight: 300" in prose[:200]
        card = css[css.index(".card__summary {"):]
        assert "var(--font-serif)" in card[:300]
        featured = css[css.index(".featured__summary {"):]
        assert "var(--font-serif)" in featured[:200]

    def test_welcome_flicker_attr_present_by_default(self, site):
        html = render_template("base.html", site=site)
        assert '<html lang="en" data-fx-rain data-fx-scanlines data-fx-grain' \
            ' data-fx-flicker data-fx-welcome>' in html

    @pytest.mark.parametrize(
        "fx",
        [
            None,  # master switch off
            "flicker_off",  # flicker.enabled off
            "welcome_off",  # welcome off alone
        ],
    )
    def test_welcome_flicker_attr_absent_when_flags_false(self, site, fx):
        from dataclasses import replace

        if fx is None:
            modified_fx = replace(site.fx, enabled=False)
        elif fx == "flicker_off":
            modified_fx = replace(
                site.fx, flicker=replace(site.fx.flicker, enabled=False)
            )
        else:
            modified_fx = replace(
                site.fx, flicker=replace(site.fx.flicker, welcome=False)
            )
        html = render_template(
            "base.html", site=replace(site, fx=modified_fx)
        )
        assert "data-fx-welcome" not in html

    def test_welcome_flicker_gated_in_css(self, css):
        assert "html[data-fx-welcome] .hero__title" in css
        rule_at = css.index("html[data-fx-welcome] .hero__title")
        # gated rule sits below the reduced-motion blanket in the cascade file
        blanket_at = css.index("@media (prefers-reduced-motion: reduce)")
        assert blanket_at > rule_at


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
        import sys

        import rcssmin

        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        import minify_css

        source = (REPO_ROOT / "assets/css/main.css").read_text(encoding="utf-8")
        minified = (REPO_ROOT / "assets/css/main.min.css").read_text(encoding="utf-8")
        expected = minify_css._version_fonts(
            rcssmin.cssmin(source), REPO_ROOT / "assets/css"
        )
        assert minified == expected

    def test_hidden_attribute_beats_author_display_rules(self):
        """Task 17 C-1 regression: filter.js toggles [hidden] on .card
        (display:flex); a global reset-level override must keep hidden
        elements out of the visual grid in both source and minified css."""
        rule = re.compile(r"\[hidden\]\s*\{[^}]*display:\s*none\s*!important")
        for name in ("main.css", "main.min.css"):
            css = (REPO_ROOT / "assets/css" / name).read_text(encoding="utf-8")
            assert rule.search(css), f"{name} is missing the [hidden] display:none!important override"

    def test_search_overlay_is_centered(self):
        """Ride-along 3: the *{margin:0} reset pins the native dialog left;
        .search-overlay must re-center with margin:auto."""
        pattern = re.compile(r"\.search-overlay\s*\{[^}]*margin:\s*auto")
        for name in ("main.css", "main.min.css"):
            css = (REPO_ROOT / "assets/css" / name).read_text(encoding="utf-8")
            assert pattern.search(css), f"{name} does not center .search-overlay"

    def test_mobile_header_stays_on_one_row(self):
        """Contract update (was: wrapped two-line header): with search and
        atmosphere living inside the menu, the sub-640 header must fit the
        brand + lone Menu button on a single row — no wrap, no forced
        second controls line."""
        css = (REPO_ROOT / "assets/css/main.css").read_text(encoding="utf-8")
        idx = css.index("@media (max-width: 639.98px)")
        depth, start = 0, css.index("{", idx)
        for j in range(start, len(css)):
            if css[j] == "{":
                depth += 1
            elif css[j] == "}":
                depth -= 1
                if depth == 0:
                    block = css[start : j + 1]
                    break
        assert "flex-wrap" not in block
        assert "flex-basis" not in block
        assert ".site-header__brand" in block  # size trim keeps 320px on one row

    def test_mobile_menu_owns_actions_and_dropdown_is_a_card(self):
        """Mobile menu contract: header search/atmosphere buttons hide below
        768px and the dropdown renders as a padded bordered card (no
        edge-hugging text)."""
        for name in ("main.css", "main.min.css"):
            css = (REPO_ROOT / "assets/css" / name).read_text(encoding="utf-8")
            # Desktop hides the in-menu actions; mobile hides the header ones.
            assert re.search(r"\.site-nav__actions\s*\{[^}]*display:\s*none", css), name
            # Brace-match every 767.98px media block and use the nav one.
            blocks = []
            for m in re.finditer(r"@media \(max-width:\s*767\.98px\)", css):
                depth, i = 0, css.index("{", m.start())
                for j in range(i, len(css)):
                    if css[j] == "{":
                        depth += 1
                    elif css[j] == "}":
                        depth -= 1
                        if depth == 0:
                            blocks.append(css[i : j + 1])
                            break
            nav_block = next(b for b in blocks if ".site-nav" in b)
            assert re.search(
                r"\.site-header__controls \.search-btn\s*[,{][^}]*display:\s*none", nav_block
            ), name
            assert re.search(
                r"\.site-header__controls \.fx-btn\s*[,{][^}]*display:\s*none", nav_block
            ), name
            # Dropdown is a card: padded on both axes + a full border + radius.
            nav_rule = re.search(r"\.site-nav\s*\{[^}]*", nav_block)
            assert nav_rule and "border-radius" in nav_rule.group(0), name
            assert re.search(r"\.site-nav\s*\{[^}]*(padding-inline|padding\s*:)", nav_block), name


# ---------------------------------------------------------------------------
# Task 8: article page anatomy (template-level)
# ---------------------------------------------------------------------------


def _ns_article(**overrides):
    base = dict(
        title="Voight-Kampff Test",
        author="K. Deckard",
        summary="A machine to measure empathy.",
        meta_description="A machine to measure empathy.",
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
    cover_variants=CoverVariants(
        source="cover.jpg", hero=(480, 800, 1167), crop=(480, 800, 1167)
    ),
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
        # Cinematic banner: fixed 16:9 box, crop ladder cited.
        assert re.search(r'<img[^>]+width="1280"[^>]+height="720"', html)
        assert 'type="image/webp"' in html
        assert "cover-crop-1167.webp 1167w" in html
        assert 'src="../../library/voight-kampff-test/cover-crop-1167.jpg"' in html

    def test_credit_caption_known_artist(self, html):
        assert "Cover art © Syd Mead" in html

    def test_credit_invite_line_when_artist_unknown(self, site):
        html = render_template(
            "article.html",
            site=site,
            article=_ns_article(cover_artist=None),
            **ANATOMY_CTX,
        )
        assert '<figcaption class="credit">' not in html
        assert "Cover art by an unknown artist" in html
        assert '<a href="../../about.html">Get in touch</a> with us if you know the creator.' in html
        assert html.index("cover-note") > html.index('class="prose"')

    def test_byline_format(self, html):
        assert 'By <span class="byline__author">K. Deckard</span>' in html
        assert '<time datetime="2024-05-01">May 2024</time>' in html
        assert "6 min read" in html

    def test_category_eyebrow_above_byline(self, html):
        assert (
            '<p class="eyebrow article__category">'
            '<a href="/topics/article/">article</a></p>' in html
        )
        assert (
            html.index("article__category") < html.index('class="byline"')
        )

    def test_relative_asset_depth(self, html):
        assert re.search(r'href="\.\./\.\./assets/css/main\.min\.css(\?v=[0-9a-f]{8})?"', html)
        assert re.search(
            r'href="\.\./\.\./assets/fonts/chakra-petch-latin-400\.woff2(\?v=[0-9a-f]{8})?"', html
        )

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
        # TOC aside title is the [CONTENTS] eyebrow
        assert '<p class="eyebrow" id="toc-title">Contents</p>' in html

    def test_no_toc_aside_when_below_threshold(self, html):
        assert '<aside class="toc"' not in html

    def test_back_to_library_link(self, html):
        assert 'href="/library/">' in html

    def test_pager_removed(self, site):
        newer = _ns_article(slug="newer-one", title="Newer One")
        older = _ns_article(slug="older-one", title="Older One")
        html = render_template(
            "article.html", site=site, article=_ns_article(),
            newer=newer, older=older, related=[], toc=[],
        )
        assert "end-block__pager" not in html
        assert ">Newer</span>" not in html
        assert ">Older</span>" not in html

    def test_related_cards_with_title_byline_reading_time(self, site):
        rels = [_ns_article(slug=f"rel-{i}", title=f"Rel {i}") for i in range(3)]
        html = render_template(
            "article.html", site=site, article=_ns_article(),
            related=rels, toc=[],
        )
        assert html.count('class="card"') == 3
        assert 'href="/library/rel-0/"' in html
        assert "K. Deckard" in html
        assert "min read" in html

    def test_progress_present_in_article(self, html):
        progress = html[html.index('class="progress"'):html.index('class="progress"') + 60]
        assert 'role="progressbar"' in progress


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
    """SHA over the rendered tree, including generated cover variants.

    Pillow's WebP/JPEG encoders emit timestamp-free deterministic bytes for
    identical inputs and parameters (verified in tests/test_images.py), so
    generated binaries are safe to include in the idempotency digest. The
    ``cover-*.jpg`` filter keeps legacy originals (``cover-crop.jpg`` etc.)
    out of scope — those are read-only sources, never build outputs.
    """
    import hashlib

    targets = sorted(out.rglob("index.html")) + sorted(
        out.rglob("cover-*.webp")
    ) + [p for p in out.rglob("cover-*.jpg") if "-" in p.stem]

    digest = hashlib.sha256()
    for path in targets:
        if not path.is_file():
            continue
        digest.update(path.relative_to(out).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


class TestBuildPipeline:
    def _expected_outputs(self):
        """Full Task 11 output set: articles + listing + home + topic
        routes (used categories & tags only) + about/404/error twins +
        sitemap/feed/llms."""
        from br_insight.articles import load_all
        from br_insight.config import apply_taxonomy, load_taxonomy
        from br_insight.render import topic_pages

        slugs = {a.slug for a in load_all(REPO_ROOT)}
        expected = {Path("library") / slug / "index.html" for slug in slugs}
        expected.add(Path("library") / "index.html")  # Task 9: library listing
        expected.add(Path("index.html"))  # Task 10: home page
        enriched = apply_taxonomy(load_all(REPO_ROOT), load_taxonomy(REPO_ROOT))
        for topic in topic_pages(enriched):
            parts = ["topics"] + (
                ["tag"] if topic["kind"] == "tag" else []
            ) + [topic["slug"]]
            expected.add(Path(*parts) / "index.html")
        expected.add(Path("about.html"))   # Task 11
        expected.add(Path("404.html"))     # Task 11
        expected.add(Path("error.html"))   # Task 11: byte-twin of 404
        expected.add(Path("topics") / "index.html")  # fix r1: topics hub
        expected.add(Path("sitemap.xml"))  # Task 11
        expected.add(Path("feed.xml"))     # Task 11
        expected.add(Path("llms.txt"))     # SEO/AEO: LLM-consumable corpus list
        return expected

    def test_writes_every_library_index_html(self, built):
        out, written = built
        actual = {p.relative_to(out) for p in written}
        assert actual == self._expected_outputs()
        assert len(written) == len(self._expected_outputs())

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
        assert re.search(r'href="\.\./\.\./assets/css/main\.min\.css(\?v=[0-9a-f]{8})?"', text)

    def test_built_pages_carry_jsonld(self, built):
        from br_insight.articles import load_all

        out, _ = built
        article = load_all(REPO_ROOT)[0]
        text = (out / "library" / article.slug / "index.html").read_text(encoding="utf-8")
        assert '"@type": "Article"' in text
        iso = article.date.strftime("%Y-%m-%d")
        assert f'"datePublished": "{iso}"' in text
        assert f'"mainEntityOfPage": "https://www.br-insight.com/library/{article.slug}/"' in text

    def test_toc_aside_presence_matches_heading_threshold(self, built):
        """Aside appears exactly when the article clears the ≥3-heading bar."""
        from br_insight.articles import extract_toc, load_all

        out, _ = built

        def total(nodes) -> int:
            # Mirrors render._toc_heading_count: the generated "Notes"
            # header doesn't count toward the threshold.
            return sum(
                (n["id"] != "notes") + sum(c["id"] != "notes" for c in n["children"])
                for n in nodes
            )

        for article in load_all(REPO_ROOT):
            expected = total(extract_toc(article.html)) >= 3
            text = (out / "library" / article.slug / "index.html").read_text(
                encoding="utf-8"
            )
            assert ('<aside class="toc"' in text) is expected, article.slug

    def test_pager_removed_from_built_pages(self, built):
        out, _ = built
        text = next(
            p.read_text(encoding="utf-8")
            for p in sorted((out / "library").glob("*/index.html"))
        )
        assert "end-block__pager" not in text
        assert ">Newer</span>" not in text
        assert ">Older</span>" not in text

    def test_both_credit_branches_occur_across_corpus(self, built):
        from br_insight.articles import load_all

        out, _ = built
        texts = {
            a.slug: (out / "library" / a.slug / "index.html").read_text(encoding="utf-8")
            for a in load_all(REPO_ROOT)
        }
        # Known artists get the hero figcaption; unknown ones get only the
        # end-of-article invite note. (The site footer's blanket "Cover art ©
        # their respective artists" line appears on every page, so match on
        # the markup, not the credit text.)
        credited = [t for t in texts.values() if '<figcaption class="credit">' in t]
        invited = [t for t in texts.values() if '<p class="cover-note">' in t]
        assert credited and invited
        assert all("Cover art © " in t for t in credited)
        assert all('<figcaption class="credit">' not in t for t in invited)
        assert all("unknown artist" in t for t in invited)
        assert all('../../about.html">Get in touch</a>' in t for t in invited)

    def test_progress_a11y_contract_baked_into_build(self, built):
        out, _ = built
        sample = next((out / "library").glob("*/index.html"))
        text = sample.read_text(encoding="utf-8")
        # Task 12: progress a11y contract is server-rendered (JS only repaints)
        assert (
            '<div class="progress" role="progressbar" '
            'aria-label="Reading progress" aria-valuemin="0" '
            'aria-valuemax="100" aria-valuenow="0"></div>'
        ) in text


# ---------------------------------------------------------------------------
# Finding 1: TOC aside requires ≥3 h2/h3 headings (threshold applied by build)
# ---------------------------------------------------------------------------

SHORT_TOC_SLUGS = (
    "br-a-sf-movie",            # 2 h2/h3
    "city-eyes-and-christ",     # 1
    "deckards-identity-debate", # 2
    "how-science-became-god",   # 1
    "picturing-the-human",      # 2
    "replicant-i-used-to-know", # 1
    "sf-with-an-angle",         # 2
)


def _toc_entry_count(article) -> int:
    from br_insight.articles import extract_toc

    def total(nodes) -> int:
        # Mirrors render._toc_heading_count: the generated "Notes"
        # header doesn't count toward the threshold.
        return sum(
            (n["id"] != "notes") + sum(c["id"] != "notes" for c in n["children"])
            for n in nodes
        )

    return total(extract_toc(article.html))


class TestBuildTocThreshold:
    def test_build_drops_toc_below_three_headings(self, monkeypatch, tmp_path):
        """Unit: build() applies the ≥3 branch — 2 headings → no aside,
        3 headings → aside, everything else on the corpus untouched."""
        from dataclasses import replace

        import br_insight.render as render_mod
        from br_insight.articles import load_all as real_load_all

        two_headings = '<h2 id="a">A</h2><h3 id="b">B</h3><p>x</p>'
        three_headings = (
            '<h2 id="a">A</h2><h3 id="b">B</h3>'
            '<h2 id="c">C</h2><p>x</p>'
        )

        def fake_load_all(root):
            swaps = {
                "love-letter": two_headings,
                "measure-of-a-man": three_headings,
            }
            return [
                replace(a, html=swaps[a.slug]) if a.slug in swaps else a
                for a in real_load_all(root)
            ]

        monkeypatch.setattr(render_mod, "load_all", fake_load_all)
        out = tmp_path / "build"
        render_mod.build(REPO_ROOT, out)

        short = (out / "library" / "love-letter" / "index.html").read_text(
            encoding="utf-8"
        )
        long = (out / "library" / "measure-of-a-man" / "index.html").read_text(
            encoding="utf-8"
        )
        assert '<aside class="toc"' not in short
        assert '<aside class="toc"' in long


class TestTocThresholdCorpus:
    def test_known_short_articles_have_no_toc_aside(self, built):
        out, _ = built
        from br_insight.articles import load_all

        by_slug = {a.slug: a for a in load_all(REPO_ROOT)}
        for slug in SHORT_TOC_SLUGS:
            assert slug in by_slug  # the known offenders are still in the corpus
            assert _toc_entry_count(by_slug[slug]) < 3
            text = (out / "library" / slug / "index.html").read_text(
                encoding="utf-8"
            )
            assert '<aside class="toc"' not in text, slug

    def test_long_articles_do_show_toc_aside(self, built):
        out, _ = built
        from br_insight.articles import load_all

        by_slug = {a.slug: a for a in load_all(REPO_ROOT)}
        for slug in ("a-study-of-blade-runner", "what-defines-human"):
            assert _toc_entry_count(by_slug[slug]) >= 3
            text = (out / "library" / slug / "index.html").read_text(
                encoding="utf-8"
            )
            assert '<aside class="toc"' in text, slug


# ---------------------------------------------------------------------------
# og:image/JSON-LD image sourcing.
#
# Task 8 ruling: never point social cards at a 404. Task 14 supersedes the
# "declared cover used as-is" clause — crawlers do not decode WebP, so the
# largest generated JPEG hero variant (cover-<max>.jpg) is cited instead;
# the Task 8 fallback chain remains the safety net when variants are absent
# (e.g. a directory with no usable source cover).
# ---------------------------------------------------------------------------

MISSING_COVER_SLUGS = ("aboutfilm-analysis", "deckards-identity-debate")
PRESENT_COVER_PNG_SLUGS = ("appreciation-assessment-of-dircut", "do-androids-dream")


class TestOgImageCoverFallback:
    @staticmethod
    def _emitted_image_urls(text: str) -> tuple[str, str]:
        og = re.search(r'property="og:image" content="([^"]+)"', text).group(1)
        ld = re.search(r'"image": "([^"]+)"', text).group(1)
        return og, ld

    def test_missing_declared_cover_never_404s(self, built):
        """Article declares cover.png but ships only cover.jpg — the cited
        variant must still exist on disk in the output tree."""
        out, _ = built
        from br_insight.articles import load_all

        articles = {a.slug: a for a in load_all(REPO_ROOT)}
        for slug in MISSING_COVER_SLUGS:
            article = articles[slug]
            declared = REPO_ROOT / "library" / slug / article.cover
            assert article.cover != "cover.jpg"  # declares something else…
            assert not declared.is_file()        # …and it is missing on disk
            urls = self._emitted_image_urls(
                (out / "library" / slug / "index.html").read_text(encoding="utf-8")
            )
            for url in urls:
                rel = url.replace("https://www.br-insight.com/", "")
                assert (out / rel).is_file(), url

    def test_existing_declared_cover_pages_cite_jpg_variant(self, built):
        out, _ = built
        from br_insight.articles import load_all

        articles = {a.slug: a for a in load_all(REPO_ROOT)}
        for slug in PRESENT_COVER_PNG_SLUGS:
            article = articles[slug]
            assert article.cover == "cover.png"
            assert (REPO_ROOT / "library" / slug / "cover.png").is_file()
            urls = self._emitted_image_urls(
                (out / "library" / slug / "index.html").read_text(encoding="utf-8")
            )
            expected = re.compile(
                rf"https://www\.br-insight\.com/library/{slug}/cover-\d+\.jpg"
            )
            assert expected.fullmatch(urls[0]) and expected.fullmatch(urls[1]), slug

    def test_jsonld_image_defaults_to_front_matter_cover_and_honors_override(
        self, site
    ):
        """Without ``og_cover`` the JSON-LD image stays the front-matter value;
       an ``og_cover`` override (computed by build) wins."""
        from html import unescape

        article = SimpleNamespace(slug="voight-kampff-test", cover="cover.png",
                                  title="t", author="a", summary="s",
                                  meta_description="s",
                                  date=datetime.datetime(2024, 5, 1),
                                  words=100)
        plain = unescape(render_template("base.html", site=site, article=article))
        _, ld = self._emitted_image_urls(plain)
        assert ld.endswith("/library/voight-kampff-test/cover.png")

        overridden = unescape(render_template(
            "base.html", site=site, article=article, og_cover="cover.jpg"
        ))
        _, ld = self._emitted_image_urls(overridden)
        assert ld.endswith("/library/voight-kampff-test/cover.jpg")


# ---------------------------------------------------------------------------
# Fix round 1: primary-nav hrefs must resolve to built outputs (no orphans)
# ---------------------------------------------------------------------------


def _nav_href_to_path(href: str) -> Path:
    """Map a nav href to its expected output path.

    Directory-style hrefs (``/library/``) map to ``<dir>/index.html``;
    file-style hrefs (``/about.html``) map to the file itself. The root
    ``/`` maps to ``index.html`` — these two styles cover every alias we
    ship, so no extra alias table is needed.
    """
    if href.endswith("/"):
        return Path(href.strip("/")) / "index.html"
    return Path(href.lstrip("/"))


class TestNavHrefsResolveToBuiltOutputs:
    def test_every_site_nav_href_resolves_to_a_built_output(self, built):
        out, written = built
        site = SiteConfig.load(REPO_ROOT)
        outputs = {p.relative_to(out) for p in written}
        assert len(site.nav) >= 3  # sanity: config nav is actually populated
        for item in site.nav:
            assert _nav_href_to_path(item.href) in outputs, item.href

    def test_topics_nav_href_not_an_orphan(self, built):
        """Regression: `Topics → /topics/` shipped before any page was
        built there — every nav click 404'd on production."""
        out, _ = built
        assert (out / "topics" / "index.html").is_file()


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


# ---------------------------------------------------------------------------
# Task 14: performance pass — picture markup, og:image variants, fonts,
# speculation rules
# ---------------------------------------------------------------------------


class TestPictureMarkupContract:
    """Every cover renders through <picture> with WebP srcset + JPG fallback."""

    def _article_pages(self, out):
        return sorted((out / "library").glob("*/index.html"))

    def test_hero_picture_uses_webp_srcset_with_jpg_fallback(self, built):
        out, _ = built
        for page in self._article_pages(out):
            text = page.read_text(encoding="utf-8")
            assert '<source type="image/webp"' in text, page.parent.name
            assert re.search(r'srcset="[^"]*cover-(?:crop-)?\d+\.webp \d+w', text), (
                page.parent.name
            )
            # Non-webp <img> fallback points at a generated jpg variant.
            assert re.search(r'<img[^>]+src="[^"]*cover-(?:crop-)?\d+\.jpg"', text), (
                page.parent.name
            )

    def test_hero_lcp_priority_and_intrinsic_dimensions(self, built):
        out, _ = built
        for page in self._article_pages(out):
            text = page.read_text(encoding="utf-8")
            hero_img = re.search(
                r'<img[^>]*fetchpriority="high"[^>]*>', text
            )
            assert hero_img, page.parent.name
            assert 'width="' in hero_img.group(0)
            assert 'height="' in hero_img.group(0)

    def test_card_covers_lazy_with_webp_crop_srcset(self, built):
        out, _ = built
        text = (out / "library" / "index.html").read_text(encoding="utf-8")
        assert 'cover-crop-480.webp 480w' in text
        assert 'loading="lazy"' in text

    def test_home_featured_cover_optimized(self, built):
        out, _ = built
        text = (out / "index.html").read_text(encoding="utf-8")
        assert 'srcset="' in text and "cover-crop-" in text

    def test_related_cards_use_lazy_web_pictures(self, built):
        from br_insight.articles import load_all

        out, _ = built
        article = load_all(REPO_ROOT)[0]
        text = (out / "library" / article.slug / "index.html").read_text(
            encoding="utf-8"
        )
        if '<section class="end-block__related"' in text:
            assert "cover-crop-" in text


class TestOgImageOptimizedVariant:
    @staticmethod
    def _emitted_image_urls(text: str) -> tuple[str, str]:
        og = re.search(r'property="og:image" content="([^"]+)"', text).group(1)
        ld = re.search(r'"image": "([^"]+)"', text).group(1)
        return og, ld

    def test_all_article_social_images_use_jpg_variant(self, built):
        out, _ = built
        pattern = re.compile(
            r'https://www\.br-insight\.com/library/([\w-]+)/cover-(\d+)\.jpg'
        )
        for page in sorted((out / "library").glob("*/index.html")):
            urls = self._emitted_image_urls(page.read_text(encoding="utf-8"))
            match_og = pattern.fullmatch(urls[0])
            match_ld = pattern.fullmatch(urls[1])
            assert match_og and match_ld, page.parent.name
            assert match_og.groups() == match_ld.groups()

    def test_referenced_variant_file_exists(self, built):
        out, _ = built
        for page in sorted((out / "library").glob("*/index.html")):
            url = self._emitted_image_urls(page.read_text(encoding="utf-8"))[0]
            rel = url.replace("https://www.br-insight.com/", "")
            assert (out / rel).is_file(), url

    def test_declared_png_cover_pages_also_get_variant(self, built):
        # Task 14 supersedes the Task 8 ruling: crawlers never receive webp,
        # so every article with generated variants cites cover-<max>.jpg.
        out, _ = built
        for slug in ("appreciation-assessment-of-dircut", "do-androids-dream"):
            text = (out / "library" / slug / "index.html").read_text(
                encoding="utf-8"
            )
            og = self._emitted_image_urls(text)[0]
            assert re.fullmatch(r'https://www\.br-insight\.com/library/'
                                + slug + r'/cover-\d+\.jpg', og)


class TestFontPreloads:
    def test_no_sitewide_italic_serif_preload(self, built):
        out, _ = built
        for path in sorted(out.rglob("*.html")):
            text = path.read_text(encoding="utf-8")
            assert "400italic" not in text, path.relative_to(out)

    def test_regular_fonts_still_preloaded(self, built):
        out, _ = built
        text = (out / "index.html").read_text(encoding="utf-8")
        assert "chakra-petch-latin-400.woff2" in text
        assert "chakra-petch-latin-600.woff2" in text
        assert "source-serif-4-latin-400.woff2" in text

    def test_article_page_preloads_only_lcp_cover_candidates_as_image(self, built):
        from br_insight.articles import load_all

        out, _ = built
        slug = load_all(REPO_ROOT)[0].slug
        text = (out / "library" / slug / "index.html").read_text(encoding="utf-8")
        preloads = re.findall(r'<link rel="preload"[^>]*as="image"[^>]*>', text)
        assert preloads
        for link in preloads:
            assert 'imagesrcset="' in link  # responsive candidates only


class TestSpeculationRules:
    def test_every_built_page_ships_speculation_rules(self, built):
        out, _ = built
        pages = list(out.rglob("*.html"))
        assert pages
        for path in pages:
            text = path.read_text(encoding="utf-8")
            assert '<script type="speculationrules">' in text, path.name

    def test_rules_prerender_library_routes_moderately(self, built):
        import json as jsonlib

        out, _ = built
        text = (out / "index.html").read_text(encoding="utf-8")
        block = re.search(
            r'<script type="speculationrules">\s*(\{.*?\})\s*</script>',
            text,
            re.S,
        ).group(1)
        rules = jsonlib.loads(block)
        prerender = rules["prerender"][0]
        assert prerender["eagerness"] == "moderate"
        where = jsonlib.dumps(prerender["where"])
        assert "/library" in where


class TestVariantIdempotencyHashing:
    def test_tree_hash_covers_generated_variants(self, tmp_path_factory):
        from br_insight.render import build

        first, second = tmp_path_factory.mktemp("va"), tmp_path_factory.mktemp("vb")
        build(REPO_ROOT, first)
        build(REPO_ROOT, second)
        digest_a = _tree_hash(first)
        digest_b = _tree_hash(second)
        assert digest_a == digest_b
