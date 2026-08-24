"""Cold-start worker: one process, one shrink, unique pasteboard only."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

t_start = time.perf_counter()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Path to PNG or TIFF bytes")
    args = parser.parse_args()

    from clipfit.core import shrink_image_bytes

    data = Path(args.input).read_bytes()
    out, _res = shrink_image_bytes(data)

    try:
        from clipfit import clipboard
        from bench.benchmark import unique_pasteboard

        if clipboard._APPKIT_OK:
            with unique_pasteboard() as pb:
                clipboard.write_png(out, pasteboard=pb)
    except Exception:
        pass

    elapsed_ms = (time.perf_counter() - t_start) * 1000.0
    print(json.dumps({"ms": round(elapsed_ms, 2), "out_bytes": len(out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
