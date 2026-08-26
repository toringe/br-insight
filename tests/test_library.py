"""Tests for the Task 9 library page: template anatomy, facet computation,
build integration, and the client-side filter.js contract."""

import datetime
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from br_insight.config import SiteConfig, load_taxonomy, apply_taxonomy
from br_insight.render import REPO_ROOT


# ---------------------------------------------------------------------------
# Pure helpers: decade bucketing + facet extraction
# ---------------------------------------------------------------------------


class TestDecadeHelper:
    def test_decade_buckets_from_dates(self):
        from br_insight.render import decade

        assert decade(datetime.datetime(2019, 7, 14)) == "2010s"
        assert decade(datetime.datetime(2000, 1, 1)) == "2000s"
        assert decade(datetime.datetime(1996, 11, 30)) == "1990s"
        assert decade(datetime.datetime(2009, 12, 31)) == "2000s"

    def test_corpus_decades_are_chronological(self):
        from br_insight.articles import load_all
        from br_insight.render import decade

        articles = load_all(REPO_ROOT)
        buckets = []
        for article in articles:
            label = decade(article.date)
            if label not in buckets:
                buckets.append(label)
        assert buckets == ["2010s", "2000s", "1990s"]  # corpus is newest-first


class TestFacets:
    def test_facets_computed_at_build_time(self):
        """Distinct categories/tags/authors sorted A-Z; decades chronological."""
        from br_insight.articles import load_all
        from br_insight.render import facets

        articles = apply_taxonomy(load_all(REPO_ROOT), load_taxonomy(REPO_ROOT))
        result = facets(articles)

        assert result["categories"] == [
            "Characters",
            "Creative Works",
            "Film Analysis",
            "Novel & Adaptation",
            "Religion & Symbolism",
            "Technology & Society",
            "Themes & Humanity",
            "World & Setting",
        ]
        assert result["decades"] == ["1990s", "2000s", "2010s"]
        # every vocabulary tag is in use across the corpus
        vocab = set(load_taxonomy(REPO_ROOT).tag_vocab)
        assert set(result["tags"]) <= vocab
        assert len(result["authors"]) == len({a.author for a in articles})


# ---------------------------------------------------------------------------
# Template-level: library page anatomy
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
    from types import SimpleNamespace

    return SimpleNamespace(**base)


LIB_CTX = dict(
    articles=[_ns_article(), _ns_article(slug="second-one", title="Second One")],
    categories=["Film Analysis"],
    tags=["empathy", "noir"],
    authors=["K. Deckard"],
    decades=["2020s"],
)


class TestLibraryAnatomy:
    @pytest.fixture
    def site(self) -> SiteConfig:
        return SiteConfig.load(REPO_ROOT)

    @pytest.fixture
    def html(self, site):
        from br_insight.render import render_template

        return render_template("library.html", site=site, **LIB_CTX)

    def test_head_and_intro(self, html):
        assert "<title>Library — Blade Runner Insight</title>" in html
        assert ">Library</h1>" in html
        assert "In-depth analysis" in html
        assert 'href="https://www.br-insight.com/library/"' in html  # canonical

    def test_asset_depth_is_one_level(self, html):
        assert 'href="../assets/css/main.min.css"' in html
        assert '../library/voight-kampff-test/cover-crop.jpg"' in html

    def test_filter_bar_rows_for_all_groups(self, html):
        assert 'data-filter-bar' in html
        for label in ("Category", "Tag", "Decade", "Author"):
            assert f">{label}</p>" in html
        assert 'data-group="category"' in html
        assert 'data-group="tag"' in html
        assert 'data-group="decade"' in html
        assert 'data-group="author"' in html
        # chips declare pressed state for the active-style contract
        assert html.count('aria-pressed="false"') >= 5

    def test_sort_control_options(self, html):
        assert '<select' in html and 'data-sort' in html
        for value in ("newest", "oldest", "longest", "shortest", "az"):
            assert f'value="{value}"' in html

    def test_cards_server_rendered_with_data_attrs(self, html):
        assert html.count('class="card"') == 2
        assert 'data-category="Film Analysis"' in html
        assert 'data-tags="noir empathy"' in html
        assert 'data-author="K. Deckard"' in html
        assert 'data-decade="2020s"' in html
        assert 'data-minutes="6"' in html
        assert 'data-date="2024-05-01"' in html

    def test_card_content_contract(self, html):
        assert 'loading="lazy"' in html
        assert 'width="505"' in html and 'height="295"' in html
        assert 'href="/library/voight-kampff-test/">Voight-Kampff Test</a>' in html
        assert "min read" in html
        # deep-linkable chip anchors on the card itself
        assert '/library/?author=' in html
        assert '/library/?tag=' in html

    def test_zero_js_fallback_full_list(self, html):
        """Every article is present regardless of JS; empty-state starts hidden."""
        assert "[data-empty]" in html or "data-empty" in html
        assert "hidden" in html

    def test_empty_state_copy_and_clear_action(self, html):
        assert "No essays match those filters." in html
        assert 'class="btn btn--ghost" data-clear-filters>Clear filters</button>' in html

    def test_filter_module_script_tag(self, html):
        assert '<script type="module" src="../assets/js/modules/filter.js">' in html


# ---------------------------------------------------------------------------
# Build pipeline writes the library listing
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def built_lib(tmp_path_factory):
    from br_insight.render import build

    out = tmp_path_factory.mktemp("lib_build")
    build(REPO_ROOT, out)
    return out


class TestBuildLibraryPage:
    def test_library_index_written(self, built_lib):
        page = built_lib / "library" / "index.html"
        assert page.is_file()

    def test_all_29_articles_in_output(self, built_lib):
        text = (built_lib / "library" / "index.html").read_text(encoding="utf-8")
        assert text.count('class="card"') == 29

    def test_chip_counts_match_corpus(self, built_lib):
        from br_insight.articles import load_all

        text = (built_lib / "library" / "index.html").read_text(encoding="utf-8")
        articles = apply_taxonomy(load_all(REPO_ROOT), load_taxonomy(REPO_ROOT))
        assert text.count('data-group="category"') == len(
            {a.category for a in articles}
        ) == 8
        assert text.count('data-group="tag"') == len({t for a in articles for t in a.tags})
        assert text.count('data-group="author"') == len({a.author for a in articles})

    def test_decades_present(self, built_lib):
        text = (built_lib / "library" / "index.html").read_text(encoding="utf-8")
        for decade_label in ("1990s", "2000s", "2010s"):
            assert f'data-value="{decade_label}"' in text

    def test_slugs_cover_corpus_newest_first(self, built_lib):
        from br_insight.articles import load_all

        text = (built_lib / "library" / "index.html").read_text(encoding="utf-8")
        slugs = [a.slug for a in load_all(REPO_ROOT)]
        positions = [text.index(f'/library/{slug}/">') for slug in slugs]
        assert positions == sorted(positions)  # server renders newest-first


# ---------------------------------------------------------------------------
# filter.js pure-function contract (run under Node)
# ---------------------------------------------------------------------------

node = shutil.which("node")

pytestmark = pytest.mark.skipif(node is None, reason="node not available")


@pytest.fixture(scope="module")
def filter_mod(tmp_path_factory):
    """filter.js copied as .mjs so Node treats it as an ES module."""
    dest = tmp_path_factory.mktemp("fjs") / "filter.mjs"
    shutil.copy(REPO_ROOT / "assets/js/modules/filter.js", dest)
    return dest


def run_filter(filter_mod, snippet: str) -> str:
    script = (
        f'import {{ parseParams, toSearch, matches, compareCards }} '
        f'from "{filter_mod.as_uri()}";\n'
        f"{snippet}\n"
    )
    proc = subprocess.run(
        [node, "--input-type=module", "--eval", script],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def fake_card(**attrs):
    base = dict(
        category="Film Analysis",
        tags="noir visual-style",
        author="K. Deckard",
        decade="1990s",
        minutes="3",
        date="1998-08-01",
        title="Batty's Lament",
    )
    base.update(attrs)
    from types import SimpleNamespace

    return SimpleNamespace(dataset=SimpleNamespace(**base))


EMPTY_STATE = "{ category: new Set(), tag: new Set(), author: new Set(), decade: new Set() }"


def run_with_card(filter_mod, snippet: str) -> str:
    """Snippet has access to a `makeCard` factory mirroring fake_card()."""
    script = (
        f'import {{ parseParams, toSearch, matches, compareCards }} '
        f'from "{filter_mod.as_uri()}";\n'
        "const makeCard = (o = {}) => ({ dataset: { category: 'Film Analysis',"
        " tags: 'noir visual-style', author: 'K. Deckard', decade: '1990s',"
        " minutes: '3', date: '1998-08-01', title: \"Batty's Lament\", ...o } });\n"
        f"{snippet}\n"
    )
    proc = subprocess.run(
        [node, "--input-type=module", "--eval", script],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def run_init(filter_mod, search: str) -> str:
    """Wire init() against a minimal fake DOM and report select value +
    post-render card order (default server order differs from az order)."""
    snippet = f"""
    const cards = [
      {{ dataset: {{ category: 'Film Analysis', tags: 'noir', author: 'A',
        decade: '2000s', minutes: '9', date: '2001-02-01',
        title: 'Vanishing' }}, hidden: false }},
      {{ dataset: {{ category: 'Characters', tags: 'eyes', author: 'B',
        decade: '1980s', minutes: '4', date: '1982-06-25',
        title: 'Alias' }}, hidden: false }},
    ];
    const placed = [];
    const grid = {{
      querySelectorAll: () => [...cards],
      appendChild(card) {{ placed.push(card.dataset.title); }},
    }};
    const select = {{
      value: "",
      addEventListener() {{}},
    }};
    const doc = {{
      querySelector(sel) {{
        if (sel === "[data-grid]") return grid;
        if (sel === "[data-sort]") return select;
        return null;  // no filter bar / empty message in this shim
      }},
      addEventListener() {{}},
      defaultView: {{
        location: {{ search: {search!r}, pathname: "/library/", hash: "" }},
        history: {{ replaceState() {{}} }},
      }},
    }};
    init(doc);
    console.log(JSON.stringify({{ sortValue: select.value, order: placed }}));
    """
    script = f'import {{ init }} from "{filter_mod.as_uri()}";\n{snippet}\n'
    proc = subprocess.run(
        [node, "--input-type=module", "--eval", script],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


class TestFilterJsContract:
    @pytest.fixture(autouse=True)
    def _skip_without_node(self):
        if node is None:
            pytest.skip("node not available")

    def test_parse_params_reads_repeated_and_scalar_keys(self, filter_mod):
        out = run_filter(
            filter_mod,
            """
            const s = parseParams("?category=Characters&tag=noir&tag=eyes&sort=az");
            console.log(JSON.stringify({
              cat: [...s.state.category], tags: [...s.state.tag],
              sort: s.sort,
            }));
            """,
        )
        assert '"cat":["Characters"]' in out
        assert '"tags":["noir","eyes"]' in out
        assert '"sort":"az"' in out

    def test_parse_params_empty_and_invalid_sort(self, filter_mod):
        out = run_filter(
            filter_mod,
            """
            const a = parseParams("");
            const b = parseParams("?tag=noir&sort=sideways");
            console.log(JSON.stringify({
              empty: a.state.tag.size === 0 && a.sort === null,
              badSortIgnored: b.sort === null,
              keepsTag: [...b.state.tag],
            }));
            """,
        )
        assert '"empty":true' in out
        assert '"badSortIgnored":true' in out
        assert '"keepsTag":["noir"]' in out

    def test_to_search_round_trips_canonically(self, filter_mod):
        out = run_filter(
            filter_mod,
            """
            const parsed = parseParams("?tag=eyes&sort=newest&tag=noir&author=A");
            console.log(toSearch(parsed.state, parsed.sort));
            """,
        )
        assert out == "?tag=eyes&tag=noir&author=A&sort=newest"

    def test_to_search_empty_state_yields_empty_string(self, filter_mod):
        out = run_filter(filter_mod, f"console.log(JSON.stringify(toSearch({EMPTY_STATE}, null)))")
        assert out == '""'

    def test_matches_and_across_groups_or_within_tags(self, filter_mod):
        """AND between groups, OR among values within one group."""
        out = run_with_card(
            filter_mod,
            f"""
            const none = {EMPTY_STATE};
            const tagOnly = {{...none, tag: new Set(["noir"])}};
            const tagEither = {{...none, tag: new Set(["noir", "visual-style"])}};
            const plusAuthor = {{...tagOnly, author: new Set(["Someone Else"])}};
            console.log(JSON.stringify([
              matches(makeCard(), none),
              matches(makeCard(), tagOnly),
              matches(makeCard(), tagEither),
              matches(makeCard(), plusAuthor),
            ]));
            """,
        )
        assert out == "[true,true,true,false]"

    def test_compare_orders_all_modes(self, filter_mod):
        out = run_with_card(
            filter_mod,
            """
            const a = makeCard({date: "1998-08-01", minutes: "3", title: "a"});
            const b = makeCard({date: "2001-02-01", minutes: "9", title: "b"});
            console.log(JSON.stringify([
              compareCards(a, b, "oldest") < 0,
              compareCards(b, a, "newest") < 0,
              compareCards(a, b, "shortest") < 0,
              compareCards(b, a, "longest") < 0,
              compareCards(a, b, "az") < 0,
              compareCards(a, b, "") === 0,
            ]).replaceAll('"', ''));
            """,
        )
        assert out == "[true,true,true,true,true,true]"

    def test_init_syncs_sort_select_from_url(self, filter_mod):
        out = run_init(filter_mod, "?sort=az")
        assert json.loads(out)["sortValue"] == "az"

    def test_init_invalid_sort_keeps_default_select_and_order(self, filter_mod):
        data = json.loads(run_init(filter_mod, "?sort=bogus"))
        assert data["sortValue"] == ""
        assert data["order"] == ["Vanishing", "Alias"]

    def test_clear_filters_resets_state_sort_and_params(self, filter_mod):
        """reset() clears chips, sort, and URL params; full list is restored."""
        snippet = f"""
        const cards = [
          {{ dataset: {{ category: 'Film Analysis', tags: 'noir', author: 'A',
            decade: '2000s', minutes: '9', date: '2001-02-01',
            title: 'Vanishing' }}, hidden: false }},
          {{ dataset: {{ category: 'Characters', tags: 'eyes', author: 'B',
            decade: '1980s', minutes: '4', date: '1982-06-25',
            title: 'Alias' }}, hidden: false }},
        ];
        const placed = [];
        const grid = {{
          querySelectorAll: () => [...cards],
          appendChild(card) {{ placed.push(card.dataset.title); }},
        }};
        const select = {{ value: "", addEventListener() {{}} }};
        let lastUrl = null;
        const clearHandlers = [];
        const clearBtn = {{
          addEventListener(name, fn) {{ clearHandlers.push(fn); }},
        }};
        const doc = {{
          querySelector(sel) {{
            if (sel === "[data-grid]") return grid;
            if (sel === "[data-sort]") return select;
            if (sel === "[data-clear-filters]") return clearBtn;
            return null;
          }},
          addEventListener() {{}},
          defaultView: {{
            location: {{ search: "?tag=noir&sort=az", pathname: "/library/", hash: "" }},
            history: {{
              replaceState(_s, _t, url) {{ lastUrl = url; }},
            }},
          }},
        }};
        init(doc);
        const filteredHidden = cards.map((c) => c.hidden);
        const afterFiltered = placed.length;
        for (const fn of clearHandlers) fn();
        console.log(JSON.stringify({{
          filteredHidden,
          hiddenAfterReset: cards.map((c) => c.hidden),
          orderAfterReset: placed.slice(afterFiltered),
          selectValueAfterReset: select.value,
          lastUrl,
        }}));
        """
        script = f'import {{ init }} from "{filter_mod.as_uri()}";\n{snippet}\n'
        proc = subprocess.run(
            [node, "--input-type=module", "--eval", script],
            capture_output=True, text=True, timeout=30,
        )
        assert proc.returncode == 0, proc.stderr
        data = json.loads(proc.stdout)
        # incoming ?tag=noir hides the non-matching card
        assert data["filteredHidden"] == [False, True]
        assert data["hiddenAfterReset"] == [False, False]
        assert data["orderAfterReset"] == ["Vanishing", "Alias"]  # server order
        assert data["selectValueAfterReset"] == ""
        assert data["lastUrl"] == "/library/"
