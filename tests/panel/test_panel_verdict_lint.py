"""Wave 1 — panel verdict schema + verdict_lint panel branch.

Fixture-driven tests for the "source":"panel" path, plus regression pins proving
the v4 reviewer-verdict path is behaviorally untouched, plus a schema/validator
drift tripwire. Stdlib + pytest only.
"""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LINT = REPO / ".claude" / "hooks" / "verdict_lint.py"
FIX = Path(__file__).resolve().parent / "fixtures"
SCHEMA = REPO / "panel" / "schema" / "panel_verdict.schema.json"


def run_lint(path):
    return subprocess.run(
        [sys.executable, str(LINT), str(path)],
        capture_output=True, text=True,
    )


# ---- panel exit-code contract ------------------------------------------------

import pytest


@pytest.mark.parametrize("fixture,expected", [
    ("plan_pass.json", 0),
    ("review_pass.json", 0),
    ("plan_fail.json", 1),
    ("plan_revise.json", 2),
    ("cost_cap_breached.json", 2),
    ("malformed_panel.json", 3),
])
def test_panel_exit_codes(fixture, expected):
    r = run_lint(FIX / fixture)
    assert r.returncode == expected, f"{fixture}: got {r.returncode}\n{r.stderr}"


def test_panel_missing_file_exits_1():
    # "source" is unreadable from an absent file, so missing shares v4's code 1.
    r = run_lint(FIX / "does_not_exist.json")
    assert r.returncode == 1, r.stderr


def test_cost_cap_overrides_pass(tmp_path):
    # A PASS verdict with cost_cap_breached:true must NOT exit 0 (ratification #3).
    v = json.loads((FIX / "plan_pass.json").read_text())
    assert v["verdict"] == "PASS"
    v["cost_cap_breached"] = True
    p = tmp_path / "v.json"
    p.write_text(json.dumps(v))
    assert run_lint(p).returncode == 2


def test_empty_expert_opinions_is_malformed(tmp_path):
    # ratification #2 — a zero-expert panel is a failed run, not a valid PASS.
    v = json.loads((FIX / "plan_pass.json").read_text())
    v["expert_opinions"] = []
    p = tmp_path / "v.json"
    p.write_text(json.dumps(v))
    assert run_lint(p).returncode == 3


def test_review_mode_null_artifact_and_findings():
    # review_pass exercises synthesis.artifact=null + findings[].arbiter_ruling.
    v = json.loads((FIX / "review_pass.json").read_text())
    assert v["synthesis"]["artifact"] is None
    assert any("arbiter_ruling" in f for f in v["synthesis"]["findings"])
    assert run_lint(FIX / "review_pass.json").returncode == 0


def test_bad_gate_enum_is_malformed(tmp_path):
    v = json.loads((FIX / "plan_pass.json").read_text())
    v["gate"] = "deploy"
    p = tmp_path / "v.json"
    p.write_text(json.dumps(v))
    assert run_lint(p).returncode == 3


def test_cost_usd_total_bool_rejected(tmp_path):
    # JSON booleans must not satisfy the number check (bool is a subclass of int).
    v = json.loads((FIX / "plan_pass.json").read_text())
    v["cost_usd_total"] = True
    p = tmp_path / "v.json"
    p.write_text(json.dumps(v))
    assert run_lint(p).returncode == 3


# ---- v4 path must be byte-for-byte behaviorally unchanged ---------------------

V4_VALID = {
    "task": "smoke", "verdict": "PASS", "findings": [],
    "escalate": False, "escalate_reason": "",
    "gates_rerun": True, "review_cycle": 1,
}


def test_v4_valid_still_exits_0(tmp_path):
    p = tmp_path / "verdict.json"
    p.write_text(json.dumps(V4_VALID))
    assert run_lint(p).returncode == 0


def test_v4_with_nonpanel_source_still_uses_v4_path(tmp_path):
    # A "source" that isn't "panel" must fall through to the v4 validator, which
    # rejects verdict "MAYBE" with code 2 (not the panel code 3).
    v = dict(V4_VALID, source="reviewer", verdict="MAYBE")
    p = tmp_path / "verdict.json"
    p.write_text(json.dumps(v))
    assert run_lint(p).returncode == 2


def test_v4_malformed_still_exits_2(tmp_path):
    p = tmp_path / "verdict.json"
    p.write_text('{"task": "x", "verdict": "MAYBE"}')
    assert run_lint(p).returncode == 2


def test_v4_missing_still_exits_1(tmp_path):
    assert run_lint(tmp_path / "nope.json").returncode == 1


# ---- schema <-> validator drift tripwire (R3) --------------------------------

def test_schema_parses_and_declares_contract():
    s = json.loads(SCHEMA.read_text())
    assert s["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    props = s["properties"]
    assert props["source"]["const"] == "panel"
    assert props["synthesis"]["properties"]["artifact"]["type"] == ["string", "null"]


def test_schema_enums_match_validator_tuples():
    # If someone edits the schema enums without updating verdict_lint (or vice
    # versa), this fails — the hand-rolled validator stays in sync with the doc.
    import importlib.util
    spec = importlib.util.spec_from_file_location("verdict_lint", LINT)
    mod = importlib.util.module_from_spec(spec)
    # Prevent the module's top-level validation run: it only executes with a real
    # file path; loading via import runs it against the default path which is
    # absent here -> SystemExit(1). Catch it so we can read the module constants.
    try:
        spec.loader.exec_module(mod)
    except SystemExit:
        pass
    s = json.loads(SCHEMA.read_text())
    props = s["properties"]
    assert tuple(props["gate"]["enum"]) == mod.PANEL_GATES
    assert tuple(props["verdict"]["enum"]) == mod.PANEL_VERDICTS
    findings = props["synthesis"]["properties"]["findings"]["items"]["properties"]
    assert tuple(findings["severity"]["enum"]) == mod.PANEL_SEVERITIES
    assert tuple(findings["arbiter_ruling"]["enum"]) == mod.PANEL_ARBITER_RULINGS
