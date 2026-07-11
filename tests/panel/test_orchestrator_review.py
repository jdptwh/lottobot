"""Wave 3 — REVIEW gate (union + arbiter on disputed) tests. All mocked."""
import panel.orchestrator as orch
from orch_fakes import FakeCallModel, arbiter, expert_review

OPUS = "anthropic/claude-opus-4.8"
GPT = "openai/gpt-5.5"
FABLE = "anthropic/claude-fable-5"
LINEUP = [OPUS, GPT]


def f(issue, severity, file="a.py", line=1, stance="issue"):
    return {"issue": issue, "severity": severity, "file": file, "line": line, "stance": stance}


def test_agreed_finding_not_disputed_no_arbiter_call():
    # both reviewers report the SAME finding at the same severity -> union, not disputed
    fake = FakeCallModel({
        OPUS: (expert_review(findings=[f("leak", "major")]), 0.002),
        GPT: (expert_review(findings=[f("leak", "major")]), 0.001),
        FABLE: (arbiter([]), 0.003),
    })
    v = orch.run_review("t", "diff", LINEUP, FABLE, call_model=fake, seed=1)
    assert FABLE not in fake.models_called()          # no disputed -> arbiter not called
    findings = v["synthesis"]["findings"]
    assert len(findings) == 1
    assert findings[0]["disputed"] is False
    assert findings[0]["arbiter_ruling"] is None
    assert sorted(findings[0]["source_models"]) == sorted(LINEUP)


def test_severity_conflict_is_disputed_and_arbiter_called_once(lint_exit):
    fake = FakeCallModel({
        OPUS: (expert_review(findings=[f("race", "critical")]), 0.002),
        GPT: (expert_review(findings=[f("race", "minor")]), 0.001),
        FABLE: (arbiter([{"id": "F1", "ruling": "upheld"}]), 0.003),
    })
    v = orch.run_review("t", "diff", LINEUP, FABLE, call_model=fake, seed=1)
    assert fake.models_called().count(FABLE) == 1     # arbiter called exactly once
    fnd = v["synthesis"]["findings"][0]
    assert fnd["disputed"] is True
    assert fnd["arbiter_ruling"] == "upheld"
    # upheld critical -> FAIL
    assert v["verdict"] == "FAIL"
    assert lint_exit(v)[0] == 1


def test_rejected_dispute_drops_from_verdict(lint_exit):
    fake = FakeCallModel({
        OPUS: (expert_review(findings=[f("style", "critical")]), 0.002),
        GPT: (expert_review(findings=[f("style", "minor")]), 0.001),
        FABLE: (arbiter([{"id": "F1", "ruling": "rejected"}]), 0.003),
    })
    v = orch.run_review("t", "diff", LINEUP, FABLE, call_model=fake, seed=1)
    fnd = v["synthesis"]["findings"][0]
    assert fnd["arbiter_ruling"] == "rejected"
    # rejected dispute is excluded from the effective verdict -> PASS
    assert v["verdict"] == "PASS"
    assert lint_exit(v)[0] == 0


def test_review_artifact_null_and_gate():
    fake = FakeCallModel({
        OPUS: (expert_review(findings=[f("x", "minor")]), 0.001),
        GPT: (expert_review(findings=[f("x", "minor")]), 0.001),
        FABLE: (arbiter([]), 0.003),
    })
    v = orch.run_review("t", "diff", LINEUP, FABLE, call_model=fake, seed=1)
    assert v["gate"] == "review"
    assert v["synthesis"]["artifact"] is None


def test_findings_deduped_and_stable_order():
    # opus reports two findings, gpt corroborates one; union dedups the shared one
    fake = FakeCallModel({
        OPUS: (expert_review(findings=[f("aaa", "minor", line=1), f("bbb", "critical", line=2)]), 0.001),
        GPT: (expert_review(findings=[f("aaa", "minor", line=1)]), 0.001),
        FABLE: (arbiter([]), 0.003),
    })
    v = orch.run_review("t", "diff", LINEUP, FABLE, call_model=fake, seed=1)
    findings = v["synthesis"]["findings"]
    assert len(findings) == 2                          # deduped (3 reported -> 2 unique)
    # stable: critical (rank 0) sorts before minor (rank 2)
    assert findings[0]["severity"] == "critical"
    assert findings[1]["severity"] == "minor"
