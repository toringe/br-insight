"""Minify CSS files in place, writing a .min.css sibling next to each source.

Usage:
    uv run python scripts/minify_css.py [paths ...]

Paths are repo-root-relative (or absolute). Defaults to assets/css/main.css.
Later tasks should re-run this after editing any source .css so the minified
sibling pages actually load stays current.

Font url() references (``../fonts/*.woff2``) also get a ``?v=<hash8>``
content-hash suffix (Task 19b) so a swapped font file busts browser caches
even though the stylesheet filename never changes. Hashes match the
``asset_ver()`` page-level suffixes in br_insight.render.
"""

import hashlib
import re
import sys
from pathlib import Path

import rcssmin

DEFAULT_TARGETS = [Path("assets/css/main.css")]
REPO_ROOT = Path(__file__).resolve().parent.parent

# url("../fonts/<file>.woff2") — optional pre-existing ?v= is replaced.
FONT_URL = re.compile(r'url\((["\']?)(\.\./fonts/[^)"\'?]+)(?:\?v=[0-9a-f]{8})?\1\)')


def _hash8(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:8]


def _version_fonts(css: str, css_dir: Path) -> str:
    def repl(match: re.Match[str]) -> str:
        quote, rel = match.group(1), match.group(2)
        target = (css_dir / rel).resolve()
        if target.is_file():
            rel = f"{rel}?v={hashlib.sha256(target.read_bytes()).hexdigest()[:8]}"
        return f"url({quote}{rel}{quote})"

    return FONT_URL.sub(repl, css)


def minify(targets: list[Path]) -> None:
    for target in targets:
        src = target if target.is_absolute() else REPO_ROOT / target
        if not src.is_file():
            raise SystemExit(f"not a file: {src}")
        out = src.with_suffix(".min.css")
        minified = rcssmin.cssmin(src.read_text(encoding="utf-8"))
        out.write_text(_version_fonts(minified, src.parent), encoding="utf-8")
        print(f"{src} -> {out}")


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    minify([Path(a) for a in args] or DEFAULT_TARGETS)


if __name__ == "__main__":
    main()
