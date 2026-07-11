"""Wave 3 — tolerant expert parsing on large / free-form prompts.

Regression cover for the viceaudit2 failure: a big multi-artifact audit prompt
pushed both experts off the exact JSON envelope (one answered the task's own
findings schema with no summary; one fenced its JSON inside prose). The brittle
parser dropped/emptied them, <2 experts survived, and the panel collapsed to a
non-forming REVISE (synthesis.artifact=None). These tests pin the recovery paths
(fenced JSON, embedded JSON, findings->summary, prose->summary), the preserved
"trivial noise is still dropped" boundary, and the raw-capture diagnostics/logging.
"""
import logging

import panel.orchestrator as orch
from orch_fakes import FakeCallModel, expert_plan, synth

FABLE = "anthropic/claude-fable-5"
GPT = "openai/gpt-5.5"
OPUS = "anthropic/claude-opus-4.8"
LINEUP = [FABLE, GPT]


def _big_multi_artifact_prompt():
    """~40KB free-form prompt built from several concatenated artifacts, mirroring
    the shape (not content) of the real audit that triggered the failure."""
    blocks = []
    for name in ("SPEC", "MOCKUP", "ROUTING", "CONFIG", "NOTES"):
        body = f"Details for {name}. " * 400
        blocks.append(f"===== ARTIFACT: {name} =====\n{body}")
    return ("AUDIT TARGET — multi-artifact planning package.\n\n"
            + "\n\n".join(blocks)
            + "\n\nReturn concrete, actionable findings only.")


# fable's real shape: valid JSON, but it answered the *task's* findings schema
# (severity/where/problem), never our envelope -> summary/recommendation empty.
FINDINGS_ONLY_JSON = (
    '{"findings": ['
    '{"severity": "major", "where": "mockup/scenes.tsx", '
    '"problem": "left-rail destinations render nothing"},'
    '{"severity": "minor", "where": "spec", "problem": "no empty-state copy"}]}'
)

# gpt's real shape: a fenced JSON block wrapped in courteous prose.
FENCED_JSON_PROSE = (
    "Here is my independent review of the planning package.\n\n"
    "```json\n"
    '{"summary": "Single-screen workspace viable but under-specified for 7/8 rails.",'
    ' "recommendation": "Block approval until each rail has a rendered panel spec.",'
    ' "plan": "inventory -> spec each panel -> define nav state",'
    ' "confidence": 0.7,'
    ' "findings": [{"severity": "critical", "issue": "7/8 rail destinations unspecified"}]}'
    "\n```\n\nHappy to expand any section on request."
)


def _plan_fake(fable_content, gpt_content, synth_cost=0.002):
    return FakeCallModel({
        FABLE: (fable_content, 0.39),
        GPT: (gpt_content, 0.20),
        OPUS: (synth(), synth_cost),
    })


# ---- the headline regression: panel forms on the failing prompt --------------

def test_large_freeform_prompt_panel_forms_with_nonconforming_experts(lint_exit):
    prompt = _big_multi_artifact_prompt()
    fake = _plan_fake(FINDINGS_ONLY_JSON, FENCED_JSON_PROSE)
    v = orch.run_plan("viceaudit2", prompt, LINEUP, OPUS, call_model=fake, seed=0, cap_usd=10.0)

    # both experts survive -> a real panel (was: 1 survivor, synthesis.artifact=None)
    assert len(v["expert_opinions"]) == 2
    assert OPUS in fake.models_called()                     # synthesis actually ran
    assert v["synthesis"]["synthesizer"] == OPUS
    assert v["synthesis"]["artifact"] not in (None,)        # not the non-forming failure
    assert v["disagreement_summary"]["blind_spots"] == []   # nobody dropped

    # every surviving expert carries NON-EMPTY content (the core assertion)
    for e in v["expert_opinions"]:
        assert e["summary"].strip(), f"empty summary survived for {e['model']}"

    by_model = {e["model"]: e for e in v["expert_opinions"]}
    assert "finding(s)" in by_model[FABLE]["summary"]        # synthesized from findings
    assert by_model[GPT]["confidence"] == 0.7               # recovered from the fenced block
    assert lint_exit(v)[0] in (0, 1, 2)                      # a valid, gate-able verdict


# ---- individual recovery paths ----------------------------------------------

def test_findings_only_json_synthesizes_summary():
    fake = _plan_fake(FINDINGS_ONLY_JSON, expert_plan(summary="ok"))
    v = orch.run_plan("t", "x", LINEUP, OPUS, call_model=fake, seed=0, cap_usd=10.0)
    fable = next(e for e in v["expert_opinions"] if e["model"] == FABLE)
    assert fable["summary"].startswith("2 finding(s):")
    assert "left-rail destinations render nothing" in fable["summary"]


def test_fenced_json_block_is_extracted():
    fake = _plan_fake(expert_plan(summary="ok"), FENCED_JSON_PROSE)
    v = orch.run_plan("t", "x", LINEUP, OPUS, call_model=fake, seed=0, cap_usd=10.0)
    gpt = next(e for e in v["expert_opinions"] if e["model"] == GPT)
    assert "under-specified" in gpt["summary"]
    assert gpt["confidence"] == 0.7


def test_embedded_json_without_fence_is_extracted():
    embedded = ('My verdict: {"summary": "looks risky", "confidence": 0.4, '
                '"findings": []} — that is my final answer.')
    fake = _plan_fake(embedded, expert_plan(summary="ok"))
    v = orch.run_plan("t", "x", LINEUP, OPUS, call_model=fake, seed=0, cap_usd=10.0)
    fable = next(e for e in v["expert_opinions"] if e["model"] == FABLE)
    assert fable["summary"] == "looks risky"
    assert fable["confidence"] == 0.4


def test_substantive_prose_is_captured_into_summary():
    prose = ("This planning package is fundamentally sound but the nested-workspace "
             "navigation model is unspecified for most destinations; I would not "
             "approve it until that is resolved.")
    fake = _plan_fake(prose, expert_plan(summary="ok"))
    v = orch.run_plan("t", "x", LINEUP, OPUS, call_model=fake, seed=0, cap_usd=10.0)
    fable = next(e for e in v["expert_opinions"] if e["model"] == FABLE)
    assert fable["summary"].startswith("This planning package is fundamentally sound")


# ---- preserved boundary: trivial noise still fails ---------------------------

def test_trivial_noise_is_still_dropped(lint_exit):
    # short non-JSON noise (a stray token / refusal) must NOT masquerade as an
    # opinion; with one real expert that leaves <2 survivors -> structured REVISE.
    fake = _plan_fake("n/a", expert_plan(summary="ok"))
    v = orch.run_plan("t", "x", LINEUP, OPUS, call_model=fake, seed=0, cap_usd=10.0)
    assert v["verdict"] == "REVISE"
    assert v["synthesis"]["artifact"] is None               # non-forming
    assert OPUS not in fake.models_called()                 # synth skipped
    assert lint_exit(v)[0] == 2


def test_empty_dict_falls_through_and_is_dropped():
    fake = _plan_fake("{}", expert_plan(summary="ok"))
    v = orch.run_plan("t", "x", LINEUP, OPUS, call_model=fake, seed=0, cap_usd=10.0)
    assert len(v["expert_opinions"]) == 1                    # {} carried no signal
    assert any("dropped expert" in b for b in v["disagreement_summary"]["blind_spots"])


# ---- raw capture: diagnostics + logging -------------------------------------

def test_diagnostics_capture_raw_and_drop_reason():
    fake = _plan_fake(FENCED_JSON_PROSE, "n/a")             # one recovered, one dropped
    v = orch.run_plan("t", "x", LINEUP, OPUS, call_model=fake, seed=0, cap_usd=10.0)
    experts = {d["model"]: d for d in v["diagnostics"]["experts"]}

    assert experts[FABLE]["survived"] is True
    assert experts[FABLE]["recovered_via"] == "fenced-json"
    assert "```json" in experts[FABLE]["raw_preview"]        # the RAW response is retained

    assert experts[GPT]["survived"] is False
    assert experts[GPT]["raw_preview"] == "n/a"
    # the drop reason is named in blind_spots, not a silent "fewer than 2"
    assert any(GPT in b for b in v["disagreement_summary"]["blind_spots"])


def test_dropped_expert_raw_is_logged(caplog):
    fake = _plan_fake("n/a", expert_plan(summary="ok"))
    with caplog.at_level(logging.WARNING, logger="panel.orchestrator"):
        orch.run_plan("t", "x", LINEUP, OPUS, call_model=fake, seed=0, cap_usd=10.0)
    drop_logs = [r for r in caplog.records if "DROPPED" in r.getMessage()]
    assert drop_logs, "expected a WARNING logging the dropped expert's raw response"
    assert any("n/a" in r.getMessage() for r in drop_logs)
