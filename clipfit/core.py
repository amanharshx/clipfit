"""Image downscaling logic for clipfit.

Fits an image under BOTH limits that break LLM chat inputs:
  1. a dimension cap (longest edge), and
  2. a byte budget, sized so the base64-encoded image stays under the common
     5 MB request limit (base64 inflates raw bytes by ~4/3).

Output is always PNG so it pastes reliably (lossless, crisp text). When a
full-color PNG is over budget we try a 256-color palette (great for
screenshots), then step the resolution down until it fits.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image

# Most vision models internally downsample to roughly this size, so capping the
# longest edge here shrinks filesize with essentially no quality loss to the model.
DEFAULT_MAX_DIM = 1568

# Keep base64(image) under a 5 MB (5,242,880 byte) request limit.
# raw <= 5,242,880 * 3/4 = 3,932,160; leave headroom for JSON/data-URI overhead.
DEFAULT_MAX_BYTES = 3_700_000

# Don't shrink resolution below this longest edge when chasing the byte budget.
MIN_DIM = 640


@dataclass
class ShrinkResult:
    """Outcome of a shrink attempt."""

    changed: bool
    original_size: tuple[int, int]
    new_size: tuple[int, int]
    original_bytes: int
    new_bytes: int
    strategy: str = ""
    note: str = ""

    def summary(self) -> str:
        ow, oh = self.original_size
        nw, nh = self.new_size
        if not self.changed:
            return f"already within limits ({ow}x{oh}, {_human(self.original_bytes)}) - {self.note}"
        extra = f" [{self.strategy}]" if self.strategy else ""
        return (
            f"{ow}x{oh} ({_human(self.original_bytes)}) "
            f"-> {nw}x{nh} ({_human(self.new_bytes)}){extra}"
        )


def _human(n: float) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}GB"


def _normalize_for_png(img: Image.Image) -> Image.Image:
    if img.mode not in ("RGB", "RGBA", "L", "LA", "P"):
        return img.convert("RGBA")
    return img


def _encode_png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _encode_png_quantized(img: Image.Image) -> bytes:
    # 256-color adaptive palette: dramatic size cut for screenshots/UI/text,
    # visually near-lossless for such content.
    rgb = img.convert("RGBA") if "A" in img.getbands() else img.convert("RGB")
    q = rgb.quantize(colors=256, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE)
    buf = io.BytesIO()
    q.save(buf, format="PNG")
    return buf.getvalue()


def shrink_image_bytes(
    data: bytes,
    max_dim: int = DEFAULT_MAX_DIM,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> tuple[bytes, ShrinkResult]:
    """Downscale image bytes to satisfy both max_dim and max_bytes.

    Returns (possibly unchanged) image bytes plus a ShrinkResult. Aspect ratio
    is always preserved. If the input is already within both limits it is
    returned untouched.
    """
    original_bytes = len(data)
    with Image.open(io.BytesIO(data)) as img:
        img.load()
        ow, oh = img.size
        base = img.copy()

    longest = max(ow, oh)

    # Fast path: already within both limits -> leave it completely alone.
    if longest <= max_dim and original_bytes <= max_bytes:
        return data, ShrinkResult(
            changed=False,
            original_size=(ow, oh),
            new_size=(ow, oh),
            original_bytes=original_bytes,
            new_bytes=original_bytes,
            note="no resize needed",
        )

    target_edge = min(max_dim, longest)
    best: tuple[bytes, tuple[int, int], str] | None = None

    while True:
        scale = target_edge / longest
        nw = max(1, round(ow * scale))
        nh = max(1, round(oh * scale))
        resized = base if (nw, nh) == (ow, oh) else base.resize(
            (nw, nh), Image.Resampling.LANCZOS
        )
        resized = _normalize_for_png(resized)

        png = _encode_png(resized)
        if len(png) <= max_bytes:
            strat = "resized" if target_edge < longest else "reencoded"
            best = (png, (nw, nh), strat)
            break

        quant = _encode_png_quantized(resized)
        if len(quant) <= max_bytes:
            best = (quant, (nw, nh), "quantized")
            break

        # Track smallest-so-far in case we bottom out at MIN_DIM.
        smaller = quant if len(quant) < len(png) else png
        best = (smaller, (nw, nh), "min-dim best-effort")

        if target_edge <= MIN_DIM:
            break
        target_edge = max(MIN_DIM, int(target_edge * 0.85))

    new_data, (nw, nh), strategy = best
    return new_data, ShrinkResult(
        changed=True,
        original_size=(ow, oh),
        new_size=(nw, nh),
        original_bytes=original_bytes,
        new_bytes=len(new_data),
        strategy=strategy,
    )
