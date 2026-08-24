"""Resident clipfit worker. Keeps Pillow/AppKit loaded and serves shrinks."""

from __future__ import annotations

import json
import socket
from typing import Callable

from .protocol import encode_request, socket_path

ShrinkFn = Callable[..., tuple[int, str]]


def handle_request(raw: bytes, shrink_fn: ShrinkFn) -> tuple[int, bytes]:
    try:
        payload = json.loads(raw.decode())
    except (UnicodeDecodeError, json.JSONDecodeError):
        body = json.dumps({"rc": 2, "msg": "invalid request"}) + "\n"
        return 2, body.encode()
    if payload.get("cmd") != "shrink":
        body = json.dumps({"rc": 2, "msg": "unknown command"}) + "\n"
        return 2, body.encode()
    rc, msg = shrink_fn(
        max_dim=int(payload.get("max_dim", 1568)),
        max_bytes=int(payload.get("max_bytes", 3_700_000)),
        quiet=bool(payload.get("quiet", False)),
        notify=bool(payload.get("notify", False)),
        sound=bool(payload.get("sound", False)),
    )
    body = json.dumps({"rc": rc, "msg": msg}) + "\n"
    return rc, body.encode()


def _default_shrink(max_dim, max_bytes, quiet, notify, sound) -> tuple[int, str]:
    from . import cli

    rc = cli._shrink_clipboard(max_dim, max_bytes, quiet, notify)
    if sound:
        cli._play_sound(ok=(rc == 0))
    return rc, ""


def serve(
    shrink_fn: ShrinkFn | None = None,
    ready=None,
    once: bool = False,
) -> None:
    fn = shrink_fn or _default_shrink
    path = socket_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(str(path))
    sock.listen(8)
    if ready is not None:
        ready.set()
    try:
        while True:
            conn, _unused = sock.accept()
            with conn:
                raw = b""
                while b"\n" not in raw:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    raw += chunk
                if raw:
                    _rc, body = handle_request(raw, shrink_fn=fn)
                    conn.sendall(body)
            if once:
                break
    finally:
        sock.close()
        try:
            path.unlink()
        except OSError:
            pass
