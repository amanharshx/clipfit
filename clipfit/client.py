"""Stdlib-only client for the resident worker. Avoids importing Pillow/AppKit."""

from __future__ import annotations

import argparse
import os
import socket
import sys

from .protocol import decode_response, encode_request, socket_path


def request_shrink(
    max_dim: int,
    max_bytes: int,
    quiet: bool,
    notify: bool,
    sound: bool,
    timeout: float = 30.0,
) -> tuple[int, str] | None:
    path = socket_path()
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(str(path))
        sock.sendall(encode_request(max_dim, max_bytes, quiet, notify, sound))
        raw = b""
        while b"\n" not in raw:
            chunk = sock.recv(4096)
            if not chunk:
                return None
            raw += chunk
        return decode_response(raw)
    except OSError:
        return None
    finally:
        sock.close()


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog="clipfit-client", add_help=False)
    parser.add_argument("--max-dim", type=int, default=int(os.environ.get("CLIPFIT_MAX_DIM", "1568")))
    parser.add_argument("--max-bytes", type=int, default=int(os.environ.get("CLIPFIT_MAX_BYTES", "3700000")))
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--notify", action="store_true")
    parser.add_argument("--sound", action="store_true")
    args = parser.parse_args(argv)

    got = request_shrink(
        max_dim=args.max_dim,
        max_bytes=args.max_bytes,
        quiet=args.quiet,
        notify=args.notify,
        sound=args.sound,
    )
    if got is not None:
        rc, msg = got
        if msg and not args.quiet:
            print(f"clipfit: {msg}")
        return rc

    # Worker is down. Fall back to a full clipfit process.
    from .hotkey import clipfit_binary

    os.execv(
        clipfit_binary(),
        [clipfit_binary()]
        + (["--quiet"] if args.quiet else [])
        + (["--notify"] if args.notify else [])
        + (["--sound"] if args.sound else [])
        + [f"--max-dim={args.max_dim}", f"--max-bytes={args.max_bytes}"],
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
