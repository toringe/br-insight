"""Lenient-but-strict front-matter parsing for library articles.

Splitting mirrors scripts/normalize_frontmatter.py; values come from
``yaml.safe_load`` (Task 2 normalized every article, so strict YAML is
safe). Callers stay type-lenient: bare ISO dates arrive as
``datetime.date`` and are normalized later via ``articles.parse_date``.
"""

from __future__ import annotations

from pathlib import Path

import yaml

FENCE = "---"


def _is_fence(line: str) -> bool:
    return line.strip() == FENCE


def split(text: str) -> tuple[str | None, str]:
    """Split raw text into (front matter block incl. fences, remainder).

    Returns ``(None, text)`` unchanged when no front matter block exists;
    a fence appearing inside the body never terminates the block early.
    """
    lines = text.splitlines(keepends=True)
    if not lines or not _is_fence(lines[0]):
        return None, text
    for i in range(1, len(lines)):
        if _is_fence(lines[i]):
            return "".join(lines[: i + 1]), "".join(lines[i + 1 :])
    return None, text


def parse(text: str) -> tuple[dict, str]:
    """Parse raw article text into (front matter dict, body string)."""
    block, body = split(text)
    if block is None:
        return {}, body
    data = yaml.safe_load(block[len(FENCE) + 1 : -len(FENCE) - 1])
    return (data or {}), body


def load(path: Path) -> tuple[dict, str]:
    """Read an ``article.md`` file into (front matter dict, body string)."""
    return parse(path.read_text(encoding="utf-8"))
