"""Image downscaling logic for clipfit.

Keeps everything the model needs (aspect ratio, sharp text) while capping the
longest edge so oversized images stop breaking LLM chat inputs.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image

# Most vision models internally downsample to roughly this size, so capping the
# longest edge here shrinks filesize with essentially no quality loss to the model.
DEFAULT_MAX_DIM = 1568


@dataclass
class ShrinkResult:
    """Outcome of a shrink attempt."""

    changed: bool
    original_size: tuple[int, int]
    new_size: tuple[int, int]
    original_bytes: int
    new_bytes: int
    note: str = ""

    def summary(self) -> str:
        ow, oh = self.original_size
        nw, nh = self.new_size
        if not self.changed:
            return f"already within limits ({ow}x{oh}, {_human(self.original_bytes)}) - {self.note}"
        return (
            f"{ow}x{oh} ({_human(self.original_bytes)}) "
            f"-> {nw}x{nh} ({_human(self.new_bytes)})"
        )


def _human(n: float) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}GB"


def shrink_image_bytes(
    data: bytes,
    max_dim: int = DEFAULT_MAX_DIM,
    fmt: str = "PNG",
) -> tuple[bytes, ShrinkResult]:
    """Downscale image bytes so the longest edge is <= max_dim.

    Returns the (possibly unchanged) image bytes plus a ShrinkResult describing
    what happened. Aspect ratio is always preserved; PNG output keeps text crisp.
    """
    original_bytes = len(data)
    with Image.open(io.BytesIO(data)) as img:
        img.load()
        ow, oh = img.size
        longest = max(ow, oh)

        if longest <= max_dim:
            return data, ShrinkResult(
                changed=False,
                original_size=(ow, oh),
                new_size=(ow, oh),
                original_bytes=original_bytes,
                new_bytes=original_bytes,
                note="no resize needed",
            )

        scale = max_dim / longest
        nw = max(1, round(ow * scale))
        nh = max(1, round(oh * scale))

        resized = img.resize((nw, nh), Image.Resampling.LANCZOS)

        # Normalize mode so PNG saving never fails on exotic modes.
        if fmt.upper() == "PNG" and resized.mode not in ("RGB", "RGBA", "L", "LA", "P"):
            resized = resized.convert("RGBA")

        out = io.BytesIO()
        # optimize=True was measured to add ~180ms on large images for identical
        # output size, so we use the default compression level (compress_level=6).
        resized.save(out, format=fmt.upper())
        new_data = out.getvalue()

    return new_data, ShrinkResult(
        changed=True,
        original_size=(ow, oh),
        new_size=(nw, nh),
        original_bytes=original_bytes,
        new_bytes=len(new_data),
    )
