import io
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image, features

from bench import benchmark as bench

WORKER = Path(__file__).resolve().parents[1] / "bench" / "cold_worker.py"


def test_p50_p95():
    p50, p95 = bench.p50_p95([10, 20, 30, 40, 50, 60, 70, 80, 90, 100])
    assert p50 == 55
    assert p95 == 100


def test_p95_fifteen_samples():
    samples = list(range(1, 16))
    _p50, p95 = bench.p50_p95(samples)
    # ceil(0.95 * 15) - 1 = 14 -> value 15
    assert p95 == 15


def test_machine_info_matches_pillow_features():
    info = bench.machine_info()
    assert info["pillow"] == Image.__version__
    assert info["zlib"] == (features.version_codec("zlib") or "unknown")
    try:
        expected_ng = features.version_feature("zlib_ng") or "none"
    except ValueError:
        expected_ng = "none"
    assert info["zlib-ng"] == expected_ng


def test_machine_info_zlib_ng_none_on_old_pillow(monkeypatch):
    def boom(_name):
        raise ValueError("unknown feature")

    monkeypatch.setattr(bench.features, "version_feature", boom)
    assert bench.machine_info()["zlib-ng"] == "none"


def test_corpus_kinds_are_valid_pngs():
    for kind in bench.CORPUS_KINDS:
        data = bench.make_corpus_png(kind, 64, 48)
        with Image.open(io.BytesIO(data)) as img:
            assert img.size == (64, 48)
            if kind == "transparency":
                assert "A" in img.getbands()
            elif kind in ("photo", "noisy"):
                assert img.mode == "RGB"
                r, g, b = img.split()
                assert r.tobytes() != g.tobytes() or g.tobytes() != b.tobytes()


def test_png_to_tiff_roundtrip():
    png = bench.make_corpus_png("browser", 32, 24)
    tiff = bench.png_to_tiff(png)
    with Image.open(io.BytesIO(tiff)) as img:
        assert img.format == "TIFF"
        assert img.size == (32, 24)


def test_resize_and_encode_do_not_decode(monkeypatch):
    img = Image.new("RGB", (200, 100), (8, 16, 32))

    def boom(*_a, **_k):
        raise AssertionError("resize/encode must not decode bytes")

    monkeypatch.setattr("bench.benchmark.Image.open", boom)
    resized = bench.resize_loaded(img, max_dim=50)
    assert max(resized.size) == 50
    png = bench.encode_resized(resized)
    assert png.startswith(b"\x89PNG")


def test_fmt_ms_uses_three_decimals_below_one_ms():
    assert "0.400" in bench._fmt_ms([0.4, 0.4, 0.4])


needs_darwin = pytest.mark.skipif(sys.platform != "darwin", reason="macOS pasteboard")


@needs_darwin
def test_unique_pasteboard_is_not_the_general_board():
    from clipfit import clipboard
    if not clipboard._APPKIT_OK:
        pytest.skip("AppKit unavailable")

    general = clipboard.NSPasteboard.generalPasteboard()
    with bench.unique_pasteboard() as pb:
        assert pb.name() != general.name()
        png = bench.make_corpus_png("browser", 16, 16)
        clipboard.write_png(png, pasteboard=pb)
        data, _orig = clipboard.read_image(pasteboard=pb)
        assert data is not None


def test_cold_worker_script_exists():
    assert WORKER.is_file()


def test_cold_worker_clipboard_failure_exits_nonzero():
    proc = subprocess.run(
        [
            sys.executable,
            str(WORKER),
            "--source",
            "clipfit-bench-missing-src",
            "--dest",
            "clipfit-bench-missing-dst",
        ],
        capture_output=True,
        text=True,
        cwd=str(WORKER.parent.parent),
    )
    assert proc.returncode != 0


@needs_darwin
def test_cold_subprocess_returns_samples():
    from clipfit import clipboard
    if not clipboard._APPKIT_OK:
        pytest.skip("AppKit unavailable")
    png = bench.make_corpus_png("browser", 32, 24)
    tiff = bench.png_to_tiff(png)
    samples = bench.cold_subprocess_samples(png, tiff, iters=1)
    assert len(samples) == 1
    assert samples[0] > 0
