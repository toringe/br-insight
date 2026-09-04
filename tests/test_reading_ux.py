"""Task 12 reading-UX modules: template anatomy, build integration, and the
pure-helper contracts of progress/toc/memory/shortcuts (run under Node,
following the subprocess harness established in test_library.py)."""

import datetime
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from br_insight.render import REPO_ROOT


# ---------------------------------------------------------------------------
# Template-level: global chrome wiring (base.html + header partial)
# ---------------------------------------------------------------------------


class TestBaseAnatomy:
    @pytest.fixture
    def html(self):
        from br_insight.config import SiteConfig
        from br_insight.render import render_template

        return render_template("base.html", site=SiteConfig.load(REPO_ROOT))

    def test_progress_bar_exposes_aria_semantics(self, html):
        snippet_start = html.index('class="progress"')
        snippet = html[snippet_start:snippet_start + 220]
        assert 'role="progressbar"' in snippet
        assert 'aria-valuemin="0"' in snippet
        assert 'aria-valuemax="100"' in snippet
        assert 'aria-valuenow="0"' in snippet
        assert 'aria-label="Reading progress"' in snippet

    def test_back_to_top_button_present_and_hidden(self, html):
        # hidden until JS proves scrollY > threshold; keeps zero-JS pages clean
        assert '<button type="button" class="top-btn" data-top' in html
        assert 'aria-label="Back to top"' in html
        btn_at = html.index("data-top")
        assert "hidden" in html[btn_at:btn_at + 120]

    def test_orchestrator_script_tag(self, html):
        assert re.search(r'<script type="module" src="/assets/js/main\.js(\?v=[0-9a-f]{8})?">', html)


class TestHeaderAnatomy:
    @pytest.fixture
    def html(self):
        from br_insight.config import SiteConfig
        from br_insight.render import render_template

        return render_template("base.html", site=SiteConfig.load(REPO_ROOT))

    def test_mobile_nav_carries_search_and_atmosphere_actions(self, html):
        """Mobile menu owns search + atmosphere: labeled duplicate actions
        live inside the nav panel (hidden on desktop via CSS)."""
        nav = html.split('<nav class="site-nav"', 1)[1].split("</nav>", 1)[0]
        for sel in ("data-search-open", "data-fx-toggle"):
            btn = re.search(f"<button[^>]*{sel}[^>]*>", nav)
            assert btn, f"nav panel is missing a {sel} action"
            assert "site-nav__action" in btn.group(0)
        fx_nav_btn = re.search(r"<button[^>]*data-fx-toggle[^>]*>", nav).group(0)
        assert "aria-pressed" in fx_nav_btn

    def test_brand_is_real_text_with_red_insight(self, html):
        """Header wordmark is plain Rajdhani text: real 'Blade Runner' words
        (no blAdeBrunner glyph trick) and 'Insight' wrapped in the eyebrow-red
        accent span. Accessible name unchanged."""
        brand = re.search(r'<a class="site-header__brand[^>]*>.*?</a>', html).group(0)
        assert "blAdeBrunner" not in brand
        assert "neon" not in brand
        assert '<span class="site-header__brand-accent">Insight</span>' in brand
        assert 'aria-label="Blade Runner Insight"' in brand
        assert re.search(r">Blade Runner\s+<span", brand)


@pytest.fixture(scope="module")
def home_html(tmp_path_factory):
    from br_insight.render import build

    out = tmp_path_factory.mktemp("ux_build")
    build(REPO_ROOT, out)
    return (out / "index.html").read_text(encoding="utf-8")


class TestHomeEssaySlugs:
    def test_slugs_json_embedded_home_only(self, home_html):
        marker = '<script type="application/json" id="essay-slugs">'
        assert marker in home_html
        blob = home_html.split(marker, 1)[1].split("</script>", 1)[0]
        slugs = json.loads(blob)
        assert len(slugs) == 29
        assert all(isinstance(s, str) and "/" not in s for s in slugs)

    def test_non_home_pages_skip_the_slug_payload(self, tmp_path_factory):
        from br_insight.render import build

        out = tmp_path_factory.mktemp("ux_build2")
        build(REPO_ROOT, out)
        library = (out / "library" / "index.html").read_text(encoding="utf-8")
        article_dir = next(p for p in out.glob("library/*/index.html"))
        assert "essay-slugs" not in library
        assert "essay-slugs" not in article_dir.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Node subprocess harness (same pattern as test_library.py)
# ---------------------------------------------------------------------------

node = shutil.which("node")

pytestmark = pytest.mark.skipif(node is None, reason="node not available")


def _copy_module(tmp_path_factory, name):
    dest = tmp_path_factory.mktemp(f"{name}-js") / f"{name}.mjs"
    shutil.copy(REPO_ROOT / "assets/js/modules" / name, dest)
    return dest.as_uri()


def _run(script):
    proc = subprocess.run(
        [node, "--input-type=module", "--eval", script],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


@pytest.fixture(scope="module")
def memory_uri(tmp_path_factory):
    return _copy_module(tmp_path_factory, "memory.js")


@pytest.fixture(scope="module")
def shortcuts_uri(tmp_path_factory):
    return _copy_module(tmp_path_factory, "shortcuts.js")


@pytest.fixture(scope="module")
def progress_uri(tmp_path_factory):
    return _copy_module(tmp_path_factory, "progress.js")


@pytest.fixture(scope="module")
def toc_uri(tmp_path_factory):
    return _copy_module(tmp_path_factory, "toc.js")


class TestMemoryJs:
    def test_make_key_normalizes_paths(self, memory_uri):
        out = _run(
            f'import {{ makeKey }} from "{memory_uri}";\n'
            "console.log(JSON.stringify([\n"
            "  makeKey('/library/tears-in-rain/'),\n"
            "  makeKey('/library/tears-in-rain'),\n"
            "  makeKey('/library/tarsis/index.html'),\n"
            "  makeKey('/'),\n"
            "]));\n"
        )
        assert out == (
            '["bri:scroll:/library/tears-in-rain",'
            '"bri:scroll:/library/tears-in-rain",'
            '"bri:scroll:/library/tarsis",'
            '"bri:scroll:/"]'
        )

    def test_decode_entry_ttl_logic(self, memory_uri):
        out = _run(
            f'import {{ decodeEntry, encodeEntry, TTL_MS }} from "{memory_uri}";\n'
            "const now = 10_000_000;\n"
            "console.log(JSON.stringify({\n"
            "  fresh: decodeEntry(encodeEntry(420, now), now),\n"
            "  expired: decodeEntry(encodeEntry(420, now - TTL_MS - 1), now),\n"
            "  edgeInTtl: decodeEntry(encodeEntry(9, now - TTL_MS), now),\n"
            "  missing: decodeEntry(null, now),\n"
            "  corrupt: decodeEntry('{y:', now),\n"
            "  badShape: decodeEntry('{\"t\":1}', now),\n"
            "}));\n"
        )
        data = json.loads(out)
        assert data["fresh"] == 420
        assert data["edgeInTtl"] == 9
        assert data["expired"] is None
        assert data["missing"] is None
        assert data["corrupt"] is None
        assert data["badShape"] is None

    def test_should_restore_threshold(self, memory_uri):
        out = _run(
            f'import {{ shouldRestore }} from "{memory_uri}";\n'
            "console.log(JSON.stringify([shouldRestore(5), shouldRestore(50),"
            " shouldRestore(5000), shouldRestore(NaN)]));\n"
        )
        assert out == "[false,false,true,false]"


class TestShortcutsJs:
    def test_routing_table(self, shortcuts_uri):
        out = _run(
            f'import {{ route }} from "{shortcuts_uri}";\n'
            "const p = { tagName: 'P' };\n"
            "console.log(JSON.stringify([\n"
            "  route('k', { ctrl: true }, p),\n"
            "  route('K', { meta: true }, p),\n"
            "  route('k', {}, p),\n"
            "  route('/', {}, p),\n"
            "  route('f', {}, p),\n"
            "  route('t', {}, p),\n"
            "  route('x', {}, p),\n"
            "]));\n"
        )
        assert out == '["search","search",null,"search",null,"top",null]'

    def test_typing_guard_blocks_plain_keys_but_not_cmd_k(self, shortcuts_uri):
        out = _run(
            f'import {{ route }} from "{shortcuts_uri}";\n'
            "for (const sel of [\n"
            "  { tagName: 'INPUT' },\n"
            "  { tagName: 'TEXTAREA' },\n"
            "  { tagName: 'SELECT' },\n"
            "  { tagName: 'DIV', isContentEditable: true },\n"
            "]) {\n"
            "  if (route('/', {}, sel) !== null) throw new Error('leaked / in ' + sel.tagName);\n"
            "  if (route('t', {}, sel) !== null) throw new Error('leaked t in ' + sel.tagName);\n"
            "}\n"
            "console.log(route('k', { ctrl: true }, { tagName: 'INPUT' }));\n"
        )
        assert out == "search"

    def test_modifiers_block_single_letter_shortcuts(self, shortcuts_uri):
        out = _run(
            f'import {{ route }} from "{shortcuts_uri}";\n'
            "const p = { tagName: 'P' };\n"
            "console.log(JSON.stringify([\n"
            "  route('f', { meta: true }, p),\n"
            "  route('f', { ctrl: true }, p),\n"
            "  route('t', { alt: true }, p),\n"
            "  route('t', { shift: true }, p),\n"
            "]));\n"
        )
        assert out == "[null,null,null,\"top\"]"

    def test_is_typing_classifications(self, shortcuts_uri):
        out = _run(
            f'import {{ isTyping }} from "{shortcuts_uri}";\n'
            "console.log(JSON.stringify([\n"
            "  isTyping({ tagName: 'INPUT' }),\n"
            "  isTyping({ tagName: 'TEXTAREA' }),\n"
            "  isTyping({ tagName: 'SELECT' }),\n"
            "  isTyping({ tagName: 'DIV', isContentEditable: true }),\n"
            "  isTyping({ tagName: 'BUTTON' }),\n"
            "  isTyping(null),\n"
            "]));\n"
        )
        assert out == "[true,true,true,true,false,false]"


class TestProgressJs:
    def test_progress_ratio_math(self, progress_uri):
        out = _run(
            f'import {{ progressRatio, clamp01 }} from "{progress_uri}";\n'
            "console.log(JSON.stringify([\n"
            "  progressRatio(0, 800, 2000),\n"
            "  progressRatio(600, 800, 2000),\n"
            "  progressRatio(1200, 800, 2000),\n"
            "  progressRatio(-5, 800, 2000),\n"
            "  progressRatio(9999, 800, 2000),\n"
            "  progressRatio(0, 800, 700),\n"
            "  clamp01(-1),\n"
            "]));\n"
        )
        values = json.loads(out)
        assert values[0] == 0
        assert values[1] == pytest.approx(0.5)
        assert values[2] == 1
        assert values[3] == 0
        assert values[4] == 1
        assert values[5] == 1
        assert values[6] == 0


class TestTocJs:
    def test_activate_sets_current_and_clears_others(self, toc_uri):
        out = _run(
            f'import {{ activate }} from "{toc_uri}";\n'
            "const mk = (id) => ({\n"
            "  hash: '#' + id,\n"
            "  attrs: {},\n"
            "  setAttribute(k, v) { this.attrs[k] = v; },\n"
            "  removeAttribute(k) { delete this.attrs[k]; },\n"
            "  hasAttribute(k) { return k in this.attrs; },\n"
            "  getAttribute(k) { return this.attrs[k] ?? null; },\n"
            "});\n"
            "const snap = (label) => console.log(JSON.stringify(label));\n"
            "const a = mk('one');\n"
            "const b = mk('two');\n"
            "snap([activate([a, b], 'nope'), a.getAttribute('aria-current'),"
            " b.getAttribute('aria-current'), a.hasAttribute('aria-current')]);\n"
            "snap([activate([a, b], 'one'), a.getAttribute('aria-current'),"
            " b.hasAttribute('aria-current')]);\n"
            "snap([activate([a, b], 'two'), b.getAttribute('aria-current'),"
            " a.hasAttribute('aria-current')]);\n"
        )
        lines = [json.loads(line) for line in out.splitlines()]
        assert lines[0][0] is None
        assert lines[0][1:] == [None, None, False]
        assert lines[1] == ["one", "true", False]
        assert lines[2] == ["two", "true", False]


@pytest.fixture(scope="module")
def main_uri(tmp_path_factory):
    # main.js resolves ./modules/* relative to its own location, so copy
    # the real tree and mark it ESM for Node.
    root = tmp_path_factory.mktemp("main-js")
    shutil.copytree(REPO_ROOT / "assets/js", root / "assets" / "js")
    (root / "package.json").write_text('{"type": "module"}', encoding="utf-8")
    return (root / "assets" / "js" / "main.js").as_uri()


class TestMenuJs:
    """main.js mobile-menu contract: toggling, Esc, and close-on-activation
    for anything inside the nav panel (links AND the search/atmosphere
    action buttons), not just links."""

    SHIM = """
const mkEl = () => ({
  attrs: {},
  handlers: {},
  addEventListener(type, fn) { (this.handlers[type] ??= []).push(fn); },
  setAttribute(k, v) { this.attrs[k] = String(v); },
  removeAttribute(k) { delete this.attrs[k]; },
  hasAttribute(k) { return k in this.attrs; },
});
const header = mkEl();
const toggle = Object.assign(mkEl(), {
  closest: (sel) => (sel === '.site-header' ? header : null),
});
const navTarget = { closest: (sel) => (sel === '.site-nav a, .site-nav button' ? navTarget : null) };
globalThis.document = {
  documentElement: mkEl(),
  querySelector: (sel) => (sel === '[data-menu-toggle]' ? toggle : null),
  addEventListener(type, fn) { (this.handlers ??= {})[type] ??= []; this.handlers[type].push(fn); },
};
"""

    def _run_menu(self, main_uri, body):
        # The shim must exist BEFORE the import: main.js runs module inits at
        # import time; only the menu block needs a working document. The body
        # runs after the awaited import so the menu handlers are bound.
        return _run(
            self.SHIM + "\n"
            f'await import("{main_uri}");\n'
            + body + "\n"
            "console.log(JSON.stringify(globalThis.result));\n"
        )

    def test_toggle_opens_and_menu_closes_on_nav_button(self, main_uri):
        out = self._run_menu(
            main_uri,
            """
toggle.handlers.click[0]();
const opened = header.hasAttribute('data-menu-open');
// Activating the in-menu search/atmosphere button must close the menu.
header.handlers.click[0]({ target: navTarget });
const closed = !header.hasAttribute('data-menu-open');
globalThis.result = { opened, closed };
""",
        )
        assert json.loads(out) == {"opened": True, "closed": True}

    def test_menu_still_closes_on_nav_link(self, main_uri):
        out = self._run_menu(
            main_uri,
            """
toggle.handlers.click[0]();
header.handlers.click[0]({ target: navTarget });
globalThis.result = header.hasAttribute('data-menu-open');
""",
        )
        assert json.loads(out) is False

    def test_escape_closes_menu(self, main_uri):
        out = self._run_menu(
            main_uri,
            """
toggle.handlers.click[0]();
const opened = header.hasAttribute('data-menu-open');
const keydowns = document.handlers.keydown ?? [];
for (const fn of keydowns) fn({ key: 'Escape' });
const closedAfterEscape = !header.hasAttribute('data-menu-open');
globalThis.result = { opened, closedAfterEscape };
""",
        )
        assert json.loads(out) == {"opened": True, "closedAfterEscape": True}
