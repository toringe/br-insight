"""Tests for the Task 9 library page: template anatomy, facet computation,
build integration, and the client-side filter.js contract."""

import datetime
import json
import re
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


class TestLibraryFacets:
    """Per-chip counts for the filter toolbar (group → value → int)."""

    def test_counts_match_corpus(self):
        from br_insight.articles import load_all
        from br_insight.render import facets, library_facets

        articles = apply_taxonomy(load_all(REPO_ROOT), load_taxonomy(REPO_ROOT))
        counts = library_facets(articles)

        assert set(counts) == {"category", "tag", "author", "decade"}
        # Known values verified against the 29-essay corpus (28 authors).
        assert counts["tag"]["noir"] == 3
        assert sum(counts["decade"].values()) == 29
        assert len(counts["author"]) == 28 == len({a.author for a in articles})
        # Same vocabularies as facets(); multi-tag articles count once per tag.
        vocab = facets(articles)
        for group, key in (
            ("categories", "category"),
            ("tags", "tag"),
            ("authors", "author"),
            ("decades", "decade"),
        ):
            assert set(counts[key]) == set(vocab[group])
            assert all(n >= 1 for n in counts[key].values())

    def test_helper_is_pure(self):
        from br_insight.render import library_facets

        articles = [
            _ns_article(),
            _ns_article(slug="second-one", title="Second One",
                        category="Characters", tags=["eyes"]),
        ]
        snapshot = [(a.slug, list(a.tags), a.category) for a in articles]

        first = library_facets(articles)
        second = library_facets(articles)

        assert first == second
        assert first["category"] == {"Film Analysis": 1, "Characters": 1}
        assert first["tag"] == {"noir": 1, "empathy": 1, "eyes": 1}
        assert first["author"] == {"K. Deckard": 2}
        assert first["decade"] == {"2020s": 2}
        assert [(a.slug, list(a.tags), a.category) for a in articles] == snapshot


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
    chip_counts={
        "category": {"Film Analysis": 2},
        "tag": {"empathy": 2, "noir": 2},
        "author": {"K. Deckard": 2},
        "decade": {"2020s": 2},
    },
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
        assert re.search(r'href="\.\./assets/css/main\.min\.css(\?v=[0-9a-f]{8})?"', html)
        assert '../library/voight-kampff-test/cover-crop.jpg"' in html

    def test_filter_toolbar_contract(self, html):
        assert 'class="filterbar" data-filter-bar aria-label="Filter articles"' in html
        assert 'filterbar__toolbar' in html
        assert 'filterbar__details' in html and 'filterbar__toggle' in html
        assert '<span class="filterbar__badge" data-filter-badge hidden>0</span>' in html
        assert '<span class="filterbar__pills" data-pills aria-label="Active filters"></span>' in html
        for label in ("Category", "Tag", "Decade", "Author"):
            assert f">{label}</p>" in html
        for group in ("category", "tag", "decade", "author"):
            assert f'data-group="{group}"' in html

    def test_panel_chips_are_compact_with_counts(self, html):
        """Chips carry the sm variant + per-chip corpus count (5 chips here)."""
        assert html.count('class="chip chip--sm"') == 5
        assert html.count('aria-pressed="false"') >= 5
        assert html.count("data-count=") == 5
        # visible count text beside the label
        assert ">2</span>" in html

    def test_tag_and_author_lists_scroll_capped(self, html):
        assert 'filterbar__chips filterbar__chips--scroll' in html

    def test_sort_control_options(self, html):
        assert '<select name="sort" id="library-sort" data-sort>' in html
        for value in ("oldest", "longest", "shortest", "az"):
            assert f'value="{value}"' in html
        assert 'value="newest"' not in html  # duplicate "Newest first" dropped
        assert html.count("Newest first") == 1

    def test_toolbar_clear_hidden_initially(self, html):
        assert ('<button type="button" class="btn btn--ghost btn--sm" '
                'data-clear-filters hidden>Clear</button>') in html

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


def run_dom(filter_mod, search: str, fire: str = "") -> str:
    """Wire init() against a fuller shim — toolbar, details, chips, pills,
    badge, clear button — optionally run ``fire`` interactions, then report
    the observable aftermath as JSON."""
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

    const makeEl = () => ({{
      attrs: {{}}, dataset: {{}}, children: [], textContent: "",
      setAttribute(k, v) {{ this.attrs[k] = String(v); }},
      getAttribute(k) {{ return this.attrs[k] ?? null; }},
      appendChild(c) {{ this.children.push(c); return c; }},
      closest() {{ return null; }},
      addEventListener() {{}},
    }});
    const makeContainer = () => {{
      const el = makeEl();
      Object.defineProperty(el, "textContent", {{
        set() {{ el.children.length = 0; }},
        get() {{ return ""; }},
      }});
      return el;
    }};

    const chips = ["tag|noir", "tag|eyes", "category|Characters"].map((pair) => {{
      const [group, value] = pair.split("|");
      const chip = makeEl();
      chip.dataset.group = group;
      chip.dataset.value = value;
      return chip;
    }});
    const barHandlers = {{}};
    const details = {{ open: false }};
    const bar = {{
      querySelector(sel) {{ return sel === "details" ? details : null; }},
      querySelectorAll(sel) {{
        return sel === "button[data-group]" ? [...chips] : [];
      }},
      addEventListener(name, fn) {{ (barHandlers[name] ||= []).push(fn); }},
    }};
    const badge = {{ hidden: true, textContent: "" }};
    const pillHandlers = {{}};
    const pills = makeContainer();
    pills.addEventListener = (name, fn) => {{ (pillHandlers[name] ||= []).push(fn); }};
    const select = {{ value: "", addEventListener() {{}} }};
    const clearHandlers = [];
    const clearBtn = {{
      hidden: true,
      addEventListener(name, fn) {{ clearHandlers.push(fn); }},
    }};
    let lastUrl = null;
    const doc = {{
      querySelector(sel) {{
        if (sel === "[data-grid]") return grid;
        if (sel === "[data-filter-bar]") return bar;
        if (sel === "[data-pills]") return pills;
        if (sel === "[data-filter-badge]") return badge;
        if (sel === "[data-sort]") return select;
        if (sel === "[data-clear-filters]") return clearBtn;
        return null;  // no empty-message shim needed here
      }},
      addEventListener() {{}},
      createElement(tag) {{
        const el = makeEl();
        el.tagName = String(tag).toUpperCase();
        return el;
      }},
      defaultView: {{
        location: {{ search: {search!r}, pathname: "/library/", hash: "" }},
        history: {{ replaceState(_s, _t, url) {{ lastUrl = url; }} }},
      }},
    }};

    init(doc);
    {fire}
    console.log(JSON.stringify({{
      detailsOpen: details.open,
      badgeText: badge.textContent,
      badgeHidden: badge.hidden,
      clearHidden: clearBtn.hidden,
      pillCount: pills.children.length,
      pillLabels: pills.children.map((p) =>
        (p.children[0] && p.children[0].textContent) || ""),
      chipPressed: chips.map((c) => c.attrs["aria-pressed"]),
      hidden: cards.map((c) => c.hidden),
      lastUrl,
    }}));
    """
    script = f'import {{ init }} from "{filter_mod.as_uri()}";\n{snippet}\n'
    proc = subprocess.run(
        [node, "--input-type=module", "--eval", script],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


class TestFilterToolbarBehavior:
    """Toolbar behavior: pills, badge, auto-open, clear (full-DOM shim)."""

    @pytest.fixture(autouse=True)
    def _skip_without_node(self):
        if node is None:
            pytest.skip("node not available")

    def test_no_deep_link_leaves_zero_state(self, filter_mod):
        data = json.loads(run_dom(filter_mod, ""))
        assert data["detailsOpen"] is False
        assert data["badgeText"] == "0" and data["badgeHidden"] is True
        assert data["pillCount"] == 0
        assert data["clearHidden"] is True
        assert data["lastUrl"] == "/library/"

    def test_deep_link_auto_opens_panel_with_pills_and_badge(self, filter_mod):
        data = json.loads(run_dom(filter_mod, "?tag=noir&category=Characters"))
        assert data["detailsOpen"] is True
        assert data["badgeText"] == "2" and data["badgeHidden"] is False
        assert data["pillCount"] == 2
        assert data["pillLabels"] == ["Characters", "noir"]  # GROUPS order
        assert data["chipPressed"] == ["true", "false", "true"]
        # AND across groups: no card is both Characters and tagged noir
        assert data["hidden"] == [True, True]

    def test_pill_remove_drops_filter_and_syncs_url(self, filter_mod):
        fire = """
        const pill = pills.children[0];
        const removeBtn = pill.children[1];
        removeBtn.closest = (sel) =>
          sel === "button" ? removeBtn : (sel === "[data-group]" ? pill : null);
        for (const fn of pillHandlers.click ?? []) {
          fn({ target: removeBtn, preventDefault() {} });
        }
        """
        data = json.loads(run_dom(filter_mod, "?tag=noir&sort=az", fire))
        assert data["pillCount"] == 0
        assert data["badgeText"] == "0" and data["badgeHidden"] is True
        assert data["clearHidden"] is True
        assert data["chipPressed"] == ["false", "false", "false"]
        assert data["hidden"] == [False, False]  # full list restored
        assert data["lastUrl"] == "/library/?sort=az"  # sort preserved

    def test_clear_restores_zero_state(self, filter_mod):
        data = json.loads(run_dom(filter_mod, "?tag=noir", "for (const fn of clearHandlers) fn();"))
        assert data["pillCount"] == 0
        assert data["badgeHidden"] is True
        assert data["clearHidden"] is True
        assert data["chipPressed"] == ["false", "false", "false"]
        assert data["hidden"] == [False, False]
        assert data["lastUrl"] == "/library/"


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

    def _chip_click(self, filter_mod, href: str) -> str:
        """Drive the doc-level click handler with an anchor-like object
        (card-footer chip deep link) and report the aftermath."""
        snippet = f"""
        const cards = [
          {{ dataset: {{ category: 'Film Analysis', tags: 'noir', author: 'A',
            decade: '2000s', minutes: '9', date: '2001-02-01',
            title: 'Vanishing' }}, hidden: false }},
          {{ dataset: {{ category: 'Characters', tags: 'eyes', author: 'B',
            decade: '1980s', minutes: '4', date: '1982-06-25',
            title: 'Alias' }}, hidden: false }},
        ];
        const grid = {{
          querySelectorAll: () => [...cards],
          appendChild() {{}},
        }};
        const handlers = {{}};
        let lastUrl = null;
        const doc = {{
          querySelector(sel) {{ return sel === "[data-grid]" ? grid : null; }},
          addEventListener(name, fn) {{ (handlers[name] ||= []).push(fn); }},
          baseURI: "http://localhost:8611/library/",
          defaultView: {{
            location: {{ search: "", pathname: "/library/", hash: "",
                         origin: "http://localhost:8611" }},
            history: {{ replaceState(_s, _t, url) {{ lastUrl = url; }} }},
          }},
        }};
        init(doc);
        const urlAfterInit = lastUrl;
        const anchor = {{ href: {href!r}, dataset: {{ link: "tag" }} }};
        anchor.closest = (sel) => (sel === "[data-link]" ? anchor : null);
        let prevented = false;
        for (const fn of handlers.click ?? []) {{
          fn({{ target: anchor, preventDefault() {{ prevented = true; }} }});
        }}
        console.log(JSON.stringify({{
          hidden: cards.map((c) => c.hidden),
          urlChanged: lastUrl !== urlAfterInit,
          prevented,
        }}));
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

    def test_card_chip_click_toggles_filter_from_anchor_href(self, filter_mod):
        """Task 17 I-1 regression: card-chip anchors expose no searchParams;
        the handler must parse link.href as a URL and apply the filter."""
        out = self._chip_click(filter_mod, "http://localhost:8611/library/?tag=eyes")
        data = json.loads(out)
        assert data["hidden"] == [True, False]  # Alias matches eyes
        assert data["urlChanged"] is True
        assert data["prevented"] is True

    def test_card_chip_click_ignores_cross_origin_and_non_http(self, filter_mod):
        """Native navigation continues for off-site or non-http(s) hrefs."""
        for href in ("http://evil.example/library/?tag=eyes", "mailto:x@y.z"):
            out = self._chip_click(filter_mod, href)
            data = json.loads(out)
            assert data["prevented"] is False
            assert data["hidden"] == [False, False]
            assert data["urlChanged"] is False
