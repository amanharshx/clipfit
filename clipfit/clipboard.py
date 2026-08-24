"""macOS clipboard image access for clipfit via NSPasteboard.

Reads PNG and TIFF off the pasteboard and writes shrunk PNG back. Import
errors are surfaced clearly so the CLI can guide install.
"""

from __future__ import annotations

from struct import unpack

from .core import DEFAULT_MAX_BYTES, DEFAULT_MAX_DIM

_PNG_SIG = b"\x89PNG\r\n\x1a\n"

try:
    from AppKit import (
        NSData,
        NSImage,
        NSPasteboard,
        NSPasteboardTypePNG,
        NSPasteboardTypeTIFF,
    )

    _APPKIT_OK = True
    _IMPORT_ERROR = ""
except Exception as exc:  # pragma: no cover - environment dependent
    _APPKIT_OK = False
    _IMPORT_ERROR = str(exc)


class ClipboardError(RuntimeError):
    """Raised when the clipboard cannot be read or written."""


def png_header_size(data: bytes) -> tuple[int, int] | None:
    """Return (width, height) from a PNG IHDR, without decoding pixels."""
    # signature (8) + chunk length (4) + type (4) + IHDR payload (13)
    if len(data) < 24 or not data.startswith(_PNG_SIG):
        return None
    length, chunk = unpack(">I4s", data[8:16])
    if chunk != b"IHDR" or length < 8:
        return None
    width, height = unpack(">II", data[16:24])
    if width < 1 or height < 1:
        return None
    return width, height


def _ensure_appkit() -> None:
    if not _APPKIT_OK:
        raise ClipboardError(
            "pyobjc (AppKit) is not available. Install it with:\n"
            "    pip install pyobjc-framework-Cocoa\n"
            f"(import error: {_IMPORT_ERROR})"
        )


def _pasteboard(pasteboard=None):
    return pasteboard if pasteboard is not None else NSPasteboard.generalPasteboard()


def read_image(
    pasteboard=None,
    max_dim: int = DEFAULT_MAX_DIM,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> tuple[bytes, int] | None:
    """Return (bytes to decode, original PNG byte count), or None if no image.

    Reads PNG first. If that PNG already fits both limits, TIFF is not fetched.
    Oversized images use TIFF when present. original byte count is always the
    PNG size when a PNG exists, so TIFF size cannot break the no-op path.
    """
    _ensure_appkit()
    pb = _pasteboard(pasteboard)

    png_data = pb.dataForType_(NSPasteboardTypePNG)
    png = bytes(png_data) if png_data is not None else None
    if png is not None:
        size = png_header_size(png)
        if size is not None and max(size) <= max_dim and len(png) <= max_bytes:
            return png, len(png)
        tiff_data = pb.dataForType_(NSPasteboardTypeTIFF)
        if tiff_data is not None:
            return bytes(tiff_data), len(png)
        return png, len(png)

    tiff_data = pb.dataForType_(NSPasteboardTypeTIFF)
    if tiff_data is not None:
        tiff = bytes(tiff_data)
        return tiff, len(tiff)
    return None


def write_png(png_bytes: bytes, pasteboard=None) -> int:
    """Replace clipboard contents with the given PNG bytes.

    Returns the pasteboard change count after writing (useful for loop-guarding
    a future watcher so it can ignore its own writes).
    """
    _ensure_appkit()
    pb = _pasteboard(pasteboard)
    ns_data = NSData.dataWithBytes_length_(png_bytes, len(png_bytes))
    pb.clearContents()

    # Write BOTH TIFF and PNG. Native macOS apps typically paste from TIFF,
    # while Electron/Chromium-based apps prefer PNG. Providing both makes the
    # shrunk image pasteable everywhere instead of depending on the target app.
    wrote_any = False

    image = NSImage.alloc().initWithData_(ns_data)
    if image is not None:
        tiff = image.TIFFRepresentation()
        if tiff is not None and pb.setData_forType_(tiff, NSPasteboardTypeTIFF):
            wrote_any = True

    if pb.setData_forType_(ns_data, NSPasteboardTypePNG):
        wrote_any = True

    if not wrote_any:
        raise ClipboardError("failed to write image data to the clipboard")
    return int(pb.changeCount())
