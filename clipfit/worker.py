"""Resident clipfit worker. Keeps Pillow/AppKit loaded and serves shrinks."""

from __future__ import annotations

import json
import os
import socket
import stat
from pathlib import Path
from typing import Callable

from .protocol import MAX_MESSAGE_BYTES, SOCKET_TIMEOUT, encode_request, socket_path

ShrinkFn = Callable[..., tuple[int, str]]


class WorkerError(RuntimeError):
    """Worker could not start."""


class WorkerAlreadyRunning(WorkerError):
    """Another worker already owns the socket."""


def _error_body(msg: str) -> bytes:
    return (json.dumps({"rc": 2, "msg": msg}) + "\n").encode()


def _require_int(payload: dict, key: str, minimum: int) -> int:
    value = payload.get(key)
    if type(value) is not int:
        raise ValueError(f"{key} must be an integer")
    if value < minimum:
        raise ValueError(f"{key} must be >= {minimum}")
    return value


def _require_bool(payload: dict, key: str) -> bool:
    value = payload.get(key, False)
    if type(value) is not bool:
        raise ValueError(f"{key} must be a boolean")
    return value


def handle_request(raw: bytes, shrink_fn: ShrinkFn) -> tuple[int, bytes]:
    try:
        payload = json.loads(raw.decode())
        if not isinstance(payload, dict):
            raise ValueError("request must be an object")
        if payload.get("cmd") != "shrink":
            raise ValueError("unknown command")
        max_dim = _require_int(payload, "max_dim", 1)
        max_bytes = _require_int(payload, "max_bytes", 1024)
        quiet = _require_bool(payload, "quiet")
        notify = _require_bool(payload, "notify")
        sound = _require_bool(payload, "sound")
        rc, msg = shrink_fn(
            max_dim=max_dim,
            max_bytes=max_bytes,
            quiet=quiet,
            notify=notify,
            sound=sound,
        )
        return rc, (json.dumps({"rc": rc, "msg": msg}) + "\n").encode()
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, KeyError):
        return 2, _error_body("invalid request")
    except Exception:
        return 2, _error_body("invalid request")


def _default_shrink(max_dim, max_bytes, quiet, notify, sound) -> tuple[int, str]:
    from . import cli

    rc = cli._shrink_clipboard(max_dim, max_bytes, quiet, notify)
    if sound:
        cli._play_sound(ok=(rc == 0))
    return rc, ""


def preload() -> None:
    from PIL import Image  # noqa: F401

    from . import clipboard, core  # noqa: F401

    clipboard._ensure_appkit()


def _claim_socket(path: Path) -> tuple[socket.socket, int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    cache_dir = Path.home() / "Library" / "Caches" / "clipfit"
    if path.parent == cache_dir:
        os.chmod(path.parent, 0o700)
    if path.exists():
        mode = path.lstat().st_mode
        if not stat.S_ISSOCK(mode):
            raise WorkerError(f"{path} exists and is not a socket")
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        probe.settimeout(0.2)
        try:
            probe.connect(str(path))
        except OSError:
            path.unlink()
        else:
            raise WorkerAlreadyRunning("clipfit worker: already running")
        finally:
            probe.close()
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(str(path))
    os.chmod(path, 0o600)
    inode = path.stat().st_ino
    sock.listen(8)
    return sock, inode


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


def _unlink_owned(path: Path, inode: int) -> None:
    try:
        st = path.lstat()
    except OSError:
        return
    if stat.S_ISSOCK(st.st_mode) and st.st_ino == inode:
        try:
            path.unlink()
        except OSError:
            pass


def serve(
    shrink_fn: ShrinkFn | None = None,
    ready=None,
    once: bool = False,
    preload_deps: bool | None = None,
) -> None:
    fn = shrink_fn or _default_shrink
    if preload_deps is None:
        preload_deps = shrink_fn is None
    if preload_deps:
        preload()
    path = socket_path()
    sock, inode = _claim_socket(path)
    print(f"clipfit worker: listening at {path}", flush=True)
    if ready is not None:
        ready.set()
    try:
        while True:
            try:
                conn, _unused = sock.accept()
            except KeyboardInterrupt:
                break
            with conn:
                raw = _read_message(conn)
                if raw is None:
                    try:
                        conn.sendall(_error_body("invalid request"))
                    except OSError:
                        pass
                else:
                    try:
                        _rc, body = handle_request(raw, shrink_fn=fn)
                        conn.sendall(body)
                    except Exception:
                        try:
                            conn.sendall(_error_body("invalid request"))
                        except OSError:
                            pass
            if once:
                break
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()
        _unlink_owned(path, inode)
