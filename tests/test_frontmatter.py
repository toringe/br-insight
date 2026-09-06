"""Tests for scripts/normalize_frontmatter.py.

Unit tests use small inline fixtures representing each legacy front-matter
quirk class; one integration test proves every real library article parses
with strict yaml.safe_load after migration.
"""

import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from normalize_frontmatter import (  # noqa: E402
    REQUIRED_TOP_LEVEL_KEYS,
    normalize_front_matter,
    split_front_matter,
)

FENCE = "---\n"

# Quirk class: tab-indented nested keys, trailing whitespace on value lines,
# DD-MM-YYYY date, unknown `cauthor` field.
FM_TABS = (
    "---\n"
    "title: A Study\n"
    "author: Majid Salim\n"
    "cover: cover.jpg\n"
    "cauthor: SoundNinja \n"
    "date: 08-12-2002\n"
    "taxonomy:\n"
    "\tcategory: article\n"
    "summary:\n"
    "\tenabled: true\n"
    "\tsize: 100\n"
    "---\n"
)
FM_TABS_BODY = "Body keeps its\ttabs and trailing spaces   \n"

# Quirk class: taxonomy and summary blocks missing entirely, copyright field.
FM_MISSING = (
    "---\n"
    "title: AboutFilm Analysis\n"
    "author: Carlo Cavagna\n"
    "cover: cover.png\n"
    "cauthor: Brijesh Lala \n"
    "date: 28-07-2000  \n"
    "copyright: AboutFilm.com and Carlo Cavagna, 2000.  \n"
    "---\n"
)

# Quirk class: multi-line folded scalar (backslash continuation) must survive.
FM_FOLDED = (
    "---\n"
    "title: Humans & Technology\n"
    "author: Thomas Gramstad\n"
    "source: http://www.ifi.uio.no/~thomas/artikler/blade-runner\\\n"
    ".html\n"
    "date: 05-03-2000\n"
    "---\n"
)

# Quirk class: unquoted scalar containing ": " is invalid YAML mapping syntax.
FM_COLON_VALUE = (
    "---\n"
    "title: Blade Runner: an Analysis\n"
    "author: Unknown\n"
    "---\n"
)


def apply(text: str) -> tuple[str, list[str]]:
    fm, body = split_front_matter(text)
    assert fm is not None
    new_fm, changes = normalize_front_matter(fm)
    return new_fm + body, changes


class TestSplitFrontMatter:
    def test_splits_at_closing_fence(self):
        fm, body = split_front_matter(FM_TABS + FM_TABS_BODY)
        assert fm.startswith(FENCE)
        assert fm.endswith("---\n")
        assert body == FM_TABS_BODY

    def test_no_front_matter(self):
        text = "just prose\nmore prose\n"
        fm, body = split_front_matter(text)
        assert fm is None
        assert body is text

    def test_body_with_later_fence_is_not_split_early(self):
        text = FENCE + "k: v\n" + FENCE + "prose\n---\nnot front matter\n"
        _, body = split_front_matter(text)
        assert body == "prose\n---\nnot front matter\n"


class TestNormalizationRules:
    def test_tabs_become_two_spaces_in_front_matter_only(self):
        result, changes = apply(FM_TABS + FM_TABS_BODY)
        fm, _ = split_front_matter(result)
        assert "\t" not in fm
        assert "  category: article\n" in fm
        assert "  enabled: true\n" in fm
        assert "tabs" in " ".join(changes)
        # Body bytes untouched: tabs preserved below the fence.
        assert result.endswith(FM_TABS_BODY)

    def test_trailing_whitespace_stripped_in_front_matter_only(self):
        result, changes = apply(FM_MISSING + FM_TABS_BODY)
        fm, _ = split_front_matter(result)
        for line in fm.splitlines():
            assert line == line.rstrip(" \t")
        assert any("whitespace" in c for c in changes)
        assert result.endswith("trailing spaces   \n")

    def test_date_coerced_to_iso(self):
        result, changes = apply(FM_TABS)
        assert "date: 2002-12-08\n" in result
        assert any("date" in c.lower() for c in changes)

    def test_date_already_iso_left_alone(self):
        text = FENCE + "title: T\nauthor: A\ndate: 2002-12-08\n" + FENCE
        result, _ = apply(text)
        assert "date: 2002-12-08\n" in result

    def test_missing_taxonomy_and_summary_injected_with_defaults(self):
        result, changes = apply(FM_MISSING)
        assert "taxonomy:\n  category: article\n" in result
        assert "summary:\n  enabled: true\n  size: 100\n" in result
        assert any("taxonomy" in c for c in changes)
        assert any("summary" in c for c in changes)

    def test_existing_blocks_not_duplicated(self):
        result, _ = apply(FM_TABS)
        assert result.count("taxonomy:") == 1
        assert result.count("summary:") == 1

    def test_colon_in_value_gets_quoted(self):
        result, changes = apply(FM_COLON_VALUE)
        assert 'title: "Blade Runner: an Analysis"\n' in result
        assert any("quoted" in c for c in changes)
        data = yaml.safe_load(split_front_matter(result)[0].split("---")[1])
        assert data["title"] == "Blade Runner: an Analysis"

    def test_already_quoted_value_left_alone(self):
        text = FENCE + 'title: "Run: the Sequel"\nauthor: A\n' + FENCE
        result, _ = apply(text)
        assert 'title: "Run: the Sequel"\n' in result

    def test_folded_continuation_lines_not_quoted(self):
        result, _ = apply(FM_FOLDED)
        assert (
            "source: http://www.ifi.uio.no/~thomas/artikler/blade-runner\\\n"
            ".html\n"
        ) in result

    def test_unknown_fields_preserved_verbatim(self):
        result, _ = apply(FM_TABS + FM_TABS_BODY)
        assert "cauthor: SoundNinja\n" in result  # only trailing space stripped

        result2, _ = apply(FM_MISSING)
        assert "copyright: AboutFilm.com and Carlo Cavagna, 2000.\n" in result2

        result3, _ = apply(FM_FOLDED)
        assert (
            "source: http://www.ifi.uio.no/~thomas/artikler/blade-runner\\\n"
            ".html\n"
        ) in result3

    def test_field_values_and_order_of_existing_fields_preserved(self):
        result, _ = apply(FM_TABS)
        lines = result.splitlines()
        assert lines[1] == "title: A Study"
        assert lines[2] == "author: Majid Salim"
        assert lines.index("cauthor: SoundNinja") < lines.index("date: 2002-12-08")


class TestIdempotency:
    @pytest.mark.parametrize(
        "text",
        [FM_TABS, FM_MISSING, FM_FOLDED, FM_COLON_VALUE],
        ids=["tabs", "missing-blocks", "folded-scalar", "colon-value"],
    )
    def test_normalize_twice_equals_once(self, text):
        once, _ = apply(text)
        twice, second_changes = apply(once)
        assert twice == once
        assert second_changes == []

    def test_normalized_fixture_parses_and_satisfies_schema(self):
        result, _ = apply(FM_TABS)
        data = yaml.safe_load(split_front_matter(result)[0].split("---")[1])
        # PyYAML resolves bare ISO dates to datetime.date; T3's parser
        # accepts both that and the plain string.
        assert str(data["date"]) == "2002-12-08"
        assert data["taxonomy"]["category"] == "article"
        assert data["summary"] == {"enabled": True, "size": 100}
        assert set(data) >= set(REQUIRED_TOP_LEVEL_KEYS)


class TestLibraryArticles:
    def test_all_30_articles_parse_with_strict_yaml(self):
        articles = sorted((REPO_ROOT / "library").glob("*/article.md"))
        assert len(articles) == 30
        failures = []
        for path in articles:
            text = path.read_text(encoding="utf-8")
            fm, body = split_front_matter(text)
            if fm is None:
                failures.append(f"{path}: no front matter")
                continue
            try:
                data = yaml.safe_load(fm[len(FENCE) : -len(FENCE)])
            except yaml.YAMLError as exc:
                failures.append(f"{path}: {exc}")
                continue
            missing = set(REQUIRED_TOP_LEVEL_KEYS) - set(data)
            if missing:
                failures.append(f"{path}: missing keys {sorted(missing)}")
            if not body.startswith("\n"):
                failures.append(f"{path}: body does not start with newline")
        assert failures == []
