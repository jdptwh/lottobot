"""Wave 5 — config editor: allowlist, validation, byte-identical round-trip, atomic."""
import os

import pytest

from panel.config import load_config, parse_config_file
from panel.dashboard import config_writer as cw


def test_editable_keys_are_the_ratified_set():
    assert set(cw.EDITABLE_KEYS) == {
        "PLANNER_MODEL", "DRAFTER_MODEL", "IMPLEMENTER_MODEL", "REVIEWER_MODEL", "BULK_MODEL",
        "PANEL_PLAN_LINEUP", "PANEL_PLAN_SYNTH", "PANEL_REVIEW_LINEUP", "PANEL_REVIEW_ARBITER",
        "MAX_IMPL_ATTEMPTS", "MAX_REVIEW_CYCLES", "MAX_BULK_RETRIES",
        "PANEL_MAX_COST_USD", "PANEL_ENABLED", "PANEL_TRIGGER", "PANEL_MODE_PLAN", "PANEL_MODE_REVIEW",
        # asset pipeline (Rule 13, spec approved 2026-07-09)
        "ASSET_ENABLED", "ASSET_MODEL_DEFAULT", "ASSET_MODEL_TEXTED",
        "ASSET_QA_JUDGE", "ASSET_MAX_ATTEMPTS", "ASSET_MAX_COST_USD",
        # video mode (video spec approved 2026-07-09)
        "ASSET_VIDEO_MODEL_DEFAULT", "ASSET_VIDEO_MODEL_AUDIO",
        "ASSET_VIDEO_MAX_COST_USD", "ASSET_VIDEO_QA_FRAMES",
    }
    # locked keys are NOT editable
    for locked in ("VERIFY_CMD", "LINT_CMD", "UI_VERIFY_CMD", "PANEL_PROVIDER",
                   "PANEL_ROUTING", "PANEL_VERDICT_PATH", "VERDICT_PATH"):
        assert locked not in cw.EDITABLE_KEYS


def test_round_trip_changes_only_target_line(tmp_config):
    before = tmp_config.read_text().split("\n")
    cw.write_editable(str(tmp_config), {"PANEL_MAX_COST_USD": "3.50"})
    after = tmp_config.read_text().split("\n")
    assert len(before) == len(after)
    # every line that is not the PANEL_MAX_COST_USD assignment is byte-identical
    for b, a in zip(before, after):
        if b.strip().startswith("PANEL_MAX_COST_USD="):
            assert a.strip().startswith("PANEL_MAX_COST_USD=") and "3.50" in a
        else:
            assert b == a
    assert load_config(str(tmp_config), warn=False).max_cost_usd == 3.50


def test_preserves_trailing_inline_comment(tmp_config):
    # PANEL_VERDICT_PATH line has a trailing comment; edit a commented line and check
    cw.write_editable(str(tmp_config), {"PANEL_ENABLED": "1"})
    line = next(l for l in tmp_config.read_text().split("\n") if l.strip().startswith("PANEL_ENABLED="))
    assert "#" in line and 'PANEL_ENABLED="1"' in line   # comment kept, value changed


@pytest.mark.parametrize("bad", [
    {"PANEL_MAX_COST_USD": "abc"},
    {"PANEL_MAX_COST_USD": "0"},
    {"MAX_IMPL_ATTEMPTS": "0"},
    {"MAX_IMPL_ATTEMPTS": "-1"},
    {"PANEL_ENABLED": "maybe"},
    {"PANEL_TRIGGER": "sometimes"},
    {"PANEL_MODE_PLAN": "bogus"},
    {"EVIL_KEY": "1"},
    {"VERIFY_CMD": "rm -rf /"},                       # locked key
    {"PANEL_PLAN_SYNTH": 'a" ; rm -rf /'},            # shell metachars
    {"PLANNER_MODEL": "x\ny"},                        # newline
    {"PANEL_PLAN_LINEUP": ""},                        # empty
])
def test_invalid_update_leaves_file_byte_identical(tmp_config, bad):
    original = tmp_config.read_bytes()
    with pytest.raises(ValueError):
        cw.write_editable(str(tmp_config), bad)
    assert tmp_config.read_bytes() == original          # unchanged on rejection


def test_atomic_write_leaves_no_temp(tmp_config):
    cw.write_editable(str(tmp_config), {"REVIEWER_MODEL": "anthropic/claude-opus-4.8"})
    leftovers = [n for n in os.listdir(tmp_config.parent) if n.startswith(".agentcfg.")]
    assert leftovers == []


def test_read_editable_returns_only_allowlist(tmp_config):
    ed = cw.read_editable(str(tmp_config))
    assert set(ed) == set(cw.EDITABLE_KEYS)
    assert "OPENROUTER_API_KEY" not in ed and "VERIFY_CMD" not in ed


def test_missing_key_is_appended(tmp_path):
    cfg = tmp_path / "agent.config"
    cfg.write_text('# header\nVERIFY_CMD="x"\n', encoding="utf-8")
    cw.write_editable(str(cfg), {"PANEL_ENABLED": "1"})
    vals = parse_config_file(str(cfg))
    assert vals["PANEL_ENABLED"] == "1" and vals["VERIFY_CMD"] == "x"   # original preserved
    assert cfg.read_text().splitlines()[0] == "# header"               # comment intact


@pytest.mark.parametrize("bad", ["inf", "-inf", "1e400", "nan", "Infinity"])
def test_cost_cap_rejects_non_finite(tmp_config, bad):
    original = tmp_config.read_bytes()
    with pytest.raises(ValueError):
        cw.write_editable(str(tmp_config), {"PANEL_MAX_COST_USD": bad})
    assert tmp_config.read_bytes() == original          # cap can't be silently disabled


def test_posint_leading_zeros_normalized():
    assert cw.EDITABLE_KEYS["MAX_IMPL_ATTEMPTS"]("007") == "7"


def test_mixed_valid_invalid_is_all_or_nothing(tmp_config):
    original = tmp_config.read_bytes()
    with pytest.raises(ValueError):
        cw.write_editable(str(tmp_config), {"PANEL_MAX_COST_USD": "1.5", "MAX_IMPL_ATTEMPTS": "0"})
    assert tmp_config.read_bytes() == original          # one bad key -> nothing written
