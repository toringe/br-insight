"""Task 15 search: build-time index contract (src/br_insight/search.py),
overlay markup anatomy in base.html, and pure JS helpers of the search
module (run under Node, following the established subprocess harness)."""

import gzip
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from br_insight.config import apply_taxonomy, load_taxonomy
from br_insight.articles import load_all
from br_insight.render import REPO_ROOT


@pytest.fixture(scope="module")
def articles():
    return apply_taxonomy(load_all(REPO_ROOT), load_taxonomy(REPO_ROOT))


# ---------------------------------------------------------------------------
# Python side: index records + writer
# ---------------------------------------------------------------------------


class TestBuildIndex:
    FIELDS = {"slug", "url", "title", "author", "date", "category", "tags",
              "summary", "body"}

    def test_one_record_per_article(self, articles):
        from br_insight.search import build_index

        records = build_index(articles)
        assert len(records) == len(articles) == 29

    def test_record_fields_complete(self, articles):
        from br_insight.search import build_index

        for record in build_index(articles):
            assert set(record) == self.FIELDS
            assert record["url"] == f"/library/{record['slug']}/"
            assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", record["date"])
            assert record["title"] and record["author"] and record["category"]
            assert isinstance(record["tags"], list)
            assert record["tags"]
            assert record["summary"]
            # body carries real prose: several hundred words per essay
            assert len(record["body"].split()) > 100

    def test_fields_are_plain_text_no_markup(self, articles):
        from br_insight.search import build_index

        tag = re.compile(r"<[a-zA-Z/][^>]*>")
        for record in build_index(articles):
            for key in ("title", "author", "category", "summary", "body"):
                assert not tag.search(record[key]), (key, record[key][:80])
                assert "\n" not in record[key]

    def test_body_text_contains_article_prose(self, articles):
        from br_insight.search import build_index

        record = next(
            r for r in build_index(articles) if r["slug"] == "postmodernist-view"
        )
        assert "Postmodern" in record["body"]


class TestWriteIndex:
    def test_writes_loadable_compact_json(self, tmp_path, articles):
        from br_insight.search import build_index, write_index

        target = write_index(tmp_path, articles)
        assert target == tmp_path / "assets" / "js" / "search-index.json"
        assert target.is_file()
        loaded = json.loads(target.read_bytes())
        assert loaded == build_index(articles)

    def test_escapes_survive_round_trip(self, tmp_path):
        # synthetic corpus quoting troublesome characters end-to-end
        import datetime

        from br_insight.articles import Article
        from br_insight.search import write_index

        hostile = Article(
            slug="quotes",
            title='He said "rain" & <miles>',
            author="O'Neill–Mori",
            cover="cover.jpg",
            cover_artist=None,
            date=datetime.datetime(2019, 6, 21),
            words=10,
            minutes=1,
            summary="A “quoted” summary…",
            copyright=None,
            source=None,
            category="Characters",
            tags=["V-K"],
            html="<h2 id=\"a\">Head</h2><p>Ce n'est qu'un adieu.</p>",
        )
        target = write_index(tmp_path, [hostile])
        record = json.loads(target.read_text(encoding="utf-8"))[0]
        assert record["title"] == 'He said "rain" & <miles>'
        assert record["summary"] == "A “quoted” summary…"
        assert record["body"] == "Head Ce n'est qu'un adieu."


class TestBudget:
    BUDGET_GZ = 200 * 1024

    def test_real_corpus_within_budget(self, tmp_path, articles):
        from br_insight.search import write_index

        target = write_index(tmp_path, articles)
        measured = len(gzip.compress(target.read_bytes(), compresslevel=9))
        assert measured <= self.BUDGET_GZ, f"{measured} B gz"


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    from br_insight.render import build

    out = tmp_path_factory.mktemp("search_build")
    build(REPO_ROOT, out)
    return out


class TestBuildIntegration:

    def test_build_emits_the_index(self, built):
        target = built / "assets" / "js" / "search-index.json"
        assert target.is_file()
        records = json.loads(target.read_bytes())
        assert len(records) == 29

    def test_real_index_passes_its_budget(self, built):
        """The emitted index passes a checks.audit run scoped to itself."""
        import gzip

        from br_insight.checks import BUDGET_SEARCH_GZ

        blob = (built / "assets" / "js" / "search-index.json").read_bytes()
        measured = len(gzip.compress(blob, compresslevel=9))
        assert measured <= BUDGET_SEARCH_GZ


# ---------------------------------------------------------------------------
# Template anatomy: overlay skeleton in base.html
# ---------------------------------------------------------------------------


class TestOverlayMarkup:
    @pytest.fixture
    def html(self):
        from br_insight.config import SiteConfig
        from br_insight.render import render_template

        return render_template("base.html", site=SiteConfig.load(REPO_ROOT))

    def test_dialog_skeleton_present_once(self, html):
        assert html.count("<dialog") == 1
        assert 'id="search-dialog"' in html
        assert "data-search-dialog" in html
        assert 'aria-labelledby="search-title"' in html
        assert 'data-search-input' in html
        assert 'data-search-close' in html
        assert 'data-search-results' in html
        assert 'data-search-hint' in html

    def test_header_button_targets_the_dialog(self, html):
        header_at = html.index('aria-controls="search-dialog"')
        assert '<dialog' in html[header_at:]

    def test_noscript_fallback_points_to_library(self, html):
        noscript = re.search(r"<noscript>(.*?)</noscript>", html, re.S)
        assert noscript, "noscript fallback missing"
        assert "/library/" in noscript.group(1)

    def test_dialog_starts_closed(self, html):
        opening = re.search(r"<dialog[^>]*>", html).group(0)
        assert "open" not in opening.split()


# ---------------------------------------------------------------------------
# Node harness: pure JS helpers
# ---------------------------------------------------------------------------

node = shutil.which("node")


def _run(script):
    proc = subprocess.run(
        [node, "--input-type=module", "--eval", script],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


@pytest.fixture(scope="module")
def search_uri(tmp_path_factory):
    dest = tmp_path_factory.mktemp("search-js") / "search.mjs"
    shutil.copy(REPO_ROOT / "assets/js/modules/search.js", dest)
    return dest.as_uri()


@pytest.fixture(scope="module")
def minisearch_uri(tmp_path_factory):
    dest = tmp_path_factory.mktemp("minisearch") / "minisearch.mjs"
    shutil.copy(
        REPO_ROOT / "assets/js/vendor/minisearch.esm.min.js", dest
    )
    return dest.as_uri()


FAKE_DOC = """
const doc = {
  activeElement: null,
  createElement(tag) {
    const el = { tagName: tag.toUpperCase(), children: [],
      appendChild(child) { this.children.push(child); },
      get textContent() {
        return el.children.map((c) =>
          typeof c === 'string' ? c : c.textContent).join('');
      } };
    return el;
  },
  createTextNode(t) { return t; },
};
"""


def _skip_no_node(cls):
    return pytest.mark.skipif(node is None, reason="node not available")(cls)


@_skip_no_node
class TestHighlightJs:
    def test_segments_split_on_terms_case_insensitive(self, search_uri):
        out = _run(
            f'import {{ highlightSegments }} from "{search_uri}";\n'
            + FAKE_DOC +
            "console.log(JSON.stringify(highlightSegments("
            "'More human than human', ['human'])));\n"
        )
        segments = json.loads(out)
        assert [(s["text"], s["hit"]) for s in segments] == [
            ("More ", False), ("human", True), (" than ", False), ("human", True)
        ]

    def test_empty_query_returns_whole_text(self, search_uri):
        out = _run(
            f'import {{ highlightSegments }} from "{search_uri}";\n'
            "console.log(JSON.stringify(highlightSegments('plain text', [])));\n"
        )
        assert [(s["text"], s["hit"]) for s in json.loads(out)] == [
            ("plain text", False)
        ]

    def test_highlight_builds_dom_without_inner_html(self, search_uri):
        # hostile payload must land as inert text nodes, never markup
        out = _run(
            f'import {{ highlightInto }} from "{search_uri}";\n'
            + FAKE_DOC +
            "const p = doc.createElement('p');\n"
            "highlightInto(p, '<img src=x onerror=alert(1)> human?',"
            " ['human'], doc);\n"
            "console.log(JSON.stringify([p.innerHTMLUsed === undefined,"
            " p.textContent]));\n"
        )
        safe, text = json.loads(out)
        assert safe
        assert text == "<img src=x onerror=alert(1)> human?"


@_skip_no_node
class TestResultRendering:
    def test_result_element_is_anchor_with_plain_text(self, search_uri):
        out = _run(
            f'import {{ buildResult }} from "{search_uri}";\n'
            + FAKE_DOC +
            "const rec = { slug: 'x', url: '/library/x/', title:"
            " 'The <Rain> Protocol', author: 'Tyrell', date: '1992-01-01',"
            " category: 'Plot', tags: ['replicants'], summary:"
            " 'Detective work &amp; despair.' };\n"
            "const li = buildResult(rec, ['rain'], doc);\n"
            "const a = li.children.find((c) => c.tagName === 'A');\n"
            "console.log(JSON.stringify([a.href,"
            " a.textContent.includes('<Rain>'), !li.htmlUsed,"
            " li.textContent.startsWith('The <Rain> Protocol')]));\n"
        )
        href, escaped, no_innerhtml, titled = json.loads(out)
        assert href == "/library/x/"
        assert escaped and no_innerhtml and titled


INTERACTION_HARNESS = FAKE_DOC + """
function fakeDialog() {
  const events = {};
  return { tagName: 'DIALOG', open: false, showModalCount: 0, listeners: events,
    addEventListener(type, fn) { (events[type] ??= []).push(fn); },
    fire(type, evt) { for (const fn of events[type] ?? []) fn(evt); },
    showModal() { this.showModalCount++; this.open = true; },
    close() { if (!this.open) return; this.open = false;
      for (const fn of events.close ?? []) fn(); } };
}
function buildHarness(opts = {}) {
  const invoker = { focused: 0, focus() { this.focused++; } };
  const dialog = fakeDialog();
  dialog.showModalSupported = opts.dialogSupport !== false;
  if (!dialog.showModalSupported) delete dialog.showModal;
  const input = { focused: 0, value: opts.inputValue || '',
    focus() { this.focused++; rootDoc.activeElement = this; } };
  const list = { children: [],
    appendChild(child) { this.children.push(child); },
    removeChild(child) { this.children.splice(this.children.indexOf(child), 1); },
    get firstChild() { return this.children[0] ?? null; },
    querySelectorAll() { return []; } };
  const opener = { handlers: [],
    addEventListener(type, fn) { this.handlers.push(fn); },
    click() { for (const fn of this.handlers) fn(); },
    closest(sel) { return sel === '[data-search-open]' ? invoker : null; } };
  const elements = {
    '[data-search-dialog]': dialog,
    '[data-search-input]': input,
    '[data-search-results]': list,
    '[data-search-hint]': { hidden: true, textContent: '' },
    '[data-search-empty]': { hidden: true },
    '[data-search-close]': { clicks: [] },
  };
  for (const el of Object.values(elements)) {
    if (!el.querySelector) el.querySelector = (sel) => elements[sel] ?? null;
    if (!el.addEventListener) {
      const bus = {};
      el.addEventListener = (type, fn) => (bus[type] ??= []).push(fn);
      el.fire = (type, evt) => {
        for (const fn of bus[type] ?? []) fn(evt); };
    }
  }
  const rootDoc = {
    ...doc,
    activeElement: null,
    querySelector(sel) { return elements[sel] ?? null; },
    querySelectorAll(sel) { return sel === '[data-search-open]' ? [opener] : []; },
  };
  const docApi = { ...rootDoc };
  return { doc: docApi, dialog, input, opener, list, invoker,
    get hint() { return elements['[data-search-hint]']; } };
}
"""


@_skip_no_node
class TestSearchInteraction:
    def test_init_inert_without_dialog_support(self, search_uri):
        out = _run(
            f'import {{ init }} from "{search_uri}";\n'
            + INTERACTION_HARNESS +
            "const h = buildHarness({ dialogSupport: false });\n"
            "console.log(JSON.stringify(init(h.doc)));\n"
        )
        assert json.loads(out) is None

    def test_open_is_lazy_then_cached_and_restores_focus(self, search_uri):
        out = _run(
            f'import {{ init }} from "{search_uri}";\n'
            + INTERACTION_HARNESS +
            "const h = buildHarness({ dialogSupport: true });\n"
            "let loads = 0;\n"
            "const record = { slug: 'x', url: '/library/x/', title:"
            " 'Rain Protocol', author: 'A', date: '1992-01-01', category: 'C',"
            " summary: 's' };\n"
            "const fakeEngine = { search() { return [{ id: 'x',"
            " terms: ['rain'], score: 1 }]; } };\n"
            "const loader = () => ++loads && Promise.resolve("
            "{ records: [record], engine: fakeEngine });\n"
            "const api = init(h.doc, { engineLoader: loader });\n"
            "if (loads !== 0) throw new Error('engine loaded before first open');\n"
            "h.opener.click();\n"  # open() settles through microtasks below
            "await null; await null; await null; await null;\n"
            "console.log(JSON.stringify([loads, h.dialog.showModalCount,"
            " h.input.focused > 0, h.invoker.focused === 0,"
            " h.list.children.length, h.hint.textContent]));\n"
            # close hands focus back to the invoker
            "api.close();\n"
            "console.log(JSON.stringify([h.dialog.open, h.invoker.focused]));\n"
            # second open reuses the cached engine — loader must not rerun;
            # the pending query then renders through buildResult
            "h.input.value = 'rain';\n"
            "h.opener.click();\n"
            "await null; await null; await null; await null;\n"
            "const anchor = h.list.children[0].children[0];\n"
            "console.log(JSON.stringify([loads, h.dialog.open,"
            " h.list.children.length, anchor.href,"
            " h.hint.hidden]));\n"
        )
        first, closed_again, reopened = (
            json.loads(line) for line in out.splitlines()
        )
        assert first == [1, 1, True, True, 0, "Search 1 essays…"]
        assert closed_again == [False, 1]
        assert reopened == [1, True, 1, "/library/x/", True]


@_skip_no_node
class TestEngineEndToEnd:
    def test_vendor_minisearch_is_importable_and_ranks(self, minisearch_uri):
        out = _run(
            f'import MiniSearch from "{minisearch_uri}";\n'
            "const docs = [\n"
            "  { slug: 'a', title: 'Neon Rain', author: 'Ford', tags: ['weather'],"
            " category: 'Setting', summary: 'city rain', body: 'rain rain' },\n"
            "  { slug: 'b', title: 'C-beams glitter', author: 'Roy', tags: [],"
            " category: 'Speech', summary: 'attack ships on fire off the shoulder',"
            " body: 'orion' }\n"
            "];\n"
            "const engine = new MiniSearch({ idField: 'slug',"
            " fields: ['title','author','tags',"
            "'category','summary','body'], storeFields: ['slug'] });\n"
            "engine.addAll(docs);\n"
            "const hits = engine.search('rain', { prefix: true, fuzzy: 0.2 });\n"
            "console.log(JSON.stringify([hits.length, hits[0].id]));\n"
        )
        count, top = json.loads(out)
        assert count == 1 and top == "a"

    def test_arrow_keys_walk_results(self, search_uri):
        out = _run(
            f'import {{ init }} from "{search_uri}";\n'
            + INTERACTION_HARNESS +
            "const h = buildHarness({ dialogSupport: true });\n"
            "init(h.doc, { engineLoader: () => Promise.resolve({ records: [],"
            " engine: { search() { return []; } } }) });\n"
            "const links = [{ focused: 0, focus() { this.focused++;"
            " h.doc.activeElement = this; } },\n"
            "  { focused: 0, focus() { this.focused++;"
            " h.doc.activeElement = this; } },\n"
            "  { focused: 0, focus() { this.focused++;"
            " h.doc.activeElement = this; } }];\n"
            "h.list.querySelectorAll = () => links;\n"
            "const key = (k) =>"
            " h.dialog.fire('keydown', { key: k, preventDefault() {} });\n"
            "key('ArrowDown'); key('ArrowDown'); key('ArrowDown');\n"  # wraps to 0
            "key('ArrowUp'); // wraps back to the last link\n"
            "console.log(JSON.stringify(links.map((l) => l.focused)));\n"
        )
        assert json.loads(out) == [1, 2, 1]
