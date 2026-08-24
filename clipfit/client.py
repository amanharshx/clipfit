"""Stdlib-only client for the resident worker. Avoids importing Pillow/AppKit."""

from __future__ import annotations

import argparse
import os
import socket
import sys

from .protocol import (
    MAX_MESSAGE_BYTES,
    SOCKET_TIMEOUT,
    decode_response,
    encode_request,
    parse_bytes,
    socket_path,
)


def _read_message(conn: socket.socket) -> bytes | None:
    conn.settimeout(SOCKET_TIMEOUT)
    raw = b""
    while b"\n" not in raw:
        remaining = MAX_MESSAGE_BYTES - len(raw)
        if remaining <= 0:
            return None
        try:
            chunk = conn.recv(min(4096, remaining + 1))
        except socket.timeout:
            return None
        if not chunk:
            return None
        raw += chunk
        if len(raw) > MAX_MESSAGE_BYTES:
            return None
    if len(raw) > MAX_MESSAGE_BYTES:
        return None
    return raw


def request_shrink(
    max_dim: int,
    max_bytes: int,
    quiet: bool,
    notify: bool,
    sound: bool,
    timeout: float = SOCKET_TIMEOUT,
) -> tuple[int, str] | None:
    path = socket_path()
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(str(path))
        sock.sendall(encode_request(max_dim, max_bytes, quiet, notify, sound))
        raw = _read_message(sock)
        if raw is None:
            return None
        return decode_response(raw)
    except (OSError, UnicodeDecodeError, ValueError, TypeError):
        return None
    finally:
        sock.close()


def _parse_bytes_arg(v: str) -> int:
    try:
        return parse_bytes(v)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    default_dim = os.environ.get("CLIPFIT_MAX_DIM", "1568")
    default_bytes = os.environ.get("CLIPFIT_MAX_BYTES", "3700000")
    parser = argparse.ArgumentParser(prog="clipfit-client", add_help=False)
    parser.add_argument("--max-dim", type=int, default=int(default_dim))
    parser.add_argument("--max-bytes", type=_parse_bytes_arg, default=_parse_bytes_arg(default_bytes))
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
