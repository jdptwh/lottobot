"""Wave 4 — config loader: parsing, precedence, coercion, edge cases."""
from panel.config import DEFAULTS, load_config, parse_config_file


def write(tmp_path, text):
    p = tmp_path / "agent.config"
    p.write_text(text, encoding="utf-8")
    return str(p)


# ---- parsing (AC-1, AC-2) ----------------------------------------------------

def test_quote_styles_and_comments(tmp_path):
    cfg = write(tmp_path, '\n'.join([
        'PANEL_ENABLED="1"',
        "PANEL_TRIGGER='always'",
        'PANEL_PROVIDER=openrouter',
        '# a full-line comment',
        'PANEL_ROUTING=exacto   # trailing inline comment',
        'PANEL_VERDICT_PATH="/tmp/v#1.json"   # hash inside quotes preserved',
        '',
    ]))
    vals = parse_config_file(cfg)
    assert vals["PANEL_ENABLED"] == "1"
    assert vals["PANEL_TRIGGER"] == "always"
    assert vals["PANEL_PROVIDER"] == "openrouter"
    assert vals["PANEL_ROUTING"] == "exacto"          # inline comment stripped
    assert vals["PANEL_VERDICT_PATH"] == "/tmp/v#1.json"  # inner '#' preserved
    assert "# a full-line comment" not in vals


def test_missing_file_yields_all_defaults():
    c = load_config(config_path="/no/such/file", environ={}, warn=False)
    assert c.enabled is False
    assert c.plan_lineup == ("anthropic/claude-fable-5", "openai/gpt-5.6-sol")
    assert c.max_cost_usd == 2.0
    assert c.verdict_path == ".claude/state/panel_verdict.json"


def test_present_but_empty_list_is_empty_not_one_empty_string(tmp_path):
    cfg = write(tmp_path, 'PANEL_PLAN_LINEUP=""\n')
    c = load_config(config_path=cfg, environ={}, warn=False)
    assert c.plan_lineup == ()          # not ('',)


# ---- precedence (AC-3) -------------------------------------------------------

def test_env_beats_file_beats_default(tmp_path):
    cfg = write(tmp_path, 'PANEL_TRIGGER="escalation"\n')
    # default
    assert load_config("/no/file", environ={}, warn=False).trigger == "novelty"
    # file over default
    assert load_config(cfg, environ={}, warn=False).trigger == "escalation"
    # env over file
    assert load_config(cfg, environ={"PANEL_TRIGGER": "always"}, warn=False).trigger == "always"


def test_empty_env_does_not_override_file(tmp_path):
    cfg = write(tmp_path, 'PANEL_TRIGGER="escalation"\n')
    # empty env var falls through to file (mirrors gate.sh ${x:-...})
    assert load_config(cfg, environ={"PANEL_TRIGGER": ""}, warn=False).trigger == "escalation"


# ---- coercion (AC-3, AC-4) ---------------------------------------------------

def test_bool_coercion():
    for t in ("1", "true", "TRUE", "yes", "on"):
        assert load_config("/no", environ={"PANEL_ENABLED": t}, warn=False).enabled is True
    for f in ("0", "false", "no", "off", ""):
        assert load_config("/no", environ={"PANEL_ENABLED": f}, warn=False).enabled is False


def test_float_coercion_and_malformed_fallback():
    assert load_config("/no", environ={"PANEL_MAX_COST_USD": "0.5"}, warn=False).max_cost_usd == 0.5
    # malformed -> falls back to default, never raises
    assert load_config("/no", environ={"PANEL_MAX_COST_USD": "abc"}, warn=False).max_cost_usd == 2.0


def test_list_splitting_strips_and_drops_empties():
    c = load_config("/no", environ={"PANEL_PLAN_LINEUP": " a/b , , c/d "}, warn=False)
    assert c.plan_lineup == ("a/b", "c/d")


# ---- defaults sanity ---------------------------------------------------------

def test_defaults_use_full_dotted_slugs():
    assert DEFAULTS["PANEL_PLAN_SYNTH"] == "anthropic/claude-opus-4.8"
    assert "," in DEFAULTS["PANEL_PLAN_LINEUP"]
    assert "fable5" not in DEFAULTS["PANEL_PLAN_LINEUP"]  # not V5_PLAN's short name


def test_slug_warning_is_non_fatal(capsys):
    # an unknown slug warns on stderr but does not raise / disable
    c = load_config("/no", environ={"PANEL_PLAN_SYNTH": "made/up-model", "PANEL_ENABLED": "1"}, warn=True)
    assert c.enabled is True
    assert "made/up-model" in capsys.readouterr().err
