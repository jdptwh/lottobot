"""Guard the panel-invocation wiring (ROUTING.md Rule 12). Token-presence ONLY — no
prose/ordering assertions, so the docs stay editable. The one regression that actually
matters (a leftover PANEL_ENABLED="1") is machine-caught here."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def test_routing_has_rule12_and_literal_cli():
    r = _read("ROUTING.md")
    assert "Rule 12" in r
    assert "python -m panel.cli" in r          # the literal invocation


def test_routing_has_all_four_trigger_tokens():
    r = _read("ROUTING.md")
    assert "PANEL_ENABLED" in r
    for tok in ("always", "novelty", "escalation"):
        assert tok in r, f"missing trigger token: {tok}"


def test_panel_disabled_by_default():
    # The dormant contract lives in the BUILT-IN default, not the working config:
    # agent.config is live operator state that the shipped dashboard toggle edits
    # (an approved Wave 5 feature), so pinning the file's value would fail every
    # time the operator legitimately arms the panel. A fresh install (no config
    # file, no env) must reproduce v4 exactly — that is what this guards.
    from panel.config import DEFAULTS, load_config
    assert DEFAULTS["PANEL_ENABLED"] == "0"
    assert load_config("nonexistent.config", environ={}, warn=False).enabled is False


def test_planner_and_reviewer_prompts_reference_the_panel():
    assert "panel_plan" in _read(".claude/agents/planner.md")
    assert "panel_review" in _read(".claude/agents/reviewer.md")


def test_integration_doc_exists():
    d = _read("docs/panel_integration.md")
    assert "--prompt-file" in d and "git diff" in d


def test_claude_md_routing_references_panel_invocation():
    assert "Rule 12" in _read("CLAUDE.md")


def test_asset_pipeline_wiring_rule13():
    r = _read("ROUTING.md")
    assert "Rule 13" in r and "asset-forge" in r
    skill = _read(".claude/skills/asset-forge/SKILL.md")
    assert "ASSET_ENABLED" in skill and "panel.asset_qa" in skill
    # dormant-by-default contract, same shape as the panel's
    from panel.dashboard.config_writer import EDITABLE_KEYS
    for key in ("ASSET_ENABLED", "ASSET_MODEL_DEFAULT", "ASSET_MODEL_TEXTED",
                "ASSET_QA_JUDGE", "ASSET_MAX_ATTEMPTS", "ASSET_MAX_COST_USD",
                "ASSET_VIDEO_MODEL_DEFAULT", "ASSET_VIDEO_MODEL_AUDIO",
                "ASSET_VIDEO_MAX_COST_USD", "ASSET_VIDEO_QA_FRAMES"):
        assert key in EDITABLE_KEYS, f"{key} not dashboard-editable"
    # video QA is visual-track only — the limitation must be documented where
    # agents read it
    assert "audio" in _read(".claude/skills/asset-forge/SKILL.md").lower()
    assert "ASSET_VIDEO_" in r
