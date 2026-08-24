import io
import sys

import pytest
from PIL import Image

import clipfit.clipboard as clipboard
from clipfit import cli


def _big_png(w=3000, h=2000) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (60, 150, 90)).save(buf, format="PNG")
    return buf.getvalue()


def test_no_clipboard_image(monkeypatch, capsys):
    monkeypatch.setattr(clipboard, "read_image", lambda *a, **k: None)
    rc = cli.main([])
    assert rc == 1
    assert "no image on the clipboard" in capsys.readouterr().out


def test_clipboard_success_writes_shrunk(monkeypatch):
    written = {}
    png = _big_png()
    monkeypatch.setattr(
        clipboard,
        "read_image",
        lambda *a, **k: (png, len(png)),
    )
    monkeypatch.setattr(clipboard, "write_png", lambda data: written.setdefault("data", data))
    rc = cli.main([])
    assert rc == 0
    # a shrunk PNG was written back, smaller than the original
    assert "data" in written
    with Image.open(io.BytesIO(written["data"])) as img:
        assert max(img.size) <= 1568


def test_clipboard_read_error(monkeypatch, capsys):
    def boom(*_a, **_k):
        raise clipboard.ClipboardError("no pyobjc")
    monkeypatch.setattr(clipboard, "read_image", boom)
    assert cli.main([]) == 2
    assert "no pyobjc" in capsys.readouterr().out


def test_clipboard_write_error(monkeypatch, capsys):
    png = _big_png()
    monkeypatch.setattr(
        clipboard,
        "read_image",
        lambda *a, **k: (png, len(png)),
    )

    def boom(_data):
        raise clipboard.ClipboardError("write failed")
    monkeypatch.setattr(clipboard, "write_png", boom)
    assert cli.main([]) == 2
    assert "write failed" in capsys.readouterr().out


needs_appkit = pytest.mark.skipif(
    sys.platform != "darwin" or not clipboard._APPKIT_OK,
    reason="AppKit pasteboard required",
)


class FakePasteboard:
    def __init__(self, types=None, write_ok=True):
        self.types = dict(types or {})
        self.write_ok = write_ok
        self.writes = []
        self.fetches = []
        self._change = 1

    def dataForType_(self, pb_type):
        self.fetches.append(pb_type)
        return self.types.get(pb_type)

    def clearContents(self):
        self.types.clear()
        self._change += 1
        return self._change

    def setData_forType_(self, data, pb_type):
        self.writes.append(pb_type)
        if not self.write_ok:
            return False
        self.types[pb_type] = data
        return True

    def changeCount(self):
        return self._change


def _small_png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (10, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


def _tiff(w: int, h: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (1, 2, 3)).save(buf, format="TIFF")
    return buf.getvalue()


def test_png_header_size_reads_ihdr():
    png = _small_png()
    assert clipboard.png_header_size(png) == (8, 8)


def test_png_header_size_rejects_truncated():
    assert clipboard.png_header_size(b"\x89PNG") is None
    assert clipboard.png_header_size(b"not-png") is None


@needs_appkit
def test_small_png_skips_tiff_fetch():
    png = _small_png()
    tiff = _tiff(8, 8)
    pb = FakePasteboard(
        types={
            clipboard.NSPasteboardTypePNG: png,
            clipboard.NSPasteboardTypeTIFF: tiff,
        }
    )
    got = clipboard.read_image(pasteboard=pb, max_dim=1568, max_bytes=3_700_000)
    assert got == (png, len(png))
    assert clipboard.NSPasteboardTypeTIFF not in pb.fetches


@needs_appkit
def test_oversized_png_fetches_tiff():
    png = _big_png()
    tiff = _tiff(3000, 2000)
    pb = FakePasteboard(
        types={
            clipboard.NSPasteboardTypePNG: png,
            clipboard.NSPasteboardTypeTIFF: tiff,
        }
    )
    data, original = clipboard.read_image(
        pasteboard=pb, max_dim=1568, max_bytes=3_700_000
    )
    assert data == tiff
    assert original == len(png)
    assert clipboard.NSPasteboardTypeTIFF in pb.fetches


@needs_appkit
def test_oversized_png_without_tiff_uses_png():
    png = _big_png()
    pb = FakePasteboard(types={clipboard.NSPasteboardTypePNG: png})
    data, original = clipboard.read_image(
        pasteboard=pb, max_dim=1568, max_bytes=3_700_000
    )
    assert data == png
    assert original == len(png)


@needs_appkit
def test_tiff_only_uses_tiff():
    tiff = _tiff(3000, 2000)
    pb = FakePasteboard(types={clipboard.NSPasteboardTypeTIFF: tiff})
    data, original = clipboard.read_image(
        pasteboard=pb, max_dim=1568, max_bytes=3_700_000
    )
    assert data == tiff
    assert original == len(tiff)


@needs_appkit
def test_read_falls_back_to_tiff():
    tiff = b"tiff-only"
    pb = FakePasteboard(types={clipboard.NSPasteboardTypeTIFF: tiff})
    assert clipboard.read_image(pasteboard=pb) == (tiff, len(tiff))


@needs_appkit
def test_read_empty_pasteboard_returns_none():
    assert clipboard.read_image(pasteboard=FakePasteboard()) is None


@needs_appkit
def test_write_png_sets_tiff_and_png():
    pb = FakePasteboard()
    png = _small_png()
    change = clipboard.write_png(png, pasteboard=pb)
    assert clipboard.NSPasteboardTypePNG in pb.writes
    assert clipboard.NSPasteboardTypeTIFF in pb.writes
    assert pb.types[clipboard.NSPasteboardTypePNG] is not None
    assert pb.types[clipboard.NSPasteboardTypeTIFF] is not None
    assert change == pb.changeCount()


@needs_appkit
def test_write_png_raises_when_set_fails():
    pb = FakePasteboard(write_ok=False)
    with pytest.raises(clipboard.ClipboardError, match="failed to write"):
        clipboard.write_png(_small_png(), pasteboard=pb)


@needs_appkit
def test_unique_pasteboard_roundtrip():
    # Named board, never the user's general clipboard.
    # Real hotkey + Accessibility still need a manual check on a Mac;
    # CI cannot drive that permission UI.
    pb = clipboard.NSPasteboard.pasteboardWithUniqueName()
    try:
        png = _small_png()
        clipboard.write_png(png, pasteboard=pb)
        data, original = clipboard.read_image(pasteboard=pb)
        assert data is not None
        with Image.open(io.BytesIO(data)) as img:
            assert img.format == "PNG"
            assert img.size == (8, 8)
        assert original == len(data)
    finally:
        pb.releaseGlobally()
