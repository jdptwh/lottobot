"""Fixture loader + socket-blocking autouse guard for the M1 scraper tests.

Mirrors the no-network discipline of tests/panel/test_no_network.py: patch
socket.socket.connect and urllib.request.urlopen (the low-level primitives
`requests`/`urllib.robotparser` both ultimately go through) so any test in
this package that accidentally tries a real connection fails loudly instead
of silently succeeding. Tests marked ``@pytest.mark.live`` are exempted —
they are excluded from the default gate by pyproject's `-m 'not live'`
addopts and are the one intentional network check the M1 spec calls for.
"""
import socket
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURE_HTML_PATH = FIXTURES_DIR / "unclaimed_prizes_2026-07-11.html"


@pytest.fixture
def fixture_html() -> str:
    """The frozen 2026-07-11 unclaimed-prizes fixture, as text."""
    return FIXTURE_HTML_PATH.read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _block_network(request, monkeypatch):
    if request.node.get_closest_marker("live"):
        yield
        return

    def no_connect(self, *a, **k):
        raise AssertionError(
            "socket.connect called — network attempted in a non-live scraper test"
        )

    def no_urlopen(*a, **k):
        raise AssertionError(
            "urllib.request.urlopen called — network attempted in a non-live scraper test"
        )

    monkeypatch.setattr(socket.socket, "connect", no_connect)
    monkeypatch.setattr("urllib.request.urlopen", no_urlopen)
    yield
