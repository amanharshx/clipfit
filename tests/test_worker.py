import json
import socket
import threading

from clipfit import worker


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


def test_socket_path_honors_env(monkeypatch, tmp_path):
    path = tmp_path / "w.sock"
    monkeypatch.setenv("CLIPFIT_SOCKET", str(path))
    assert worker.socket_path() == path


def test_serve_one_request(monkeypatch):
    sock_path = "/tmp/clipfit-test-worker.sock"
    monkeypatch.setenv("CLIPFIT_SOCKET", sock_path)
    seen = {}

    def shrink(**kwargs):
        seen.update(kwargs)
        return 0, "already within limits"

    ready = threading.Event()

    def run():
        worker.serve(shrink_fn=shrink, ready=ready, once=True)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    assert ready.wait(timeout=2)
    conn = socket.socket(socket.AF_UNIX)
    conn.settimeout(2)
    conn.connect(str(sock_path))
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
