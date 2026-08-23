# clipfit

Shrink oversized clipboard images so LLM chats can actually read them.

Many chat tools silently drop or mangle images past a size limit (e.g. Kiro
skips images wider than 2000px), which breaks the "screenshot → paste into an
LLM" workflow. `clipfit` downscales the image on your clipboard so its longest
edge fits under a cap, **preserving aspect ratio and text sharpness**. Images
already within the limit are left untouched.

It's **opt-in per image** — you copy exactly as before, and only fire clipfit
(via a hotkey) when the image is headed for an LLM. Nothing runs on every copy.

## Install

```bash
cd clipfit
python3 -m venv .venv
.venv/bin/pip install -e .
```

Requires macOS (uses `NSPasteboard` via pyobjc) and Python 3.9+.

## Usage

```bash
clipfit                    # shrink the clipboard image in place (longest edge -> 1568px)
clipfit --max-dim 2000     # use a different cap
clipfit --quiet --notify   # no terminal output, show a macOS notification (hotkey mode)
clipfit path/to/img.png    # shrink a file instead -> writes img_fit.png
```

The default cap is **1568px** — most vision models downsample to about that
size internally, so going lower shrinks filesize with basically no quality loss
to the model. Override with `--max-dim` or the `CLIPFIT_MAX_DIM` env var.

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
