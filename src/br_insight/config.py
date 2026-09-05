"""Site configuration loading: curated taxonomy and site settings."""

from __future__ import annotations

import os
import subprocess
import warnings
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from br_insight.articles import Article


class TaxonomyError(ValueError):
    """Raised when the curated taxonomy is invalid against the corpus."""


class SiteConfigError(ValueError):
    """Raised when the site configuration is invalid against the corpus."""


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
                raise TaxonomyError(f"duplicate YAML key: {key!r}")
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


# ---------------------------------------------------------------------------
# Site settings (_data/site.yaml)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NavItem:
    """Single top-level navigation entry."""

    label: str
    href: str


@dataclass(frozen=True)
class FeaturedConfig:
    """Featured-article selection: explicit slug or monthly rotation."""

    slug: str
    fallback: str


@dataclass(frozen=True)
class SocialLinks:
    """Owner social profiles surfaced in page footers."""

    twitter: str


@dataclass(frozen=True)
class FxToggle:
    """On/off switch for a single atmosphere effect."""

    enabled: bool


@dataclass(frozen=True)
class FlickerFx:
    """Neon-flicker switches (``welcome`` is consumed by fx.js — Task 13)."""

    enabled: bool
    welcome: bool


@dataclass(frozen=True)
class RainFx:
    """Tunable parameters for the client-side rain effect."""

    enabled: bool
    density: int
    speed: float
    tier_auto: bool


@dataclass(frozen=True)
class FxConfig:
    """Client-side atmosphere effects (consumed by the FX task)."""

    enabled: bool
    atmosphere_toggle: bool
    rain: RainFx
    flicker: FlickerFx
    scanlines: FxToggle
    grain: FxToggle


@dataclass(frozen=True)
class SiteConfig:
    """Typed view over ``_data/site.yaml``, backed by complete defaults."""

    name: str
    tagline: str
    base_url: str
    established: int
    featured: FeaturedConfig
    social: SocialLinks
    nav: tuple[NavItem, ...]
    fx: FxConfig

    @classmethod
    def load(cls, root: Path) -> SiteConfig:
        return load_site_config(root)


_SITE_DEFAULTS: dict = {
    "name": "Blade Runner Insight",
    "tagline": "In-depth analytical perspectives on Ridley Scott's Blade Runner",
    "base_url": "https://www.br-insight.com",
    "established": 1996,
    "featured": {"slug": "", "fallback": "monthly-rotation"},
    "social": {"twitter": ""},
    "nav": [
        {"label": "Home", "href": "/"},
        {"label": "Library", "href": "/library/"},
        {"label": "Topics", "href": "/topics/"},
        {"label": "About", "href": "/about.html"},
    ],
    "fx": {
        "enabled": True,
        "atmosphere_toggle": True,
        "rain": {"enabled": True, "density": 120, "speed": 1.0, "tier_auto": True},
        "flicker": {"enabled": True, "welcome": True},
        "scanlines": {"enabled": True},
        "grain": {"enabled": True},
    },
}


def _deep_merge(base: Mapping, override: Mapping) -> dict:
    """Recursively merge ``override`` onto ``base``; scalars/lists replace."""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _build_fx(data: Mapping) -> FxConfig:
    return FxConfig(
        enabled=bool(data["enabled"]),
        atmosphere_toggle=bool(data["atmosphere_toggle"]),
        rain=RainFx(
            enabled=bool(data["rain"]["enabled"]),
            density=int(data["rain"]["density"]),
            speed=float(data["rain"]["speed"]),
            tier_auto=bool(data["rain"]["tier_auto"]),
        ),
        flicker=FlickerFx(
            enabled=bool(data["flicker"]["enabled"]),
            welcome=bool(data["flicker"]["welcome"]),
        ),
        scanlines=FxToggle(bool(data["scanlines"]["enabled"])),
        grain=FxToggle(bool(data["grain"]["enabled"])),
    )


def _build_site_config(data: Mapping) -> SiteConfig:
    return SiteConfig(
        name=str(data["name"]),
        tagline=str(data["tagline"]),
        base_url=str(data["base_url"]),
        established=int(data["established"]),
        featured=FeaturedConfig(
            slug=str(data["featured"]["slug"]),
            fallback=str(data["featured"]["fallback"]),
        ),
        social=SocialLinks(twitter=str(data["social"]["twitter"])),
        nav=tuple(
            NavItem(label=str(entry["label"]), href=str(entry["href"]))
            for entry in data["nav"]
        ),
        fx=_build_fx(data["fx"]),
    )


def load_site_config(root: Path) -> SiteConfig:
    """Parse ``_data/site.yaml`` merged over built-in defaults.

    A missing file or empty document yields the untouched defaults; nested
    mappings merge key-by-key so partial overrides never drop sibling keys.
    Unknown top-level keys emit a loud ``UserWarning`` and are ignored.
    """
    path = root / "_data" / "site.yaml"
    data: Mapping = {}
    if path.exists():
        try:
            data = _read_yaml(path) or {}
        except TaxonomyError as exc:  # duplicate keys surface with site context
            raise SiteConfigError(str(exc)) from exc
    unknown = sorted(set(data) - set(_SITE_DEFAULTS))
    if unknown:
        warnings.warn(
            f"{path.name}: ignoring unknown top-level key(s): "
            + ", ".join(unknown),
            stacklevel=2,
        )
        data = {key: value for key, value in data.items() if key in _SITE_DEFAULTS}
    return _build_site_config(_deep_merge(_SITE_DEFAULTS, data))


def resolve_featured(
    site: SiteConfig, articles: Iterable[Article], year_month: str
) -> Article:
    """Pick the featured article for ``year_month`` (``YYYYMM``).

    With an explicit ``site.featured.slug`` set, that article must exist in
    the corpus. Otherwise a deterministic monthly rotation applies: article
    slugs sorted alphabetically, indexed by ``int(year_month) % len(slugs)``.
    """
    by_slug = {article.slug: article for article in articles}
    slug = site.featured.slug.strip()
    if slug:
        if slug not in by_slug:
            raise SiteConfigError(
                f"featured slug does not match any article: {slug!r}"
            )
        return by_slug[slug]
    slugs = sorted(by_slug)
    if not slugs:
        raise SiteConfigError("no articles available for featured rotation")
    return by_slug[slugs[int(year_month) % len(slugs)]]


ARCHIVE_PICK_COUNT = 3


def cyrb53(text: str) -> int:
    """cyrb53 string hash (32-bit ops, 53-bit output).

    The client carousel (assets/js/modules/archive.js) implements the
    identical function, so build-time picks and view-time picks agree
    exactly. Slugs are slugify() output, i.e. ASCII, where the JS
    charCodeAt loop and this code-point loop see the same input.
    """
    h1 = 0xDEADBEEF
    h2 = 0x41C6CE57
    for ch in text:
        c = ord(ch)
        h1 = ((h1 ^ c) * 2654435761) & 0xFFFFFFFF
        h2 = ((h2 ^ c) * 1597334677) & 0xFFFFFFFF
    h1 = (((h1 ^ (h1 >> 16)) * 2246822507) & 0xFFFFFFFF) ^ (
        ((h2 ^ (h2 >> 13)) * 3266489909) & 0xFFFFFFFF
    )
    h1 &= 0xFFFFFFFF
    h2 = ((h2 ^ (h2 >> 16)) * 2246822507) & 0xFFFFFFFF
    h2 ^= ((h1 ^ (h1 >> 13)) * 3266489909) & 0xFFFFFFFF
    h2 &= 0xFFFFFFFF
    return (2097151 & h2) * 4294967296 + h1


def cyrb53_hex(text: str) -> str:
    """cyrb53 as 13 hex chars so lexicographic sort == numeric sort."""
    return f"{cyrb53(text):013x}"


def resolve_archive_picks(
    articles: Iterable[Article],
    iso_year_week: str,
    exclude_slug: str | None = None,
) -> list[Article]:
    """Deterministic weekly picks for the home "From the archive" row.

    Orders article slugs by ``cyrb53_hex(slug + ":" + iso_year_week)``
    (slug as tie-break) and takes the first ``ARCHIVE_PICK_COUNT``,
    returned newest-first, so the same week always yields the same picks
    and a new week reshuffles them. The featured essay (``exclude_slug``)
    is excluded to avoid duplicating the hero card.
    """
    pool = sorted(
        (a for a in articles if a.slug != exclude_slug),
        key=lambda a: a.slug,
    )
    if not pool:
        return []
    picks = sorted(
        pool,
        key=lambda a: (cyrb53_hex(f"{a.slug}:{iso_year_week}"), a.slug),
    )[:ARCHIVE_PICK_COUNT]
    return sorted(picks, key=lambda a: a.date, reverse=True)


_DEV_BRANCH = "dev"

# Branch-name env vars, in probe order: Cloudflare Pages CI, GitHub
# Actions, Cloudflare Workers Builds, then other CI conventions before
# falling back to the local checkout.
_BRANCH_ENV_VARS = (
    "CF_PAGES_BRANCH",
    "GITHUB_REF_NAME",
    "GIT_BRANCH",
    "BRANCH_NAME",
)


def _git_branch() -> str | None:
    """Current branch of the local checkout, tolerating any git failure."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def dev_banner_enabled() -> bool:
    """Show the DEVELOPMENT VERSION banner? True only for dev builds.

    Deliberately a build-time decision, not a template fact: the banner
    markup merges identically across branches, while this probe keeps
    the rendered output branch-conditional. ``BRI_DEV_BANNER`` ("1"/"0")
    overrides every probe — handy for forcing a local preview either
    way. Probe order: explicit override, then CI-provided branch names
    (Cloudflare Pages, GitHub Actions, Workers Builds, generic), then
    the local checkout's branch.
    """
    override = os.environ.get("BRI_DEV_BANNER")
    if override is not None:
        return override.strip() == "1"
    branch = next(
        (os.environ[name] for name in _BRANCH_ENV_VARS if os.environ.get(name)),
        None,
    ) or _git_branch()
    return branch is not None and branch.strip() == _DEV_BRANCH
