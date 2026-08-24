import json
import sys
from pathlib import Path

import pytest
from PIL import Image

from bench import benchmark as bench


def test_p50_p95():
    p50, p95 = bench.p50_p95([10, 20, 30, 40, 50, 60, 70, 80, 90, 100])
    assert p50 == 50
    assert p95 == 100


def test_machine_info_has_runtime():
    info = bench.machine_info()
    assert "python" in info
    assert "pillow" in info
    assert "platform" in info


def test_corpus_kinds_are_valid_pngs():
    for kind in bench.CORPUS_KINDS:
        data = bench.make_corpus_png(kind, 64, 48)
        with Image.open(__import__("io").BytesIO(data)) as img:
            assert img.size == (64, 48)
            if kind == "transparency":
                assert "A" in img.getbands()


def test_png_to_tiff_roundtrip():
    png = bench.make_corpus_png("browser", 32, 24)
    tiff = bench.png_to_tiff(png)
    with Image.open(__import__("io").BytesIO(tiff)) as img:
        assert img.format == "TIFF"
        assert img.size == (32, 24)


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
    path = Path(__file__).resolve().parents[1] / "bench" / "cold_worker.py"
    assert path.is_file()


def test_cold_subprocess_returns_samples():
    data = bench.make_corpus_png("browser", 32, 24)
    samples = bench.cold_subprocess_samples(data, iters=1)
    assert len(samples) == 1
    assert samples[0] > 0
