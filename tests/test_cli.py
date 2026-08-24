import importlib
import io

import pytest
from PIL import Image

from clipfit import cli
import clipfit.hotkey as hotkey


def _make_png(path, w=400, h=300):
    Image.new("RGB", (w, h), (10, 20, 30)).save(path, format="PNG")


def test_help_prints_usage(capsys):
    assert cli.main(["--help"]) == 0
    out = capsys.readouterr().out
    assert "USAGE" in out


def test_version(capsys):
    assert cli.main(["--version"]) == 0
    assert "clipfit" in capsys.readouterr().out


def test_missing_file(tmp_path, capsys):
    rc = cli.main([str(tmp_path / "nope.png")])
    assert rc == 1
    assert "file not found" in capsys.readouterr().out


def test_directory_input_is_rejected(tmp_path, capsys):
    rc = cli.main([str(tmp_path)])
    assert rc == 1
    assert "not a file" in capsys.readouterr().out


def test_corrupt_image_has_friendly_error(tmp_path, capsys):
    bad = tmp_path / "broken.png"
    bad.write_bytes(b"this is not an image")
    rc = cli.main([str(bad)])
    assert rc == 2
    assert "could not process" in capsys.readouterr().out


def test_invalid_max_dim_is_rejected():
    with pytest.raises(SystemExit):
        cli.main(["x.png", "--max-dim", "abc"])


def test_invalid_max_bytes_is_rejected():
    with pytest.raises(SystemExit):
        cli.main(["x.png", "--max-bytes", "abc"])


def test_invalid_env_var_is_rejected(monkeypatch):
    monkeypatch.setenv("CLIPFIT_MAX_BYTES", "abc")
    with pytest.raises(SystemExit):
        cli.main(["x.png"])


def test_nonfinite_max_bytes_is_rejected(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["x.png", "--max-bytes", "inf"])
    assert exc.value.code == 2
    assert "invalid byte size" in capsys.readouterr().err


def test_nonfinite_max_bytes_env_is_rejected(monkeypatch, capsys):
    monkeypatch.setenv("CLIPFIT_MAX_BYTES", "1e999mb")
    with pytest.raises(SystemExit) as exc:
        cli.main(["x.png"])
    assert exc.value.code == 2
    assert "invalid byte size" in capsys.readouterr().err


def test_sound_plays_basso_on_error(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_play_sound", lambda ok: calls.append(ok))
    cli.main([str(tmp_path / "nope.png"), "--sound"])
    assert calls == [False]


def test_sound_plays_pop_on_success(tmp_path, monkeypatch):
    src = tmp_path / "pic.png"
    _make_png(src)
    calls = []
    monkeypatch.setattr(cli, "_play_sound", lambda ok: calls.append(ok))
    assert cli.main([str(src), "--sound"]) == 0
    assert calls == [True]


@pytest.fixture()
def isolated_hotkey(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    importlib.reload(hotkey)
    return hotkey


def test_hotkey_set_missing_skhd(isolated_hotkey, monkeypatch, capsys):
    monkeypatch.setattr(isolated_hotkey, "skhd_available", lambda: False)
    rc = cli.main(["hotkey", "set", "--hotkey", "cmd+shift+v"])
    assert rc == 2
    out = capsys.readouterr().out
    assert "skhd not found" in out
    assert "Accessibility" not in out
    assert isolated_hotkey.current_binding() is None


def test_hotkey_set_success_when_skhd_running(isolated_hotkey, monkeypatch, capsys):
    monkeypatch.setattr(isolated_hotkey, "skhd_available", lambda: True)
    monkeypatch.setattr(isolated_hotkey, "restart_service", lambda: True)
    def no_pane():
        raise AssertionError("Accessibility pane should not open")

    monkeypatch.setattr(isolated_hotkey, "open_accessibility_pane", no_pane)
    rc = cli.main(["hotkey", "set", "--hotkey", "cmd+shift+v"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Hotkey set" in out
    assert "You're all set" in out
    assert "Accessibility permission" not in out
    assert isolated_hotkey.current_binding() is not None


def test_hotkey_set_accessibility_when_skhd_not_running(isolated_hotkey, monkeypatch, capsys):
    opened = []
    monkeypatch.setattr(isolated_hotkey, "skhd_available", lambda: True)
    monkeypatch.setattr(isolated_hotkey, "restart_service", lambda: False)
    monkeypatch.setattr(isolated_hotkey, "open_accessibility_pane", lambda: opened.append(True))
    rc = cli.main(["hotkey", "set", "--hotkey", "option+shift+v"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Accessibility permission" in out
    assert "skhd not found" not in out
    assert opened == [True]


def test_hotkey_show_missing_skhd_is_not_accessibility(isolated_hotkey, monkeypatch, capsys):
    monkeypatch.setattr(isolated_hotkey, "skhd_available", lambda: True)
    monkeypatch.setattr(isolated_hotkey, "restart_service", lambda: True)
    monkeypatch.setattr(isolated_hotkey, "open_accessibility_pane", lambda: None)
    assert cli.main(["hotkey", "set", "--hotkey", "cmd+shift+v"]) == 0
    capsys.readouterr()
    monkeypatch.setattr(isolated_hotkey, "skhd_available", lambda: False)
    rc = cli.main(["hotkey", "show"])
    assert rc == 2
    out = capsys.readouterr().out
    assert "skhd not found" in out
    assert "Accessibility" not in out
