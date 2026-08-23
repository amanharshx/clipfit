# clipfit

Shrink big clipboard images so LLM chats can read them.

Chat tools reject images for two reasons: the image is too wide (Kiro skips
anything over 2000px), or the file is too big (many tools cap a request at
5 MB). clipfit resizes the image on your clipboard to fit both limits. It keeps
the aspect ratio, and the text stays sharp. If the image is already small
enough, clipfit leaves it alone.

You run it per image. Copy the way you always do, then press a hotkey only when
the image is going to an LLM. Nothing runs on every copy.

## How it fits the limits

1. Shrink the longest edge to `--max-dim` (default 1568px).
2. Keep a full-quality PNG if it fits `--max-bytes`.
3. If it does not fit, try a 256-color PNG. This stays sharp for screenshots
   and UI.
4. If it still does not fit, lower the resolution until it does.

The output is always PNG. clipfit puts both a TIFF and a PNG on the clipboard,
so the image pastes into native Mac apps and into Electron or Chromium chat
boxes.

## Install

```bash
cd clipfit
python3 -m venv .venv
.venv/bin/pip install -e .
```

Needs macOS (it uses `NSPasteboard` through pyobjc) and Python 3.9 or newer.

## Usage

```bash
clipfit                    # shrink the clipboard image in place
clipfit --max-dim 2000     # set a different longest-edge cap
clipfit --max-bytes 3.5mb  # set a different size budget
clipfit --quiet --notify   # no terminal output, show a macOS notification (for a hotkey)
clipfit path/to/img.png    # shrink a file instead; writes img_fit.png
```

The default cap is 1568px. Most vision models shrink images to about that size
anyway, so a lower cap saves space with no real quality loss to the model. The
default size budget is about 3.7MB, which keeps the base64 image under a common
5 MB limit. Change either one with `--max-dim` and `--max-bytes`, or with the
`CLIPFIT_MAX_DIM` and `CLIPFIT_MAX_BYTES` environment variables.

## Bind a hotkey

Point a keyboard shortcut at `bin/clipfit-hotkey`. Take a screenshot as usual,
press the shortcut, then paste. Only that keypress touches the clipboard.

Use whichever hotkey tool you already have.

skhd (`brew install skhd`), in `~/.config/skhd/skhdrc`:

```
# Option+Shift+V: shrink the clipboard image for LLMs
alt + shift - v : /Users/aman/Developer/clipfit/bin/clipfit-hotkey
```

Hammerspoon, in `~/.hammerspoon/init.lua`:

```lua
hs.hotkey.bind({"alt", "shift"}, "V", function()
  hs.task.new("/Users/aman/Developer/clipfit/bin/clipfit-hotkey", nil):start()
end)
```

Automator Quick Action: New, then Quick Action, set input to "no input", add a
Run Shell Script step that runs `/Users/aman/Developer/clipfit/bin/clipfit-hotkey`,
save it, then assign a shortcut in System Settings, Keyboard, Keyboard
Shortcuts, Services.

## Notes

- Works with Maccy. After clipfit replaces the clipboard, Maccy stores the
  smaller image, which is usually what you want.
- File mode keeps your original and writes a new `_fit.png` file. Clipboard
  mode replaces the clipboard. To keep the full-size copy, grab it from Maccy.

## Test

```bash
.venv/bin/pip install pytest
.venv/bin/python -m pytest
```
