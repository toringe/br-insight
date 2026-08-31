"""Task 13 cinematic FX: build-time config injection (__FX__ payload + html
presence flags), fx.js gating matrix, and pure rain.js helpers (run under
Node, following the subprocess harness established in test_reading_ux.py)."""

import json
import re
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from br_insight.config import SiteConfig
from br_insight.render import REPO_ROOT


# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------


def _patched_fx(fx, *, enabled=True, rain=True, scanlines=True, grain=True,
                flicker=True, welcome=True):
    """A SiteConfig.fx copy with individual effect flags flipped."""
    return type(fx)(
        enabled=enabled,
        atmosphere_toggle=fx.atmosphere_toggle,
        rain=replace(fx.rain, enabled=rain),
        flicker=type(fx.flicker)(enabled=flicker, welcome=welcome),
        scanlines=type(fx.scanlines)(enabled=scanlines),
        grain=type(fx.grain)(enabled=grain),
    )


def _expected_fx_payload():
    """The single source of truth: exactly what SiteConfig.fx must serialize."""
    site = SiteConfig.load(REPO_ROOT)
    return {
        "enabled": site.fx.enabled,
        "rain": {
            "enabled": site.fx.rain.enabled,
            "density": site.fx.rain.density,
            "speed": site.fx.rain.speed,
            "tier_auto": site.fx.rain.tier_auto,
        },
        "flicker": {
            "enabled": site.fx.flicker.enabled,
            "welcome": site.fx.flicker.welcome,
        },
        "scanlines": {"enabled": site.fx.scanlines.enabled},
        "grain": {"enabled": site.fx.grain.enabled},
    }


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    from br_insight.render import build

    out = tmp_path_factory.mktemp("fx_build")
    build(REPO_ROOT, out)
    return out


def _render_base(**fx_overrides):
    site = SiteConfig.load(REPO_ROOT)
    if fx_overrides:
        site = replace(site, fx=_patched_fx(site.fx, **fx_overrides))
    from br_insight.render import render_template

    return render_template("base.html", site=site)


# ---------------------------------------------------------------------------
# Template-level: payload + presence-flag injection (base.html)
# ---------------------------------------------------------------------------

FX_ATTRS = ("data-fx-rain", "data-fx-scanlines", "data-fx-grain",
            "data-fx-flicker", "data-fx-welcome")


class TestBaseInjection:
    def test_payload_matches_siteconfig_round_trip(self):
        html = _render_base()
        blob = html.split("window.__FX__=", 1)[1].split("</script>", 1)[0]
        assert json.loads(blob.rstrip(";")) == _expected_fx_payload()

    def test_payload_is_compact_single_line(self):
        html = _render_base()
        assert re.search(r"<script>window\.__FX__=.+?</script>", html)

    @pytest.mark.parametrize("attr", FX_ATTRS)
    def test_presence_flags_emitted_when_enabled(self, attr):
        opening = re.search(r"<html[^>]*>", _render_base()).group(0)
        assert attr in opening

    def test_payload_omitted_when_master_disabled(self):
        html = _render_base(enabled=False)
        assert "__FX__" not in html

    @pytest.mark.parametrize(
        "override,dropped_attr",
        [
            ({"enabled": False}, FX_ATTRS),
            ({"rain": False}, ("data-fx-rain",)),
            ({"scanlines": False}, ("data-fx-scanlines",)),
            ({"grain": False}, ("data-fx-grain",)),
            ({"flicker": False}, ("data-fx-flicker", "data-fx-welcome")),
            ({"welcome": False}, ("data-fx-welcome",)),
        ],
    )
    def test_flags_dropped_when_effect_disabled(self, override, dropped_attr):
        opening = re.search(r"<html[^>]*>", _render_base(**override)).group(0)
        for attr in dropped_attr:
            assert attr not in opening
        for attr in FX_ATTRS:
            if attr not in dropped_attr:
                assert attr in opening

    def test_welcome_flag_still_requires_full_chain(self):
        # flicker.welcome requested but flicker.enabled off -> neither attr
        opening = re.search(
            r"<html[^>]*>", _render_base(flicker=False, welcome=True)
        ).group(0)
        assert "data-fx-welcome" not in opening
        assert "data-fx-flicker" not in opening


class TestHeaderToggleVisibility:
    def test_atmosphere_button_present_by_default(self):
        assert "data-fx-toggle" in _render_base()

    def test_atmosphere_button_hidden_when_fx_disabled(self):
        assert "data-fx-toggle" not in _render_base(enabled=False)

    def test_atmosphere_button_hidden_when_atmosphere_toggle_off(self):
        site = SiteConfig.load(REPO_ROOT)
        site = replace(site, fx=replace(site.fx, atmosphere_toggle=False))
        from br_insight.render import render_template

        assert "data-fx-toggle" not in render_template("base.html", site=site)


# ---------------------------------------------------------------------------
# Build integration: every page gains the payload + flags
# ---------------------------------------------------------------------------


class TestBuiltPagesCarryFx:
    def test_home_carries_payload_with_correct_values(self, built):
        text = (built / "index.html").read_text(encoding="utf-8")
        blob = text.split("window.__FX__=", 1)[1].split("</script>", 1)[0]
        payload = json.loads(blob.rstrip(";"))
        assert payload == _expected_fx_payload()
        assert payload["rain"]["density"] == 120
        assert payload["rain"]["speed"] == 1.0

    def test_article_page_carries_payload_and_flags(self, built):
        sample = next((built / "library").glob("*/index.html"))
        text = sample.read_text(encoding="utf-8")
        assert "window.__FX__=" in text
        opening = re.search(r"<html[^>]*>", text).group(0)
        assert "data-fx-rain" in opening
        assert "data-fx-welcome" in opening

    def test_sitemap_feed_do_not_gain_fx_markup(self, built):
        sitemap = (built / "sitemap.xml").read_text(encoding="utf-8")
        feed = (built / "feed.xml").read_text(encoding="utf-8")
        assert "__FX__" not in sitemap
        assert "__FX__" not in feed


# ---------------------------------------------------------------------------
# Node subprocess harness (same pattern as test_reading_ux.py)
# ---------------------------------------------------------------------------

node = shutil.which("node")

pytestmark = pytest.mark.skipif(node is None, reason="node not available")


def _copy_modules(tmp_path_factory, *names):
    dest_dir = tmp_path_factory.mktemp("fx-js")
    uris = []
    for name in names:
        dest = dest_dir / f"{name.removesuffix('.js')}.mjs"
        shutil.copy(REPO_ROOT / "assets/js/modules" / name, dest)
        uris.append(dest.as_uri())
    return uris


def _run(script):
    proc = subprocess.run(
        [node, "--input-type=module", "--eval", script],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def _el_shim():
    return ('const mkEl = () => ({\n'
            '  attrs: {},\n'
            '  setAttribute(k, v) { this.attrs[k] = String(v); },\n'
            '  removeAttribute(k) { delete this.attrs[k]; },\n'
            '  hasAttribute(k) { return k in this.attrs; },\n'
            '});\n')


# The exact __FX__ payload the build emits for the shipped defaults.
FULL_CONFIG = (
    '{"enabled":true,'
    '"rain":{"enabled":true,"density":120,"speed":1.0,"tier_auto":true},'
    '"flicker":{"enabled":true,"welcome":true},'
    '"scanlines":{"enabled":true},"grain":{"enabled":true}}'
)

RAIN_ONLY_CONFIG = (
    '{"enabled":true,'
    '"rain":{"enabled":true,"density":80,"speed":1.4,"tier_auto":false},'
    '"flicker":{"enabled":false,"welcome":false},'
    '"scanlines":{"enabled":false},"grain":{"enabled":false}}'
)


@pytest.fixture(scope="module")
def fx_uri(tmp_path_factory):
    return _copy_modules(tmp_path_factory, "fx.js")[0]


@pytest.fixture(scope="module")
def rain_uri(tmp_path_factory):
    return _copy_modules(tmp_path_factory, "rain.js")[0]


_FX_MATRIX_BODY = """
for (const [label, config, env] of CASES) {
  const resolved = resolve(config, env);
  const el = mkEl();
  // simulate the build-time attributes being present; applyFx owns them after
  for (const a of ['data-fx-rain','data-fx-scanlines','data-fx-grain',
                   'data-fx-flicker','data-fx-welcome']) el.setAttribute(a, '');
  applyFx(el, resolved);
  console.log(JSON.stringify({
    label,
    configured: resolved.configured,
    blanketOff: resolved.blanketOff,
    active: resolved.active,
    attrs: Object.keys(el.attrs).sort(),
  }));
}
"""


class TestFxGatingMatrix:
    """config (on/off/partial) x atmosphere toggle x focus attr x reduced-motion."""

    CASES = [
        ("all_on", FULL_CONFIG, "atm"),
        ("atmosphere_off", FULL_CONFIG, "noatm"),
        ("focus_mode", FULL_CONFIG, "focus"),
        ("reduced_motion", FULL_CONFIG, "reduced"),
        ("no_config", None, "atm"),
        ("rain_only", RAIN_ONLY_CONFIG, "atm"),
    ]

    EXPECTED = {
        "all_on": {
            "configured": True,
            "blanketOff": False,
            "active": {"rain": True, "scanlines": True, "grain": True,
                       "flicker": True, "welcome": True},
            "attrs": ["data-fx-flicker", "data-fx-grain", "data-fx-rain",
                      "data-fx-scanlines", "data-fx-welcome"],
        },
        "atmosphere_off": {
            "configured": True,
            "blanketOff": True,
            "active": {"rain": False, "scanlines": False, "grain": False,
                       "flicker": False, "welcome": False},
            "attrs": ["data-fx-off"],
        },
        "focus_mode": {
            "configured": True,
            "blanketOff": True,
            "active": {"rain": False, "scanlines": False, "grain": False,
                       "flicker": False, "welcome": False},
            "attrs": ["data-fx-off"],
        },
        "reduced_motion": {
            "configured": True,
            "blanketOff": True,
            "active": {"rain": False, "scanlines": False, "grain": False,
                       "flicker": False, "welcome": False},
            "attrs": ["data-fx-off"],
        },
        "no_config": {
            "configured": False,
            "blanketOff": True,
            "active": {"rain": False, "scanlines": False, "grain": False,
                       "flicker": False, "welcome": False},
            "attrs": [],
        },
        "rain_only": {
            "configured": True,
            "blanketOff": False,
            "active": {"rain": True, "scanlines": False, "grain": False,
                       "flicker": False, "welcome": False},
            "attrs": ["data-fx-rain"],
        },
    }

    def test_matrix(self, fx_uri):
        envs = json.dumps([
            {"atmosphere": True, "focus": False, "reduced": False},
            {"atmosphere": False, "focus": False, "reduced": False},
            {"atmosphere": True, "focus": True, "reduced": False},
            {"atmosphere": True, "focus": False, "reduced": True},
        ])
        cases = [
            f'["{label}", "{cfg}", "{env_ix}"]'
            for label, cfg, env_ix in [
                ("all_on", "full", 0),
                ("atmosphere_off", "full", 1),
                ("focus_mode", "full", 2),
                ("reduced_motion", "full", 3),
                ("no_config", "none", 0),
                ("rain_only", "rainOnly", 0),
            ]
        ]
        script = "\n".join([
            f'import {{ resolve, applyFx }} from "{fx_uri}";',
            _el_shim(),
            f'const CONFIGS = {{full: {FULL_CONFIG},'
            f' rainOnly: {RAIN_ONLY_CONFIG}, none: null}};',
            f"const ENVS = {envs};",
            "const CASES = [\n  "
            + ",\n  ".join(cases) + "\n];",
            "const lookup = ([label, cfgKey, envIx]) =>"
            " [label, CONFIGS[cfgKey], ENVS[envIx]];",
            _FX_MATRIX_BODY.replace("of CASES", "of CASES.map(lookup)")
            .replace("[label, config, env]", "[label, config, env]"),
        ])
        rows = {row["label"]: row for row in map(json.loads, _run(script).splitlines())}
        assert set(rows) == {case[0] for case in self.CASES}
        for label, _, _ in self.CASES:
            expected = self.EXPECTED[label]
            assert rows[label]["configured"] == expected["configured"], label
            assert rows[label]["blanketOff"] == expected["blanketOff"], label
            assert rows[label]["active"] == expected["active"], label
            assert rows[label]["attrs"] == expected["attrs"], label


class TestFxPersistenceHelpers:
    def test_atmosphere_pref_round_trip_default_on(self, fx_uri):
        out = _run(
            f'import {{ loadPref, savePref }} from "{fx_uri}";\n'
            "const store = new Map();\n"
            "const shim = { getItem: (k) => store.has(k) ? store.get(k) : null,"
            " setItem: (k, v) => store.set(k, String(v)) };\n"
            "const unset = loadPref(shim);\n"
            "savePref(shim, false);\n"
            "const off = loadPref(shim);\n"
            "savePref(shim, true);\n"
            "const on = loadPref(shim);\n"
            "console.log(JSON.stringify({ unset, off, on }));\n"
        )
        assert json.loads(out) == {"unset": True, "off": False, "on": True}

    def test_atmosphere_pref_tolerates_broken_storage(self, fx_uri):
        out = _run(
            f'import {{ loadPref, savePref }} from "{fx_uri}";\n'
            "const throwingSave = { getItem: () => null,"
            " setItem() { throw new Error('blocked'); } };\n"
            "savePref(throwingSave, false);\n"
            "console.log(JSON.stringify([\n"
            "  loadPref(throwingSave),\n"
            "  loadPref(null),\n"
            "]));\n"
        )
        assert json.loads(out) == [True, True]


class TestFxInitGuards:
    def test_init_without_config_is_a_noop_not_a_crash(self, fx_uri):
        out = _run(
            f'import {{ init }} from "{fx_uri}";\n'
            + _el_shim()
            + """
// Minimal document stub: no __FX__, no toggle, no matchMedia, no observer.
globalThis.document = {
  documentElement: mkEl(),
  querySelector: () => null,
  querySelectorAll: () => [],
  addEventListener() {},
  defaultView: {},
};
init(document);
console.log(JSON.stringify(Object.keys(document.documentElement.attrs)));
"""
        )
        # No config -> data-fx-off must NOT appear; nothing gets written.
        assert json.loads(out) == []

    def test_init_binds_and_syncs_every_fx_toggle(self, fx_uri):
        """Header + in-menu duplicate atmosphere buttons must ALL receive the
        click binding and stay aria-pressed in lockstep."""
        out = _run(
            f'import {{ init }} from "{fx_uri}";\n'
            + _el_shim()
            + """
const mkBtn = () => Object.assign(mkEl(), {
  handlers: [],
  addEventListener(type, fn) { this.handlers.push([type, fn]); },
});
const btns = [mkBtn(), mkBtn()];
const store = new Map();
globalThis.document = {
  documentElement: mkEl(),
  querySelector: () => null,
  querySelectorAll: (sel) => (sel === '[data-fx-toggle]' ? btns : []),
  addEventListener() {},
  defaultView: {
    __FX__: """ + RAIN_ONLY_CONFIG + """,
    matchMedia: () => ({ matches: false, addEventListener() {} }),
    localStorage: {
      getItem: (k) => (store.has(k) ? store.get(k) : null),
      setItem: (k, v) => store.set(k, String(v)),
    },
  },
};
init(document);
const bound = btns.map((b) => b.handlers.filter(([t]) => t === 'click').length);
const initial = btns.map((b) => b.attrs['aria-pressed']);
// Toggle through the FIRST button only; both must flip in lockstep.
for (const [, fn] of btns[0].handlers.filter(([t]) => t === 'click')) fn();
const afterToggle = btns.map((b) => b.attrs['aria-pressed']);
console.log(JSON.stringify({ bound, initial, afterToggle }));
"""
        )
        data = json.loads(out)
        assert data["bound"] == [1, 1]
        assert data["initial"] == ["true", "true"]
        assert data["afterToggle"] == ["false", "false"]

    def test_focus_attr_change_reapplies_gating(self, fx_uri):
        out = _run(
            f'import {{ init }} from "{fx_uri}";\n'
            + _el_shim()
            + """
let mutationCb = null;
globalThis.MutationObserver = class {
  constructor(cb) { mutationCb = cb; }
  observe() {}
  disconnect() {}
};
const html = mkEl();
globalThis.document = {
  documentElement: html,
  querySelector: () => null,
  querySelectorAll: () => [],
  addEventListener() {},
  defaultView: {
    __FX__: """ + FULL_CONFIG + """,
    matchMedia: () => ({ matches: false, addEventListener() {} }),
  },
};
init(document);
const afterInit = Object.keys(html.attrs).sort();
// Focus mode engages elsewhere (focus.js); the observer must react.
html.setAttribute('data-focus', '');
mutationCb();
const afterFocus = Object.keys(html.attrs).sort();
console.log(JSON.stringify([afterInit, afterFocus]));
"""
        )
        after_init, after_focus = json.loads(out)
        assert "data-fx-rain" in after_init and "data-fx-off" not in after_init
        # data-focus stays (focus.js owns it); every fx attr but the blanket goes.
        assert "data-fx-off" in after_focus and "data-focus" in after_focus
        assert not any(a.startswith("data-fx-") and a != "data-fx-off"
                       for a in after_focus)


class TestRainHelpers:
    def test_drop_count_scales_with_viewport_and_clamps(self, rain_uri):
        out = _run(
            f'import {{ dropsForWidth }} from "{rain_uri}";\n'
            "console.log(JSON.stringify([\n"
            "  dropsForWidth(120, 1920),\n"   # wide viewport: full density
            "  dropsForWidth(120, 1280),\n"   # reference width: full density
            "  dropsForWidth(120, 640),\n"    # half viewport: half density
            "  dropsForWidth(120, 320),\n"    # tiny viewport: clamped scale
            "  dropsForWidth(80, 160)\n"      # tiny viewport keeps >= 32 drops
            "]));\n"
        )
        assert json.loads(out) == [120, 120, 60, 48, 32]

    def test_split_drops_partitions_density(self, rain_uri):
        """Depth split: far+near sum to the total, near gets the majority,
        and tiny totals still give both layers at least one drop."""
        out = _run(
            f'import {{ splitDrops }} from "{rain_uri}";\n'
            "console.log(JSON.stringify([\n"
            "  splitDrops(120),\n"
            "  splitDrops(60),\n"
            "  splitDrops(8),\n"
            "  splitDrops(1),\n"
            "]));\n"
        )
        results = json.loads(out)
        for far, near in results:
            assert far >= 1 and near >= 1
        # Deterministic 60/40-ish split (near majority, rounding stable).
        assert results[0] == [48, 72]
        assert results[1] == [24, 36]
        assert results[2] == [3, 5]
        assert results[3] == [1, 1]

    def test_downgrade_tiers_halve_density_to_floor(self, rain_uri):
        out = _run(
            f'import {{ downgradeTier }} from "{rain_uri}";\n'
            "console.log(JSON.stringify([\n"
            "  downgradeTier(120), downgradeTier(60), downgradeTier(30),\n"
            "  downgradeTier(10), downgradeTier(10)\n"
            "]));\n"
        )
        values = json.loads(out)
        assert values[:3] == [60, 30, 15]
        assert values[3] == values[4]  # floored: further halving is capped

    def test_watchdog_verdict_ladder(self, rain_uri):
        out = _run(
            f'import {{ watchdogVerdict, FRAME_BUDGET_MS }} from "{rain_uri}";\n'
            "if (FRAME_BUDGET_MS !== 24) throw new Error('budget drifted');\n"
            "console.log(JSON.stringify([\n"
            "  watchdogVerdict(16, 0),\n"     # healthy frame
            "  watchdogVerdict(24, 0),\n"     # budget edge stays healthy
            "  watchdogVerdict(24.01, 0),\n"  # over budget on tier 0 -> tier down
            "  watchdogVerdict(40, 1),\n"     # still slow after downgrade -> pause
            "]));\n"
        )
        assert json.loads(out) == ["hold", "hold", "downgrade", "pause"]

    def test_module_never_touches_dom_on_import(self, rain_uri):
        # Importing rain.js with no DOM at all must not explode.
        out = _run(
            f'import * as rain from "{rain_uri}";\n'
            "console.log(typeof rain.createRain);\n"
        )
        assert out == "function"


# ---------------------------------------------------------------------------
# Size budget: rain.js + fx.js <= 10 KB gzipped combined
# ---------------------------------------------------------------------------


class TestSizeBudget:
    def test_new_js_within_budget(self):
        import gzip

        total = 0
        for name in ("rain.js", "fx.js"):
            raw = (REPO_ROOT / "assets/js/modules" / name).read_bytes()
            gz = len(gzip.compress(raw))
            total += gz
            print(f"{name}: raw={len(raw)}B gz={gz}B")
        assert total <= 10 * 1024
