"""Wave 5 — HTTP-level UI smoke (GATE 3) + security invariants. All stdlib."""
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from panel.dashboard.server import make_server

REPO = Path(__file__).resolve().parents[2]
DASH = REPO / "panel" / "dashboard"


@pytest.fixture
def server(tmp_config, tmp_verdict, cost_log):
    httpd = make_server("127.0.0.1", 0, config_path=str(tmp_config),
                        verdict_path=str(tmp_verdict), cost_log_path=str(cost_log))
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    host, port = httpd.server_address
    try:
        yield f"http://{host}:{port}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        t.join(timeout=5)


def _get(base, path):
    with urllib.request.urlopen(base + path, timeout=5) as r:
        return r.status, r.read().decode("utf-8"), r.headers.get("Content-Type", "")


def test_bind_guard_refuses_non_loopback(cost_log):
    with pytest.raises(ValueError):
        make_server("0.0.0.0", 0, config_path="x", cost_log_path=str(cost_log))


def test_all_allowed_routes_200(server):
    st, body, ct = _get(server, "/")
    assert st == 200 and "text/html" in ct and "Latest verdict" in body
    for api in ("/api/verdict", "/api/cost", "/api/config"):
        st, body, ct = _get(server, api)
        assert st == 200 and "application/json" in ct
        json.loads(body)                                # parseable


def test_no_external_resources_in_page(server):
    _, body, _ = _get(server, "/")
    assert "http://" not in body and "https://" not in body   # no CDN/external


@pytest.mark.parametrize("path", ["/api/run", "/api/plan", "/api/review", "/api/execute", "/api/task", "/nope"])
def test_task_initiation_routes_are_absent(server, path):
    # GET
    try:
        st = urllib.request.urlopen(server + path, timeout=5).status
    except urllib.error.HTTPError as e:
        st = e.code
    assert st in (404, 405)
    # POST
    try:
        req = urllib.request.Request(server + path, data=b"{}",
                                     headers={"Content-Type": "application/json"}, method="POST")
        st = urllib.request.urlopen(req, timeout=5).status
    except urllib.error.HTTPError as e:
        st = e.code
    assert st in (404, 405)


def test_config_get_returns_only_allowlist(server):
    from panel.dashboard.config_writer import EDITABLE_KEYS
    _, body, _ = _get(server, "/api/config")
    data = json.loads(body)
    assert set(data) == set(EDITABLE_KEYS)
    assert not any("API_KEY" in k or "TOKEN" in k for k in data)


def test_post_config_round_trip_json(server, tmp_config):
    req = urllib.request.Request(server + "/api/config",
                                 data=json.dumps({"PANEL_MAX_COST_USD": "4.25"}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=5) as r:
        assert r.status == 200 and json.loads(r.read())["ok"] is True
    from panel.config import load_config
    assert load_config(str(tmp_config), warn=False).max_cost_usd == 4.25


def test_post_invalid_config_rejected(server, tmp_config):
    original = tmp_config.read_bytes()
    req = urllib.request.Request(server + "/api/config",
                                 data=json.dumps({"PANEL_MAX_COST_USD": "abc"}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        urllib.request.urlopen(req, timeout=5)
        assert False, "expected 400"
    except urllib.error.HTTPError as e:
        assert e.code == 400
    assert tmp_config.read_bytes() == original          # unchanged


# ---- security invariants (static) --------------------------------------------

def test_dashboard_imports_no_orchestrator_or_cli():
    # Must run in a FRESH interpreter: the shared pytest session has already imported
    # panel.orchestrator/panel.cli via other tests, so an in-process sys.modules check
    # would be polluted. A subprocess proves the dashboard's OWN import graph is clean.
    import subprocess
    import sys
    code = (
        "import importlib, sys\n"
        "for m in ('panel.dashboard','panel.dashboard.server','panel.dashboard.render',"
        "'panel.dashboard.config_writer','panel.dashboard.costlog','panel.dashboard.__main__'):\n"
        "    importlib.import_module(m)\n"
        "assert 'panel.orchestrator' not in sys.modules, 'orchestrator imported'\n"
        "assert 'panel.cli' not in sys.modules, 'cli imported'\n"
        "print('ok')\n"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=str(REPO))
    assert r.returncode == 0, r.stderr


def test_dashboard_sources_have_no_subprocess_or_secret():
    for pyfile in DASH.glob("*.py"):
        src = pyfile.read_text()
        for banned in ("subprocess", "os.system", "os.popen", "ANTHROPIC_API_KEY",
                       "OPENROUTER_API_KEY"):
            assert banned not in src, f"{pyfile.name} contains {banned}"
