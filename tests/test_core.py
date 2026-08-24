import io

import pytest
from PIL import Image

from clipfit.core import (
    DEFAULT_MAX_BYTES,
    QUALITY_FLOOR,
    ByteBudgetError,
    _encode_png_quantized,
    _normalize_for_png,
    shrink_image_bytes,
)


def _png(w: int, h: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (120, 30, 200)).save(buf, format="PNG")
    return buf.getvalue()


def _noisy_png(w: int, h: int) -> bytes:
    """High-entropy image that does NOT compress small as PNG."""
    noise = Image.effect_noise((w, h), 120).convert("RGB")
    buf = io.BytesIO()
    noise.save(buf, format="PNG")
    return buf.getvalue()


def test_retries_level_6_before_quantizing_when_level_3_misses_budget(monkeypatch):
    # Level 3 can land a few KB over the budget when level 6 still fits.
    # Quantizing in that gap would drop full-color RGB to a 256-color palette.
    levels = []

    def encode(img, compress_level=3):
        levels.append(compress_level)
        buf = io.BytesIO()
        img.save(buf, format="PNG", compress_level=6)
        png = buf.getvalue()
        if compress_level == 3:
            return png + bytes(max(0, DEFAULT_MAX_BYTES + 1 - len(png)))
        return png

    monkeypatch.setattr("clipfit.core._encode_png", encode)

    def boom(*_args, **_kwargs):
        raise AssertionError("quantizer should not run when level 6 fits")

    monkeypatch.setattr("clipfit.core._encode_png_quantized", boom)

    out, res = shrink_image_bytes(_png(4000, 3000), max_dim=1568)
    assert levels == [3, 6]
    assert "quantized" not in res.strategy
    with Image.open(io.BytesIO(out)) as img:
        assert img.mode != "P"


def test_skips_level_6_when_level_3_is_far_over_budget(monkeypatch):
    levels = []

    def encode(img, compress_level=3):
        levels.append(compress_level)
        buf = io.BytesIO()
        img.save(buf, format="PNG", compress_level=6)
        png = buf.getvalue()
        if compress_level == 3:
            return png + bytes(DEFAULT_MAX_BYTES * 2)
        return png

    monkeypatch.setattr("clipfit.core._encode_png", encode)

    def quant(*_args, **_kwargs):
        buf = io.BytesIO()
        Image.new("RGB", (8, 8), (1, 2, 3)).quantize(colors=256).save(buf, format="PNG")
        return buf.getvalue()

    monkeypatch.setattr("clipfit.core._encode_png_quantized", quant)

    _out, res = shrink_image_bytes(_png(4000, 3000), max_dim=1568)
    assert levels == [3]
    assert "quantized" in res.strategy


def test_downscales_oversized_landscape():
    data = _png(4000, 3000)
    out, res = shrink_image_bytes(data, max_dim=1568)
    assert res.changed
    assert max(res.new_size) == 1568
    # aspect ratio preserved
    assert res.new_size == (1568, 1176)
    # output is a valid, smaller image
    with Image.open(io.BytesIO(out)) as img:
        assert img.size == (1568, 1176)
    assert res.new_bytes < res.original_bytes


def test_downscales_oversized_portrait():
    data = _png(1000, 5000)
    _out, res = shrink_image_bytes(data, max_dim=2000)
    assert res.changed
    assert res.new_size == (400, 2000)


def test_leaves_small_image_untouched():
    data = _png(800, 600)
    out, res = shrink_image_bytes(data, max_dim=1568)
    assert not res.changed
    assert out == data
    assert res.new_size == (800, 600)


def test_exact_limit_is_untouched():
    data = _png(1568, 1000)
    _out, res = shrink_image_bytes(data, max_dim=1568)
    assert not res.changed


def test_fits_byte_budget_via_quantize_or_resize():
    # A noisy 1568px PNG easily exceeds a tight budget; output must fit it.
    data = _noisy_png(1600, 1200)
    budget = 400_000
    out, res = shrink_image_bytes(data, max_dim=1568, max_bytes=budget)
    assert res.changed
    assert len(out) <= budget, f"output {len(out)} exceeds budget {budget}"
    # still a valid, decodable PNG
    with Image.open(io.BytesIO(out)) as img:
        assert max(img.size) <= 1568


def test_small_but_within_byte_budget_untouched():
    data = _png(800, 600)  # tiny flat PNG, well under any budget
    out, res = shrink_image_bytes(data, max_dim=1568, max_bytes=DEFAULT_MAX_BYTES)
    assert not res.changed
    assert out == data


def test_oversized_dims_but_recompresses_under_budget():
    # Big dimensions, simple content: dimension cap applies, bytes fit as PNG.
    data = _png(4000, 3000)
    out, res = shrink_image_bytes(data, max_dim=1568, max_bytes=DEFAULT_MAX_BYTES)
    assert res.changed
    assert max(res.new_size) == 1568
    assert len(out) <= DEFAULT_MAX_BYTES


def test_skips_quantizer_when_full_color_png_fits(monkeypatch):
    # Flat images fit as full-color PNG. Quantizing them is wasted latency.
    def boom(*_args, **_kwargs):
        raise AssertionError("quantizer should not run when full-color PNG fits")

    monkeypatch.setattr("clipfit.core._encode_png_quantized", boom)
    data = _png(4000, 3000)
    out, res = shrink_image_bytes(data, max_dim=1568, max_bytes=DEFAULT_MAX_BYTES)
    assert res.changed
    assert "quantized" not in res.strategy
    assert len(out) <= DEFAULT_MAX_BYTES



def test_output_always_fits_byte_budget():
    # A noisy image with a tight budget must still come out under the budget.
    data = _noisy_png(1600, 1200)
    budget = 80_000
    out, res = shrink_image_bytes(data, max_dim=1568, max_bytes=budget)
    assert res.changed
    assert len(out) <= budget
    with Image.open(io.BytesIO(out)) as img:
        assert img.format == "PNG"


def test_can_resize_below_quality_floor():
    # A budget too small to fit even at the floor must push resolution lower,
    # and the result must warn that it went below the readable size.
    data = _noisy_png(1600, 1200)
    budget = 12_000
    out, res = shrink_image_bytes(data, max_dim=1568, max_bytes=budget)
    assert len(out) <= budget
    assert max(res.new_size) < QUALITY_FLOOR
    assert "hard to read" in res.note


def test_tries_quality_floor_before_shrinking_below_it():
    # A budget that fits at 640px (small palette) but not at the larger step
    # above it must land exactly on 640px, not skip past to ~589px.
    data = _noisy_png(1600, 1200)
    base = Image.open(io.BytesIO(data))

    def size_at(edge: int, colors: int) -> int:
        scale = edge / 1600
        im = base.resize((round(1600 * scale), round(1200 * scale)), Image.Resampling.LANCZOS)
        return len(_encode_png_quantized(_normalize_for_png(im), colors))

    budget = size_at(QUALITY_FLOOR, 64)  # 640px / 64-color fits exactly
    out, res = shrink_image_bytes(data, max_dim=1568, max_bytes=budget)
    assert len(out) <= budget
    assert max(res.new_size) == QUALITY_FLOOR


def test_impossible_budget_raises():
    # A budget smaller than any possible PNG must raise, so a successful return
    # always means the output fit. Raising also proves the loop terminates.
    data = _noisy_png(1600, 1200)
    with pytest.raises(ByteBudgetError):
        shrink_image_bytes(data, max_dim=1568, max_bytes=10)


def test_max_dim_below_floor_does_not_blame_budget():
    # Going below 640px because the user asked for --max-dim 500 (with plenty of
    # byte budget) must not claim the byte budget forced it.
    data = _png(1600, 1200)
    _out, res = shrink_image_bytes(data, max_dim=500, max_bytes=DEFAULT_MAX_BYTES)
    assert max(res.new_size) == 500
    assert "byte budget" not in res.note
    assert "hard to read" in res.note


def _jpeg(w: int, h: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (30, 90, 160)).save(buf, format="JPEG")
    return buf.getvalue()


def test_force_png_reencodes_small_image():
    # Without force_png this is a no-op; with it, always re-encode to PNG.
    data = _png(800, 600)
    out, res = shrink_image_bytes(data, force_png=True)
    assert res.changed
    assert res.new_size == (800, 600)
    with Image.open(io.BytesIO(out)) as img:
        assert img.format == "PNG"


def test_force_png_converts_jpeg_to_png():
    data = _jpeg(800, 600)
    out, res = shrink_image_bytes(data, force_png=True)
    assert res.changed
    with Image.open(io.BytesIO(out)) as img:
        assert img.format == "PNG"
        assert img.size == (800, 600)


def test_original_bytes_is_report_only_and_does_not_skip_budget():
    # A small original_bytes override must not pass through a large payload.
    tiff_buf = io.BytesIO()
    Image.effect_noise((400, 300), 120).convert("RGB").save(tiff_buf, format="TIFF")
    tiff = tiff_buf.getvalue()
    assert len(tiff) > 1024

    out, res = shrink_image_bytes(
        tiff, max_dim=1568, max_bytes=1024, original_bytes=1
    )
    assert len(out) <= 1024
    assert res.new_bytes == len(out)
    assert res.original_bytes == 1
    assert res.changed


def test_original_bytes_reports_png_size_when_processing_tiff():
    png = _png(4000, 3000)
    tiff_buf = io.BytesIO()
    Image.new("RGB", (4000, 3000), (120, 30, 200)).save(tiff_buf, format="TIFF")
    tiff = tiff_buf.getvalue()
    out, res = shrink_image_bytes(
        tiff, max_dim=1568, original_bytes=len(png), force_png=True
    )
    assert res.original_bytes == len(png)
    assert res.changed
    assert len(out) <= DEFAULT_MAX_BYTES
    with Image.open(io.BytesIO(out)) as img:
        assert img.format == "PNG"


def test_exif_transpose_result_is_not_copied_again(monkeypatch):
    # ImageOps.exif_transpose already returns a copy (or a transposed image).
    # A second copy doubles peak RAM (~58 MiB extra at 6K RGB).
    n = {"copies": 0}
    orig = Image.Image.copy

    def spy(self):
        n["copies"] += 1
        return orig(self)

    monkeypatch.setattr(Image.Image, "copy", spy)
    shrink_image_bytes(_png(800, 600))
    assert n["copies"] == 1


def test_force_png_applies_exif_orientation():
    # A 40x20 JPEG tagged Orientation=6 displays as 20x40. The output PNG must
    # bake in that rotation (PNG has no orientation tag), not stay sideways.
    img = Image.new("RGB", (40, 20), (200, 10, 10))
    exif = img.getexif()
    exif[0x0112] = 6  # Orientation
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    data = buf.getvalue()

    out, res = shrink_image_bytes(data, force_png=True)
    assert res.new_size == (20, 40)
    with Image.open(io.BytesIO(out)) as result:
        assert result.size == (20, 40)
        assert result.getexif().get(0x0112, 1) == 1  # no leftover orientation
