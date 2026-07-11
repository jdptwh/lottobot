"""Regression tests for the GPT-drop root cause (2026-07): strict structured-output
schemas must be valid for OpenAI-compatible strict mode, a route that rejects
response_format outright must not silently drop the expert, and dropped experts
must carry their failure reason into the verdict. All mocked; no network."""
import panel.orchestrator as orch
from orch_fakes import FakeCallModel, expert_plan, synth
from panel.errors import TerminalProviderError

DEEPSEEK = "deepseek/deepseek-v4-pro"
GPT = "openai/gpt-5.5"
OPUS = "anthropic/claude-opus-4.8"
LINEUP = [DEEPSEEK, GPT]


# ---- strict-mode schema validity ---------------------------------------------

def _assert_strict_ok(schema, path="$"):
    """OpenAI strict mode rejects any object schema that omits
    additionalProperties:false or leaves a property out of required."""
    if not isinstance(schema, dict):
        return
    if schema.get("type") == "object":
        assert schema.get("additionalProperties") is False, f"{path}: additionalProperties must be false"
        props = schema.get("properties", {})
        assert set(schema.get("required", [])) == set(props), f"{path}: required must list every property"
        for k, sub in props.items():
            _assert_strict_ok(sub, f"{path}.{k}")
    if "items" in schema:
        _assert_strict_ok(schema["items"], f"{path}[]")


def test_all_response_format_schemas_are_strict_mode_valid():
    for rf in (orch._PLAN_EXPERT_RF, orch._REVIEW_EXPERT_RF, orch._SYNTH_RF, orch._ARBITER_RF):
        js = rf["json_schema"]
        assert rf["type"] == "json_schema" and js["strict"] is True
        assert js["schema"]["type"] == "object"
        assert js["schema"]["properties"], f"{js['name']}: bare object schema regressed"
        _assert_strict_ok(js["schema"], js["name"])


def test_plan_and_review_experts_get_gate_specific_schemas():
    fake = FakeCallModel({DEEPSEEK: (expert_plan(), 0.001), GPT: (expert_plan(), 0.001),
                          OPUS: (synth(), 0.002)})
    orch.run_plan("t", "x", LINEUP, OPUS, call_model=fake, seed=1)
    expert_rfs = [c["response_format"] for c in fake.calls if c["model"] != OPUS]
    assert all(rf["json_schema"]["name"] == "expert_plan" for rf in expert_rfs)


# ---- 400 fallback: retry once without response_format -------------------------

def test_schema_rejected_expert_falls_back_without_response_format():
    bad_schema = TerminalProviderError(
        "Invalid schema for response_format 'expert_plan': "
        "'additionalProperties' is required to be supplied and to be false", code=400)
    fake = FakeCallModel({
        DEEPSEEK: (expert_plan(summary="ds"), 0.001),
        GPT: [bad_schema, (expert_plan(summary="gpt"), 0.001)],
        OPUS: (synth(), 0.002),
    })
    v = orch.run_plan("t", "x", LINEUP, OPUS, call_model=fake, seed=1)
    gpt_calls = [c for c in fake.calls if c["model"] == GPT]
    assert len(gpt_calls) == 2
    assert gpt_calls[0]["response_format"] is not None
    assert gpt_calls[1]["response_format"] is None          # fallback drops the rf
    assert len(v["expert_opinions"]) == 2                    # GPT survived
    assert not any("dropped expert" in b
                   for b in v["disagreement_summary"]["blind_spots"])


def test_auth_error_does_not_fall_back():
    fake = FakeCallModel({
        DEEPSEEK: (expert_plan(), 0.001),
        GPT: TerminalProviderError("invalid credentials", code=401),
        OPUS: (synth(), 0.002),
    })
    v = orch.run_plan("t", "x", LINEUP, OPUS, call_model=fake, seed=1)
    assert len([c for c in fake.calls if c["model"] == GPT]) == 1   # no second attempt
    assert v["verdict"] == "REVISE"                                  # <2 survivors


# ---- dropped experts carry their reason ---------------------------------------

def test_dropped_expert_blind_spot_includes_reason():
    fake = FakeCallModel({
        DEEPSEEK: (expert_plan(), 0.001),
        GPT: TerminalProviderError("out of credits", code=402),
        OPUS: (synth(), 0.002),
    })
    v = orch.run_plan("t", "x", LINEUP, OPUS, call_model=fake, seed=1)
    notes = [b for b in v["disagreement_summary"]["blind_spots"] if "dropped expert" in b]
    assert notes, "dropped expert must be surfaced"
    assert GPT in notes[0] and "out of credits" in notes[0]


# ---- fenced-JSON tolerance -----------------------------------------------------

def test_fenced_json_expert_output_still_parses():
    fenced = '```json\n{"summary": "s", "recommendation": "r", "plan": "p", ' \
             '"confidence": 0.7, "findings": []}\n```'
    fake = FakeCallModel({DEEPSEEK: (expert_plan(), 0.001), GPT: (fenced, 0.001),
                          OPUS: (synth(), 0.002)})
    v = orch.run_plan("t", "x", LINEUP, OPUS, call_model=fake, seed=1)
    assert len(v["expert_opinions"]) == 2
