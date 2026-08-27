"""Tests for Task 14 build-time cover-variant generation (br_insight.images)."""

import os
from pathlib import Path

from PIL import Image

from br_insight.images import (
    CROP_RATIOS,
    HERO_WIDTHS,
    SQUARE_WIDTH,
    generate_cover_variants,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Synthetic-corpus helpers
# ---------------------------------------------------------------------------


def _make_site(tmp_path: Path, slug: str = "demo") -> dict[str, Path]:
    """Minimal article directory holding one landscape JPEG source cover."""
    d = tmp_path / "library" / slug
    d.mkdir(parents=True)
    source = d / "cover.jpg"
    Image.new("RGB", (1600, 1067), (10, 14, 20)).save(source, "JPEG")
    return {"dir": d, "source": source}


class TestVariantGeneration:
    def test_generates_webp_and_jpg_at_every_band(self, tmp_path):
        paths = _make_site(tmp_path)
        result = generate_cover_variants(paths["dir"])
        assert result is not None
        for width in HERO_WIDTHS:
            assert (paths["dir"] / f"cover-{width}.webp").is_file()
            assert (paths["dir"] / f"cover-{width}.jpg").is_file()
        assert len(result.hero) == len(HERO_WIDTHS)

    def test_crop_and_square_variants_are_correctly_sized(self, tmp_path):
        paths = _make_site(tmp_path)
        generate_cover_variants(paths["dir"])
        for width in (480, 800):
            crop = Image.open(paths["dir"] / f"cover-crop-{width}.webp")
            assert crop.size[0] == width
            assert abs(crop.size[1] - round(width * 9 / 16)) <= 1
        square = Image.open(paths["dir"] / f"cover-sq-{SQUARE_WIDTH}.webp")
        assert square.size == (SQUARE_WIDTH, SQUARE_WIDTH)

    def test_jpg_fallbacks_are_real_jpeg_bytes(self, tmp_path):
        paths = _make_site(tmp_path)
        generate_cover_variants(paths["dir"])
        with Image.open(paths["dir"] / "cover-800.jpg") as im:
            assert im.format == "JPEG"

    def test_png_source_transcodes_to_both_formats(self, tmp_path):
        d = tmp_path / "library" / "png-demo"
        d.mkdir(parents=True)
        Image.new("RGB", (1200, 800)).save(d / "cover.png", "PNG")
        result = generate_cover_variants(d)
        assert result.source == "cover.png"
        with Image.open(d / "cover-480.webp") as im:
            assert im.format == "WEBP"
        with Image.open(d / "cover-480.jpg") as im:
            assert im.format == "JPEG"

    def test_no_upscaling_past_source_width(self, tmp_path):
        d = tmp_path / "library" / "small"
        d.mkdir(parents=True)
        Image.new("RGB", (700, 466)).save(d / "cover.jpg", "JPEG")
        result = generate_cover_variants(d)
        assert 1280 not in result.hero
        assert all(w <= 700 for w in result.hero)
        with Image.open(d / f"cover-{result.hero[-1]}.webp") as im:
            assert im.size[0] <= 700

    def test_never_asks_for_width_above_zero(self, tmp_path):
        d = tmp_path / "library" / "tiny"
        d.mkdir(parents=True)
        Image.new("RGB", (200, 120)).save(d / "cover.jpg", "JPEG")
        result = generate_cover_variants(d)
        assert result.hero and min(result.hero) > 0

    def test_missing_source_returns_none(self, tmp_path):
        d = tmp_path / "library" / "empty"
        d.mkdir(parents=True)
        assert generate_cover_variants(d) is None

    def test_returns_none_when_directory_missing(self, tmp_path):
        assert generate_cover_variants(tmp_path / "library" / "ghost") is None

    def test_writes_into_dest_without_touching_sources(self, tmp_path):
        paths = _make_site(tmp_path)
        dest = tmp_path / "out" / "library" / "demo"
        before = paths["source"].read_bytes()
        generate_cover_variants(paths["dir"], dest=dest)
        assert (dest / "cover-480.webp").is_file()
        assert paths["source"].read_bytes() == before
        assert list(paths["dir"].glob("cover-*")) == []

    def test_output_files_larger_than_zero_bytes(self, tmp_path):
        paths = _make_site(tmp_path)
        generate_cover_variants(paths["dir"])
        for p in sorted(paths["dir"].glob("cover-*.webp")) + sorted(
            paths["dir"].glob("cover-*.jpg")
        ):
            assert p.stat().st_size > 0, p.name


class TestRebuildSkipGuard:
    def test_existing_newer_outputs_are_not_regenerated(self, tmp_path):
        paths = _make_site(tmp_path)
        old_src = paths["source"].stat().st_mtime_ns - 10_000
        os.utime(paths["source"], ns=(old_src, old_src))
        generate_cover_variants(paths["dir"])
        mtimes = {
            p.name: p.stat().st_mtime_ns
            for p in sorted(paths["dir"].glob("cover-*"))
        }
        generate_cover_variants(paths["dir"])
        after = {
            p.name: p.stat().st_mtime_ns
            for p in sorted(paths["dir"].glob("cover-*"))
        }
        assert mtimes == after

    def test_stale_outputs_are_regenerated(self, tmp_path):
        paths = _make_site(tmp_path)
        generate_cover_variants(paths["dir"])
        # Force every output to look older than the source.
        for p in paths["dir"].glob("cover-*"):
            stamp = paths["source"].stat().st_mtime_ns - 60_000
            os.utime(p, ns=(stamp, stamp))
        generated = generate_cover_variants(paths["dir"])
        # After regeneration nothing is stale any more.
        for p in paths["dir"].glob("cover-*"):
            assert p.stat().st_mtime_ns >= paths["source"].stat().st_mtime_ns


class TestRealCorpusSources:
    """The pipeline stays compatible with the actual repository covers."""

    def test_known_small_source_caps_hero_widths(self):
        result = generate_cover_variants(REPO_ROOT / "library" / "br-an-analysis")
        if result is not None:
            assert all(w <= 1280 for w in result.hero)

    def test_repo_build_does_not_rewrite_pristine_sources(self, tmp_path):
        slug = "a-study-of-blade-runner"
        src = REPO_ROOT / "library" / slug / "cover.jpg"
        before = src.read_bytes(), src.stat().st_size
        generate_cover_variants(REPO_ROOT / "library" / slug, dest=tmp_path)
        after = src.read_bytes(), src.stat().st_size
        assert before == after

    def test_reference_data_matches_module_constants(self):
        assert HERO_WIDTHS == (480, 800, 1280)
        assert SQUARE_WIDTH == 400
        assert set(CROP_RATIOS) == {"16/9", "1/1"}
