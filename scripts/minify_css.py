"""Minify CSS files in place, writing a .min.css sibling next to each source.

Usage:
    uv run python scripts/minify_css.py [paths ...]

Paths are repo-root-relative (or absolute). Defaults to assets/css/main.css.
Later tasks should re-run this after editing any source .css so the minified
sibling pages actually load stays current.
"""

import sys
from pathlib import Path

import rcssmin

DEFAULT_TARGETS = [Path("assets/css/main.css")]
REPO_ROOT = Path(__file__).resolve().parent.parent


def minify(targets: list[Path]) -> None:
    for target in targets:
        src = target if target.is_absolute() else REPO_ROOT / target
        if not src.is_file():
            raise SystemExit(f"not a file: {src}")
        out = src.with_suffix(".min.css")
        out.write_text(rcssmin.cssmin(src.read_text(encoding="utf-8")), encoding="utf-8")
        print(f"{src} -> {out}")


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    minify([Path(a) for a in args] or DEFAULT_TARGETS)


if __name__ == "__main__":
    main()
