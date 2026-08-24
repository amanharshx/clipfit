"""Unix-socket protocol for the clipfit worker. Stdlib only."""

from __future__ import annotations

import json
import os
from pathlib import Path


def socket_path() -> Path:
    env = os.environ.get("CLIPFIT_SOCKET")
    if env:
        return Path(env)
    return Path.home() / "Library" / "Caches" / "clipfit" / "worker.sock"


def encode_request(
    max_dim: int,
    max_bytes: int,
    quiet: bool,
    notify: bool,
    sound: bool,
) -> bytes:
    payload = {
        "cmd": "shrink",
        "max_dim": int(max_dim),
        "max_bytes": int(max_bytes),
        "quiet": bool(quiet),
        "notify": bool(notify),
        "sound": bool(sound),
    }
    return (json.dumps(payload, separators=(",", ":")) + "\n").encode()


def decode_response(raw: bytes) -> tuple[int, str]:
    payload = json.loads(raw.decode())
    return int(payload.get("rc", 2)), str(payload.get("msg", ""))
