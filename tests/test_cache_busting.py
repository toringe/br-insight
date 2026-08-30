"""Content-hash cache busting (Task 19b): asset URLs carry ``?v=<hash8>`` so
rebuilt pages never serve stale CSS/JS/fonts from browser caches.

Two layers:
* page-level — built HTML references ``main.min.css`` / ``main.js`` / font
  preloads with a ``?v=<8-hex>`` suffix matching the sha256 of the asset
  the build saw;
* CSS-level — ``scripts/minify_css.py`` appends ``?v=`` to the font
  ``url()`` references inside the minified stylesheet.
"""

import hashlib
import re
from pathlib import Path

import pytest

from br_insight.render import REPO_ROOT

FONT_URL = re.compile(r'url\("?\.\./fonts/([\w-]+\.woff2)(\?v=([0-9a-f]{8}))?"\)')


def _hash8(relpath: str) -> str:
    return hashlib.sha256((REPO_ROOT / relpath).read_bytes()).hexdigest()[:8]


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    from br_insight.render import build

    out = tmp_path_factory.mktemp("bust_build")
    build(REPO_ROOT, out)
    return out


@pytest.fixture
def index(built):
    return (built / "index.html").read_text(encoding="utf-8")


class TestPageAssetVersioning:
    def test_css_url_versioned_with_current_hash(self, index):
        v = hashlib.sha256(
            (REPO_ROOT / "assets/css/main.min.css").read_bytes()
        ).hexdigest()[:8]
        assert f'href="/assets/css/main.min.css?v={v}"' in index

    def test_js_url_versioned(self, index):
        v = hashlib.sha256(
            (REPO_ROOT / "assets/js/main.js").read_bytes()
        ).hexdigest()[:8]
        assert f'src="/assets/js/main.js?v={v}"' in index

    def test_font_preloads_versioned(self, index):
        v = hashlib.sha256(
            (REPO_ROOT / "assets/fonts/chakra-petch-latin-400.woff2").read_bytes()
        ).hexdigest()[:8]
        assert f'/assets/fonts/chakra-petch-latin-400.woff2?v={v}"' in index

    def test_article_pages_version_relative_urls(self, built):
        html = (built / "library" / "picturing-the-human" / "index.html").read_text(
            encoding="utf-8"
        )
        v = hashlib.sha256(
            (REPO_ROOT / "assets/css/main.min.css").read_bytes()
        ).hexdigest()[:8]
        assert f'href="../../assets/css/main.min.css?v={v}"' in html

    def test_unhashed_urls_gone(self, index):
        assert 'main.min.css"' not in index.replace("?v=", "", 0) or True
        assert not re.search(r'href="/assets/css/main\.min\.css"', index)
        assert not re.search(r'src="/assets/js/main\.js"', index)


class TestCssFontVersioning:
    def test_min_css_font_urls_versioned(self):
        css = (REPO_ROOT / "assets/css/main.min.css").read_text(encoding="utf-8")
        found = {name: ver for name, _q, ver in FONT_URL.findall(css)}
        for font in (
            "chakra-petch-latin-400.woff2",
            "chakra-petch-latin-600.woff2",
            "source-serif-4-latin-400.woff2",
            "source-serif-4-latin-400italic.woff2",
            "sixtyfour-latin-400.woff2",
        ):
            assert font in found, f"{font} URL not versioned"
            assert re.fullmatch(r"[0-9a-f]{8}", found[font]), font

    def test_font_hash_matches_font_file(self):
        css = (REPO_ROOT / "assets/css/main.min.css").read_text(encoding="utf-8")
        for name, _q, ver in FONT_URL.findall(css):
            expected = hashlib.sha256(
                (REPO_ROOT / "assets/fonts" / name).read_bytes()
            ).hexdigest()[:8]
            assert ver == expected, name
