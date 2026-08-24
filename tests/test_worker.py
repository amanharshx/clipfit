import json
import os
import socket
import stat
import threading
import time
from pathlib import Path

import pytest

from clipfit import protocol, worker
from clipfit.protocol import MAX_MESSAGE_BYTES, SOCKET_TIMEOUT


def _sock(name: str) -> str:
    return f"/tmp/{name}"


def test_encode_request_is_one_json_line():
    raw = worker.encode_request(max_dim=1568, max_bytes=3700000, quiet=True, notify=True, sound=True)
    assert raw.endswith(b"\n")
    payload = json.loads(raw.decode())
    assert payload["cmd"] == "shrink"
    assert payload["max_dim"] == 1568
    assert payload["quiet"] is True


def test_handle_request_calls_shrink_and_returns_rc():
    calls = {}

    def shrink(max_dim, max_bytes, quiet, notify, sound):
        calls["args"] = (max_dim, max_bytes, quiet, notify, sound)
        return 0, "ok"

    req = worker.encode_request(max_dim=100, max_bytes=2048, quiet=True, notify=False, sound=False)
    rc, body = worker.handle_request(req, shrink_fn=shrink)
    assert rc == 0
    assert json.loads(body)["rc"] == 0
    assert calls["args"] == (100, 2048, True, False, False)


def test_handle_request_rejects_bad_json():
    rc, body = worker.handle_request(b"not-json\n", shrink_fn=lambda **k: (0, ""))
    assert rc == 2
    assert "invalid" in json.loads(body)["msg"]


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"cmd": "shrink", "max_dim": "bad", "max_bytes": 2048, "quiet": False, "notify": False, "sound": False},
        {"cmd": "shrink", "max_dim": -1, "max_bytes": 2048, "quiet": False, "notify": False, "sound": False},
        {"cmd": "shrink", "max_dim": 10, "max_bytes": 0, "quiet": False, "notify": False, "sound": False},
        {"cmd": "shrink", "max_dim": 10, "max_bytes": 2048, "quiet": 1, "notify": False, "sound": False},
    ],
)
def test_handle_request_rejects_wrong_shape(payload):
    raw = (json.dumps(payload) + "\n").encode()
    rc, body = worker.handle_request(raw, shrink_fn=lambda **k: (0, "ok"))
    assert rc == 2
    assert json.loads(body)["rc"] == 2


def test_handle_request_survives_shrink_exception():
    def boom(**_k):
        raise RuntimeError("nope")

    req = worker.encode_request(max_dim=100, max_bytes=2048, quiet=True, notify=False, sound=False)
    rc, body = worker.handle_request(req, shrink_fn=boom)
    assert rc == 2
    assert json.loads(body)["rc"] == 2


def test_socket_path_honors_env(monkeypatch, tmp_path):
    path = tmp_path / "w.sock"
    monkeypatch.setenv("CLIPFIT_SOCKET", str(path))
    assert worker.socket_path() == path


def test_claim_refuses_regular_file(tmp_path):
    path = tmp_path / "not-a-socket"
    path.write_text("keep me")
    with pytest.raises(worker.WorkerError, match="not a socket"):
        worker._claim_socket(path)
    assert path.read_text() == "keep me"


def test_claim_rejects_live_worker(monkeypatch):
    path = Path(_sock("clipfit-test-claim-live.sock"))
    monkeypatch.setenv("CLIPFIT_SOCKET", str(path))
    ready = threading.Event()

    def run():
        worker.serve(shrink_fn=lambda **k: (0, "ok"), ready=ready, once=False, preload_deps=False)

    threading.Thread(target=run, daemon=True).start()
    assert ready.wait(timeout=2)
    with pytest.raises(worker.WorkerAlreadyRunning):
        worker._claim_socket(path)
    # consume the waiting accept so the thread can exit
    s = socket.socket(socket.AF_UNIX)
    s.settimeout(1)
    s.connect(str(path))
    s.sendall(worker.encode_request(1, 2048, True, False, False))
    s.close()


def test_claim_removes_stale_socket():
    path = Path(_sock("clipfit-test-stale.sock"))
    if path.exists():
        path.unlink()
    stale = socket.socket(socket.AF_UNIX)
    stale.bind(str(path))
    stale.close()
    assert path.exists()
    sock, inode = worker._claim_socket(path)
    try:
        assert path.exists()
        assert stat.S_ISSOCK(path.stat().st_mode)
        assert path.stat().st_ino == inode
    finally:
        sock.close()
        path.unlink(missing_ok=True)


def test_old_worker_does_not_unlink_replacement():
    path = Path(_sock("clipfit-test-owned.sock"))
    if path.exists():
        path.unlink()
    first, inode1 = worker._claim_socket(path)
    first.close()
    path.unlink()
    second, inode2 = worker._claim_socket(path)
    assert inode1 != inode2
    worker._unlink_owned(path, inode1)
    assert path.exists()
    second.close()
    path.unlink()


def test_serve_one_request(monkeypatch):
    sock_path = _sock("clipfit-test-worker.sock")
    monkeypatch.setenv("CLIPFIT_SOCKET", sock_path)
    seen = {}

    def shrink(**kwargs):
        seen.update(kwargs)
        return 0, "already within limits"

    ready = threading.Event()

    def run():
        worker.serve(shrink_fn=shrink, ready=ready, once=True, preload_deps=False)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    assert ready.wait(timeout=2)
    conn = socket.socket(socket.AF_UNIX)
    conn.settimeout(2)
    conn.connect(sock_path)
    conn.sendall(worker.encode_request(max_dim=1568, max_bytes=3700000, quiet=True, notify=False, sound=False))
    data = b""
    while b"\n" not in data:
        chunk = conn.recv(4096)
        assert chunk
        data += chunk
    conn.close()
    t.join(timeout=2)
    assert json.loads(data.decode())["rc"] == 0
    assert seen["max_dim"] == 1568


def test_idle_client_times_out_without_blocking_next(monkeypatch):
    sock_path = _sock("clipfit-test-idle.sock")
    monkeypatch.setenv("CLIPFIT_SOCKET", sock_path)
    n = {"n": 0}

    def shrink(**_k):
        n["n"] += 1
        return 0, "ok"

    ready = threading.Event()

    def run():
        worker.serve(shrink_fn=shrink, ready=ready, once=False, preload_deps=False)

    threading.Thread(target=run, daemon=True).start()
    assert ready.wait(timeout=2)
    idle = socket.socket(socket.AF_UNIX)
    idle.settimeout(SOCKET_TIMEOUT + 1)
    idle.connect(sock_path)
    time.sleep(SOCKET_TIMEOUT + 0.3)
    idle.close()
    ok = socket.socket(socket.AF_UNIX)
    ok.settimeout(2)
    ok.connect(sock_path)
    ok.sendall(worker.encode_request(10, 2048, True, False, False))
    data = b""
    while b"\n" not in data:
        data += ok.recv(4096)
    ok.close()
    assert json.loads(data.decode())["rc"] == 0
    assert n["n"] == 1


def test_oversized_request_rejected(monkeypatch):
    sock_path = _sock("clipfit-test-oversize.sock")
    monkeypatch.setenv("CLIPFIT_SOCKET", sock_path)
    ready = threading.Event()

    def run():
        worker.serve(shrink_fn=lambda **k: (0, "ok"), ready=ready, once=True, preload_deps=False)

    threading.Thread(target=run, daemon=True).start()
    assert ready.wait(timeout=2)
    conn = socket.socket(socket.AF_UNIX)
    conn.settimeout(2)
    conn.connect(sock_path)
    try:
        conn.sendall(b"x" * (MAX_MESSAGE_BYTES + 50))
    except BrokenPipeError:
        pass
    data = b""
    try:
        while b"\n" not in data:
            chunk = conn.recv(4096)
            if not chunk:
                break
            data += chunk
    except (socket.timeout, BrokenPipeError):
        data = b""
    conn.close()
    if data:
        assert json.loads(data.decode())["rc"] == 2


def test_worker_survives_malformed_then_handles_valid(monkeypatch):
    sock_path = _sock("clipfit-test-survive.sock")
    monkeypatch.setenv("CLIPFIT_SOCKET", sock_path)
    n = {"n": 0}

    def shrink(**_k):
        n["n"] += 1
        return 0, "ok"

    ready = threading.Event()

    def run():
        worker.serve(shrink_fn=shrink, ready=ready, once=False, preload_deps=False)

    threading.Thread(target=run, daemon=True).start()
    assert ready.wait(timeout=2)
    bad = socket.socket(socket.AF_UNIX)
    bad.settimeout(2)
    bad.connect(sock_path)
    bad.sendall(b"[]\n")
    bad.recv(4096)
    bad.close()
    good = socket.socket(socket.AF_UNIX)
    good.settimeout(2)
    good.connect(sock_path)
    good.sendall(worker.encode_request(10, 2048, True, False, False))
    data = b""
    while b"\n" not in data:
        data += good.recv(4096)
    good.close()
    assert json.loads(data.decode())["rc"] == 0
    assert n["n"] == 1


def test_preload_runs_before_ready(monkeypatch):
    sock_path = _sock("clipfit-test-preload.sock")
    monkeypatch.setenv("CLIPFIT_SOCKET", sock_path)
    order = []

    def fake_preload():
        order.append("preload")

    monkeypatch.setattr(worker, "preload", fake_preload)
    ready = threading.Event()

    def on_ready():
        order.append("ready")
        ready.set()

    class Flag:
        def set(self):
            on_ready()

        def is_set(self):
            return ready.is_set()

    def run():
        worker.serve(shrink_fn=lambda **k: (0, "ok"), ready=Flag(), once=True, preload_deps=True)

    threading.Thread(target=run, daemon=True).start()
    assert ready.wait(timeout=2)
    assert order == ["preload", "ready"]
    s = socket.socket(socket.AF_UNIX)
    s.settimeout(1)
    s.connect(sock_path)
    s.sendall(worker.encode_request(10, 2048, True, False, False))
    s.close()


def test_parse_bytes_mb():
    assert protocol.parse_bytes("3.5mb") == int(3.5 * 1024 * 1024)
    assert protocol.parse_bytes("800kb") == 800 * 1024
    assert protocol.parse_bytes("3700000") == 3700000
