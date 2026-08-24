import io

from PIL import Image

from clipfit import cli


def _write_jpeg(path, w=800, h=600):
    Image.new("RGB", (w, h), (30, 90, 160)).save(path, format="JPEG")


def test_file_mode_writes_small_jpeg_as_png(tmp_path):
    src = tmp_path / "shot.jpeg"
    _write_jpeg(src)
    rc = cli.main([str(src)])
    assert rc == 0
    out = tmp_path / "shot_fit.png"
    assert out.exists()
    with Image.open(out) as img:
        assert img.format == "PNG"
        assert img.size == (800, 600)


def test_file_mode_writes_small_png(tmp_path):
    src = tmp_path / "pic.png"
    Image.new("RGB", (400, 300), (1, 2, 3)).save(src, format="PNG")
    rc = cli.main([str(src)])
    assert rc == 0
    out = tmp_path / "pic_fit.png"
    assert out.exists()
    with Image.open(out) as img:
        assert img.format == "PNG"


def test_file_mode_does_not_modify_source(tmp_path):
    src = tmp_path / "shot.jpeg"
    _write_jpeg(src)
    before = src.read_bytes()
    cli.main([str(src)])
    assert src.read_bytes() == before


def test_file_mode_missing_file(tmp_path):
    rc = cli.main([str(tmp_path / "nope.png")])
    assert rc == 1
