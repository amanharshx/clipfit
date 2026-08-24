"""clipfit command-line interface.

Default action shrinks the clipboard image. The ``hotkey`` subcommand group
manages the keyboard shortcut (set / show / remove).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from . import __version__
from .core import (
    DEFAULT_MAX_BYTES,
    DEFAULT_MAX_DIM,
    ByteBudgetError,
    ClipfitImageError,
    shrink_image_bytes,
)

DEFAULT_HOTKEY = "option+shift+v"

TOP_HELP = """\
clipfit \u2014 fewer pixels, fewer tokens, same readable image. For pasting into LLMs.

USAGE
  clipfit [options]           shrink the image on the clipboard (default)
  clipfit <file> [options]    shrink an image file -> writes <name>_fit.png
  clipfit hotkey <command>    manage the keyboard shortcut

HOTKEY COMMANDS
  clipfit hotkey set          choose/change the shortcut (interactive)
  clipfit hotkey show         show the current shortcut and its status
  clipfit hotkey remove       remove the shortcut

OPTIONS
  --max-dim N       cap the longest edge in pixels (default 1568)
  --max-bytes SIZE  output byte budget, e.g. 3.5mb (default ~3.7mb)
  --quiet           no terminal output (for hotkey use)
  --notify          post a macOS notification with the result
  --sound           play a short sound on success/failure (for hotkey use)
  -h, --help        show this help
  --version         show version

EXAMPLES
  clipfit                        shrink what's on the clipboard
  clipfit shot.png --max-dim 2000
  clipfit hotkey set --hotkey cmd+shift+v
"""

HOTKEY_HELP = """\
clipfit hotkey \u2014 manage the shortcut that shrinks the clipboard image.

USAGE
  clipfit hotkey set [--hotkey COMBO] [--yes]   set or change the shortcut
  clipfit hotkey show                           show the current shortcut and status
  clipfit hotkey remove                         remove the shortcut

Examples of COMBO: option+shift+v, cmd+shift+v, ctrl+opt+s
"""


# --- shared output helpers ----------------------------------------------------

def _report(msg: str, quiet: bool, notify: bool) -> None:
    if not quiet:
        print(f"clipfit: {msg}")
    if notify:
        _macos_notify(msg)


def _macos_notify(msg: str) -> None:
    text = msg.replace('"', "'")
    try:
        subprocess.run(
            ["osascript", "-e", f'display notification "{text}" with title "clipfit"'],
            check=False, timeout=5, capture_output=True,
        )
    except Exception:
        pass


def _play_sound(ok: bool) -> None:
    snd = "/System/Library/Sounds/Pop.aiff" if ok else "/System/Library/Sounds/Basso.aiff"
    try:
        subprocess.Popen(["afplay", snd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def _parse_bytes(v: str) -> int:
    s = str(v).strip().lower()
    mult = 1
    if s.endswith("mb"):
        mult, s = 1024 * 1024, s[:-2]
    elif s.endswith("kb"):
        mult, s = 1024, s[:-2]
    elif s.endswith("b"):
        s = s[:-1]
    try:
        return int(float(s) * mult)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"invalid byte size '{v}'; use a value such as 3.5mb"
        ) from None


# --- shrink command -----------------------------------------------------------

def _shrink_clipboard(max_dim: int, max_bytes: int, quiet: bool, notify: bool) -> int:
    from . import clipboard

    try:
        data = clipboard.read_image()
    except clipboard.ClipboardError as exc:
        _report(str(exc), quiet=False, notify=notify)
        return 2

    if data is None:
        _report("no image on the clipboard - nothing to do", quiet, notify)
        return 1

    try:
        new_data, result = shrink_image_bytes(data, max_dim=max_dim, max_bytes=max_bytes)
    except (ClipfitImageError, ByteBudgetError) as exc:
        _report(str(exc), quiet=False, notify=notify)
        return 2
    if not result.changed:
        _report(result.summary(), quiet, notify)
        return 0

    try:
        clipboard.write_png(new_data)
    except clipboard.ClipboardError as exc:
        _report(str(exc), quiet=False, notify=notify)
        return 2

    _report(result.summary(), quiet, notify)
    return 0


def _shrink_file(path: Path, max_dim: int, max_bytes: int, quiet: bool, notify: bool) -> int:
    if not path.exists():
        _report(f"file not found: {path}", quiet=False, notify=notify)
        return 1
    if not path.is_file():
        _report(f"not a file: {path}", quiet=False, notify=notify)
        return 1

    try:
        data = path.read_bytes()
    except OSError as exc:
        _report(f"could not read {path}: {exc}", quiet=False, notify=notify)
        return 2

    # File mode always writes a PNG next to the source, even if no resize is
    # needed, so the advertised <name>_fit.png is always produced.
    try:
        new_data, result = shrink_image_bytes(
            data, max_dim=max_dim, max_bytes=max_bytes, force_png=True
        )
    except (ClipfitImageError, ByteBudgetError) as exc:
        _report(f"could not process {path}: {exc}", quiet=False, notify=notify)
        return 2

    out_path = path.with_name(f"{path.stem}_fit.png")
    try:
        out_path.write_bytes(new_data)
    except OSError as exc:
        _report(f"could not write {out_path}: {exc}", quiet=False, notify=notify)
        return 2

    _report(f"{result.summary()} -> {out_path}", quiet, notify)
    return 0


def _build_shrink_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="clipfit", add_help=False)
    p.add_argument("path", nargs="?")
    p.add_argument("--max-dim", type=int,
                   default=os.environ.get("CLIPFIT_MAX_DIM", str(DEFAULT_MAX_DIM)))
    p.add_argument("--max-bytes", type=_parse_bytes,
                   default=os.environ.get("CLIPFIT_MAX_BYTES", str(DEFAULT_MAX_BYTES)))
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--notify", action="store_true")
    p.add_argument("--sound", action="store_true")
    return p


def _run_shrink(argv: list[str]) -> int:
    args = _build_shrink_parser().parse_args(argv)
    if args.max_dim < 1:
        _report("--max-dim must be >= 1", quiet=False, notify=args.notify)
        rc = 2
    elif args.max_bytes < 1024:
        _report("--max-bytes is too small (min 1024)", quiet=False, notify=args.notify)
        rc = 2
    elif args.path:
        rc = _shrink_file(Path(args.path).expanduser(), args.max_dim, args.max_bytes,
                          args.quiet, args.notify)
    else:
        rc = _shrink_clipboard(args.max_dim, args.max_bytes, args.quiet, args.notify)

    if args.sound:
        _play_sound(ok=(rc == 0))
    return rc


# --- hotkey commands ----------------------------------------------------------

def _hotkey_after_set(hk, quiet: bool = False) -> None:
    """Restart skhd and print Accessibility guidance."""
    hk.restart_service()
    if hk.accessibility_ok():
        print("  skhd is running with Accessibility. You're all set.")
        print("  Copy an image, press your shortcut, then paste.")
    else:
        print()
        print("\u26a0 skhd needs Accessibility permission to catch the shortcut.")
        print("  Opening System Settings \u2192 Privacy & Security \u2192 Accessibility.")
        print(f"  Turn on skhd ({hk.skhd_binary_path()}), then run:  clipfit hotkey show")
        hk.open_accessibility_pane()


def _hotkey_set(argv: list[str]) -> int:
    from . import hotkey as hk

    parser = argparse.ArgumentParser(prog="clipfit hotkey set", add_help=False)
    parser.add_argument("--hotkey")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("-h", "--help", action="store_true")
    args = parser.parse_args(argv)
    if args.help:
        print(HOTKEY_HELP)
        return 0

    existing = hk.current_binding()

    # Non-interactive paths.
    if args.hotkey or args.yes:
        combo = args.hotkey or DEFAULT_HOTKEY
        try:
            parsed = hk.parse_hotkey(combo)
        except hk.HotkeyError as exc:
            print(f"clipfit: {exc}")
            return 2
        conflict = hk.find_conflict(parsed.skhd)
        if conflict:
            print(f"\u26a0 {parsed.skhd} is already bound in your skhd config to something else.")
            print("  Pick a different combo, or edit ~/.config/skhd/skhdrc yourself.")
            return 2
        hk.set_binding(parsed)
        if existing:
            print(f"\u2713 Hotkey set: {parsed.pretty}")
        else:
            print(f"\u2713 Hotkey set: {parsed.pretty}")
        print("  skhd reloaded.")
        hk.restart_service()
        return 0

    # Interactive path.
    if existing:
        old_skhd, old_pretty = existing
        print("Change clipfit hotkey")
        print()
        print(f"Current shortcut is {old_pretty}. Press Enter to keep it.")
        prompt = "Or type a new one: "
        default_combo = old_skhd
    else:
        old_pretty = None
        print("clipfit hotkey setup")
        print()
        print("Default shortcut is Option+Shift+V. Press Enter to use it.")
        prompt = "Or type your own (e.g. cmd+shift+v, ctrl+opt+s): "
        default_combo = DEFAULT_HOTKEY

    while True:
        try:
            raw = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 1
        combo = raw or default_combo
        try:
            parsed = hk.parse_hotkey(combo)
        except hk.HotkeyError as exc:
            print(f"clipfit: {exc}")
            continue
        conflict = hk.find_conflict(parsed.skhd)
        if conflict:
            print(f"\u26a0 {parsed.skhd} is already bound in your skhd config to something else.")
            print("  Pick a different combo.")
            continue
        break

    print()
    if existing and parsed.skhd == existing[0]:
        print(f"\u2713 Hotkey unchanged: {parsed.pretty}")
        hk.set_binding(parsed)
        _hotkey_after_set(hk)
        return 0

    hk.set_binding(parsed)
    if existing:
        print(f"\u2713 Hotkey changed: {old_pretty} \u2192 {parsed.pretty}")
    else:
        print(f"\u2713 Hotkey set: {parsed.pretty}")
        print("  Writing skhd config\u2026 done")
    _hotkey_after_set(hk)
    return 0


def _hotkey_show(argv: list[str]) -> int:
    from . import hotkey as hk

    binding = hk.current_binding()
    if not binding:
        print("No clipfit hotkey is set. Run  clipfit hotkey set  to add one.")
        return 0

    _skhd_combo, pretty = binding
    running = hk.service_running()
    print(f"Current shortcut:  {pretty}")
    print(f"Runs:              clipfit")
    print(f"skhd service:      {'running' if running else 'not running'}")
    if hk.accessibility_ok():
        print(f"Accessibility:     granted")
    else:
        print(f"Accessibility:     looks missing \u2014 turn on skhd in "
              f"System Settings \u2192 Accessibility")
    return 0


def _hotkey_remove(argv: list[str]) -> int:
    from . import hotkey as hk

    existing = hk.current_binding()
    removed = hk.remove_binding()
    if removed:
        hk.restart_service()
        pretty = existing[1] if existing else "unknown"
        print(f"Removed the clipfit hotkey (was {pretty}). skhd reloaded.")
    else:
        print("Nothing to remove \u2014 no clipfit hotkey is set.")
    return 0


def _run_hotkey(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(HOTKEY_HELP)
        return 0
    sub, rest = argv[0], argv[1:]
    if sub == "set":
        return _hotkey_set(rest)
    if sub == "show":
        return _hotkey_show(rest)
    if sub == "remove":
        return _hotkey_remove(rest)
    print(f"clipfit: unknown hotkey command '{sub}'. Try: set, show, remove.")
    return 2


# --- entry point --------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if argv and argv[0] == "hotkey":
        return _run_hotkey(argv[1:])
    if argv and argv[0] == "--version":
        print(f"clipfit {__version__}")
        return 0
    if argv and argv[0] in ("-h", "--help"):
        print(TOP_HELP)
        return 0

    return _run_shrink(argv)


if __name__ == "__main__":
    sys.exit(main())
