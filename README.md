# clipfit

Shrink oversized clipboard images so LLM chats can actually read them.

Many chat tools reject images on **two** axes: dimensions (e.g. Kiro skips
images wider than 2000px) and filesize (e.g. a 5 MB base64 request limit).
`clipfit` downscales the image on your clipboard so it fits **both** —
preserving aspect ratio and text sharpness. Images already within the limits
are left untouched.

It's **opt-in per image** — you copy exactly as before, and only fire clipfit
(via a hotkey) when the image is headed for an LLM. Nothing runs on every copy.

## How it fits the limits

1. Cap the longest edge at `--max-dim` (default 1568px).
2. Keep a full-quality lossless PNG if it fits `--max-bytes`.
3. If not, try a 256-color palette PNG (near-lossless for screenshots/UI).
4. If still too big, step the resolution down until it fits.

Output is always PNG, so it pastes reliably into native macOS apps and
Electron/Chromium chat inputs alike (both TIFF and PNG are written to the
clipboard).

## Install

```bash
cd clipfit
python3 -m venv .venv
.venv/bin/pip install -e .
```

Requires macOS (uses `NSPasteboard` via pyobjc) and Python 3.9+.

## Usage

```bash
clipfit                    # shrink the clipboard image in place
clipfit --max-dim 2000     # different longest-edge cap
clipfit --max-bytes 3.5mb  # different byte budget (keeps base64 under limits)
clipfit --quiet --notify   # no terminal output, show a macOS notification (hotkey mode)
clipfit path/to/img.png    # shrink a file instead -> writes img_fit.png
```

The default cap is **1568px** — most vision models downsample to about that
size internally, so going lower shrinks filesize with basically no quality loss
to the model. The default byte budget is **~3.7MB** so the base64-encoded image
stays under a common 5MB request limit. Override with `--max-dim` / `--max-bytes`
or the `CLIPFIT_MAX_DIM` / `CLIPFIT_MAX_BYTES` env vars.

## Bind a hotkey (the intended flow)

Point a keyboard shortcut at `bin/clipfit-hotkey`. Then: screenshot as usual
→ hit the shortcut → paste. Only that keypress touches the clipboard.

Pick whichever hotkey mechanism you already use:

**skhd** (`brew install skhd`) — add to `~/.config/skhd/skhdrc`:

```
# ⌥⇧V -> shrink clipboard image for LLMs
alt + shift - v : /Users/aman/Developer/clipfit/bin/clipfit-hotkey
```

**Hammerspoon** — in `~/.hammerspoon/init.lua`:

```lua
hs.hotkey.bind({"alt", "shift"}, "V", function()
  hs.task.new("/Users/aman/Developer/clipfit/bin/clipfit-hotkey", nil):start()
end)
```

**Automator Quick Action** — New → Quick Action → "no input" → Run Shell Script
`/Users/aman/Developer/clipfit/bin/clipfit-hotkey`, save, then assign a shortcut
in System Settings → Keyboard → Keyboard Shortcuts → Services.

## Notes

- Coexists with Maccy: after clipfit rewrites the clipboard, Maccy stores the
  shrunk version (usually what you want).
- Non-destructive to originals only in file mode; clipboard mode replaces the
  clipboard contents. If you want the full-res copy kept, grab it from Maccy.

## Test

```bash
.venv/bin/pip install pytest
.venv/bin/python -m pytest
```
