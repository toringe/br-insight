"""Tests for br_insight.config: taxonomy loading, validation, and enrichment."""

import datetime
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
