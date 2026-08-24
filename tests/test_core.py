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
