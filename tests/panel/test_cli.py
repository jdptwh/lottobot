"""Wave 4 — CLI: no-op when disabled, enabled write + exit lockstep, secret hygiene."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

import panel.cli as cli
import panel.orchestrator as orch
from orch_fakes import FakeCallModel, arbiter, expert_plan, expert_review, synth

REPO = Path(__file__).resolve().parents[2]
LINT = REPO / ".claude" / "hooks" / "verdict_lint.py"
F, G, O, FABLE = ("anthropic/claude-fable-5", "openai/gpt-5.5",
                  "anthropic/claude-opus-4.8", "anthropic/claude-fable-5")


def cfg_file(tmp_path, enabled, verdict_path):
    p = tmp_path / "agent.config"
    p.write_text(
        f'PANEL_ENABLED="{enabled}"\n'
        f'PANEL_VERDICT_PATH="{verdict_path}"\n'
        f'PANEL_PLAN_LINEUP="{F},{G}"\nPANEL_PLAN_SYNTH="{O}"\n'
        f'PANEL_REVIEW_LINEUP="{O},{G}"\nPANEL_REVIEW_ARBITER="{FABLE}"\n',
        encoding="utf-8")
    return str(p)


def plan_fake(synth_findings=None):
    return FakeCallModel({F: (expert_plan(), 0.001), G: (expert_plan(), 0.001),
                          O: (synth(findings=synth_findings), 0.002)})


# ---- disabled no-op (AC-4) ---------------------------------------------------

def test_disabled_is_noop(tmp_path, monkeypatch):
    vp = tmp_path / "verdict.json"
    conf = cfg_file(tmp_path, "0", str(vp))

    def boom(*a, **k):
        raise AssertionError("orchestrator must not be called when disabled")

    monkeypatch.setattr(orch, "run_plan", boom)
    monkeypatch.setattr(orch, "run_review", boom)
    code = cli.main(["plan", "task", "--task-id", "t", "--config", conf])
    assert code == 0
    assert not vp.exists()           # no file written


# ---- enabled happy path (AC-5, AC-6) -----------------------------------------

def test_enabled_writes_valid_verdict(tmp_path):
    vp = tmp_path / "state" / "verdict.json"   # nested -> parent dirs created
    conf = cfg_file(tmp_path, "1", str(vp))
    code = cli.main(["plan", "the task", "--task-id", "demo", "--config", conf],
                    call_model=plan_fake())
    assert code == 0
    v = json.loads(vp.read_text())
    assert v["gate"] == "plan" and v["source"] == "panel" and v["verdict"] == "PASS"
    # secret hygiene: no key material in the written file
    assert "OPENROUTER_API_KEY" not in vp.read_text()
    assert "ANTHROPIC_API_KEY" not in vp.read_text()


def test_review_subcommand(tmp_path):
    vp = tmp_path / "verdict.json"
    conf = cfg_file(tmp_path, "1", str(vp))
    fake = FakeCallModel({
        O: (expert_review(findings=[{"issue": "x", "severity": "minor", "file": "a", "line": 1, "stance": "issue"}]), 0.001),
        G: (expert_review(findings=[{"issue": "x", "severity": "minor", "file": "a", "line": 1, "stance": "issue"}]), 0.001),
        FABLE: (arbiter([]), 0.003),
    })
    code = cli.main(["review", "diff", "--task-id", "r1", "--config", conf], call_model=fake)
    v = json.loads(vp.read_text())
    assert v["gate"] == "review" and v["synthesis"]["artifact"] is None
    assert code in (0, 1, 2)


def test_prompt_from_file_and_missing_prompt(tmp_path):
    vp = tmp_path / "verdict.json"
    conf = cfg_file(tmp_path, "1", str(vp))
    pf = tmp_path / "spec.md"
    pf.write_text("a long spec prompt", encoding="utf-8")
    assert cli.main(["plan", "--task-id", "t", "--prompt-file", str(pf), "--config", conf],
                    call_model=plan_fake()) == 0
    # no prompt source -> error exit 2, no orchestrator call
    vp.unlink()
    code = cli.main(["plan", "--task-id", "t", "--config", conf], call_model=plan_fake())
    assert code == 2 and not vp.exists()


# ---- exit-code lockstep with verdict_lint (AC-7) -----------------------------

def _cli_exit_for(tmp_path, synth_findings):
    vp = tmp_path / "verdict.json"
    conf = cfg_file(tmp_path, "1", str(vp))
    code = cli.main(["plan", "task", "--task-id", "t", "--config", conf],
                    call_model=plan_fake(synth_findings))
    lint = subprocess.run([sys.executable, str(LINT), str(vp)], capture_output=True, text=True)
    return code, lint.returncode


@pytest.mark.parametrize("findings", [
    None,                                          # PASS -> 0
    [{"severity": "major", "issue": "m"}],         # REVISE -> 2
    [{"severity": "critical", "issue": "c"}],      # FAIL -> 1
])
def test_cli_exit_equals_verdict_lint(tmp_path, findings):
    cli_code, lint_code = _cli_exit_for(tmp_path, findings)
    assert cli_code == lint_code


def test_cost_cap_exit_is_two(tmp_path):
    vp = tmp_path / "verdict.json"
    conf = cfg_file(tmp_path, "1", str(vp))
    # tiny cap via env override; experts @0.03 each breach 0.05 before synth
    fake = FakeCallModel({F: (expert_plan(), 0.03), G: (expert_plan(), 0.03), O: (synth(), 0.02)})
    code = cli.main(["plan", "task", "--task-id", "t", "--config", conf],
                    call_model=fake, )
    # default cap 2.00 -> not breached; now force a tiny cap via env
    import os
    monkey = dict(os.environ)
    os.environ["PANEL_MAX_COST_USD"] = "0.05"
    try:
        vp.unlink()
        fake2 = FakeCallModel({F: (expert_plan(), 0.03), G: (expert_plan(), 0.03), O: (synth(), 0.02)})
        code2 = cli.main(["plan", "task", "--task-id", "t", "--config", conf], call_model=fake2)
    finally:
        os.environ.clear(); os.environ.update(monkey)
    v = json.loads(vp.read_text())
    assert v["cost_cap_breached"] is True and code2 == 2
