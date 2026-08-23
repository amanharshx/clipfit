import io

from PIL import Image

from clipfit.core import DEFAULT_MAX_BYTES, shrink_image_bytes


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
