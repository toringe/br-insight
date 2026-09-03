"""archive.js weekly-carousel contract (run under Node).

Mirrors the filter.js harness in tests/test_library.py: copy the module
as .mjs, import it in a --input-type=module eval, drive init() against a
minimal DOM shim, and assert the observable aftermath as JSON.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

node = shutil.which("node")

pytestmark = pytest.mark.skipif(node is None, reason="node not available")


@pytest.fixture(scope="module")
def archive_mod(tmp_path_factory):
    dest = tmp_path_factory.mktemp("ajs") / "archive.mjs"
    shutil.copy(REPO_ROOT / "assets/js/modules/archive.js", dest)
    return dest


def run_archive(archive_mod, snippet: str) -> str:
    script = (
        f'import {{ init, fnv1a32, isoYearWeek, pick, cyrb53Hex }} '
        f'from "{archive_mod.as_uri()}";\n'
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


ITEMS = [
    {
        "slug": f"essay-{i}",
        "title": f"Essay {i}",
        "author": f"Author {i}",
        "minutes": 5,
        "date": f"20{10 + i:02d}-01-01",
        "category": "Film Analysis",
        "tags": ["noir"],
        "crop": [480, 800],
    }
    for i in range(10)
]


class TestPureHelpers:
    def test_cyrb53_parity_with_python(self, archive_mod):
        # locked to br_insight.config.cyrb53 — both sides must agree or the
        # build-week skip logic breaks (server DOM vs client recomputation)
        out = run_archive(
            archive_mod,
            'console.log(JSON.stringify([cyrb53Hex("foobar"), cyrb53Hex(""),'
            ' cyrb53Hex("essay-0:2026-W35")]));',
        )
        from br_insight.config import cyrb53_hex

        assert json.loads(out) == [
            cyrb53_hex("foobar"),
            cyrb53_hex(""),
            cyrb53_hex("essay-0:2026-W35"),
        ]

    def test_fnv_vectors(self, archive_mod):
        out = run_archive(
            archive_mod,
            'console.log(JSON.stringify([fnv1a32(""), fnv1a32("a"), fnv1a32("foobar")]));',
        )
        assert json.loads(out) == ["811c9dc5", "e40c292c", "bf9cf968"]

    def test_iso_year_week_matches_iso_monday_based_weeks(self, archive_mod):
        # 2026-08-26 is a Wednesday in ISO week 35; 2026-08-30 is Sunday of
        # the same week; 2026-08-31 (Monday) opens week 36. Node runs these
        # in the machine's local tz — build Dates via the local constructor
        # exactly as the module does, so tz is factored out on both sides.
        out = run_archive(
            archive_mod,
            """
            const at = (y, m, d) => { const t = isoYearWeek(new Date(y, m, d)); return t; };
            console.log(JSON.stringify([at(2026, 7, 26), at(2026, 7, 30), at(2026, 7, 31)]));
            """,
        )
        assert json.loads(out) == ["2026-W35", "2026-W35", "2026-W36"]

    def test_pick_excludes_caps_and_sorts_newest_first(self, archive_mod):
        out = run_archive(
            archive_mod,
            f"const items = {json.dumps(ITEMS)};\n"
            'console.log(JSON.stringify(pick(items, "2026-W35", "")));',
        )
        picked = json.loads(out)
        assert len(picked) == 3
        dates = [item["date"] for item in picked]
        assert dates == sorted(dates, reverse=True)

    def test_pick_stable_within_week(self, archive_mod):
        out = run_archive(
            archive_mod,
            f"const items = {json.dumps(ITEMS)};\n"
            'const a = pick(items, "2026-W35", "").map((i) => i.slug);\n'
            'const b = pick(items, "2026-W35", "").map((i) => i.slug);\n'
            'const weeks = [1, 2, 3, 4].map((n) => pick(items, `2027-W${n}`, "").map((i) => i.slug));\n'
            "console.log(JSON.stringify([a, b, weeks]));",
        )
        a, b, weeks = json.loads(out)
        assert a == b
        # across several future weeks the pick set actually rotates
        assert len({tuple(w) for w in weeks}) > 1

    def test_pick_excludes_featured_slug(self, archive_mod):
        out = run_archive(
            archive_mod,
            f"const items = {json.dumps(ITEMS)};\n"
            'const plain = pick(items, "2026-W35", "").map((i) => i.slug);\n'
            'const excluded = pick(items, "2026-W35", plain[0]).map((i) => i.slug);\n'
            "console.log(JSON.stringify([plain, excluded]));",
        )
        plain, excluded = json.loads(out)
        assert plain[0] not in excluded
        assert len(excluded) == 3


class TestInit:
    def _snippet(self, items):
        return (
            f"const items = {json.dumps(items)};\n"
            "const grid = makeGrid(buildWeek === undefined ? isoYearWeek() : buildWeek);\n"
            "const payload = { textContent: JSON.stringify(items) };\n"
            "const doc = {\n"
            "  querySelector(sel) { return sel === '[data-archive-grid]' ? grid : null; },\n"
            "  getElementById(id) { return id === 'archive-payload' ? payload : null; },\n"
            "};\n"
            "init(doc);\n"
            "const shown = grid._calls.renders ? grid._calls.html : '';\n"
            "const cardCount = shown.match(/<article/g);\n"
            "console.log(JSON.stringify({\n"
            "  renders: grid._calls.renders,\n"
            "  cardCount: cardCount ? cardCount.length : 0,\n"
            "}));\n"
        )

    def _run(self, archive_mod, items, featuredSlug="essay-9"):
        preamble = (
            "let buildWeek;\n"
            "function makeGrid(week) {\n"
            "  const calls = { renders: 0, html: 'server-fallback' };\n"
            "  const grid = {\n"
            f"    dataset: {{ buildWeek: week, featuredSlug: {json.dumps(featuredSlug)} }},\n"
            "    set innerHTML(v) { calls.renders += 1; calls.html = v; },\n"
            "    get innerHTML() { return calls.html; },\n"
            "    _calls: calls,\n"
            "  };\n"
            "  return grid;\n"
            "}\n"
        )
        return run_archive(archive_mod, preamble + self._snippet(items))

    def test_build_week_skips_the_swap(self, archive_mod):
        # buildWeek is the visitor's actual current week → server DOM stands
        out = self._run(archive_mod, ITEMS)
        data = json.loads(out)
        assert data == {"renders": 0, "cardCount": 0}

    def test_other_week_replaces_with_four_cards(self, archive_mod):
        preamble = (
            'const buildWeek = "2020-W01";\n'
            "function makeGrid(week) {\n"
            "  const calls = { renders: 0, html: 'server-fallback' };\n"
            "  const grid = {\n"
            f"    dataset: {{ buildWeek: week, featuredSlug: {json.dumps('essay-9')} }},\n"
            "    set innerHTML(v) { calls.renders += 1; calls.html = v; },\n"
            "    get innerHTML() { return calls.html; },\n"
            "    _calls: calls,\n"
            "  };\n"
            "  return grid;\n"
            "}\n"
        )
        out = run_archive(archive_mod, preamble + self._snippet(ITEMS))
        data = json.loads(out)
        assert data["renders"] == 1
        assert data["cardCount"] == 3

    def test_empty_payload_noops(self, archive_mod):
        out = self._run(archive_mod, [])
        assert json.loads(out) == {"renders": 0, "cardCount": 0}
