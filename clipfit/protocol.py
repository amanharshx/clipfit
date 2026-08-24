"""Unix-socket protocol for the clipfit worker. Stdlib only."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path

MAX_MESSAGE_BYTES = 8192
SOCKET_TIMEOUT = 2.0


def socket_path() -> Path:
    env = os.environ.get("CLIPFIT_SOCKET")
    if env:
        return Path(env)
    return Path.home() / "Library" / "Caches" / "clipfit" / "worker.sock"


def parse_bytes(v: str) -> int:
    """Parse 3700000, 3.5mb, 800kb, 12b. Raises ValueError on bad input."""
    s = str(v).strip().lower()
    mult = 1
    if s.endswith("mb"):
        mult, s = 1024 * 1024, s[:-2]
    elif s.endswith("kb"):
        mult, s = 1024, s[:-2]
    elif s.endswith("b"):
        s = s[:-1]
    try:
        value = float(s) * mult
        if not math.isfinite(value):
            raise ValueError("not a finite size")
        return int(value)
    except (ValueError, OverflowError) as exc:
        raise ValueError(f"invalid byte size '{v}'; use a value such as 3.5mb") from exc


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
    if not isinstance(payload, dict):
        raise ValueError("response is not an object")
    rc = payload.get("rc")
    msg = payload.get("msg", "")
    if type(rc) is not int:
        raise ValueError("response rc is not an int")
    if not isinstance(msg, str):
        raise ValueError("response msg is not a string")
    return rc, msg
