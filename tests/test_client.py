import os
import socket
import threading

import pytest

from clipfit import client, worker


def test_client_talks_to_worker(tmp_path, monkeypatch):
    sock_path = "/tmp/clipfit-test-client.sock"
    monkeypatch.setenv("CLIPFIT_SOCKET", sock_path)

    def shrink(**_kwargs):
        return 0, "shrunk"

    ready = threading.Event()

    def run():
        worker.serve(shrink_fn=shrink, ready=ready, once=True, preload_deps=False)

    threading.Thread(target=run, daemon=True).start()
    assert ready.wait(timeout=2)
    rc, msg = client.request_shrink(max_dim=1568, max_bytes=3700000, quiet=True, notify=False, sound=False)
    assert rc == 0
    assert msg == "shrunk"


def test_client_returns_none_when_no_server(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPFIT_SOCKET", str(tmp_path / "missing.sock"))
    assert client.request_shrink(max_dim=1568, max_bytes=3700000, quiet=True, notify=False, sound=False) is None


def test_client_parses_mb_env(monkeypatch):
    monkeypatch.setenv("CLIPFIT_MAX_BYTES", "3.5mb")
    seen = {}

    def fake(**kwargs):
        seen.update(kwargs)
        return 0, "ok"

    monkeypatch.setattr(client, "request_shrink", fake)
    assert client.main([]) == 0
    assert seen["max_bytes"] == int(3.5 * 1024 * 1024)


def test_client_invalid_env_is_argparse_error(monkeypatch, capsys):
    monkeypatch.setenv("CLIPFIT_MAX_DIM", "abc")
    with pytest.raises(SystemExit) as exc:
        client.main([])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "invalid" in err.lower() or "error" in err.lower()


def test_client_invalid_bytes_env_is_argparse_error(monkeypatch, capsys):
    monkeypatch.setenv("CLIPFIT_MAX_BYTES", "abc")
    with pytest.raises(SystemExit) as exc:
        client.main([])
    assert exc.value.code == 2
    assert "invalid byte size" in capsys.readouterr().err


def test_read_message_uses_passed_timeout(monkeypatch):
    seen = {}

    class Fake:
        def settimeout(self, t):
            seen["t"] = t

        def recv(self, _n):
            raise socket.timeout()

    assert client._read_message(Fake(), timeout=30.0) is None
    assert seen["t"] == 30.0


def test_malformed_response_falls_back(monkeypatch):
    sock_path = "/tmp/clipfit-test-bad-resp.sock"
    monkeypatch.setenv("CLIPFIT_SOCKET", sock_path)
    ready = threading.Event()

    def run():
        if os.path.exists(sock_path):
            os.unlink(sock_path)
        srv = socket.socket(socket.AF_UNIX)
        srv.bind(sock_path)
        srv.listen(1)
        ready.set()
        conn, _ = srv.accept()
        conn.recv(4096)
        conn.sendall(b"[]\n")
        conn.close()
        srv.close()
        os.unlink(sock_path)

    threading.Thread(target=run, daemon=True).start()
    assert ready.wait(timeout=2)
    assert client.request_shrink(10, 2048, True, False, False) is None
