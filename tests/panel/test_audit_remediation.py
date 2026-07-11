"""Regression tests for the v5.1 self-audit findings. Each pins the exact
FAILURE PATH that previously slipped through (provider returns garbage, hostile
config, cross-origin POST) — the happy-path suites never exercised these."""
import json

import panel.asset_qa as aq  # noqa: F401  (kept: asserts the module still imports)
import panel.orchestrator as orch
from orch_fakes import FakeCallModel, arbiter, expert_plan, expert_review, synth
from panel.errors import TerminalProviderError

OPUS = "anthropic/claude-opus-4.8"
GPT = "openai/gpt-5.5"
FABLE = "anthropic/claude-fable-5"
LINEUP = [OPUS, GPT]


def f(issue, severity, file="a.py", line=1, stance="issue"):
    return {"issue": issue, "severity": severity, "file": file, "line": line, "stance": stance}


# ---- Finding 1: synthesizer fail-open -> false PASS ---------------------------------

def test_unparseable_synthesizer_yields_revise_not_pass(lint_exit):
    fake = FakeCallModel({
        OPUS: (expert_plan(summary="a"), 0.001),
        GPT: (expert_plan(summary="b"), 0.001),
        FABLE: ("::: not json at all, model melted down :::", 0.002),   # garbage synth
    })
    v = orch.run_plan("t", "do X", LINEUP, FABLE, call_model=fake, seed=1)
    assert v["verdict"] == "REVISE"                       # was PASS before the fix
    assert v["synthesis"]["artifact"] is None
    assert any("parseable" in b for b in v["disagreement_summary"]["blind_spots"])
    assert lint_exit(v)[0] == 2                           # REVISE -> exit 2 (human)


def test_valid_synthesizer_with_empty_findings_still_passes(lint_exit):
    # the fix must NOT punish a legitimately clean synthesis
    fake = FakeCallModel({
        OPUS: (expert_plan(), 0.001), GPT: (expert_plan(), 0.001),
        FABLE: (synth(findings=[]), 0.002),
    })
    v = orch.run_plan("t", "x", LINEUP, FABLE, call_model=fake, seed=1)
    assert v["verdict"] == "PASS" and lint_exit(v)[0] == 0


# ---- Finding 2: arbiter fail-open -> disputed critical silently dropped -------------

def _disputed_critical_fake(arb_response):
    # OPUS says critical, GPT says the same finding is not_an_issue -> DISPUTED
    return FakeCallModel({
        OPUS: (expert_review(findings=[f("rce", "critical", stance="issue")]), 0.002),
        GPT: (expert_review(findings=[f("rce", "critical", stance="not_an_issue")]), 0.001),
        FABLE: arb_response,
    })


def test_failed_arbiter_keeps_disputed_critical_fail_closed(lint_exit):
    fake = _disputed_critical_fake(("garbage, arbiter died", 0.003))   # unparseable arbiter
    v = orch.run_review("t", "diff", LINEUP, FABLE, call_model=fake, seed=1)
    assert v["verdict"] == "FAIL"                         # was PASS before the fix
    assert any("did not rule" in b for b in v["disagreement_summary"]["blind_spots"])
    assert lint_exit(v)[0] == 1


def test_arbiter_explicit_reject_still_drops_the_finding(lint_exit):
    # the fix must still honor a real "rejected" ruling
    fake = _disputed_critical_fake((arbiter([{"id": "F1", "ruling": "rejected"}]), 0.003))
    v = orch.run_review("t", "diff", LINEUP, FABLE, call_model=fake, seed=1)
    assert v["verdict"] == "PASS" and lint_exit(v)[0] == 0


# ---- Cycle-2 findings (surfaced by re-auditing the fixes) --------------------------

def test_arbiter_provider_failure_does_not_crash_review(lint_exit):
    # a 500 on the SINGLE arbiter call must fail closed, not raise out of run_review
    fake = _disputed_critical_fake(TerminalProviderError("Internal Server Error", code=500))
    v = orch.run_review("t", "diff", LINEUP, FABLE, call_model=fake, seed=1)
    assert v["verdict"] == "FAIL"                         # disputed critical kept fail-closed
    assert lint_exit(v)[0] == 1


def test_malformed_arbiter_rulings_null_does_not_crash(lint_exit):
    # {"rulings": null} previously made .get("rulings", []) return None -> TypeError
    fake = _disputed_critical_fake(('{"rulings": null}', 0.003))
    v = orch.run_review("t", "diff", LINEUP, FABLE, call_model=fake, seed=1)
    assert v["verdict"] == "FAIL"                         # unruled -> fail closed


def test_truthy_nonlist_model_fields_never_crash(lint_exit):
    # cycle-3: a parseable-but-wrong-typed field ({"findings": 1}, {"rulings": "x"})
    # must not raise a TypeError out of the run (was: `x or []` let truthy non-lists
    # through into a for-loop).
    bad_synth = '{"artifact": "plan", "findings": 1, "consensus_points": "nope", ' \
                '"contradictions": 7, "blind_spots": {"a": 1}, "unique_insights": 3}'
    fake = FakeCallModel({OPUS: (expert_plan(), 0.001), GPT: (expert_plan(), 0.001),
                          FABLE: (bad_synth, 0.002)})
    v = orch.run_plan("t", "x", LINEUP, FABLE, call_model=fake, seed=1)   # must not raise
    assert v["verdict"] in ("PASS", "REVISE", "FAIL")
    assert lint_exit(v)[0] in (0, 1, 2)                   # schema-valid regardless

    bad_arb = _disputed_critical_fake(('{"rulings": 1}', 0.003))          # truthy non-list
    v2 = orch.run_review("t", "diff", LINEUP, FABLE, call_model=bad_arb, seed=1)
    assert v2["verdict"] == "FAIL"                        # unruled -> fail closed, no crash


def test_review_cost_cap_breach_keeps_union_findings(lint_exit):
    # two reviewers @0.03 = 0.06 > cap 0.05 -> breach BEFORE arbitration; a critical
    # already unioned must survive into the verdict (was discarded -> false PASS)
    fake = FakeCallModel({
        OPUS: (expert_review(findings=[f("rce", "critical")]), 0.03),
        GPT: (expert_review(findings=[f("rce", "critical")]), 0.03),
        FABLE: (arbiter([]), 0.01),
    })
    v = orch.run_review("t", "diff", LINEUP, FABLE, call_model=fake, seed=1, cap_usd=0.05)
    assert v["cost_cap_breached"] is True
    assert v["verdict"] == "FAIL"                         # critical preserved through the breach
    assert v["synthesis"]["findings"], "union findings discarded on cap breach"


# ---- Final-audit findings (post-remediation re-run, 2026-07-09) ---------------------

def test_cost_meter_rejects_insane_provider_costs():
    from panel.cost_meter import CostMeter
    m = CostMeter(cap_usd=1.0)
    # malformed usage.cost falls through to the token fallback when possible...
    m.add({"cost": float("nan"), "model": "deepseek/deepseek-v4-flash",
           "prompt_tokens": 1000, "completion_tokens": 1000})
    assert m.total > 0 and m.total == m.total          # finite, not NaN
    before = m.total
    m.add({"cost": -5.0, "model": "deepseek/deepseek-v4-flash",
           "prompt_tokens": 1000, "completion_tokens": 1000})
    assert m.total > before                            # negative "refund" rejected
    # ...and raises loudly when there is no fallback either
    import pytest as _pt
    with _pt.raises(ValueError):
        m.add({"cost": float("inf"), "model": "unknown/model"})


def test_malformed_finding_line_does_not_crash_union(lint_exit):
    bad = {"issue": "leak", "severity": "major", "file": "a.py", "line": "abc",
           "stance": "issue"}
    fake = FakeCallModel({
        OPUS: (expert_review(findings=[bad]), 0.002),
        GPT: (expert_review(findings=[bad]), 0.001),
        FABLE: (arbiter([]), 0.003),
    })
    v = orch.run_review("t", "diff", LINEUP, FABLE, call_model=fake, seed=1)  # no crash
    assert v["verdict"] == "REVISE" and lint_exit(v)[0] == 2


def test_unhashable_arbiter_id_does_not_crash(lint_exit):
    fake = _disputed_critical_fake(('{"rulings": [{"id": [], "ruling": "rejected"}]}', 0.003))
    v = orch.run_review("t", "diff", LINEUP, FABLE, call_model=fake, seed=1)  # no crash
    assert v["verdict"] == "FAIL"                       # non-str id dropped -> fail closed


def test_prose_only_reviewers_cannot_yield_clean_pass(lint_exit):
    # both reviewers answer in prose (tolerantly captured, findings channel lost):
    # an empty union must NOT read as a clean PASS
    prose = "Overall this change looks broadly reasonable to me based on the description " \
            "provided, though I could not fully assess the details in this format."
    fake = FakeCallModel({OPUS: (prose, 0.002), GPT: (prose, 0.001),
                          FABLE: (arbiter([]), 0.003)})
    v = orch.run_review("t", "diff", LINEUP, FABLE, call_model=fake, seed=1)
    assert v["verdict"] == "REVISE"                     # was PASS before the fix
    assert any("prose" in b for b in v["disagreement_summary"]["blind_spots"])
    assert lint_exit(v)[0] == 2


def test_structured_reviewers_with_prose_peer_still_work(lint_exit):
    prose = "I reviewed this change carefully and have written up my thoughts in " \
            "free-form because the JSON format was inconvenient for me today."
    fake = FakeCallModel({
        OPUS: (expert_review(findings=[f("rce", "critical")]), 0.002),
        GPT: (prose, 0.001),
        FABLE: (arbiter([]), 0.003),
    })
    v = orch.run_review("t", "diff", LINEUP, FABLE, call_model=fake, seed=1)
    assert v["verdict"] == "FAIL"                       # structured critical still lands
    assert any("prose" in b for b in v["disagreement_summary"]["blind_spots"])


def test_review_findings_carry_issue_text(lint_exit):
    fake = FakeCallModel({
        OPUS: (expert_review(findings=[f("connection leak in pool", "major", file="db.py", line=42)]), 0.002),
        GPT: (expert_review(findings=[f("connection leak in pool", "major", file="db.py", line=42)]), 0.001),
        FABLE: (arbiter([]), 0.003),
    })
    v = orch.run_review("t", "diff", LINEUP, FABLE, call_model=fake, seed=1)
    fnd = v["synthesis"]["findings"][0]
    assert fnd["issue"] == "connection leak in pool"    # actionable text in the artifact
    assert fnd["file"] == "db.py" and fnd["line"] == 42
    assert lint_exit(v)[0] == 2


def test_asset_sanitize_defects_nonlist_and_audio_enforced(tmp_path):
    # {"defects": 1} must not crash; and audio criteria PASS is downgraded in CODE
    assert aq._sanitize({"verdict": "PASS", "defects": 1})["verdict"] == "PASS"
    from orch_fakes import FakeCallModel as FCM
    img = tmp_path / "f.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
    fake = FCM({"openai/gpt-5.6-luna": ({"verdict": "PASS", "score": 1.0,
                                         "defects": [], "reprompt_hint": ""}, 0.01)})
    out = aq.judge_video("clip.mp4", "- clip has background music", "google/veo3.1",
                         frames=2, call_model=fake, prober=lambda _: 4.0,
                         extractor=lambda v, t, d: [img, img])
    assert out["verdict"] == "REVISE"                   # judge said PASS; code fails closed
    assert any("audio" in d["problem"] for d in out["defects"])


# ---- Finding 6: non-finite cost cap is a silent bypass ------------------------------

def test_config_rejects_infinite_cost_cap():
    from panel.config import load_config
    for bad in ("inf", "nan", "-inf", "0", "-5"):
        c = load_config(config_path="/no/file", environ={"PANEL_MAX_COST_USD": bad}, warn=False)
        assert c.max_cost_usd == 2.0, f"{bad!r} should fall back to default, got {c.max_cost_usd}"
    good = load_config(config_path="/no/file", environ={"PANEL_MAX_COST_USD": "3.5"}, warn=False)
    assert good.max_cost_usd == 3.5
