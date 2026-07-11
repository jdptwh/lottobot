"""Wave 3 — PLAN gate (aggregator synthesis) tests. All mocked; no network."""
import panel.orchestrator as orch
from orch_fakes import FakeCallModel, expert_plan, synth

DEEPSEEK = "deepseek/deepseek-v4-pro"
GPT = "openai/gpt-5.5"
OPUS = "anthropic/claude-opus-4.8"
LINEUP = [DEEPSEEK, GPT]


def base_fake(synth_findings=None, contradictions=None, cost=0.001):
    return FakeCallModel({
        DEEPSEEK: (expert_plan(summary="ds"), cost),
        GPT: (expert_plan(summary="gpt"), cost),
        OPUS: (synth(findings=synth_findings, contradictions=contradictions), 0.002),
    })


def test_each_expert_called_once_plus_synth():
    fake = base_fake()
    orch.run_plan("t1", "do X", LINEUP, OPUS, call_model=fake, seed=1)
    called = fake.models_called()
    assert called.count(DEEPSEEK) == 1
    assert called.count(GPT) == 1
    assert called.count(OPUS) == 1


def test_plan_shape_and_pass_verdict(lint_exit):
    v = orch.run_plan("t1", "do X", LINEUP, OPUS, call_model=base_fake(), seed=1)
    assert v["gate"] == "plan"
    assert v["source"] == "panel"
    assert len(v["expert_opinions"]) == 2
    assert v["synthesis"]["synthesizer"] == OPUS
    assert v["synthesis"]["artifact"]           # non-null merged plan
    assert v["verdict"] == "PASS"
    assert lint_exit(v)[0] == 0


def test_critical_finding_yields_fail(lint_exit):
    fake = base_fake(synth_findings=[{"severity": "critical", "issue": "bad"}])
    v = orch.run_plan("t1", "x", LINEUP, OPUS, call_model=fake, seed=1)
    assert v["verdict"] == "FAIL"
    assert lint_exit(v)[0] == 1


def test_major_finding_yields_revise(lint_exit):
    fake = base_fake(synth_findings=[{"severity": "major", "issue": "meh"}])
    v = orch.run_plan("t1", "x", LINEUP, OPUS, call_model=fake, seed=1)
    assert v["verdict"] == "REVISE"
    assert lint_exit(v)[0] == 2


def test_contradictions_force_revise_even_without_findings(lint_exit):
    # J1: unresolved contradictions force at least REVISE
    fake = base_fake(contradictions=[{"topic": "approach",
                                      "positions": [{"label": "Expert A", "stance": "x"},
                                                    {"label": "Expert B", "stance": "y"}]}])
    v = orch.run_plan("t1", "x", LINEUP, OPUS, call_model=fake, seed=1)
    assert v["verdict"] == "REVISE"
    assert lint_exit(v)[0] == 2


def test_identity_stripped_from_synth_payload():
    fake = base_fake()
    orch.run_plan("t1", "do X", LINEUP, OPUS, call_model=fake, seed=1)
    synth_call = next(c for c in fake.calls if c["model"] == OPUS)
    payload = " ".join(m["content"] for m in synth_call["messages"])
    for leak in ("deepseek", "gpt-5.5", "openai/", "anthropic/", "opus", "fable"):
        assert leak not in payload.lower(), f"identity leak: {leak}"
    assert "Expert A" in payload and "Expert B" in payload


def test_seeded_order_is_deterministic():
    def order_for(seed):
        fake = base_fake()
        orch.run_plan("t1", "x", LINEUP, OPUS, call_model=fake, seed=seed)
        # experts appear in expert_opinions in dispatch (shuffled) order
        fake2 = base_fake()
        orch.run_plan("t1", "x", LINEUP, OPUS, call_model=fake2, seed=seed)
        v1 = [e for e in fake.models_called() if e != OPUS]
        v2 = [e for e in fake2.models_called() if e != OPUS]
        return v1, v2
    a, b = order_for(7)
    assert a == b                     # same seed -> identical order across runs


def test_template_token_reaches_synth():
    fake = base_fake()
    orch.run_plan("t1", "x", LINEUP, OPUS, call_model=fake, seed=1)
    synth_call = next(c for c in fake.calls if c["model"] == OPUS)
    payload = " ".join(m["content"] for m in synth_call["messages"])
    assert "do not infer missing facts" in payload.lower()


def test_response_format_requested():
    fake = base_fake()
    orch.run_plan("t1", "x", LINEUP, OPUS, call_model=fake, seed=1)
    assert all(c["response_format"]["type"] == "json_schema" for c in fake.calls)
