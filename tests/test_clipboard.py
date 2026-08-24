import io

from PIL import Image

import clipfit.clipboard as clipboard
from clipfit import cli


def _big_png(w=3000, h=2000) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (60, 150, 90)).save(buf, format="PNG")
    return buf.getvalue()


def test_no_clipboard_image(monkeypatch, capsys):
    monkeypatch.setattr(clipboard, "read_image", lambda: None)
    rc = cli.main([])
    assert rc == 1
    assert "no image on the clipboard" in capsys.readouterr().out


def test_clipboard_success_writes_shrunk(monkeypatch):
    written = {}
    monkeypatch.setattr(clipboard, "read_image", lambda: _big_png())
    monkeypatch.setattr(clipboard, "write_png", lambda data: written.setdefault("data", data))
    rc = cli.main([])
    assert rc == 0
    # a shrunk PNG was written back, smaller than the original
    assert "data" in written
    with Image.open(io.BytesIO(written["data"])) as img:
        assert max(img.size) <= 1568


def test_clipboard_read_error(monkeypatch, capsys):
    def boom():
        raise clipboard.ClipboardError("no pyobjc")
    monkeypatch.setattr(clipboard, "read_image", boom)
    assert cli.main([]) == 2
    assert "no pyobjc" in capsys.readouterr().out


def test_clipboard_write_error(monkeypatch, capsys):
    monkeypatch.setattr(clipboard, "read_image", lambda: _big_png())

    def boom(_data):
        raise clipboard.ClipboardError("write failed")
    monkeypatch.setattr(clipboard, "write_png", boom)
    assert cli.main([]) == 2
    assert "write failed" in capsys.readouterr().out
