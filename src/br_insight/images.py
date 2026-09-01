"""Build-time cover-variant generation (Task 14).

Every article's source cover is transposed into responsive WebP variants
plus JPEG fallbacks (crawlers and older browsers skip WebP) and a 16:9 card
crop set. Sources are never modified; outputs already newer than the source
are left alone so repeated in-tree builds stay idempotent.

Naming contract:
    cover-{W}.webp|.jpg          full-bleed hero candidates
    cover-crop-{W}.webp|.jpg     16:9 center crop for cards/featured

``W`` is always the *actual* pixel width written (never wider than the
source), and every width reported by :class:`CoverVariants` is guaranteed
to exist on disk after :func:`generate_cover_variants` runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

# Width ladder per use site.
HERO_WIDTHS: tuple[int, ...] = (480, 800, 1280)
CROP_WIDTHS: tuple[int, ...] = (480, 800, 1280)

# Center-crop aspect ratio (filename fragment → ratio).
CROP_RATIOS: dict[str, float] = {"16/9": 16 / 9}

JPEG_QUALITY = 80
WEBP_QUALITY = 80

_RESAMPLE = Image.Resampling.LANCZOS

_SOURCES = ("cover.png", "cover.jpg")


@dataclass(frozen=True)
class CoverVariants:
    """Widths actually generated for one article cover."""

    source: str
    hero: tuple[int, ...]
    crop: tuple[int, ...]


def _flatten(im: Image.Image) -> Image.Image:
    """Composite transparency-bearing modes onto white for JPEG output."""
    if im.mode in ("RGBA", "LA", "PA", "P"):
        rgba = im.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        return Image.alpha_composite(background, rgba).convert("RGB")
    return im.convert("RGB")


def _center_crop(im: Image.Image, ratio: float) -> Image.Image:
    """Largest centered rect of ``ratio`` (w/h) inside ``im``."""
    w, h = im.size
    if w / h > ratio:  # too wide → trim width
        target_w = round(h * ratio)
        left = (w - target_w) // 2
        return im.crop((left, 0, left + target_w, h))
    target_h = round(w / ratio)  # too tall → trim height
    top = (h - target_h) // 2
    return im.crop((0, top, w, top + target_h))


def _effective_widths(requested: tuple[int, ...], natural: int) -> tuple[int, ...]:
    """Dedupe requested widths, capped at the natural pixel width."""
    widths = {min(w, natural) for w in requested if w > 0}
    widths.discard(0)
    return tuple(sorted(widths))


def _is_current(output: Path, source_mtime_ns: int) -> bool:
    """True when ``output`` exists and is at least as new as the source."""
    try:
        return output.stat().st_mtime_ns >= source_mtime_ns
    except FileNotFoundError:
        return False


def generate_cover_variants(
    src_dir: Path, dest: Path | None = None
) -> CoverVariants | None:
    """Generate every missing/stale variant for a single article directory.

    ``src_dir`` is ``library/<slug>/`` holding the source cover;
    ``dest`` defaults to ``src_dir`` (in-tree regeneration). Returns the
    plan of generated widths, or ``None`` when no usable source exists.
    """
    dest_dir = Path(dest) if dest is not None else src_dir
    source_name = next(
        (name for name in _SOURCES if (src_dir / name).is_file()), None
    )
    if source_name is None:
        return None
    source = src_dir / source_name
    source_mtime = source.stat().st_mtime_ns

    with Image.open(source) as opened:
        opened.load()
        base_rgb = _flatten(opened)

    try:
        hero_widths = _effective_widths(HERO_WIDTHS, base_rgb.size[0])
        crop_widths = _effective_widths(
            CROP_WIDTHS, _center_crop(base_rgb, CROP_RATIOS["16/9"]).size[0]
        )
        plan = CoverVariants(
            source=source_name,
            hero=hero_widths,
            crop=crop_widths,
        )

        images: list[tuple[str, Image.Image]] = []
        for width in hero_widths:
            scaled = base_rgb.resize((width, round(base_rgb.size[1] * width / base_rgb.size[0])), _RESAMPLE) \
                if width != base_rgb.size[0] else base_rgb
            images.append((f"cover-{width}", scaled))
        cropped = _center_crop(base_rgb, CROP_RATIOS["16/9"])
        for width in crop_widths:
            scaled = (
                cropped.resize((width, round(cropped.size[1] * width / cropped.size[0])), _RESAMPLE)
                if width != cropped.size[0]
                else cropped
            )
            images.append((f"cover-crop-{width}", scaled))
        for stem, image in images:
            output_stem = dest_dir / stem
            if not _is_current(output_stem.with_suffix(".webp"), source_mtime):
                _write(dest_dir, f"{stem}.webp", image, "WEBP", quality=WEBP_QUALITY)
            if not _is_current(output_stem.with_suffix(".jpg"), source_mtime):
                _write(dest_dir, f"{stem}.jpg", image, "JPEG", quality=JPEG_QUALITY)
    finally:
        base_rgb.close()
    return plan


def _write(dest_dir: Path, filename: str, image: Image.Image, fmt: str, **params):
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / filename
    image.save(path, fmt, **params)
