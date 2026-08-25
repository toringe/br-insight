#!/usr/bin/env python3
"""One-time migration: normalize legacy YAML front matter in library articles.

Rules applied to the front matter block only (article body stays byte-identical):
  - leading tabs expand to two spaces each
  - trailing whitespace is stripped from every line
  - `date:` values in DD-MM-YYYY form are coerced to ISO YYYY-MM-DD
  - single-line scalars containing ": " or a trailing ":" are double-quoted
    (unquoted, they are invalid YAML mapping syntax)
  - missing top-level blocks are injected with defaults:
      taxonomy.category = article, summary.enabled = true, summary.size = 100
  - all other fields (cauthor, copyright, source, ...) are preserved untouched

Usage:
    uv run python scripts/normalize_frontmatter.py

The script is idempotent: a second run rewrites nothing.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LIBRARY_DIR = REPO_ROOT / "library"

FENCE = "---"
FENCE_LINE = FENCE + "\n"

DATE_RE = re.compile(r"^date:[ \t]*(\d{2})-(\d{2})-(\d{4})[ \t]*$")
TOP_LEVEL_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*:")
TOP_LEVEL_SCALAR_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*):[ \t]+(.+)$")

REQUIRED_TOP_LEVEL_KEYS = ("title", "author", "date", "taxonomy", "summary")

DEFAULT_BLOCKS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("taxonomy", ("taxonomy:", "  category: article")),
    ("summary", ("summary:", "  enabled: true", "  size: 100")),
)


def split_front_matter(text: str) -> tuple[str | None, str]:
    """Split raw text into (front matter block incl. fences, remainder).

    Returns ``(None, text)`` unchanged when no front matter block is present.
    """
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip() != FENCE:
        return None, text
    for i in range(1, len(lines)):
        if lines[i].rstrip() == FENCE:
            return "".join(lines[: i + 1]), "".join(lines[i + 1 :])
    return None, text


def _expand_leading_tabs(line: str) -> str:
    stripped = line.lstrip("\t")
    return "  " * (len(line) - len(stripped)) + stripped


def _quote_ambiguous_scalar(line: str) -> tuple[str, bool]:
    """Double-quote a single-line scalar whose value contains ": " or a
    trailing ":" — both are invalid as unquoted YAML mapping scalars."""
    match = TOP_LEVEL_SCALAR_RE.match(line)
    if not match:
        return line, False
    key, value = match.groups()
    if value.startswith(('"', "'")) or value.endswith("\\"):
        return line, False
    if ": " not in value and not value.rstrip().endswith(":"):
        return line, False
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'{key}: "{escaped}"', True


def normalize_front_matter(fm_text: str) -> tuple[str, list[str]]:
    """Normalize a front matter block (fences included).

    Returns the normalized block and a list of human-readable change labels;
    an empty label list means the input was already normalized.
    """
    lines = fm_text.splitlines(keepends=True)
    if not lines:
        return fm_text, []
    changes: list[str] = []
    out: list[str] = []

    content_lines = lines[1:-1] if lines and lines[-1].rstrip() == FENCE else lines[1:]
    closing = lines[-1] if lines and lines[-1].rstrip() == FENCE else FENCE_LINE

    for raw in content_lines:
        had_newline = raw.endswith("\n")
        line = _expand_leading_tabs(raw)
        if line != raw and "tabs expanded to spaces" not in changes:
            changes.append("tabs expanded to spaces")
        content = line.rstrip(" \t\n")
        if content != line.rstrip("\n") and "trailing whitespace stripped" not in changes:
            changes.append("trailing whitespace stripped")
        content, quoted = _quote_ambiguous_scalar(content)
        if quoted:
            changes.append("quoted scalar containing colon")
        date_match = DATE_RE.match(content)
        if date_match:
            day, month, year = date_match.groups()
            content = f"date: {year}-{month}-{day}"
            changes.append(f"date coerced to ISO ({year}-{month}-{day})")
        out.append(content + ("\n" if had_newline else ""))

    present = {m.group(0).split(":")[0] for line in out if (m := TOP_LEVEL_KEY_RE.match(line))}
    for name, block_lines in DEFAULT_BLOCKS:
        if name not in present:
            out.extend(line + "\n" for line in block_lines)
            changes.append(f"injected default {name} block")

    return lines[0] + "".join(out) + closing, changes


def normalize_article(path: Path) -> bool:
    """Normalize one article file in place. Returns True when it changed."""
    text = path.read_text(encoding="utf-8")
    fm, body = split_front_matter(text)
    if fm is None:
        raise ValueError(f"{path}: no front matter block found")
    new_fm, changes = normalize_front_matter(fm)
    if new_fm == fm:
        print(f"{path.relative_to(REPO_ROOT)}: unchanged")
        return False
    path.write_text(new_fm + body, encoding="utf-8", newline="")
    print(f"{path.relative_to(REPO_ROOT)}: {'; '.join(changes)}")
    return True


def main() -> int:
    articles = sorted(LIBRARY_DIR.glob("*/article.md"))
    if not articles:
        print(f"no article.md files under {LIBRARY_DIR}", file=sys.stderr)
        return 1
    changed = 0
    errors = 0
    for path in articles:
        try:
            changed += normalize_article(path)
        except ValueError as exc:
            print(exc, file=sys.stderr)
            errors += 1
    print(f"\n{changed}/{len(articles)} files updated, {errors} error(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
