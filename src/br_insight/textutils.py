"""Small text helpers shared across the br-insight package."""

from __future__ import annotations

import re
import unicodedata

_NON_SLUG = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    """URL-safe slug: lowercase, diacritics stripped, non-alphanumerics to hyphens.

    Mechanical and lossy by design: ``director's-cut`` becomes
    ``director-s-cut`` (the apostrophe is a separator, not a dropped
    character), so category and tag URLs derive from one shared rule.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return _NON_SLUG.sub("-", stripped.lower()).strip("-")
