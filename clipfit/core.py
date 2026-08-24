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

from PIL import Image, ImageOps, UnidentifiedImageError


class ByteBudgetError(ValueError):
    """Raised when no PNG can be produced under the requested byte budget."""


class ClipfitImageError(ValueError):
    """Raised when the input bytes cannot be read as an image."""

# Most vision models internally downsample to roughly this size, so capping the
# longest edge here shrinks filesize with essentially no quality loss to the model.
DEFAULT_MAX_DIM = 1568

# Keep base64(image) under a 5 MB (5,242,880 byte) request limit.
# raw <= 5,242,880 * 3/4 = 3,932,160; leave headroom for JSON/data-URI overhead.
DEFAULT_MAX_BYTES = 3_700_000

# Below this longest edge, text starts to get hard to read. clipfit only goes
# lower when the byte budget forces it; the byte limit is a hard guarantee.
QUALITY_FLOOR = 640


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
        line = (
            f"{ow}x{oh} ({_human(self.original_bytes)}) "
            f"-> {nw}x{nh} ({_human(self.new_bytes)}){extra}"
        )
        if self.note:
            line += f" - {self.note}"
        return line


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


def _encode_png_quantized(img: Image.Image, colors: int = 256) -> bytes:
    # Adaptive palette: dramatic size cut for screenshots/UI/text, visually
    # near-lossless for such content. Fewer colors = smaller file.
    rgb = img.convert("RGBA") if "A" in img.getbands() else img.convert("RGB")
    q = rgb.quantize(colors=colors, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE)
    buf = io.BytesIO()
    q.save(buf, format="PNG")
    return buf.getvalue()


def _floor_note(longest_edge: int) -> str:
    if longest_edge < QUALITY_FLOOR:
        return f"output is below {QUALITY_FLOOR}px; text may be hard to read"
    return ""


def shrink_image_bytes(
    data: bytes,
    max_dim: int = DEFAULT_MAX_DIM,
    max_bytes: int = DEFAULT_MAX_BYTES,
    force_png: bool = False,
    original_bytes: int | None = None,
) -> tuple[bytes, ShrinkResult]:
    """Downscale image bytes to satisfy both max_dim and max_bytes.

    Returns (possibly unchanged) image bytes plus a ShrinkResult. Aspect ratio
    is always preserved. If the input is already within both limits it is
    returned untouched, unless force_png is set (then it is always re-encoded
    to PNG, even when no resize is needed). A successful return guarantees
    len(output) <= max_bytes.

    Raises ByteBudgetError only when no PNG fits, which needs a budget smaller
    than the tiniest possible PNG (well under the CLI's 1024-byte minimum).
    """
    if original_bytes is None:
        original_bytes = len(data)
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            # Bake in EXIF orientation so rotated phone/camera JPEGs are not
            # saved sideways when re-encoded to PNG (PNG has no orientation tag).
            base = ImageOps.exif_transpose(img).copy()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ClipfitImageError(f"not a readable image ({exc})") from exc
    ow, oh = base.size

    longest = max(ow, oh)

    # Fast path: already within both limits -> leave it completely alone.
    # Skipped when force_png is set, so file mode always produces a PNG.
    if not force_png and longest <= max_dim and original_bytes <= max_bytes:
        return data, ShrinkResult(
            changed=False,
            original_size=(ow, oh),
            new_size=(ow, oh),
            original_bytes=original_bytes,
            new_bytes=original_bytes,
            note="no resize needed",
        )

    target_edge = min(max_dim, longest)

    while True:
        scale = target_edge / longest
        nw = max(1, round(ow * scale))
        nh = max(1, round(oh * scale))
        resized = base if (nw, nh) == (ow, oh) else base.resize(
            (nw, nh), Image.Resampling.LANCZOS
        )
        resized = _normalize_for_png(resized)

        # Full-color PNG first. Quantize only if that encoding is over budget.
        full = _encode_png(resized)
        if len(full) <= max_bytes:
            out_bytes = full
            strategy = "resized" if target_edge < longest else "reencoded"
            note = _floor_note(target_edge)
            break

        palettes = [256] + ([128, 64] if target_edge <= QUALITY_FLOOR else [])
        smallest = len(full)
        fit: tuple[bytes, str] | None = None
        for colors in palettes:
            quantized = _encode_png_quantized(resized, colors)
            smallest = min(smallest, len(quantized))
            if len(quantized) <= max_bytes:
                fit = (quantized, f"quantized {colors}c")
                break

        if fit is not None:
            out_bytes, strategy = fit
            note = _floor_note(target_edge)
            break

        if target_edge <= 1:
            raise ByteBudgetError(
                f"cannot produce a PNG under {_human(max_bytes)} "
                f"(smallest clipfit can make is {_human(smallest)})"
            )

        # Nothing fit at this size. Shrink further, but land exactly on the
        # readable floor when a plain step would skip past it, so we try 640px
        # (with smaller palettes) before going below it.
        next_edge = max(1, int(target_edge * 0.85))
        if target_edge > QUALITY_FLOOR and next_edge < QUALITY_FLOOR:
            target_edge = QUALITY_FLOOR
        else:
            target_edge = next_edge

    return out_bytes, ShrinkResult(
        changed=True,
        original_size=(ow, oh),
        new_size=(nw, nh),
        original_bytes=original_bytes,
        new_bytes=len(out_bytes),
        strategy=strategy,
        note=note,
    )
