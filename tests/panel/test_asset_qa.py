"""Asset pipeline Wave 1 — QA judge, cross-family picker, loop bookkeeping,
sidecar, CLI. All mocked; no network, no image models."""
import json

import pytest

import panel.asset_qa as aq
from orch_fakes import FakeCallModel

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
GEN = "google/nano-banana-2-pro"
LUNA = "openai/gpt-5.6-luna"


def png(tmp_path, name="asset.png"):
    p = tmp_path / name
    p.write_bytes(PNG)
    return p


def qa_json(verdict="PASS", score=0.9, defects=None, hint=""):
    return {"verdict": verdict, "score": score, "defects": defects or [], "reprompt_hint": hint}


# ---- cross-family judge (spec ruling 1) ----------------------------------------

def test_pick_judge_avoids_generator_family():
    assert aq.family(aq.pick_judge("openai/gpt-image-2")) != "openai"
    assert aq.family(aq.pick_judge("google/nano-banana-2-pro")) != "google"


def test_preferred_judge_same_family_is_overridden():
    j = aq.pick_judge("openai/gpt-image-2", preferred="openai/gpt-5.6-luna")
    assert aq.family(j) != "openai"          # bias-avoidance beats preference


def test_preferred_judge_cross_family_is_honored():
    assert aq.pick_judge(GEN, preferred="openai/gpt-5.6-sol") == "openai/gpt-5.6-sol"


def test_no_cross_family_judge_raises():
    with pytest.raises(ValueError, match="no cross-family judge"):
        aq.pick_judge("openai/gpt-image-2", pool=("openai/gpt-5.6-luna",))


# ---- judge call -----------------------------------------------------------------

def test_judge_sends_criteria_and_image_with_strict_schema(tmp_path):
    fake = FakeCallModel({LUNA: (qa_json(), 0.002)})
    out = aq.judge_asset(png(tmp_path), "no text artifacts", GEN, call_model=fake)
    assert out["verdict"] == "PASS" and out["judge"] == LUNA and out["cost_usd"] == 0.002
    call = fake.calls[0]
    rf = call["response_format"]["json_schema"]
    assert rf["strict"] is True and rf["schema"]["additionalProperties"] is False
    user = next(m for m in call["messages"] if m["role"] == "user")
    assert user["content"][0]["text"].startswith("ACCEPTANCE CRITERIA:")
    assert user["content"][1]["type"] == "image_url"


def test_judge_fenced_output_still_parses(tmp_path):
    fenced = "```json\n" + json.dumps(qa_json("REVISE", 0.4)) + "\n```"
    fake = FakeCallModel({LUNA: (fenced, 0.002)})
    out = aq.judge_asset(png(tmp_path), "c", GEN, call_model=fake)
    assert out["verdict"] == "REVISE" and out["score"] == 0.4


def test_sanitize_fails_closed():
    assert aq._sanitize({})["verdict"] == "REVISE"                       # unparseable -> REVISE
    assert aq._sanitize({"verdict": "MAYBE", "score": 5})["score"] == 1.0  # clamp
    contradictory = aq._sanitize(qa_json("PASS", defects=[{"criterion": "c", "problem": "p"}]))
    assert contradictory["verdict"] == "REVISE"                          # PASS+defects -> REVISE


def test_non_image_asset_rejected(tmp_path):
    doc = tmp_path / "notes.md"
    doc.write_text("hello", encoding="utf-8")
    with pytest.raises(ValueError, match="must be an image"):
        aq.judge_asset(doc, "c", GEN, call_model=FakeCallModel({}))


# ---- loop bookkeeping (spec ruling 2) --------------------------------------------

def _loop_with(*verdict_scores, criteria="crit"):
    loop = aq.ForgeLoop(criteria, max_attempts=3, max_cost_usd=1.0)
    for i, (v, s) in enumerate(verdict_scores):
        qa = dict(qa_json(v, s, defects=[] if v == "PASS" else
                          [{"criterion": "c", "problem": f"p{i}"}], hint=f"h{i}"),
                  judge=LUNA, cost_usd=0.01)
        loop.record(f"a{i}.png", f"prompt{i}", qa)
    return loop


def test_pass_stops_loop_and_reports_pass():
    loop = _loop_with(("REVISE", 0.3), ("PASS", 0.9))
    assert not loop.should_continue()
    r = loop.result()
    assert r["status"] == "PASS" and r["escalate_to_panel"] is False
    assert r["best"]["qa"]["score"] == 0.9


def test_exhausted_attempts_escalates_to_panel_with_best_kept():
    loop = _loop_with(("REVISE", 0.3), ("REVISE", 0.6), ("REVISE", 0.5))
    assert not loop.should_continue()
    r = loop.result()
    assert r["status"] == "EXHAUSTED" and r["escalate_to_panel"] is True
    assert r["best"]["qa"]["score"] == 0.6           # best candidate never discarded


def test_budget_exhaustion_stops_loop():
    loop = aq.ForgeLoop("c", max_attempts=10, max_cost_usd=0.05)
    loop.record("a.png", "p", dict(qa_json("REVISE", 0.2), judge=LUNA, cost_usd=0.01),
                gen_cost_usd=0.05)
    assert not loop.should_continue()                # 0.06 >= 0.05 cap
    assert loop.result()["escalate_to_panel"] is True


def test_next_prompt_folds_defects_and_hint():
    loop = _loop_with(("REVISE", 0.3))
    nxt = loop.next_prompt("a teal satellite icon")
    assert nxt.startswith("a teal satellite icon")
    assert "REJECTED" in nxt and "c: p0" in nxt and "h0" in nxt


def test_sidecar_written_next_to_asset(tmp_path):
    loop = _loop_with(("PASS", 1.0))
    asset = png(tmp_path)
    side = aq.write_sidecar(asset, loop.result())
    assert side.name == "asset.png.forge.json"
    data = json.loads(side.read_text(encoding="utf-8"))
    assert data["status"] == "PASS" and data["attempts"][0]["prompt"] == "prompt0"


# ---- CLI --------------------------------------------------------------------------

def test_cli_pass_exit_0_revise_exit_2(tmp_path, capsys):
    img = png(tmp_path)
    fake = FakeCallModel({LUNA: (qa_json("PASS"), 0.002)})
    assert aq.main(["--image", str(img), "--criteria", "c", "--generator-model", GEN],
                   call_model=fake) == 0
    assert json.loads(capsys.readouterr().out)["verdict"] == "PASS"
    fake2 = FakeCallModel({LUNA: (qa_json("REVISE", 0.2), 0.002)})
    assert aq.main(["--image", str(img), "--criteria", "c", "--generator-model", GEN],
                   call_model=fake2) == 2


def test_cli_errors_exit_3(tmp_path):
    assert aq.main(["--image", str(tmp_path / "missing.png"), "--criteria", "c",
                    "--generator-model", GEN], call_model=FakeCallModel({})) == 3
    img = png(tmp_path)
    assert aq.main(["--image", str(img), "--generator-model", GEN],
                   call_model=FakeCallModel({})) == 3     # no criteria
