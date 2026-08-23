"""clipfit CLI.

Default action: grab the image on the clipboard, downscale it to fit LLM input
limits, and write the smaller version back. Only images larger than the cap are
changed; everything else is left untouched.

Usage:
    clipfit                     # shrink clipboard image in place
    clipfit --max-dim 2000      # custom longest-edge cap
    clipfit --max-bytes 4mb     # custom byte budget (keeps base64 under limits)
    clipfit path/to/img.png     # shrink a file instead (writes *_fit.png)
    clipfit --quiet             # suppress output (for hotkey use)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .core import DEFAULT_MAX_BYTES, DEFAULT_MAX_DIM, shrink_image_bytes


def _parse_bytes(v: str) -> int:
    """Parse a byte budget like '3700000', '3.5mb', '900kb'."""
    s = str(v).strip().lower()
    mult = 1
    if s.endswith("mb"):
        mult, s = 1024 * 1024, s[:-2]
    elif s.endswith("kb"):
        mult, s = 1024, s[:-2]
    elif s.endswith("b"):
        s = s[:-1]
    return int(float(s) * mult)


def _report(msg: str, quiet: bool, notify: bool) -> None:
    if not quiet:
        print(f"clipfit: {msg}")
    if notify:
        _macos_notify(msg)


def _macos_notify(msg: str) -> None:
    """Post a macOS notification (best-effort; ignored on failure)."""
    import subprocess

    text = msg.replace('"', "'")
    script = f'display notification "{text}" with title "clipfit"'
    try:
        subprocess.run(["osascript", "-e", script], check=False, timeout=5)
    except Exception:
        pass


def _run_clipboard(max_dim: int, max_bytes: int, quiet: bool, notify: bool) -> int:
    from . import clipboard

    try:
        data = clipboard.read_image()
    except clipboard.ClipboardError as exc:
        _report(str(exc), quiet=False, notify=notify)
        return 2

    if data is None:
        _report("no image on the clipboard - nothing to do", quiet, notify)
        return 1

    new_data, result = shrink_image_bytes(data, max_dim=max_dim, max_bytes=max_bytes)
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


def _run_file(path: Path, max_dim: int, max_bytes: int, quiet: bool, notify: bool) -> int:
    if not path.exists():
        _report(f"file not found: {path}", quiet=False, notify=notify)
        return 1

    data = path.read_bytes()
    new_data, result = shrink_image_bytes(data, max_dim=max_dim, max_bytes=max_bytes)
    if not result.changed:
        _report(result.summary(), quiet, notify)
        return 0

    out_path = path.with_name(f"{path.stem}_fit.png")
    out_path.write_bytes(new_data)
    _report(f"{result.summary()} -> {out_path}", quiet, notify)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="clipfit",
        description="Shrink oversized images so LLM chats can read them.",
    )
    p.add_argument(
        "path",
        nargs="?",
        help="optional image file to shrink; if omitted, uses the clipboard",
    )
    p.add_argument(
        "--max-dim",
        type=int,
        default=int(os.environ.get("CLIPFIT_MAX_DIM", DEFAULT_MAX_DIM)),
        help=f"cap for the longest edge in pixels (default: {DEFAULT_MAX_DIM}, "
        "or $CLIPFIT_MAX_DIM)",
    )
    p.add_argument(
        "--max-bytes",
        type=_parse_bytes,
        default=_parse_bytes(os.environ.get("CLIPFIT_MAX_BYTES", str(DEFAULT_MAX_BYTES))),
        help=f"byte budget for the output, e.g. 3.5mb (default: {DEFAULT_MAX_BYTES}, "
        "or $CLIPFIT_MAX_BYTES). Sized so base64 stays under a 5MB request limit.",
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="suppress terminal output (useful when bound to a hotkey)",
    )
    p.add_argument(
        "--notify",
        action="store_true",
        help="post a macOS notification with the result (for hotkey use)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.max_dim < 1:
        _report("--max-dim must be >= 1", quiet=False, notify=args.notify)
        return 2
    if args.max_bytes < 1024:
        _report("--max-bytes is too small (min 1024)", quiet=False, notify=args.notify)
        return 2

    if args.path:
        return _run_file(
            Path(args.path).expanduser(),
            args.max_dim,
            args.max_bytes,
            args.quiet,
            args.notify,
        )
    return _run_clipboard(args.max_dim, args.max_bytes, args.quiet, args.notify)


if __name__ == "__main__":
    sys.exit(main())
