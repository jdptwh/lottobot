"""Wave-6 packaging — the stdlib .env loader (panel/secrets.py)."""
from panel import secrets


def test_parse_env_styles():
    d = secrets.parse_env('\n'.join([
        'OPENROUTER_API_KEY=sk-or-abc',
        'export ANTHROPIC_API_KEY="sk-ant-xyz"   # inline comment',
        "QUOTED='v#1'",
        '# a comment',
        '',
        'BARE = spaced ',
    ]))
    assert d["OPENROUTER_API_KEY"] == "sk-or-abc"
    assert d["ANTHROPIC_API_KEY"] == "sk-ant-xyz"      # export prefix + quotes + comment stripped
    assert d["QUOTED"] == "v#1"                          # hash inside quotes preserved
    assert d["BARE"] == "spaced"


def test_load_env_sets_missing_only(tmp_path):
    env = {}
    p = tmp_path / ".env"
    p.write_text('OPENROUTER_API_KEY=sk-or-1\nOTHER=2\n', encoding="utf-8")
    loaded = secrets.load_env(str(p), environ=env)
    assert set(loaded) == {"OPENROUTER_API_KEY", "OTHER"}
    assert env["OPENROUTER_API_KEY"] == "sk-or-1"


def test_existing_env_wins(tmp_path):
    env = {"OPENROUTER_API_KEY": "already-set"}
    p = tmp_path / ".env"
    p.write_text('OPENROUTER_API_KEY=from-file\n', encoding="utf-8")
    loaded = secrets.load_env(str(p), environ=env)
    assert env["OPENROUTER_API_KEY"] == "already-set"   # not overwritten
    assert "OPENROUTER_API_KEY" not in loaded


def test_missing_file_is_noop():
    assert secrets.load_env("/no/such/.env", environ={}) == []
