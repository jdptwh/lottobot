"""Wave 3 — defensive sanitization of untrusted model output (reviewer cycle-1 fixes).

verdict_lint.py is more lenient than the JSON schema, so these adversarial-input
tests assert the emitted dict is schema-valid AND that unrecognized model output is
dropped/clamped/normalized before it reaches the verdict or the gate.
"""
import panel.orchestrator as orch
from orch_fakes import (
    FakeCallModel, arbiter, assert_valid_panel_verdict, expert_plan, expert_review, synth,
)

DEEPSEEK = "deepseek/deepseek-v4-pro"
GPT = "openai/gpt-5.5"
OPUS = "anthropic/claude-opus-4.8"
FABLE = "anthropic/claude-fable-5"


def test_plan_unknown_severity_dropped(lint_exit):
    fake = FakeCallModel({
        DEEPSEEK: (expert_plan(), 0.001),
        GPT: (expert_plan(), 0.001),
        OPUS: (synth(findings=[{"severity": "blocker", "issue": "bogus"},
                               {"severity": "major", "issue": "real"}]), 0.002),
    })
    v = orch.run_plan("t", "x", [DEEPSEEK, GPT], OPUS, call_model=fake, seed=1, cap_usd=10.0)
    sevs = [f["severity"] for f in v["synthesis"]["findings"]]
    assert "blocker" not in sevs and "major" in sevs   # unknown dropped, valid kept
    assert v["verdict"] == "REVISE"                     # from the surviving major
    assert_valid_panel_verdict(v)
    assert lint_exit(v)[0] == 2                          # real verdict_lint accepts it


def test_plan_confidence_clamped(lint_exit):
    fake = FakeCallModel({
        DEEPSEEK: (expert_plan(confidence=5.0), 0.001),   # out of range high
        GPT: (expert_plan(confidence=-2.0), 0.001),       # out of range low
        OPUS: (synth(), 0.002),
    })
    v = orch.run_plan("t", "x", [DEEPSEEK, GPT], OPUS, call_model=fake, seed=1, cap_usd=10.0)
    for e in v["expert_opinions"]:
        assert 0.0 <= e["confidence"] <= 1.0
    assert_valid_panel_verdict(v)
    assert lint_exit(v)[0] == 0


def test_plan_contradictions_normalized_to_schema_shape(lint_exit):
    fake = FakeCallModel({
        DEEPSEEK: (expert_plan(), 0.001),
        GPT: (expert_plan(), 0.001),
        OPUS: (synth(contradictions=["they disagree on the approach"]), 0.002),  # bare strings
    })
    v = orch.run_plan("t", "x", [DEEPSEEK, GPT], OPUS, call_model=fake, seed=1, cap_usd=10.0)
    contradictions = v["disagreement_summary"]["contradictions"]
    assert all(isinstance(c, dict) and "topic" in c and "positions" in c for c in contradictions)
    assert v["verdict"] == "REVISE"                     # J1 preserved despite reshaping
    assert_valid_panel_verdict(v)
    assert lint_exit(v)[0] == 2


def test_review_unknown_severity_dropped(lint_exit):
    def f(sev):
        return {"issue": "x", "severity": sev, "file": "a.py", "line": 1, "stance": "issue"}
    fake = FakeCallModel({
        OPUS: (expert_review(findings=[f("blocker"), f("minor")]), 0.001),
        GPT: (expert_review(findings=[f("blocker")]), 0.001),
        FABLE: (arbiter([]), 0.003),
    })
    v = orch.run_review("t", "diff", [OPUS, GPT], FABLE, call_model=fake, seed=1, cap_usd=10.0)
    sevs = [f2["severity"] for f2 in v["synthesis"]["findings"]]
    assert "blocker" not in sevs                         # unknown dropped
    assert all(s in ("critical", "major", "minor") for s in sevs)
    assert_valid_panel_verdict(v)
    assert lint_exit(v)[0] in (0, 1, 2)


def test_review_emitted_dict_is_schema_valid():
    def f(sev):
        return {"issue": "y", "severity": sev, "file": "b.py", "line": 3, "stance": "issue"}
    fake = FakeCallModel({
        OPUS: (expert_review(confidence=9.0, findings=[f("critical")]), 0.001),
        GPT: (expert_review(findings=[f("minor")]), 0.001),
        FABLE: (arbiter([{"id": "F1", "ruling": "upheld"}]), 0.003),
    })
    v = orch.run_review("t", "diff", [OPUS, GPT], FABLE, call_model=fake, seed=1, cap_usd=10.0)
    assert_valid_panel_verdict(v)                        # incl. clamped confidence
