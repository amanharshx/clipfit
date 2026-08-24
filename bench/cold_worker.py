"""Cold-start worker: read unique source pasteboard, shrink, write dest."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--dest", required=True)
    args = parser.parse_args()

    from clipfit import clipboard
    from clipfit.core import shrink_image_bytes

    clipboard._ensure_appkit()
    src = clipboard.NSPasteboard.pasteboardWithName_(args.source)
    dst = clipboard.NSPasteboard.pasteboardWithName_(args.dest)
    if src is None or dst is None:
        print("clipfit bench: pasteboard not found", file=sys.stderr)
        return 1

    got = clipboard.read_image(pasteboard=src)
    if got is None:
        print("clipfit bench: no image on source pasteboard", file=sys.stderr)
        return 1

    data, original_bytes = got
    force_png = clipboard.png_header_size(data) is None
    out, _res = shrink_image_bytes(
        data, original_bytes=original_bytes, force_png=force_png
    )
    clipboard.write_png(out, pasteboard=dst)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
