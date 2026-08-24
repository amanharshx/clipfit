import importlib

import pytest


@pytest.fixture()
def hk(tmp_path, monkeypatch):
    # Isolate the skhd config to a temp dir so tests never touch the real one.
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    import clipfit.hotkey as hotkey
    importlib.reload(hotkey)
    return hotkey


# --- combo parsing ---

def test_parse_basic(hk):
    p = hk.parse_hotkey("cmd+shift+v")
    assert p.skhd == "cmd + shift - v"
    assert p.pretty == "Command + Shift + V"


def test_parse_aliases_and_order(hk):
    p = hk.parse_hotkey("opt+shift+v")           # opt -> alt
    assert p.skhd == "alt + shift - v"
    assert p.pretty == "Option + Shift + V"


def test_parse_separators(hk):
    # spaces, plus, and dash all work as separators
    assert hk.parse_hotkey("ctrl - alt - s").skhd == "ctrl + alt - s"


def test_parse_dedup_mods(hk):
    assert hk.parse_hotkey("cmd+cmd+v").skhd == "cmd - v"


def test_parse_named_key(hk):
    assert hk.parse_hotkey("cmd+shift+space").skhd == "cmd + shift - space"


def test_parse_requires_modifier(hk):
    with pytest.raises(hk.HotkeyError):
        hk.parse_hotkey("v")


def test_parse_rejects_bad_modifier(hk):
    with pytest.raises(hk.HotkeyError):
        hk.parse_hotkey("meta+v")


def test_parse_rejects_bad_key(hk):
    with pytest.raises(hk.HotkeyError):
        hk.parse_hotkey("cmd+shift+banana")


# --- skhd config block management ---

def test_set_creates_block(hk):
    assert hk.current_binding() is None
    hk.set_binding(hk.parse_hotkey("option+shift+v"))
    binding = hk.current_binding()
    assert binding is not None
    skhd, pretty = binding
    assert skhd == "alt + shift - v"
    assert pretty == "Option + Shift + V"
    text = hk.config_path().read_text()
    assert hk.BLOCK_START in text and hk.BLOCK_END in text


def test_set_replaces_block_not_duplicates(hk):
    hk.set_binding(hk.parse_hotkey("option+shift+v"))
    hk.set_binding(hk.parse_hotkey("cmd+shift+v"))
    text = hk.config_path().read_text()
    assert text.count(hk.BLOCK_START) == 1
    assert hk.current_binding()[0] == "cmd + shift - v"


def test_set_preserves_user_bindings(hk):
    # Pre-existing user config outside the clipfit block must survive.
    cfg = hk.config_path()
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text("cmd - t : open -a Terminal\n")
    hk.set_binding(hk.parse_hotkey("option+shift+v"))
    text = cfg.read_text()
    assert "cmd - t : open -a Terminal" in text
    assert hk.BLOCK_START in text


def test_remove_only_strips_clipfit_block(hk):
    cfg = hk.config_path()
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text("cmd - t : open -a Terminal\n")
    hk.set_binding(hk.parse_hotkey("option+shift+v"))
    assert hk.remove_binding() is True
    text = cfg.read_text()
    assert "cmd - t : open -a Terminal" in text
    assert hk.BLOCK_START not in text
    assert hk.current_binding() is None


def test_remove_when_nothing_set(hk):
    assert hk.remove_binding() is False


def test_conflict_detection(hk):
    cfg = hk.config_path()
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text("shift + cmd - v : echo hi\n")  # same combo, different order
    conflict = hk.find_conflict("cmd + shift - v")
    assert conflict is not None and "echo hi" in conflict


def test_no_conflict_with_clipfit_own_block(hk):
    hk.set_binding(hk.parse_hotkey("cmd+shift+v"))
    # clipfit's own block must not count as a conflict
    assert hk.find_conflict("cmd + shift - v") is None


def test_restart_false_when_skhd_missing(hk, monkeypatch):
    monkeypatch.setattr(hk.shutil, "which", lambda _name: None)
    assert hk.skhd_available() is False
    assert hk.restart_service() is False


def test_restart_true_when_service_stays_up(hk, monkeypatch):
    monkeypatch.setattr(hk.shutil, "which", lambda _name: "/opt/homebrew/bin/skhd")
    monkeypatch.setattr(hk.subprocess, "run", lambda *a, **k: type("R", (), {"returncode": 0})())
    assert hk.restart_service() is True


def test_restart_false_when_skhd_exits(hk, monkeypatch):
    monkeypatch.setattr(hk.shutil, "which", lambda _name: "/opt/homebrew/bin/skhd")

    def fake_run(cmd, *a, **k):
        if cmd[:1] == ["pgrep"] or (isinstance(cmd, list) and cmd[0] == "pgrep"):
            return type("R", (), {"returncode": 1})()
        return type("R", (), {"returncode": 0})()

    monkeypatch.setattr(hk.subprocess, "run", fake_run)
    assert hk.restart_service() is False
