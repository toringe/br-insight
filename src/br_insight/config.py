"""Site configuration loading: taxonomy curation (later: site settings)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from br_insight.articles import Article


class TaxonomyError(ValueError):
    """Raised when the curated taxonomy is invalid against the corpus."""


@dataclass(frozen=True)
class TaxonomyAssignment:
    """Curated classification for a single article."""

    category: str
    tags: tuple[str, ...]


@dataclass(frozen=True)
class Taxonomy:
    """Curated vocabulary and per-article assignments."""

    categories: tuple[str, ...]
    tag_vocab: frozenset[str]
    assignments: Mapping[str, TaxonomyAssignment]


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys."""

    def construct_mapping(self, node, deep=False):
        seen = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=True)
            if key in seen:
                raise TaxonomyError(f"duplicate key in taxonomy: {key!r}")
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def _read_yaml(path: Path):
    with path.open(encoding="utf-8") as fh:
        return yaml.load(fh, Loader=_StrictLoader)


def load_taxonomy(root: Path) -> Taxonomy:
    """Parse ``_data/taxonomy.yaml`` from the site root."""
    data = _read_yaml(root / "_data" / "taxonomy.yaml")
    return Taxonomy(
        categories=tuple(data["categories"]),
        tag_vocab=frozenset(data["tag_vocab"]),
        assignments={
            slug: TaxonomyAssignment(entry["category"], tuple(entry["tags"]))
            for slug, entry in data["assignments"].items()
        },
    )


def apply_taxonomy(articles: Iterable[Article], taxonomy: Taxonomy) -> list[Article]:
    """Validate coverage and return new articles with curated category/tags.

    Every assignment must reference an article on disk, every tag must come
    from ``tag_vocab``, and every article must be assigned exactly once.
    Input articles are never mutated; enrichment uses ``dataclasses.replace``.
    """
    known_slugs = {article.slug for article in articles}
    unknown_slugs = sorted(set(taxonomy.assignments) - known_slugs)
    if unknown_slugs:
        raise TaxonomyError(
            "assignments reference unknown article slug(s): "
            + ", ".join(unknown_slugs)
        )

    unknown_tags = sorted(
        {tag for entry in taxonomy.assignments.values() for tag in entry.tags}
        - taxonomy.tag_vocab
    )
    if unknown_tags:
        raise TaxonomyError("unknown tag(s): " + ", ".join(unknown_tags))

    unassigned = sorted(known_slugs - set(taxonomy.assignments))
    if unassigned:
        raise TaxonomyError("unassigned article(s): " + ", ".join(unassigned))

    return [
        replace(
            article,
            category=taxonomy.assignments[article.slug].category,
            tags=list(taxonomy.assignments[article.slug].tags),
        )
        for article in articles
    ]
