import io

from PIL import Image

from clipfit.core import shrink_image_bytes


def _png(w: int, h: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (120, 30, 200)).save(buf, format="PNG")
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
