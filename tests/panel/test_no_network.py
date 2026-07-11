"""Wave 2 — hard tripwire: the mocked adapter path must never touch the network.

We make any real connection attempt fail loudly (socket.connect and
urllib.request.urlopen both raise). A mocked-transport call must still succeed,
proving the default gate cannot make a real request. We patch the `connect`
METHOD (not the socket class) so we don't disturb ssl's `class SSLSocket(socket)`.
"""
import json
import socket

import pytest

from panel.adapters import call_model


def test_mocked_transport_never_connects(monkeypatch):
    def no_connect(self, *a, **k):
        raise AssertionError("socket.connect called — network attempted in the gate")

    def no_urlopen(*a, **k):
        raise AssertionError("urllib.request.urlopen called — network attempted in the gate")

    monkeypatch.setattr(socket.socket, "connect", no_connect)
    monkeypatch.setattr("urllib.request.urlopen", no_urlopen)

    body = json.dumps({"choices": [{"message": {"content": "ok"}}],
                       "usage": {"cost": 0.001, "prompt_tokens": 3, "completion_tokens": 1}}).encode()

    def transport(url, data, headers):
        return 200, body

    r = call_model("m", [{"role": "user", "content": "hi"}], api_key="k", transport=transport)
    assert r.content == "ok"


def test_default_transport_would_use_urllib(monkeypatch):
    # Sanity: the DEFAULT transport really routes through urllib (so the guard
    # above is meaningful). Intercept urlopen and confirm it is reached.
    called = {"hit": False}

    def fake_urlopen(*a, **k):
        called["hit"] = True
        raise AssertionError("stop after proving urllib is the default path")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    with pytest.raises(AssertionError):
        call_model("m", [{"role": "user", "content": "hi"}], api_key="k")
    assert called["hit"] is True
