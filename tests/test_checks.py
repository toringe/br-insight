"""Tests for Task 14 site audits: asset budgets + internal link checking."""

from br_insight.checks import BUDGET_CSS_GZ, BUDGET_JS_GZ, audit
from br_insight.cli import main


def _make_site(tmp_path):
    """Minimal built-looking site: one page + referenced css/js."""
    css = tmp_path / "assets" / "css" / "site.css"
    js = tmp_path / "assets" / "js" / "app.js"
    mod = tmp_path / "assets" / "js" / "helper.js"
    page = tmp_path / "index.html"
    other = tmp_path / "about.html"
    for p in (css.parent, js.parent):
        p.mkdir(parents=True)
    css.write_text("body{color:#0af}\n")
    js.write_text('import { hi } from "./helper.js";\nconsole.log(hi);\n')
    mod.write_text("export const hi = 1;\n")
    page.write_text(
        "<html><head>"
        '<link rel="stylesheet" href="assets/css/site.css">'
        '<script type="module" src="assets/js/app.js"></script>'
        "</head><body>"
        '<a href="about.html">About</a>'
        '<a href="#top" id="top">Top</a>'
        "</body></html>",
        encoding="utf-8",
    )
    other.write_text('<html><body><p id="ok"></p></body></html>', encoding="utf-8")
    return {"page": page, "css": css, "js": js, "mod": mod}


class TestBudgets:
    def test_small_site_passes(self, tmp_path):
        _make_site(tmp_path)
        ok, report = audit(tmp_path)
        assert ok
        assert any("PASS" in line for line in report)

    def test_just_under_budget_passes(self, tmp_path):
        paths = _make_site(tmp_path)
        import os

        with open(paths["css"], "ab") as fh:
            fh.write(os.urandom(34_000))  # stays just under the 35 KB limit
        ok, _ = audit(tmp_path)
        assert ok

    def test_inflated_css_fails_budget(self, tmp_path):
        paths = _make_site(tmp_path)
        blob = b"z" * 200_000  # compresses poorly per-byte ratio ~1/1000? no: z's compress great
        # Incompressible random data instead:
        import os

        blob = os.urandom(40_000)
        with open(paths["css"], "ab") as fh:
            fh.write(blob)
        ok, report = audit(tmp_path)
        assert not ok
        assert any("CSS" in line and "exceeds" in line for line in report)

    def test_inflated_js_fails_budget(self, tmp_path):
        paths = _make_site(tmp_path)
        import os

        with open(paths["js"], "ab") as fh:
            fh.write(os.urandom(40_000))
        ok, report = audit(tmp_path)
        assert not ok
        assert any("JS" in line and "exceeds" in line for line in report)

    def test_unreferenced_assets_do_not_count(self, tmp_path):
        paths = _make_site(tmp_path)
        orphan = tmp_path / "assets" / "js" / "legacy.js"
        import os

        orphan.write_bytes(os.urandom(40_000))
        ok, _ = audit(tmp_path)
        assert ok

    def test_module_import_chain_counts_toward_budget(self, tmp_path):
        paths = _make_site(tmp_path)
        import os

        with open(paths["mod"], "ab") as fh:
            fh.write(os.urandom(40_000))
        ok, report = audit(tmp_path)
        assert not ok

    def test_search_index_budget_applies_when_present(self, tmp_path):
        _make_site(tmp_path)
        import os

        idx = tmp_path / "search-index.json"
        idx.write_bytes(os.urandom(220_000))
        ok, report = audit(tmp_path)
        assert not ok
        assert any("search-index" in line.lower() for line in report)


class TestLinkChecker:
    def test_clean_site_has_no_link_findings(self, tmp_path):
        _make_site(tmp_path)
        ok, report = audit(tmp_path)
        assert not any("missing" in line.lower() for line in report), report

    def test_broken_absolute_href_is_reported(self, tmp_path):
        paths = _make_site(tmp_path)
        text = paths["page"].read_text(encoding="utf-8")
        paths["page"].write_text(
            text.replace("about.html", "/library/nope/"), encoding="utf-8"
        )
        ok, report = audit(tmp_path)
        assert not ok
        assert any("/library/nope/" in line for line in report)

    def test_broken_relative_href_with_dotdot_resolves_before_existing_check(
        self, tmp_path
    ):
        page = tmp_path / "library" / "x" / "index.html"
        page.parent.mkdir(parents=True)
        page.write_text('<html><body><a href="../../assets/img/gone.png">x</a></body></html>')
        ok, report = audit(tmp_path)
        assert not ok
        assert any("gone.png" in line for line in report)

    def test_missing_anchor_on_other_page_is_reported(self, tmp_path):
        paths = _make_site(tmp_path)
        text = paths["page"].read_text(encoding="utf-8")
        paths["page"].write_text(
            text.replace('href="about.html"', 'href="about.html#ghost"'),
            encoding="utf-8",
        )
        ok, report = audit(tmp_path)
        assert not ok
        assert any("#ghost" in line for line in report)

    def test_directory_links_map_to_index_html(self, tmp_path):
        paths = _make_site(tmp_path)
        text = paths["page"].read_text(encoding="utf-8")
        sub = tmp_path / "docs" / "index.html"
        sub.parent.mkdir(parents=True)
        sub.write_text("<html><body>hi</body></html>", encoding="utf-8")
        paths["page"].write_text(
            text.replace("about.html", "/docs/"), encoding="utf-8"
        )
        ok, _ = audit(tmp_path)
        assert ok

    def test_query_strings_are_stripped_before_resolution(self, tmp_path):
        paths = _make_site(tmp_path)
        text = paths["page"].read_text(encoding="utf-8")
        paths["page"].write_text(
            text.replace("about.html", "/about.html?filter=x&y=2"),
            encoding="utf-8",
        )
        ok, _ = audit(tmp_path)
        assert ok

    def test_external_and_data_urls_are_ignored(self, tmp_path):
        paths = _make_site(tmp_path)
        text = paths["page"].read_text(encoding="utf-8")
        paths["page"].write_text(
            text.replace("</body></html>", '<a href="https://offsite.example/x">e</a>'
                         '<img src="data:image/gif;base64,R0lGOD">'
                         '<a href="mailto:t@t.example">m</a></body></html>')
        )
        ok, _ = audit(tmp_path)
        assert ok

    def test_img_src_broken_image_reported(self, tmp_path):
        paths = _make_site(tmp_path)
        text = paths["page"].read_text(encoding="utf-8")
        paths["page"].write_text(
            text.replace("</body></html>", '<img src="/img/missing.jpg"></body></html>')
        )
        ok, report = audit(tmp_path)
        assert not ok
        assert any("missing.jpg" in line for line in report)

    def test_srcset_entries_are_checked(self, tmp_path):
        paths = _make_site(tmp_path)
        text = paths["page"].read_text(encoding="utf-8")
        paths["page"].write_text(
            text.replace("</body></html>",
                         '<source srcset="assets/img/a.webp 480w, assets/img/b.webp 800w">'
                         '<img src="assets/css/../img/fake-cover.webp"></body></html>')
        )
        (tmp_path / "assets" / "img").mkdir()
        (tmp_path / "assets" / "img" / "b.webp").write_bytes(b"x")
        ok, report = audit(tmp_path)
        assert not ok
        assert any(("a.webp" in line or "fake-cover.webp" in line) for line in report)


class TestCliWiring:
    def test_check_command_exit_zero_on_clean_site(self, tmp_path):
        _make_site(tmp_path)
        assert main(["check", "--out", str(tmp_path)]) == 0

    def test_check_command_exit_one_when_broken(self, tmp_path):
        paths = _make_site(tmp_path)
        text = paths["page"].read_text(encoding="utf-8")
        paths["page"].write_text(text.replace("about.html", "/gone/"))
        assert main(["check", "--out", str(tmp_path)]) == 1

    def test_budget_constants_match_global_constraints(self):
        assert BUDGET_CSS_GZ == 35 * 1024
        assert BUDGET_JS_GZ == 25 * 1024
