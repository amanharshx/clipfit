"""Compare encode strategies for the shrunk (~1568px) output.

The resize target is roughly constant regardless of source resolution, so the
output-encode cost is roughly fixed. This isolates decode vs resize vs encode
and compares PNG settings against JPEG to guide the default.
"""

from __future__ import annotations

import io
import statistics
import time

from PIL import Image

from bench.benchmark import make_realistic_png  # reuse realistic content
from clipfit.core import DEFAULT_MAX_DIM

ITERS = 20
WARMUP = 3


def timed(fn):
    for _ in range(WARMUP):
        fn()
    s = []
    for _ in range(ITERS):
        t0 = time.perf_counter()
        fn()
        s.append((time.perf_counter() - t0) * 1000)
    return statistics.median(s)


def human(n: float) -> str:
    for u in ("B", "KB", "MB"):
        if n < 1024 or u == "MB":
            return f"{n:.1f}{u}"
        n /= 1024
    return f"{n:.1f}MB"


def main() -> None:
    # Use a 6K source (worst case) to get the shrunk image.
    src = make_realistic_png(6016, 3384)
    with Image.open(io.BytesIO(src)) as im:
        im.load()
        scale = DEFAULT_MAX_DIM / max(im.size)
        shrunk = im.resize(
            (round(im.size[0] * scale), round(im.size[1] * scale)),
            Image.Resampling.LANCZOS,
        ).convert("RGB")

    print(f"shrunk output size: {shrunk.size}\n")

    # Isolate decode + resize (no encode).
    def decode_only():
        with Image.open(io.BytesIO(src)) as i:
            i.load()

    def resize_only():
        with Image.open(io.BytesIO(src)) as i:
            i.load()
            sc = DEFAULT_MAX_DIM / max(i.size)
            i.resize((round(i.size[0] * sc), round(i.size[1] * sc)), Image.Resampling.LANCZOS)

    print(f"{'stage/encoder':<28}{'ms':>8}{'out size':>12}")
    print("-" * 48)
    print(f"{'decode 6K only':<28}{timed(decode_only):>8.1f}{'-':>12}")
    print(f"{'decode+resize (no encode)':<28}{timed(resize_only):>8.1f}{'-':>12}")

    strategies = [
        ("PNG optimize=True", dict(format="PNG", optimize=True)),
        ("PNG (default)", dict(format="PNG")),
        ("PNG compress_level=6", dict(format="PNG", compress_level=6)),
        ("PNG compress_level=1", dict(format="PNG", compress_level=1)),
        ("JPEG q=90", dict(format="JPEG", quality=90)),
        ("JPEG q=85", dict(format="JPEG", quality=85)),
        ("WEBP q=90", dict(format="WEBP", quality=90)),
    ]

    for label, kw in strategies:
        def enc(kw=kw):
            b = io.BytesIO()
            shrunk.save(b, **kw)
            return b.getvalue()

        ms = timed(enc)
        size = len(enc())
        print(f"{label:<28}{ms:>8.1f}{human(size):>12}")

    print("\nnote: total clipfit op ~= decode + resize + chosen encoder.")


if __name__ == "__main__":
    main()
