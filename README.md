<h1 align="center">🖼️🤏 clipfit</h1>

<p align="center">
  <strong>Fewer pixels, fewer tokens, same readable image. Made for pasting images into LLMs.</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.9%2B-blue" alt="Python 3.9+">
  <img src="https://img.shields.io/badge/platform-macOS-lightgrey" alt="Platform macOS">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT License">
</p>

<p align="center">
  <a href="#what-it-does">What it does</a> ·
  <a href="#install">Install</a> ·
  <a href="#set-up-the-hotkey">Set up the hotkey</a> ·
  <a href="#usage">Usage</a> ·
  <a href="#how-it-works">How it works</a> ·
  <a href="#behavior-and-limitations">Behavior and limitations</a>
</p>

---

> [!IMPORTANT]
> clipfit is **macOS** only. It uses the macOS clipboard, and skhd for the hotkey, so it does not run on Windows or Linux.

clipfit is a small macOS tool that shrinks the image on your clipboard so it is ready to paste into an LLM chat. It runs from one hotkey and keeps the text sharp.

## What it does

LLM chats handle large images differently. Some reject or silently skip
oversized inputs: [Amazon Q Developer](https://docs.aws.amazon.com/amazonq/latest/qdeveloper-ug/ide-chat-context.html)
caps image attachments at 3.75 MB, while
[Claude through Amazon Bedrock or Google Cloud](https://platform.claude.com/docs/en/build-with-claude/vision)
caps base64-encoded images at 5 MB.
clipfit keeps screenshots below these limits and reduces upload size.
Depending on the model, fewer pixels can also use fewer vision tokens. If the
image already fits, clipfit does nothing.

| Before | After clipfit |
| --- | --- |
| 3420 × 2214, ~1 MB screenshot | 1568 × 1015, fits limits above |
| 7680 × 4320 (8K), 86 MB | 1568 × 882, under clipfit's byte budget, in about half a second |

You run it per image. Copy the way you always do, then press a hotkey only when
the image is going to an LLM. Nothing runs on every copy.

## Install

```bash
brew install amanharshx/tap/clipfit
```

This installs clipfit and skhd, which provides the global hotkey. Prebuilt
wheels are used, so the install takes seconds, not minutes.

With pipx:

```bash
pipx install git+https://github.com/amanharshx/clipfit
```

pipx installs clipfit only. Install skhd separately
(`brew install asmvik/formulae/skhd`) if you
want `clipfit hotkey set`, or bind clipfit through another launcher.

Needs macOS (it uses `NSPasteboard` through pyobjc) and Python 3.9 or newer.

Developed and tested on a MacBook Air (15-inch, M4), 2880 × 1864 display. It
does not depend on screen size, so it should work on any Mac. clipfit only
looks at the image, not the display.

## Set up the hotkey

The simplest way, once installed:

```bash
clipfit hotkey set
clipfit worker
```

First configure the hotkey, then start the worker. `clipfit worker` stays in
the foreground, so leave that terminal open. It keeps Pillow and AppKit loaded
so the hotkey does not pay Python startup on every press. There is no launchd
or auto-start yet. If the worker is not running, `clipfit-client` falls back
to a normal `clipfit` process.

`clipfit hotkey set` asks for a shortcut (Enter accepts the default,
Option+Shift+V), writes an skhd binding to `clipfit-client` in a marked block
in your `~/.config/skhd/skhdrc`, starts skhd, and opens the Accessibility pane
so you can allow skhd. If you already had a clipfit hotkey, run
`clipfit hotkey set` again so it points at `clipfit-client`. After that: copy
an image, press the shortcut, then paste. Only that keypress touches the
clipboard.

`clipfit hotkey set` needs skhd on your PATH. If it is missing, clipfit says so
and exits; it does not treat that as an Accessibility problem.

macOS asks you to grant skhd Accessibility once. No installer can do this for
you; it is an OS security prompt. Run `clipfit hotkey show` to confirm the
status afterward.

Prefer a different launcher (Raycast, Hammerspoon, Karabiner, BetterTouchTool)?
Bind its shortcut to run `clipfit --quiet --notify --sound`. clipfit shrinks the
clipboard in place, so any launcher works.

<details>
<summary>Hammerspoon example</summary>

In `~/.hammerspoon/init.lua`. Replace the path with the output of
`which clipfit` (Intel Homebrew uses `/usr/local/bin`):

```lua
hs.hotkey.bind({"alt", "shift"}, "V", function()
  hs.task.new("/opt/homebrew/bin/clipfit", nil, {"--quiet", "--notify", "--sound"}):start()
end)
```

</details>

## Usage

```bash
clipfit                    # shrink the clipboard image in place
clipfit --max-dim 2000     # set a different longest-edge cap
clipfit --max-bytes 3.5mb  # set a different size budget
clipfit path/to/img.png    # shrink a file instead; writes img_fit.png

clipfit hotkey set         # pick or change the shortcut (interactive)
clipfit worker             # keep a warm process for the hotkey (foreground)
clipfit hotkey show        # show the current shortcut and status
clipfit hotkey remove      # remove the shortcut
```

Change either cap with `--max-dim` and `--max-bytes`, or with the
`CLIPFIT_MAX_DIM` and `CLIPFIT_MAX_BYTES` environment variables. The defaults
are 1568px and about 3.7 MB; the reasoning is below.

## How it works

1. Cap the longest edge at `--max-dim` (1568px by default).
2. Keep a full-color PNG if it fits `--max-bytes`.
3. If needed, try a 256-color PNG.
4. At or below 640px, also try 128- and 64-color palettes.
5. If it still does not fit, keep reducing the resolution until it does.

The byte limit is a hard guarantee. If clipfit has to go below 640px, it warns
that text may become harder to read.

The output is always PNG. clipfit puts both a TIFF and a PNG on the clipboard,
so the image pastes into native Mac apps and into Electron or Chromium chat
boxes.

## Why these defaults

**1568px longest edge.** This matches the native long-edge limit used by
[standard-resolution Claude vision](https://platform.claude.com/docs/en/build-with-claude/vision).
It also reduces upload time and can reduce vision-token use. Newer
high-resolution models can process more detail, so increase `--max-dim` when
working with dense diagrams or very small text.

**~3.7 MB byte budget.** [Claude through Amazon Bedrock or Google Cloud](https://platform.claude.com/docs/en/build-with-claude/vision)
limits each base64-encoded image to 5 MB. Base64 adds about 33% overhead, so
the raw image must stay below roughly 3.9 MB. clipfit targets 3.7 MB to leave
margin. That also fits [Amazon Q Developer's 3.75 MB image-attachment
limit](https://docs.aws.amazon.com/amazonq/latest/qdeveloper-ug/ide-chat-context.html).

Other products allow larger uploads: the [direct Claude API](https://platform.claude.com/docs/en/build-with-claude/vision)
accepts 10 MB base64-encoded images, [ChatGPT](https://help.openai.com/en/articles/8400551-image-inputs-for-chatgpt-faq)
accepts 20 MB per image, and [Gemini Apps](https://support.google.com/gemini/answer/14903178)
accepts files up to 100 MB. Use `--max-bytes` or `CLIPFIT_MAX_BYTES` when
another limit is preferable.

## Large and ultrawide screenshots

Screen size does not matter. clipfit caps the longest edge, so a bigger capture
just shrinks more. A full 8K grab (7680 × 4320, about 86 MB) comes out at
1568 × 882 and under 5 MB, in about half a second. The slow part is decoding the
large source, so very big images take a bit longer than a laptop screenshot.

Ultrawide is the one trade-off. A 5120 × 1440 screen shrinks to 1568 × 441. It
fits and pastes, but 441px tall makes the text small and harder for the model
to read. That is what capping the width does to a very wide image. On such a
screen, capture a window or a region instead of the full width.

## Behavior and limitations

- Clipboard mode replaces the current clipboard image. If you use a clipboard
  manager such as Maccy, the original stays in its history.
- File mode leaves the source file alone and writes a new `_fit.png` next to it.

## Development

```bash
git clone https://github.com/amanharshx/clipfit.git
cd clipfit
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/pip install pytest
.venv/bin/pytest
```

## License

MIT. See [LICENSE](./LICENSE).
