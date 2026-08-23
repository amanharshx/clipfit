"""Benchmark clipfit across realistic Mac screenshot resolutions.

Measures, per stage, in milliseconds:
  decode  - PNG bytes -> PIL image
  resize  - LANCZOS downscale to the cap
  encode  - shrunk image -> PNG bytes
  total   - full shrink_image_bytes() call
  cbwrite - writing the shrunk PNG back to the clipboard (optional)

Uses synthetic but non-trivial content (gradient + shapes + noise) so PNG
encode/decode times reflect real screenshots, not trivially compressible fills.
"""

from __future__ import annotations

import io
import statistics
import time

from PIL import Image, ImageDraw, ImageChops

from clipfit.core import DEFAULT_MAX_DIM, shrink_image_bytes

# Common Mac capture resolutions (retina backing-store pixels).
RESOLUTIONS = [
    ("MBP 13\" retina", 2560, 1600),
    ("MBP 14\" retina", 3024, 1964),
    ("MBP 16\" retina", 3456, 2234),
    ("4K external", 3840, 2160),
    ("5K iMac/Studio", 5120, 2880),
    ("6K Pro Display XDR", 6016, 3384),
]

ITERS = 15
WARMUP = 3


def make_realistic_png(w: int, h: int) -> bytes:
    """Gradient background + UI-like rectangles + noise overlay -> PNG bytes."""
    base = Image.new("RGB", (w, h))
    px = base.load()
    # Cheap diagonal gradient.
    for y in range(0, h, 4):
        for x in range(0, w, 4):
            c = ((x * 255) // w, (y * 255) // h, ((x + y) * 255) // (w + h))
            for dy in range(4):
                for dx in range(4):
                    if x + dx < w and y + dy < h:
                        px[x + dx, y + dy] = c

    draw = ImageDraw.Draw(base)
    for i in range(40):
        x0 = (i * 97) % w
        y0 = (i * 53) % h
        draw.rectangle([x0, y0, x0 + 180, y0 + 60], outline=(255, 255, 255), width=2)
        draw.text((x0 + 6, y0 + 6), f"label {i} :: value_{i*7}", fill=(240, 240, 240))

    noise = Image.effect_noise((w, h), 24).convert("RGB")
    base = ImageChops.add(base, noise, scale=2.0)

    buf = io.BytesIO()
    base.save(buf, format="PNG")
    return buf.getvalue()


def timed(fn, iters=ITERS, warmup=WARMUP):
    for _ in range(warmup):
        fn()
    samples = []
    for _ in range(iters):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1000.0)
    return statistics.median(samples), min(samples), max(samples)


def stage_times(data: bytes, max_dim: int):
    def decode():
        with Image.open(io.BytesIO(data)) as im:
            im.load()
        return im

    def resize_encode():
        with Image.open(io.BytesIO(data)) as im:
            im.load()
            ow, oh = im.size
            scale = max_dim / max(ow, oh)
            r = im.resize((round(ow * scale), round(oh * scale)), Image.Resampling.LANCZOS)
        b = io.BytesIO()
        r.save(b, format="PNG", optimize=True)
        return b.getvalue()

    dec = timed(decode)
    tot = timed(lambda: shrink_image_bytes(data, max_dim=max_dim))
    return dec, tot


def human(n: float) -> str:
    for u in ("B", "KB", "MB"):
        if n < 1024 or u == "MB":
            return f"{n:.1f}{u}"
        n /= 1024
    return f"{n:.1f}MB"


def main() -> None:
    print(f"clipfit benchmark  (cap={DEFAULT_MAX_DIM}px, {ITERS} iters, median ms)\n")
    header = f"{'resolution':<22}{'MP':>6}{'decode':>10}{'total':>10}{'in size':>11}{'out size':>11}{'reduction':>11}"
    print(header)
    print("-" * len(header))

    try:
        from clipfit import clipboard
        cb_ok = True
    except Exception:
        cb_ok = False

    for name, w, h in RESOLUTIONS:
        data = make_realistic_png(w, h)
        (dec_med, _, _), (tot_med, tot_min, tot_max) = stage_times(data, DEFAULT_MAX_DIM)
        out, res = shrink_image_bytes(data, max_dim=DEFAULT_MAX_DIM)
        mp = (w * h) / 1e6
        reduction = 100 * (1 - res.new_bytes / res.original_bytes)
        print(
            f"{name:<22}{mp:>5.1f}{dec_med:>10.1f}{tot_med:>10.1f}"
            f"{human(res.original_bytes):>11}{human(res.new_bytes):>11}{reduction:>10.0f}%"
        )

    print("\nnote: 'total' = decode + resize + PNG re-encode (the full clipfit op).")

    if cb_ok:
        # End-to-end clipboard round trip on the largest resolution.
        data = make_realistic_png(6016, 3384)
        out, _ = shrink_image_bytes(data, max_dim=DEFAULT_MAX_DIM)

        def write():
            clipboard.write_png(out)

        med, lo, hi = timed(write, iters=10, warmup=2)
        print(f"\nclipboard write (6K shrunk PNG): median {med:.1f} ms  (min {lo:.1f}, max {hi:.1f})")
    else:
        print("\nclipboard write: skipped (AppKit unavailable)")


if __name__ == "__main__":
    main()
