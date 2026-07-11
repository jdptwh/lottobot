"""Config-editor dropdowns (2026-07 UX fix): lineups are checkbox chips, synth/
arbiter are selects over the verified slug list, roles get a datalist — and the
server comma-joins repeated lineup checkbox values into the config CSV."""
import threading
import urllib.error
import urllib.parse
import urllib.request

import pytest

from panel.config import load_config
from panel.dashboard.render import render_index
from panel.dashboard.server import make_server
from panel.prices import VERIFIED_PRICES

_COST = {"total_usd": 0, "count": 0, "latest": None}


def _page(editable):
    return render_index({"present": False}, _COST, editable)


def test_lineups_render_as_checkbox_groups():
    html = _page({"PANEL_PLAN_LINEUP": "anthropic/claude-fable-5,openai/gpt-5.5"})
    assert 'type="checkbox" name="PANEL_PLAN_LINEUP"' in html
    assert 'type="checkbox" name="PANEL_REVIEW_LINEUP"' in html
    # configured slugs come back checked; other verified slugs are offered unchecked
    assert 'value="openai/gpt-5.5" form="cfg" checked' in html
    assert 'value="deepseek/deepseek-v4-pro" form="cfg">' in html


def test_synth_and_arbiter_render_as_selects_with_verified_options():
    html = _page({"PANEL_PLAN_SYNTH": "anthropic/claude-opus-4.8"})
    assert '<select class="cfg-in" name="PANEL_PLAN_SYNTH"' in html
    assert '<select class="cfg-in" name="PANEL_REVIEW_ARBITER"' in html
    assert 'value="anthropic/claude-opus-4.8" selected' in html
    for slug in VERIFIED_PRICES:
        assert slug in html


def test_unknown_configured_slug_still_offered():
    # a hand-edited exotic slug must round-trip, not vanish on next save
    html = _page({"PANEL_PLAN_SYNTH": "acme/quantum-9"})
    assert 'value="acme/quantum-9" selected' in html


def test_role_fields_are_selects():
    html = _page({"PLANNER_MODEL": "claude-opus-4-8"})
    for key in ("PLANNER_MODEL", "REVIEWER_MODEL", "IMPLEMENTER_MODEL",
                "DRAFTER_MODEL", "BULK_MODEL"):
        assert f'<select class="cfg-in" name="{key}"' in html
    assert 'value="claude-opus-4-8" selected' in html


def test_unknown_role_value_is_preserved_as_selected_option():
    html = _page({"BULK_MODEL": "my-custom-model"})
    assert 'value="my-custom-model" selected' in html


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


def _post_form(base, pairs):
    data = urllib.parse.urlencode(pairs).encode()
    req = urllib.request.Request(base + "/api/config", data=data, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def test_checkbox_lineup_values_are_comma_joined(server, tmp_config):
    st = _post_form(server, [("PANEL_PLAN_LINEUP", ""),           # hidden blank
                             ("PANEL_PLAN_LINEUP", "anthropic/claude-fable-5"),
                             ("PANEL_PLAN_LINEUP", "openai/gpt-5.5"),
                             ("PANEL_PLAN_LINEUP", "deepseek/deepseek-v4-pro")])
    assert st == 200                       # urllib follows the 303 back to /
    cfg = load_config(str(tmp_config), warn=False)
    assert cfg.plan_lineup == ("anthropic/claude-fable-5", "openai/gpt-5.5",
                               "deepseek/deepseek-v4-pro")


def test_empty_lineup_selection_is_rejected_not_silently_saved(server, tmp_config):
    original = tmp_config.read_bytes()
    assert _post_form(server, [("PANEL_PLAN_LINEUP", "")]) == 400   # only the hidden blank
    assert tmp_config.read_bytes() == original


def test_cross_origin_post_is_refused(server, tmp_config):
    # audit fix: a page the user visits must not be able to drive /api/config
    original = tmp_config.read_bytes()
    data = urllib.parse.urlencode({"PANEL_MAX_COST_USD": "9.99"}).encode()
    req = urllib.request.Request(server + "/api/config", data=data, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded",
                                          "Origin": "http://evil.example.com"})
    try:
        urllib.request.urlopen(req, timeout=5)
        assert False, "expected 403"
    except urllib.error.HTTPError as e:
        assert e.code == 403
    assert tmp_config.read_bytes() == original          # config untouched


def test_same_origin_post_is_allowed(server, tmp_config):
    base = server                                        # loopback origin
    data = urllib.parse.urlencode({"PANEL_MAX_COST_USD": "4.75"}).encode()
    req = urllib.request.Request(base + "/api/config", data=data, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded",
                                          "Origin": base})
    with urllib.request.urlopen(req, timeout=5) as r:
        assert r.status == 200
    from panel.config import load_config
    assert load_config(str(tmp_config), warn=False).max_cost_usd == 4.75
