import json
import socket
import threading

from clipfit import client, worker


def test_client_talks_to_worker(tmp_path, monkeypatch):
    sock_path = "/tmp/clipfit-test-client.sock"
    monkeypatch.setenv("CLIPFIT_SOCKET", sock_path)

    def shrink(**_kwargs):
        return 0, "shrunk"

    ready = threading.Event()

    def run():
        worker.serve(shrink_fn=shrink, ready=ready, once=True)

    threading.Thread(target=run, daemon=True).start()
    assert ready.wait(timeout=2)
    rc, msg = client.request_shrink(max_dim=1568, max_bytes=3700000, quiet=True, notify=False, sound=False)
    assert rc == 0
    assert msg == "shrunk"


def test_client_returns_none_when_no_server(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPFIT_SOCKET", str(tmp_path / "missing.sock"))
    assert client.request_shrink(max_dim=1568, max_bytes=3700000, quiet=True, notify=False, sound=False) is None
