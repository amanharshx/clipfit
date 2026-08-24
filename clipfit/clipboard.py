"""macOS clipboard image access for clipfit via NSPasteboard.

Reads image data (PNG/TIFF) off the general pasteboard and writes shrunk PNG
data back. Import errors are surfaced clearly so the CLI can guide install.
"""

from __future__ import annotations

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


def _ensure_appkit() -> None:
    if not _APPKIT_OK:
        raise ClipboardError(
            "pyobjc (AppKit) is not available. Install it with:\n"
            "    pip install pyobjc-framework-Cocoa\n"
            f"(import error: {_IMPORT_ERROR})"
        )


def _pasteboard(pasteboard=None):
    return pasteboard if pasteboard is not None else NSPasteboard.generalPasteboard()


def read_image(pasteboard=None) -> bytes | None:
    """Return image bytes from the clipboard, or None if no image is present.

    Prefers PNG; falls back to TIFF (screenshots often land as TIFF).
    """
    _ensure_appkit()
    pb = _pasteboard(pasteboard)

    for pb_type in (NSPasteboardTypePNG, NSPasteboardTypeTIFF):
        data = pb.dataForType_(pb_type)
        if data is not None:
            return bytes(data)
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
