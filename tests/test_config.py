"""Tests for br_insight.config: taxonomy loading, validation, and enrichment."""

import datetime
from dataclasses import replace
from pathlib import Path

import pytest

import br_insight.articles as articles
import br_insight.config as config
from br_insight.textutils import slugify

REPO_ROOT = Path(__file__).resolve().parents[1]


class TestSlugify:
    def test_apostrophes_become_hyphens(self):
        assert slugify("director's-cut") == "director-s-cut"

    def test_ampersands_and_spaces_collapse_to_single_hyphen(self):
        assert slugify("Themes & Humanity") == "themes-humanity"

    def test_strips_diacritics(self):
        assert slugify("André") == "andre"

    def test_lowercases_and_trims_edge_hyphens(self):
        assert slugify("--Religion & Symbolism--") == "religion-symbolism"


def _make_article(slug):
    return articles.Article(
        slug=slug,
        title=f"Title {slug}",
        author="Author",
        cover="cover.jpg",
        cover_artist=None,
        date=datetime.datetime(2000, 1, 1),
        words=100,
        minutes=1,
        summary="Summary.",
        copyright=None,
        source=None,
        category="article",
        tags=[],
        html="<p>x</p>",
    )


def _taxonomy(assignments, categories=("Film Analysis", "Characters"),
              vocab=("noir", "eyes")):
    return config.Taxonomy(
        categories=tuple(categories),
        tag_vocab=frozenset(vocab),
        assignments={
            slug: config.TaxonomyAssignment(entry["category"], tuple(entry["tags"]))
            for slug, entry in assignments.items()
        },
    )


class TestApplyTaxonomy:
    def test_unknown_assignment_slug_is_rejected_and_listed(self):
        corpus = [_make_article("known")]
        taxonomy = _taxonomy({"ghost": {"category": "Film Analysis", "tags": []}})
        with pytest.raises(config.TaxonomyError, match="ghost"):
            config.apply_taxonomy(corpus, taxonomy)

    def test_unknown_tag_is_rejected_and_listed(self):
        corpus = [_make_article("s1")]
        taxonomy = _taxonomy(
            {"s1": {"category": "Film Analysis", "tags": ["bogus"]}}
        )
        with pytest.raises(config.TaxonomyError, match="bogus"):
            config.apply_taxonomy(corpus, taxonomy)

    def test_unassigned_article_is_rejected_and_listed(self):
        corpus = [_make_article("assigned"), _make_article("forgotten")]
        taxonomy = _taxonomy(
            {"assigned": {"category": "Film Analysis", "tags": ["noir"]}}
        )
        with pytest.raises(config.TaxonomyError, match="forgotten"):
            config.apply_taxonomy(corpus, taxonomy)

    def test_enriches_category_and_tags(self):
        corpus = [_make_article("s1"), _make_article("s2")]
        taxonomy = _taxonomy(
            {
                "s1": {"category": "Film Analysis", "tags": ["noir"]},
                "s2": {"category": "Characters", "tags": ["eyes", "noir"]},
            }
        )
        enriched = {a.slug: a for a in config.apply_taxonomy(corpus, taxonomy)}
        assert enriched["s1"].category == "Film Analysis"
        assert enriched["s1"].tags == ["noir"]
        assert enriched["s2"].category == "Characters"
        assert enriched["s2"].tags == ["eyes", "noir"]

    def test_input_articles_are_left_untouched(self):
        original = _make_article("s1")
        taxonomy = _taxonomy(
            {"s1": {"category": "Film Analysis", "tags": ["noir"]}}
        )
        (enriched,) = config.apply_taxonomy([original], taxonomy)
        assert original.category == "article"
        assert original.tags == []
        assert enriched is not original


TAXONOMY_TEXT = (
    "categories: [A, B]\n"
    "tag_vocab: [x, y]\n"
    "assignments:\n"
    "  s1: {category: A, tags: [x]}\n"
)


def _write_taxonomy(tmp_path, text):
    data_dir = tmp_path / "_data"
    data_dir.mkdir()
    (data_dir / "taxonomy.yaml").write_text(text, encoding="utf-8")


class TestLoadTaxonomy:
    def test_parses_categories_vocab_and_assignments(self, tmp_path):
        _write_taxonomy(
            tmp_path,
            TAXONOMY_TEXT + "  s2: {category: B, tags: [y]}\n",
        )
        taxonomy = config.load_taxonomy(tmp_path)
        assert taxonomy.categories == ("A", "B")
        assert taxonomy.tag_vocab == frozenset({"x", "y"})
        assert taxonomy.assignments["s2"].category == "B"
        assert taxonomy.assignments["s2"].tags == ("y",)

    def test_duplicate_assignment_slug_is_rejected(self, tmp_path):
        _write_taxonomy(
            tmp_path,
            TAXONOMY_TEXT + "  s1: {category: B, tags: [y]}\n",
        )
        with pytest.raises(config.TaxonomyError, match="s1"):
            config.load_taxonomy(tmp_path)


@pytest.fixture(scope="module")
def real_corpus():
    return articles.load_all(REPO_ROOT)


@pytest.fixture(scope="module")
def real_taxonomy():
    return config.load_taxonomy(REPO_ROOT)


@pytest.fixture(scope="module")
def enriched_corpus(real_corpus, real_taxonomy):
    return config.apply_taxonomy(real_corpus, real_taxonomy)


class TestRealCorpus:
    def test_owner_reviewed_counts(self, real_taxonomy):
        assert len(real_taxonomy.categories) == 8
        assert len(real_taxonomy.tag_vocab) == 29
        assert len(real_taxonomy.assignments) == 29

    def test_known_entries_transcribed_verbatim(self, real_taxonomy):
        assert real_taxonomy.categories[:2] == (
            "Film Analysis",
            "Themes & Humanity",
        )
        assert "director's-cut" in real_taxonomy.tag_vocab
        assert real_taxonomy.assignments["a-study-of-blade-runner"] == (
            config.TaxonomyAssignment(
                "Film Analysis",
                ("cinematography", "noir", "tears-in-rain"),
            )
        )

    def test_all_29_articles_validate_and_enrich(self, enriched_corpus):
        assert len(enriched_corpus) == 29
        slugs = {a.slug for a in enriched_corpus}
        assert slugs == set(real_taxonomy_assignments_slugs())

    def test_every_category_and_tag_comes_from_the_vocabulary(
        self, real_taxonomy, enriched_corpus
    ):
        for article in enriched_corpus:
            assert article.category in real_taxonomy.categories
            assert set(article.tags) <= real_taxonomy.tag_vocab
            assert article.tags

    def test_spot_checks(self, enriched_corpus):
        by_slug = {a.slug: a for a in enriched_corpus}
        assert by_slug["worn-down-hell"].category == "World & Setting"
        assert by_slug["worn-down-hell"].tags == ["los-angeles-2019", "dystopia"]
        assert by_slug["love-letter"].category == "Creative Works"
        assert by_slug["love-letter"].tags == ["fan-fiction", "rachael"]

    def test_source_corpus_keeps_placeholder_taxonomy(
        self, real_corpus, enriched_corpus
    ):
        originals = {a.slug: a for a in real_corpus}
        for article in enriched_corpus:
            assert originals[article.slug].category == "article"
            assert originals[article.slug].tags == []


def real_taxonomy_assignments_slugs():
    return set(config.load_taxonomy(REPO_ROOT).assignments)


# ---------------------------------------------------------------------------
# Site config
# ---------------------------------------------------------------------------


def _write_site(tmp_path, text):
    data_dir = tmp_path / "_data"
    data_dir.mkdir(exist_ok=True)
    (data_dir / "site.yaml").write_text(text, encoding="utf-8")


class TestSiteConfigDefaults:
    def test_empty_yaml_yields_complete_defaults(self, tmp_path):
        _write_site(tmp_path, "")
        site = config.SiteConfig.load(tmp_path)
        assert site.name == "Blade Runner Insight"
        assert site.tagline
        assert site.base_url == "https://www.br-insight.com"
        assert site.established == 1996
        assert site.featured.slug == ""
        assert site.featured.fallback == "monthly-rotation"
        assert site.social.twitter == ""
        assert [(item.label, item.href) for item in site.nav] == [
            ("Home", "/"),
            ("Library", "/library/"),
            ("Topics", "/topics/"),
            ("About", "/about.html"),
        ]

    def test_missing_yaml_file_yields_defaults(self, tmp_path):
        site = config.SiteConfig.load(tmp_path)
        assert site.name == "Blade Runner Insight"
        assert site.fx.enabled is True

    def test_minimal_yaml_overrides_only_given_keys(self, tmp_path):
        _write_site(tmp_path, "name: Other Name\n")
        site = config.SiteConfig.load(tmp_path)
        assert site.name == "Other Name"
        assert site.base_url == "https://www.br-insight.com"
        assert site.fx.rain.density == 120

    def test_nested_override_merges_deeply(self, tmp_path):
        _write_site(
            tmp_path,
            "fx:\n  rain:\n    density: 42\n",
        )
        site = config.SiteConfig.load(tmp_path)
        assert site.fx.rain.density == 42
        assert site.fx.rain.speed == 1.0
        assert site.fx.rain.tier_auto is True
        assert site.fx.flicker.enabled is True

    def test_fx_defaults_match_controller_ruling(self, tmp_path):
        _write_site(tmp_path, "")
        fx = config.SiteConfig.load(tmp_path).fx
        assert fx.enabled is True
        assert fx.atmosphere_toggle is True
        assert fx.rain == config.RainFx(
            enabled=True, density=120, speed=1.0, tier_auto=True
        )
        assert fx.flicker == config.FlickerFx(enabled=True, welcome=True)
        assert fx.scanlines == config.FxToggle(enabled=True)
        assert fx.grain == config.FxToggle(enabled=True)

    def test_flicker_welcome_defaults_on_and_overrides_independently(self, tmp_path):
        _write_site(tmp_path, "")
        assert config.SiteConfig.load(tmp_path).fx.flicker.welcome is True
        _write_site(tmp_path, "fx:\n  flicker:\n    welcome: false\n")
        fx = config.SiteConfig.load(tmp_path).fx
        assert fx.flicker == config.FlickerFx(enabled=True, welcome=False)

    def test_unknown_top_level_key_warns_loudly(self, tmp_path):
        _write_site(tmp_path, "bogus_key: 1\n")
        with pytest.warns(UserWarning, match="bogus_key"):
            site = config.SiteConfig.load(tmp_path)
        assert site.name == "Blade Runner Insight"

    def test_duplicate_top_level_key_is_rejected(self, tmp_path):
        _write_site(tmp_path, "name: A\nname: B\n")
        with pytest.raises(config.SiteConfigError, match="name"):
            config.SiteConfig.load(tmp_path)


class TestResolveFeatured:
    def _config(self, tmp_path, slug=""):
        base = config.SiteConfig.load(tmp_path)
        return replace(
            base,
            featured=config.FeaturedConfig(
                slug=slug, fallback=base.featured.fallback
            ),
        )

    def test_explicit_slug_returns_that_article(self, tmp_path):
        corpus = [_make_article("b"), _make_article("a")]
        article = config.resolve_featured(
            self._config(tmp_path, "a"), corpus, "202608"
        )
        assert article.slug == "a"

    def test_explicit_unknown_slug_is_rejected_and_named(self, tmp_path):
        corpus = [_make_article("a")]
        with pytest.raises(config.SiteConfigError, match="ghost"):
            config.resolve_featured(
                self._config(tmp_path, "ghost"), corpus, "202608"
            )

    def test_rotation_is_deterministic_within_a_month(self, tmp_path):
        corpus = [_make_article("c"), _make_article("a"), _make_article("b")]
        first = config.resolve_featured(
            self._config(tmp_path), corpus, "202608"
        )
        second = config.resolve_featured(
            self._config(tmp_path), corpus, "202608"
        )
        assert first is second

    def test_rotation_indexes_sorted_slugs_by_month_modulo(self, tmp_path):
        corpus = [_make_article("c"), _make_article("a"), _make_article("b")]
        article = config.resolve_featured(
            self._config(tmp_path), corpus, "202608"
        )
        slugs = sorted(a.slug for a in corpus)
        assert article.slug == slugs[int("202608") % len(slugs)]

    def test_rotation_changes_with_the_month(self, tmp_path):
        corpus = [_make_article("c"), _make_article("a"), _make_article("b")]
        august = config.resolve_featured(
            self._config(tmp_path), corpus, "202608"
        )
        july = config.resolve_featured(
            self._config(tmp_path), corpus, "202607"
        )
        assert august.slug != july.slug

    def test_rotation_with_empty_corpus_is_rejected(self, tmp_path):
        with pytest.raises(config.SiteConfigError, match="no articles"):
            config.resolve_featured(self._config(tmp_path), [], "202608")


class TestResolveArchivePicks:
    def test_picks_are_capped_newest_first_and_deterministic(self):
        corpus = [_make_article(f"article-{i}") for i in range(8)]
        picks = config.resolve_archive_picks(corpus, "2026-W35")
        assert len(picks) == config.ARCHIVE_PICK_COUNT == 3
        assert picks == sorted(picks, key=lambda a: a.date, reverse=True)
        again = config.resolve_archive_picks(corpus, "2026-W35")
        assert [a.slug for a in again] == [a.slug for a in picks]

    def test_picks_change_with_the_week_but_stay_deterministic(self):
        corpus = [_make_article(f"slug-{i}") for i in range(12)]

        def picks_for(week):
            return [
                a.slug for a in config.resolve_archive_picks(corpus, week)
            ]

        assert picks_for("2026-W35") == picks_for("2026-W35")
        # across a year of weeks the pick set actually rotates
        distinct = {
            tuple(picks_for(f"2026-W{n:02d}")) for n in range(1, 53)
        }
        assert len(distinct) > 1

    def test_featured_slug_is_excluded(self):
        corpus = [_make_article(f"slug-{i}") for i in range(8)]
        plain = [a.slug for a in config.resolve_archive_picks(corpus, "2026-W35")]
        excluded = [
            a.slug
            for a in config.resolve_archive_picks(
                corpus, "2026-W35", exclude_slug=plain[0]
            )
        ]
        assert plain[0] not in excluded
        assert len(excluded) == 3
        assert set(excluded) <= {a.slug for a in corpus}
        assert set(excluded) != set(plain)

    def test_empty_corpus_yields_no_picks(self):
        assert config.resolve_archive_picks([], "2026-W35") == []

    def test_corpus_smaller_than_pick_count_returns_all(self):
        corpus = [_make_article("only"), _make_article("another")]
        picks = config.resolve_archive_picks(corpus, "2026-W35")
        assert {a.slug for a in picks} == {"only", "another"}

    def test_cyrb53_parity_with_client_hash(self):
        # vector locked by the JS implementation in archive.js (run under
        # Node in tests/test_archive_js.py) — both sides must stay in sync
        assert config.cyrb53("foobar") == 3480908510889717
        assert config.cyrb53("") == 3338908027751811
        # hex form sorts lexicographically like the number
        assert config.cyrb53_hex("foobar") == f"{config.cyrb53('foobar'):013x}"


class TestRealSiteYaml:
    def test_owner_values_load_from_repo(self):
        site = config.SiteConfig.load(REPO_ROOT)
        assert site.name == "Blade Runner Insight"
        assert site.tagline
        assert site.base_url == "https://www.br-insight.com"
        assert site.established == 1996
        assert site.featured == config.FeaturedConfig(
            slug="postmodernist-view", fallback="monthly-rotation"
        )
        assert site.social.twitter == "brinsight"
        assert site.fx.flicker == config.FlickerFx(enabled=True, welcome=True)
        assert [item.label for item in site.nav] == [
            "Home", "Library", "Topics", "About",
        ]

    def test_real_featured_slug_resolves_against_corpus(self, real_corpus):
        site = config.SiteConfig.load(REPO_ROOT)
        article = config.resolve_featured(site, real_corpus, "202608")
        assert article.slug == "postmodernist-view"


class TestDevBannerEnabled:
    """Branch-conditional dev banner: build-time probe, not a template fact."""

    def test_explicit_override_wins(self, monkeypatch):
        monkeypatch.setenv("BRI_DEV_BANNER", "0")
        monkeypatch.setenv("CF_PAGES_BRANCH", "dev")
        assert config.dev_banner_enabled() is False
        monkeypatch.setenv("BRI_DEV_BANNER", "1")
        monkeypatch.setenv("CF_PAGES_BRANCH", "master")
        assert config.dev_banner_enabled() is True

    @pytest.mark.parametrize("env_name", ["CF_PAGES_BRANCH", "GITHUB_REF_NAME", "GIT_BRANCH", "BRANCH_NAME"])
    def test_ci_branch_probes(self, monkeypatch, env_name):
        monkeypatch.delenv("BRI_DEV_BANNER", raising=False)
        for name in config._BRANCH_ENV_VARS:
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setenv(env_name, "dev")
        assert config.dev_banner_enabled() is True
        monkeypatch.setenv(env_name, "master")
        assert config.dev_banner_enabled() is False

    def test_no_branch_signal_defaults_off(self, monkeypatch):
        monkeypatch.delenv("BRI_DEV_BANNER", raising=False)
        for name in config._BRANCH_ENV_VARS:
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setenv("PATH", "")  # git subprocess cannot run
        assert config.dev_banner_enabled() is False

    def test_header_template_gates_on_flag(self):
        from br_insight.render import render_template

        site = config.SiteConfig.load(REPO_ROOT)
        with_banner = render_template(
            "partials/header.html", site=site, dev_banner=True
        )
        without = render_template(
            "partials/header.html", site=site, dev_banner=False
        )
        assert 'class="dev-banner"' in with_banner
        assert 'class="dev-banner"' not in without
        # context values shadow the build-time global in both directions
