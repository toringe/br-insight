"""Tests for br_insight.articles: Article model, loaders, and helpers."""

import datetime
import re
from pathlib import Path

import pytest

import br_insight.articles as articles
import br_insight.frontmatter as frontmatter


class TestReadingTime:
    def test_zero_words_clamps_to_one_minute(self):
        assert articles.reading_time(0) == 1

    def test_exactly_220_words_is_one_minute(self):
        assert articles.reading_time(220) == 1

    def test_441_words_rounds_up_to_three_minutes(self):
        assert articles.reading_time(441) == 3


class TestParseDate:
    def test_legacy_dd_mm_yyyy_string(self):
        assert articles.parse_date("08-12-2002") == datetime.datetime(2002, 12, 8)

    def test_iso_string(self):
        assert articles.parse_date("2002-12-08") == datetime.datetime(2002, 12, 8)

    def test_date_object_from_yaml_becomes_datetime(self):
        raw = datetime.date(2002, 12, 8)
        parsed = articles.parse_date(raw)
        assert isinstance(parsed, datetime.datetime)
        assert parsed == datetime.datetime(2002, 12, 8)

    def test_datetime_object_passes_through(self):
        raw = datetime.datetime(2002, 12, 8, 13, 30)
        assert articles.parse_date(raw) is raw


FENCE = "---\n"


class TestSplitFrontMatter:
    def test_splits_at_closing_fence(self):
        text = FENCE + "title: A Study\n" + FENCE + "Body prose.\n"
        fm, body = frontmatter.split(text)
        assert body == "Body prose.\n"
        assert fm.startswith(FENCE)

    def test_body_with_later_fence_is_not_split_early(self):
        text = FENCE + "title: T\n" + FENCE + "prose\n---\nnot front matter\n"
        _, body = frontmatter.split(text)
        assert body == "prose\n---\nnot front matter\n"

    def test_no_front_matter_returns_empty_dict_and_text(self):
        text = "just prose\nmore prose\n"
        data, body = frontmatter.parse(text)
        assert data == {}
        assert body is text


class TestParseFrontMatter:
    def test_parses_yaml_and_preserves_body(self):
        text = (
            FENCE
            + "title: A Study\nauthor: Majid Salin\ncauthor: SoundNinja\ndate: 2002-12-08\n"
            + FENCE
            + "\nBody starts here.\n"
        )
        data, body = frontmatter.parse(text)
        assert data["title"] == "A Study"
        assert data["author"] == "Majid Salin"
        assert data["cauthor"] == "SoundNinja"
        assert body == "\nBody starts here.\n"

    def test_nested_blocks_parse_as_dicts(self):
        text = (
            FENCE
            + "taxonomy:\n  category: article\nsummary:\n  enabled: true\n  size: 100\n"
            + FENCE
            + "body\n"
        )
        data, _ = frontmatter.parse(text)
        assert data["taxonomy"] == {"category": "article"}
        assert data["summary"] == {"enabled": True, "size": 100}

    def test_bare_iso_date_resolves_to_date_object(self):
        # PyYAML resolves bare unquoted ISO dates to datetime.date; the
        # parser stays type-lenient and hands it to parse_date untouched.
        text = FENCE + "date: 2002-12-08\n" + FENCE + "body\n"
        data, _ = frontmatter.parse(text)
        assert isinstance(data["date"], datetime.date)


DISSERTATION_BODY = (
    "\n*This dissertation was written between September 1997 and February"
    " 1998, and formed part of a final examination.*\n\n### Introduction\n\n"
    "Blade Runner opened in US cinemas on the 25th June 1982.\n"
)


class TestExtractSummary:
    def test_truncates_first_paragraph_at_size_words_with_ellipsis(self):
        summary = articles.extract_summary(DISSERTATION_BODY, size=5)
        assert summary == "This dissertation was written between…"

    def test_strips_emphasis_markers_from_summary_text(self):
        summary = articles.extract_summary(DISSERTATION_BODY, size=100)
        assert summary.startswith("This dissertation was written")
        assert "*" not in summary
        assert "_" not in summary

    def test_short_paragraph_is_not_truncated(self):
        body = "\nHello _emphasized_ world.\n\nMore prose.\n"
        assert articles.extract_summary(body, size=10) == (
            "Hello emphasized world."
        )

    def test_leading_blank_lines_are_skipped(self):
        body = "\n\n\nFirst real words here.\n"
        assert articles.extract_summary(body, size=4) == (
            "First real words here."
        )

    def test_heading_led_first_block_skips_to_first_prose_paragraph(self):
        body = (
            '## The "No" Arguments\n\n'
            "Ever since the movie was released people watching it has been"
            " divided in two.\n"
        )
        summary = articles.extract_summary(body, size=100)
        assert summary.startswith("Ever since the movie")
        assert "#" not in summary
        assert '"' not in summary or "No" not in summary

    def test_multiple_leading_headings_skipped_to_first_prose(self):
        body = "## Opening Section\n\n### Subsection Here\n\nActual prose begins.\n"
        assert articles.extract_summary(body, size=4) == (
            "Actual prose begins."
        )

    def test_strips_blockquote_markers_from_summary_text(self):
        body = (
            "> The Postmodern reply to the Modern consists of recognizing"
            " that the past must be revisited.\n\nProse follows.\n"
        )
        summary = articles.extract_summary(body, size=100)
        assert summary.startswith("The Postmodern reply to the Modern")
        assert ">" not in summary

    def test_strips_blockquote_markers_from_lazy_continuation_lines(self):
        body = (
            "> First quoted line\n"
            "> second quoted line\n\n"
            "Prose follows.\n"
        )
        summary = articles.extract_summary(body, size=100)
        assert summary == "First quoted line second quoted line"


def _write_article(root, slug, front_matter, body):
    directory = root / "library" / slug
    directory.mkdir(parents=True)
    text = FENCE + front_matter + FENCE + body
    (directory / "article.md").write_text(text, encoding="utf-8")


FULL_FM = (
    "title: Newer Study\n"
    "author: Jane Doe\n"
    "cover: cover.jpg\n"
    "cauthor: Cover Artist\n"
    "date: 2002-12-08\n"
    "copyright: (c) Jane Doe, 2002.\n"
    "taxonomy:\n"
    "  category: article\n"
    "summary:\n"
    "  enabled: true\n"
    "  size: 5\n"
)
FULL_BODY = (
    "\n*This dissertation was written between September 1997 and February"
    " 1998, and formed part of a final examination.*\n\n### Introduction\n\n"
    "Blade Runner opened in US cinemas on the 25th June 1982.\n"
)

LEGACY_FM = (
    'title: "Blade Runner: an Analysis"\n'
    "author: Unknown\n"
    "cover: cover.png\n"
    "date: 28-07-2000\n"
    "source: http://example.com/source.html\n"
    "taxonomy:\n"
    "  category: article\n"
    "summary:\n"
    "  enabled: true\n"
    "  size: 100\n"
)
LEGACY_BODY = "\nLike most of the best science fiction, Blade Runner is not really concerned.\n"


class TestLoadAll:
    def test_returns_articles_sorted_newest_first(self, tmp_path):
        _write_article(tmp_path, "older", LEGACY_FM, LEGACY_BODY)
        _write_article(tmp_path, "newer", FULL_FM, FULL_BODY)
        loaded = articles.load_all(tmp_path)
        assert [a.slug for a in loaded] == ["newer", "older"]

    def test_full_front_matter_maps_onto_article(self, tmp_path):
        (article,) = articles.load_all(_root_with_newer_only(tmp_path))
        assert article.title == "Newer Study"
        assert article.author == "Jane Doe"
        assert article.cover == "cover.jpg"
        assert article.cover_artist == "Cover Artist"
        assert article.date == datetime.datetime(2002, 12, 8)
        assert article.copyright == "(c) Jane Doe, 2002."
        assert article.category == "article"

    def test_legacy_date_and_optional_fields(self, tmp_path):
        _write_article(tmp_path, "legacy", LEGACY_FM, LEGACY_BODY)
        (article,) = articles.load_all(tmp_path)
        assert article.date == datetime.datetime(2000, 7, 28)
        assert article.cover_artist is None
        assert article.copyright is None
        assert article.source == "http://example.com/source.html"

    def test_unknown_author_passes_through(self, tmp_path):
        _write_article(tmp_path, "legacy", LEGACY_FM, LEGACY_BODY)
        (article,) = articles.load_all(tmp_path)
        assert article.author == "Unknown"

    def test_word_count_and_reading_time(self, tmp_path):
        (article,) = articles.load_all(_root_with_newer_only(tmp_path))
        assert article.words == len(FULL_BODY.split())
        assert article.minutes == articles.reading_time(article.words)

    def test_summary_uses_front_matter_size_and_strips_markdown(self, tmp_path):
        (article,) = articles.load_all(_root_with_newer_only(tmp_path))
        assert article.summary == "This dissertation was written between…"


def _root_with_newer_only(tmp_path):
    _write_article(tmp_path, "newer", FULL_FM, FULL_BODY)
    return tmp_path


class TestRenderMarkdown:
    def test_h2_h3_get_trailing_anchor_link(self):
        html = articles.render_markdown("## One\n\n### Two\n")
        assert '<h2 id="one">One <a class="anchor" href="#one">#</a></h2>' in html
        assert '<h3 id="two">Two <a class="anchor" href="#two">#</a></h3>' in html

    def test_non_h2_h3_get_id_but_no_anchor(self):
        html = articles.render_markdown("# Top\n\n#### Deep\n")
        assert '<h1 id="top">' in html
        assert '<h4 id="deep">' in html
        assert 'class="anchor"' not in html

    def test_duplicate_headings_get_sequential_ids(self):
        html = articles.render_markdown("## Same\n\n## Same\n")
        assert '<h2 id="same">Same' in html
        assert '<h2 id="same-2">Same' in html
        assert 'href="#same-2"' in html

    def test_literal_suffix_collision_stays_unique(self):
        html = articles.render_markdown("## Same\n\n## Same\n\n## Same-2\n")
        ids = re.findall(r'<h2 id="([^"]+)">', html)
        assert len(ids) == len(set(ids))

    def test_slugless_heading_never_gets_empty_id(self):
        html = articles.render_markdown("## 日本語\n\n#### ★★★\n")
        assert 'id=""' not in html
        assert 'href="#"' not in html
        assert '<h2 id="section">' in html
        assert '<h4 id="section-2">' in html

    def test_heading_gets_slugified_id(self):
        html = articles.render_markdown("# Hello World\n\nBody.\n")
        assert '<h1 id="hello-world">Hello World</h1>' in html

    def test_subheading_ids_are_slugified_and_unique_safe(self):
        html = articles.render_markdown("### Introduction\n\n### Introduction, Part 2\n")
        assert '<h3 id="introduction">' in html
        assert '<h3 id="introduction-part-2">' in html

    def test_inline_markup_in_heading_does_not_break_id(self):
        html = articles.render_markdown("## The *Blade Runner* FAQ\n")
        assert '<h2 id="the-blade-runner-faq">' in html

    def test_paragraphs_render_without_ids(self):
        html = articles.render_markdown("Just a paragraph.\n")
        assert "<p>Just a paragraph.</p>" in html


TOC_BODY = (
    "## Alpha\n\nalpha prose.\n\n"
    "### Beta\n\nbeta prose.\n\n"
    "### Gamma\n\ngamma prose.\n\n"
    "## Delta\n\ndelta prose.\n\n"
    "#### Skipped depth\n"
)


class TestExtractToc:
    def test_collects_only_h2_h3_with_ids_and_text(self):
        toc = articles.extract_toc(articles.render_markdown(TOC_BODY))
        assert [(e["level"], e["id"]) for e in toc] == [
            (2, "alpha"),
            (2, "delta"),
        ]
        assert toc[0]["text"] == "Alpha"

    def test_h3_nest_under_preceding_h2(self):
        toc = articles.extract_toc(articles.render_markdown(TOC_BODY))
        assert [(c["level"], c["id"]) for c in toc[0]["children"]] == [
            (3, "beta"),
            (3, "gamma"),
        ]
        assert toc[1]["children"] == []

    def test_orphan_h3_becomes_top_level_entry(self):
        toc = articles.extract_toc(
            articles.render_markdown("### Lone\n")
        )
        assert [e["id"] for e in toc] == ["lone"]

    def test_empty_document_yields_no_entries(self):
        assert articles.extract_toc("<p>no headings</p>") == []


def _make_article(slug, tags=(), date=datetime.datetime(2000, 1, 1)):
    return articles.Article(
        slug=slug,
        title=f"Title {slug}",
        author="Author",
        cover="cover.jpg",
        cover_artist=None,
        date=date,
        words=100,
        minutes=articles.reading_time(100),
        summary="Summary.",
        copyright=None,
        source=None,
        category="article",
        tags=list(tags),
        html="<p>x</p>",
    )


class TestRelated:
    def test_ranks_by_shared_tag_count_desc_and_takes_top_three(self):
        target = _make_article("target", tags=["x", "y"])
        pool = [
            _make_article("two-shared", tags=["x", "y", "w"]),
            _make_article("one-shared-b", tags=["x", "z"]),
            _make_article("none", tags=["q"]),
            _make_article("one-shared-a", tags=["y"]),
        ]
        result = articles.related(target, [target] + pool)
        assert [a.slug for a in result] == [
            "two-shared",
            "one-shared-b",
            "one-shared-a",
        ]

    def test_excludes_self_from_results(self):
        target = _make_article("target", tags=["x"])
        assert articles.related(target, [target]) == []

    def test_articles_without_shared_tags_are_excluded(self):
        target = _make_article("target", tags=["x"])
        other = [_make_article("unrelated", tags=["q"])]
        assert articles.related(target, other) == []

    def test_returns_at_most_three(self):
        target = _make_article("target", tags=["x"])
        pool = [_make_article(f"p{i}", tags=["x"]) for i in range(5)]
        assert len(articles.related(target, pool)) == 3

    def test_real_corpus_has_empty_tags_so_related_is_empty(self, tmp_path):
        _write_article(tmp_path, "newer", FULL_FM, FULL_BODY)
        corpus = articles.load_all(tmp_path)
        assert all(a.tags == [] for a in corpus)
        assert articles.related(corpus[0], corpus) == []


REPO_ROOT = Path(__file__).resolve().parents[1]
NO_CAUTOR_SLUGS = {
    "parting-of-the-mist",
    "significance-of-the-unicorn",
}


@pytest.fixture(scope="module")
def corpus():
    return articles.load_all(REPO_ROOT)


class TestRealLibrary:
    def test_loads_exactly_29_articles(self, corpus):
        assert len(corpus) == 29

    def test_sorted_newest_first(self, corpus):
        dates = [a.date for a in corpus]
        assert dates == sorted(dates, reverse=True)

    def test_every_article_is_complete(self, corpus):
        for article in corpus:
            assert article.title
            assert article.author
            assert article.cover
            assert isinstance(article.date, datetime.datetime)
            assert article.words > 0
            assert article.minutes >= 1
            assert article.summary
            assert article.category == "article"
            assert article.html

    def test_missing_cauthor_maps_to_none_for_known_slugs(self, corpus):
        by_slug = {a.slug: a for a in corpus}
        for slug in NO_CAUTOR_SLUGS:
            assert by_slug[slug].cover_artist is None
        assert sum(a.cover_artist is None for a in corpus) == 2

    def test_unknown_author_passes_through_unchanged(self, corpus):
        by_slug = {a.slug: a for a in corpus}
        assert by_slug["br-an-analysis"].author == "Unknown"

    def test_summaries_match_first_prose_paragraph_and_configured_size(
        self, corpus
    ):
        truncated = 0
        for article in corpus:
            _, body = frontmatter.load(
                REPO_ROOT / "library" / article.slug / "article.md"
            )
            paragraph = next(
                (
                    p.strip()
                    for p in body.split("\n\n")
                    if p.strip()
                    and not all(
                        re.match(r"^\s{0,3}#{1,6}(?:\s|$)", line)
                        for line in p.splitlines()
                        if line.strip()
                    )
                ),
                "",
            )
            paragraph = re.sub(r"^\s{0,3}>\s?", "", paragraph, flags=re.MULTILINE)
            paragraph_words = len(paragraph.split())
            if paragraph_words > 100:
                assert len(article.summary.rstrip("…").split()) == 100
                assert article.summary.endswith("…")
                truncated += 1
            else:
                assert not article.summary.endswith("…")
                assert len(article.summary.split()) == paragraph_words
        assert truncated, "expected some articles to have truncated summaries"
