"""Keyboard-shortcut management for clipfit, backed by skhd.

Parses a friendly combo like ``cmd+shift+v`` into skhd syntax, manages a
clearly marked block inside ``~/.config/skhd/skhdrc`` (so the user's other
bindings are never touched), and controls the skhd service.

macOS only. skhd must be installed (the Homebrew formula depends on it).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

BLOCK_START = "# >>> clipfit >>>"
BLOCK_END = "# <<< clipfit <<<"

# Friendly modifier names -> skhd modifier tokens.
_MOD_ALIASES = {
    "cmd": "cmd", "command": "cmd", "\u2318": "cmd",
    "ctrl": "ctrl", "control": "ctrl", "\u2303": "ctrl",
    "alt": "alt", "opt": "alt", "option": "alt", "\u2325": "alt",
    "shift": "shift", "\u21e7": "shift",
}
# Pretty display names.
_MOD_PRETTY = {"cmd": "Command", "ctrl": "Control", "alt": "Option", "shift": "Shift"}
# Stable display/order for modifiers (matches the spec: Command first).
_MOD_ORDER = ["cmd", "ctrl", "alt", "shift"]

# A small set of named keys skhd understands, beyond single characters.
_NAMED_KEYS = {
    "space", "return", "tab", "escape", "delete", "backspace",
    "up", "down", "left", "right",
    "home", "end", "pageup", "pagedown",
    "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10", "f11", "f12",
}


class HotkeyError(ValueError):
    """Raised when a combo cannot be parsed."""


@dataclass
class ParsedHotkey:
    mods: list[str]          # skhd modifier tokens, normalized order
    key: str                 # skhd key token
    skhd: str                # e.g. "cmd + shift - v"
    pretty: str              # e.g. "Command + Shift + V"


def parse_hotkey(combo: str) -> ParsedHotkey:
    """Parse ``cmd+shift+v`` (or ``cmd + shift - v``) into skhd + pretty forms."""
    if not combo or not combo.strip():
        raise HotkeyError("empty shortcut")

    # Accept +, -, and whitespace as separators between tokens.
    tokens = [t for t in re.split(r"[+\-\s]+", combo.strip().lower()) if t]
    if len(tokens) < 2:
        raise HotkeyError(
            f'could not read "{combo}" as a shortcut. '
            "Use modifiers (cmd, ctrl, alt/opt, shift) plus one key, e.g. cmd+shift+v."
        )

    *mod_tokens, key = tokens

    mods: list[str] = []
    for m in mod_tokens:
        if m not in _MOD_ALIASES:
            raise HotkeyError(
                f'"{m}" is not a modifier. Use cmd, ctrl, alt/opt, or shift.'
            )
        norm = _MOD_ALIASES[m]
        if norm not in mods:
            mods.append(norm)

    if not mods:
        raise HotkeyError("a shortcut needs at least one modifier (cmd, ctrl, alt, shift).")

    if not (len(key) == 1 and key.isalnum()) and key not in _NAMED_KEYS:
        raise HotkeyError(
            f'"{key}" is not a valid key. Use a single letter/number or one of: '
            + ", ".join(sorted(_NAMED_KEYS))
        )

    ordered = [m for m in _MOD_ORDER if m in mods]
    skhd = " + ".join(ordered) + " - " + key
    pretty = " + ".join(_MOD_PRETTY[m] for m in ordered) + " + " + key.upper()
    return ParsedHotkey(mods=ordered, key=key, skhd=skhd, pretty=pretty)


def skhd_to_pretty(skhd_combo: str) -> str:
    """Turn a skhd binding LHS (``cmd + shift - v``) into ``Command + Shift + V``."""
    left, _, key = skhd_combo.partition("-")
    mods = [m.strip() for m in left.split("+") if m.strip()]
    ordered = [m for m in _MOD_ORDER if m in mods]
    key = key.strip()
    key_disp = key.upper() if len(key) == 1 else key
    parts = [_MOD_PRETTY.get(m, m) for m in ordered]
    parts.append(key_disp)
    return " + ".join(parts)


def _normalize_skhd(skhd_combo: str) -> str:
    """Normalize a skhd LHS for conflict comparison (sorted mods + key)."""
    left, _, key = skhd_combo.partition("-")
    mods = sorted(m.strip() for m in left.split("+") if m.strip())
    return "+".join(mods) + "-" + key.strip()


# --- skhd config file ---------------------------------------------------------

def config_path() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "skhd" / "skhdrc"


def _read_config() -> str:
    p = config_path()
    return p.read_text() if p.exists() else ""


def _write_config(text: str) -> None:
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def _strip_block(text: str) -> str:
    """Remove the clipfit-managed block, returning the rest of the config."""
    pattern = re.compile(
        re.escape(BLOCK_START) + r".*?" + re.escape(BLOCK_END) + r"\n?",
        re.DOTALL,
    )
    return pattern.sub("", text)


def clipfit_binary() -> str:
    """Path to the clipfit executable for the skhd binding.

    Prefer the stable PATH entry (e.g. /opt/homebrew/bin/clipfit) and do NOT
    resolve symlinks, so a Homebrew upgrade that changes the Cellar version does
    not break the binding.
    """
    found = shutil.which("clipfit")
    if found:
        return found
    argv0 = Path(sys.argv[0])
    if argv0.name == "clipfit":
        return str(argv0 if argv0.is_absolute() else argv0.resolve())
    # Dev fallback: console script alongside the current interpreter.
    return str(Path(sys.executable).parent / "clipfit")


def _binding_command() -> str:
    return f"{clipfit_binary()} --quiet --notify --sound"


def current_binding() -> tuple[str, str] | None:
    """Return (skhd_combo, pretty) for the clipfit block, or None if unset."""
    text = _read_config()
    m = re.search(
        re.escape(BLOCK_START) + r"(.*?)" + re.escape(BLOCK_END),
        text,
        re.DOTALL,
    )
    if not m:
        return None
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        lhs = line.split(":", 1)[0].strip()
        if lhs:
            return lhs, skhd_to_pretty(lhs)
    return None


def find_conflict(skhd_combo: str) -> str | None:
    """Return a conflicting non-clipfit binding line, if the combo is taken."""
    text = _strip_block(_read_config())
    target = _normalize_skhd(skhd_combo)
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        lhs = line.split(":", 1)[0].strip()
        if not lhs or "-" not in lhs:
            continue
        try:
            if _normalize_skhd(lhs) == target:
                return line
        except Exception:
            continue
    return None


def set_binding(parsed: ParsedHotkey) -> None:
    """Write (or replace) the clipfit block with the given hotkey."""
    base = _strip_block(_read_config()).rstrip()
    block = (
        f"{BLOCK_START}\n"
        f"# clipfit: shrink the clipboard image for LLM chats\n"
        f"{parsed.skhd} : {_binding_command()}\n"
        f"{BLOCK_END}\n"
    )
    text = (base + "\n\n" if base else "") + block
    _write_config(text)


def remove_binding() -> bool:
    """Remove the clipfit block. Returns True if something was removed."""
    text = _read_config()
    if BLOCK_START not in text:
        return False
    _write_config(_strip_block(text).rstrip() + "\n")
    return True


# --- skhd service -------------------------------------------------------------

def skhd_available() -> bool:
    return shutil.which("skhd") is not None


def missing_skhd_message() -> str:
    return (
        "skhd not found. Install it with `brew install skhd`, "
        "or bind clipfit through another launcher. "
        "pipx and source installs do not include skhd."
    )


def restart_service() -> bool:
    """Restart skhd. True if a skhd process is running afterward."""
    if not skhd_available():
        return False
    try:
        subprocess.run(
            ["skhd", "--restart-service"],
            check=False,
            capture_output=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return service_running()


def service_running() -> bool:
    return subprocess.run(["pgrep", "-x", "skhd"], capture_output=True).returncode == 0


def accessibility_ok() -> bool:
    """Heuristic: skhd only stays running if it has Accessibility access.

    skhd aborts immediately without it, so a live process is a reliable signal.
    """
    return service_running()


def open_accessibility_pane() -> None:
    subprocess.run(
        ["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"],
        check=False, capture_output=True,
    )


def skhd_binary_path() -> str:
    return shutil.which("skhd") or "/opt/homebrew/bin/skhd"
