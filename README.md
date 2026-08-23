<h1 align="center">🖼️🤏 clipfit</h1>

<p align="center">
  <strong>Shrink big clipboard images so LLM chats can read them.</strong>
</p>

<p align="center">
  One hotkey resizes the screenshot on your clipboard to fit an LLM's size
  limits, then you paste as usual. Aspect ratio kept, text stays sharp.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.9%2B-blue" alt="Python 3.9+">
  <img src="https://img.shields.io/badge/platform-macOS-lightgrey" alt="Platform macOS">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT License">
</p>

<p align="center">
  <a href="#see-it">See it</a> ·
  <a href="#install">Install</a> ·
  <a href="#usage">Usage</a> ·
  <a href="#bind-a-hotkey">Hotkey</a> ·
  <a href="#how-it-fits-the-limits">How it works</a> ·
  <a href="#large-and-ultrawide-displays">Big displays</a>
</p>

---

## See it

Chat tools reject images for two reasons: the image is too wide (Kiro skips
anything over 2000px), or the file is too big (many tools cap a request at
5 MB). clipfit fixes both. If the image is already small enough, it does
nothing.

| Before | After clipfit |
| --- | --- |
| 3420 x 2214, ~1 MB screenshot | 1568 x 1015, fits the 2000px and 5 MB limits |
| 7680 x 4320 (8K), 86 MB | 1568 x 882, base64 under 5 MB, in about half a second |

You run it per image. Copy the way you always do, then press a hotkey only when
the image is going to an LLM. Nothing runs on every copy.

## Install

```bash
git clone https://github.com/amanharshx/clipfit.git
cd clipfit
python3 -m venv .venv
.venv/bin/pip install -e .
```

Needs macOS (it uses `NSPasteboard` through pyobjc) and Python 3.9 or newer.

Developed and tested on a MacBook Air (15-inch, M4), 2880 x 1864 display. It
does not depend on screen size, so it should work on any Mac. clipfit only
looks at the image, not the display.

## Usage

```bash
clipfit                    # shrink the clipboard image in place
clipfit --max-dim 2000     # set a different longest-edge cap
clipfit --max-bytes 3.5mb  # set a different size budget
clipfit --quiet --notify   # no terminal output, show a macOS notification (for a hotkey)
clipfit path/to/img.png    # shrink a file instead; writes img_fit.png
```

Change either cap with `--max-dim` and `--max-bytes`, or with the
`CLIPFIT_MAX_DIM` and `CLIPFIT_MAX_BYTES` environment variables. The defaults
are 1568px and about 3.7MB; the reasoning is below.

## Why these defaults

**1568px longest edge.** Most vision models downsample images to roughly this
size before they look at them. Capping here shrinks the file with no real
quality loss to the model, and it clears width limits like Kiro's 2000px.

**~3.7 MB byte budget.** This targets the strictest common limit: the Claude
API rejects any image larger than 5 MB *after base64 encoding*. That is the
exact error you get in Kiro (which runs Claude): `image exceeds 5 MB maximum`.
Base64 makes an image about 33% bigger (4/3), so to keep the encoded image
under 5 MB the raw image must stay under ~3.9 MB. clipfit aims for 3.7 MB to
leave a margin.

Other tools set different limits (OpenAI allows about 20 MB, for example). If
yours is stricter or looser, change `--max-bytes` or `CLIPFIT_MAX_BYTES`.

## Bind a hotkey

Point a keyboard shortcut at `bin/clipfit-hotkey`. Take a screenshot as usual,
press the shortcut, then paste. Only that keypress touches the clipboard. You
hear a short sound on success, since macOS can hide notifications.

In the examples below, replace `/path/to/clipfit` with the full path to your
clone (run `pwd` inside the repo to get it).

<details>
<summary><strong>skhd</strong> (recommended, lightest)</summary>

`brew install skhd`, then add to `~/.config/skhd/skhdrc`:

```
# Option+Shift+V: shrink the clipboard image for LLMs
alt + shift - v : /path/to/clipfit/bin/clipfit-hotkey
```

Start it as a login service with `skhd --start-service`. macOS will ask for
Accessibility permission the first time; grant it to skhd in System Settings,
Privacy & Security, Accessibility.

</details>

<details>
<summary><strong>Hammerspoon</strong></summary>

In `~/.hammerspoon/init.lua`:

```lua
hs.hotkey.bind({"alt", "shift"}, "V", function()
  hs.task.new("/path/to/clipfit/bin/clipfit-hotkey", nil):start()
end)
```

</details>

<details>
<summary><strong>Automator Quick Action</strong> (no install)</summary>

New, then Quick Action, set input to "no input", add a Run Shell Script step
that runs `/path/to/clipfit/bin/clipfit-hotkey`, save it, then
assign a shortcut in System Settings, Keyboard, Keyboard Shortcuts, Services.

</details>

The wrapper has a tunable block at the top. Change `CLIPFIT_MAX_DIM` or
`CLIPFIT_MAX_BYTES` there to adjust the caps for every press.

## How it fits the limits

1. Shrink the longest edge to `--max-dim` (default 1568px).
2. Keep a full-quality PNG if it fits `--max-bytes`.
3. If it does not fit, try a 256-color PNG. This stays sharp for screenshots
   and UI.
4. If it still does not fit, lower the resolution until it does.

The output is always PNG. clipfit puts both a TIFF and a PNG on the clipboard,
so the image pastes into native Mac apps and into Electron or Chromium chat
boxes.

## Large and ultrawide displays

Screen size does not matter. clipfit caps the longest edge, so a bigger capture
just shrinks more. A full 8K grab (7680 x 4320, about 86MB) comes out at
1568 x 882 and under 5MB, in about half a second. The slow part is decoding the
large source, so very big images take a bit longer than a laptop screenshot.

Ultrawide is the one trade-off. A 5120 x 1440 screen shrinks to 1568 x 441. It
fits and pastes, but 441px tall makes the text small and harder for the model
to read. That is what capping the width does to a very wide image. On such a
screen, capture a window or a region instead of the full width.

## Limitations

- macOS only. It reads and writes the clipboard through `NSPasteboard`.
- Clipboard mode replaces the clipboard with the smaller image. Your original
  full-size copy stays in Maccy's history if you use it.
- Very wide (ultrawide) full-screen grabs end up short after the width cap; see
  above.

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

## License

MIT. See [LICENSE](./LICENSE).
