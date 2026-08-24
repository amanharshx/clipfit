"""Benchmark clipfit without touching the general clipboard.

Measures p50/p95 ms for:
  decode, resize, encode, full shrink, unique-pasteboard read/write
  and a cold subprocess (Python + imports + shrink).

Uses a small synthetic corpus (terminal, IDE, browser, photo, transparency)
plus a noisy worst-case image. TIFF inputs are measured separately from PNG.
"""

from __future__ import annotations

import io
import math
import os
import platform
import statistics
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, features

from clipfit.core import DEFAULT_MAX_DIM, shrink_image_bytes

RESOLUTIONS = [
    ("MBP 13\" retina", 2560, 1600),
    ("MBP 14\" retina", 3024, 1964),
    ("MBP 16\" retina", 3456, 2234),
    ("4K external", 3840, 2160),
    ("5K iMac/Studio", 5120, 2880),
    ("6K Pro Display XDR", 6016, 3384),
]

CORPUS_KINDS = (
    "terminal",
    "ide",
    "browser",
    "photo",
    "transparency",
    "noisy",
)

ITERS = 15
WARMUP = 3
COLD_ITERS = 8


def p50_p95(samples: list[float]) -> tuple[float, float]:
    if not samples:
        return 0.0, 0.0
    s = sorted(samples)
    p50 = float(statistics.median(s))
    p95 = float(s[math.ceil(0.95 * len(s)) - 1])
    return p50, p95


def machine_info() -> dict[str, str]:
    return {
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "pillow": Image.__version__,
        "zlib": features.version_codec("zlib") or "unknown",
        "zlib-ng": features.version_feature("zlib_ng") or "none",
    }


def make_corpus_png(kind: str, w: int, h: int) -> bytes:
    if kind == "terminal":
        img = Image.new("RGB", (w, h), (20, 20, 24))
        draw = ImageDraw.Draw(img)
        for i in range(max(8, h // 18)):
            draw.text((8, 4 + i * 16), f"$ echo line {i}  " + ("x" * 40), fill=(180, 255, 180))
    elif kind == "ide":
        img = Image.new("RGB", (w, h), (30, 32, 40))
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, 160, h], fill=(40, 42, 54))
        for i in range(max(8, h // 18)):
            draw.text((172, 8 + i * 16), f"def fn_{i}(): return {i}", fill=(200, 200, 240))
    elif kind == "browser":
        img = _browser_ui(w, h)
    elif kind == "photo":
        img = ImageChops.add(_gradient_rgb(w, h), _rgb_noise(w, h, 80), scale=2.0)
    elif kind == "transparency":
        img = Image.new("RGBA", (w, h), (40, 80, 160, 180))
        draw = ImageDraw.Draw(img)
        draw.rectangle([w // 8, h // 8, w * 7 // 8, h * 7 // 8], fill=(255, 255, 255, 80))
    elif kind == "noisy":
        img = _rgb_noise(w, h, 120)
    else:
        raise ValueError(f"unknown corpus kind {kind!r}")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _rgb_noise(w: int, h: int, sigma: float) -> Image.Image:
    return Image.merge(
        "RGB",
        (
            Image.effect_noise((w, h), sigma),
            Image.effect_noise((w, h), sigma * 1.17),
            Image.effect_noise((w, h), sigma * 0.83),
        ),
    )


def _gradient_rgb(w: int, h: int) -> Image.Image:
    base = Image.new("RGB", (w, h))
    px = base.load()
    for y in range(0, h, 4):
        for x in range(0, w, 4):
            c = ((x * 255) // w, (y * 255) // h, ((x + y) * 255) // max(1, w + h))
            for dy in range(4):
                for dx in range(4):
                    if x + dx < w and y + dy < h:
                        px[x + dx, y + dy] = c
    return base


def _browser_ui(w: int, h: int) -> Image.Image:
    base = Image.new("RGB", (w, h))
    px = base.load()
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
        draw.text((x0 + 6, y0 + 6), f"label {i} :: value_{i * 7}", fill=(240, 240, 240))
    noise = Image.effect_noise((w, h), 24).convert("RGB")
    return ImageChops.add(base, noise, scale=2.0)


def make_realistic_png(w: int, h: int) -> bytes:
    """Kept for encode_bench. Browser-like synthetic screenshot."""
    return make_corpus_png("browser", w, h)


def png_to_tiff(png: bytes) -> bytes:
    buf = io.BytesIO()
    with Image.open(io.BytesIO(png)) as img:
        img.load()
        img.save(buf, format="TIFF")
    return buf.getvalue()


@contextmanager
def unique_pasteboard():
    from clipfit import clipboard

    clipboard._ensure_appkit()
    pb = clipboard.NSPasteboard.pasteboardWithUniqueName()
    try:
        yield pb
    finally:
        pb.releaseGlobally()


def timed_samples(fn, iters: int = ITERS, warmup: int = WARMUP) -> list[float]:
    for _ in range(warmup):
        fn()
    samples = []
    for _ in range(iters):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1000.0)
    return samples


def human(n: float) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB"):
        if size < 1024 or unit == "MB":
            return f"{size:.0f}B" if unit == "B" else f"{size:.2f}{unit}"
        size /= 1024
    return f"{size:.2f}MB"


def _fmt_one(ms: float) -> str:
    return f"{ms:.3f}" if ms < 1 else f"{ms:.1f}"


def _fmt_ms(samples: list[float]) -> str:
    p50, p95 = p50_p95(samples)
    return f"{_fmt_one(p50)} / {_fmt_one(p95)}"


def decode_loaded(data: bytes) -> Image.Image:
    im = Image.open(io.BytesIO(data))
    im.load()
    return im


def resize_loaded(img: Image.Image, max_dim: int) -> Image.Image:
    ow, oh = img.size
    scale = max_dim / max(ow, oh)
    if scale >= 1:
        return img
    return img.resize((round(ow * scale), round(oh * scale)), Image.Resampling.LANCZOS)


def encode_resized(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", compress_level=3)
    return buf.getvalue()


def stage_samples(data: bytes, max_dim: int) -> dict[str, list[float]]:
    loaded = decode_loaded(data)
    resized = resize_loaded(loaded, max_dim)
    return {
        "decode": timed_samples(lambda: decode_loaded(data)),
        "resize": timed_samples(lambda: resize_loaded(loaded, max_dim)),
        "encode": timed_samples(lambda: encode_resized(resized)),
        "total": timed_samples(lambda: shrink_image_bytes(data, max_dim=max_dim)),
    }


def clipboard_samples(png: bytes) -> dict[str, list[float]] | None:
    try:
        from clipfit import clipboard
        if not clipboard._APPKIT_OK:
            return None
    except Exception:
        return None

    reads: list[float] = []
    writes: list[float] = []
    full: list[float] = []
    with unique_pasteboard() as pb:
        clipboard.write_png(png, pasteboard=pb)

        def read():
            clipboard.read_image(pasteboard=pb)

        def write():
            clipboard.write_png(png, pasteboard=pb)

        def roundtrip():
            clipboard.write_png(png, pasteboard=pb)
            clipboard.read_image(pasteboard=pb)

        reads = timed_samples(read)
        writes = timed_samples(write)
        full = timed_samples(roundtrip)
    return {"read": reads, "write": writes, "roundtrip": full}


def seed_pasteboard(pb, png: bytes, tiff: bytes) -> None:
    from clipfit import clipboard

    clipboard._ensure_appkit()
    pb.clearContents()
    png_data = clipboard.NSData.dataWithBytes_length_(png, len(png))
    tiff_data = clipboard.NSData.dataWithBytes_length_(tiff, len(tiff))
    if not pb.setData_forType_(png_data, clipboard.NSPasteboardTypePNG):
        raise RuntimeError("failed to seed PNG on unique pasteboard")
    if not pb.setData_forType_(tiff_data, clipboard.NSPasteboardTypeTIFF):
        raise RuntimeError("failed to seed TIFF on unique pasteboard")


def cold_subprocess_samples(
    png: bytes,
    tiff: bytes,
    iters: int = COLD_ITERS,
) -> list[float]:
    from clipfit import clipboard

    if not clipboard._APPKIT_OK:
        raise RuntimeError("AppKit is required for the cold clipboard benchmark")

    worker = Path(__file__).with_name("cold_worker.py")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1]) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    samples = []
    with unique_pasteboard() as src, unique_pasteboard() as dst:
        seed_pasteboard(src, png, tiff)
        src_name = src.name()
        dst_name = dst.name()
        for _ in range(iters):
            t0 = time.perf_counter()
            proc = subprocess.run(
                [
                    sys.executable,
                    str(worker),
                    "--source",
                    src_name,
                    "--dest",
                    dst_name,
                ],
                capture_output=True,
                text=True,
                env=env,
            )
            samples.append((time.perf_counter() - t0) * 1000.0)
            if proc.returncode != 0:
                raise RuntimeError(proc.stderr or proc.stdout)
    return samples


def main() -> None:
    info = machine_info()
    print("clipfit benchmark")
    for k, v in info.items():
        print(f"  {k}: {v}")
    print(f"  cap: {DEFAULT_MAX_DIM}px  warm iters: {ITERS}  cold iters: {COLD_ITERS}")
    print("  clipboard: unique pasteboard (never general)")
    print()

    header = (
        f"{'case':<28}{'decode':>16}{'resize':>16}{'encode':>16}"
        f"{'total':>16}{'in':>10}{'out':>10}"
    )
    print("Warm shrink (p50 / p95 ms)")
    print(header)
    print("-" * len(header))

    # Default matrix: browser PNG at each resolution, plus corpus at 4K.
    cases: list[tuple[str, bytes]] = []
    for name, w, h in RESOLUTIONS:
        cases.append((f"{name} png", make_corpus_png("browser", w, h)))
    w4, h4 = 3840, 2160
    for kind in CORPUS_KINDS:
        cases.append((f"4K {kind} png", make_corpus_png(kind, w4, h4)))
    cases.append(("4K browser tiff", png_to_tiff(make_corpus_png("browser", w4, h4))))
    cases.append(("6K noisy png", make_corpus_png("noisy", 6016, 3384)))

    for label, data in cases:
        stages = stage_samples(data, DEFAULT_MAX_DIM)
        out, res = shrink_image_bytes(data, max_dim=DEFAULT_MAX_DIM)
        print(
            f"{label:<28}"
            f"{_fmt_ms(stages['decode']):>16}"
            f"{_fmt_ms(stages['resize']):>16}"
            f"{_fmt_ms(stages['encode']):>16}"
            f"{_fmt_ms(stages['total']):>16}"
            f"{human(res.original_bytes):>10}"
            f"{human(len(out)):>10}"
        )

    cb = clipboard_samples(make_corpus_png("browser", 1280, 800))
    print()
    if cb is None:
        print("Unique pasteboard: skipped (AppKit unavailable)")
    else:
        print("Unique pasteboard (1280x800 PNG, p50 / p95 ms)")
        print(f"  read       {_fmt_ms(cb['read'])}")
        print(f"  write      {_fmt_ms(cb['write'])}")
        print(f"  roundtrip  {_fmt_ms(cb['roundtrip'])}")

    print()
    print("Cold subprocess (launch + imports + clipboard + shrink, p50 / p95 ms)")
    for label, w, h in (
        ("13-inch", 2560, 1600),
        ("4K", 3840, 2160),
        ("6K", 6016, 3384),
    ):
        png = make_corpus_png("browser", w, h)
        tiff = png_to_tiff(png)
        samples = cold_subprocess_samples(png, tiff)
        print(f"  {label:<16}{_fmt_ms(samples)}")


if __name__ == "__main__":
    main()
