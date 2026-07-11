"""Packaging Wave 1 — portable Atlas shim + templated MCP registration.
No network; the shim's version check runs against a FAKE node on PATH (Windows only)."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CMD = ROOT / "scripts" / "atlas-mcp.cmd"
EXAMPLE = ROOT / ".mcp.json.example"


def _setup_mod():
    spec = importlib.util.spec_from_file_location("_pkg_setup", ROOT / "scripts" / "setup.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---- no machine-specific residue --------------------------------------------------

def test_shim_has_no_hardcoded_user_paths():
    src = CMD.read_text(encoding="utf-8")
    for residue in ("JoeyD", "nvm\\v20", "Users\\"):
        assert residue not in src, f"machine-specific path in shim: {residue}"
    assert "NODE20_DIR" in src and "ATLAS_MCP_CHECK" in src


def test_example_is_valid_json_with_placeholders():
    cfg = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    server = cfg["mcpServers"]["atlascloud"]
    assert "{{HARNESS_ROOT}}" in server["command"]
    assert server["env"]["ATLASCLOUD_API_KEY"] == "{{ATLASCLOUD_API_KEY}}"


# ---- render/write ------------------------------------------------------------------

def test_render_mcp_resolves_root_and_key(tmp_path):
    shutil.copy(EXAMPLE, tmp_path / ".mcp.json.example")
    mod = _setup_mod()
    cfg = json.loads(mod.render_mcp(tmp_path, "apikey-test-123"))
    server = cfg["mcpServers"]["atlascloud"]
    assert "{{" not in json.dumps(cfg)                       # every placeholder resolved
    assert Path(server["command"]).is_absolute()
    assert server["command"].endswith("atlas-mcp.cmd")
    assert str(tmp_path) in server["command"]
    assert server["env"]["ATLASCLOUD_API_KEY"] == "apikey-test-123"


def test_render_mcp_includes_node20_override_when_given(tmp_path):
    shutil.copy(EXAMPLE, tmp_path / ".mcp.json.example")
    mod = _setup_mod()
    with_dir = json.loads(mod.render_mcp(tmp_path, "k", node20_dir=r"C:\node20"))
    assert with_dir["mcpServers"]["atlascloud"]["env"]["NODE20_DIR"] == r"C:\node20"
    without = json.loads(mod.render_mcp(tmp_path, "k"))
    assert "NODE20_DIR" not in without["mcpServers"]["atlascloud"]["env"]


def test_write_mcp_creates_file(tmp_path):
    shutil.copy(EXAMPLE, tmp_path / ".mcp.json.example")
    mod = _setup_mod()
    p = mod.write_mcp(tmp_path, "apikey-x")
    assert p.name == ".mcp.json"
    assert json.loads(p.read_text(encoding="utf-8"))["mcpServers"]["atlascloud"]


def test_real_mcp_json_is_gitignored():
    # Must hold in ANY install (targets may not be git repos yet): the ignore file
    # itself carries the rule. When git is available AND this is a repo, also ask git.
    gi = ROOT / ".gitignore"
    assert gi.exists() and ".mcp.json" in gi.read_text(encoding="utf-8"), \
        ".gitignore must cover .mcp.json (holds the Atlas key)"
    r = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=str(ROOT),
                       capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip() == "true":
        r2 = subprocess.run(["git", "check-ignore", ".mcp.json"], cwd=str(ROOT),
                            capture_output=True, text=True)
        assert r2.returncode == 0, "git does not ignore .mcp.json"


# ---- shim version gate (Windows: fake `node` on PATH) ------------------------------

def _run_shim_with_fake_node(tmp_path, version):
    fake = tmp_path / "node.bat"
    fake.write_text(f"@echo {version}\n", encoding="utf-8")
    env = dict(os.environ, ATLAS_MCP_CHECK="1",
               PATH=f"{tmp_path};{os.environ.get('PATH', '')}")
    env.pop("NODE20_DIR", None)
    return subprocess.run(["cmd", "/c", str(CMD)], env=env,
                          capture_output=True, text=True, timeout=30)


@pytest.mark.skipif(os.name != "nt", reason="cmd shim is Windows-only")
def test_shim_accepts_node_20():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        r = _run_shim_with_fake_node(Path(td), "v20.15.1")
        assert r.returncode == 0, r.stdout + r.stderr
        assert "check OK" in r.stdout


@pytest.mark.skipif(os.name != "nt", reason="cmd shim is Windows-only")
def test_shim_rejects_node_18_with_instructions():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        r = _run_shim_with_fake_node(Path(td), "v18.19.0")
        assert r.returncode == 1
        assert "Node 20+" in (r.stdout + r.stderr)
        assert "NODE20_DIR" in (r.stdout + r.stderr)


# ---- vendored watch-video skill ------------------------------------------------------

def test_watch_video_vendored_pinned_with_licenses():
    d = ROOT / ".claude" / "skills" / "watch-video"
    for f in ("SKILL.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "VENDORED.md"):
        assert (d / f).exists(), f"vendored skill missing {f}"
    vend = (d / "VENDORED.md").read_text(encoding="utf-8")
    assert "Pinned commit:" in vend and "Local modifications" in vend
    for script in ("watch.py", "frames.py", "transcribe.py", "download.py"):
        assert (d / "scripts" / script).exists()
    skill = (d / "SKILL.md").read_text(encoding="utf-8")
    assert "frame-level" in skill        # harness trigger modification present


# ---- install-into: the harness is self-contained ------------------------------------

@pytest.mark.skipif(os.environ.get("HARNESS_SELF_TEST") == "1",
                    reason="already inside a self-containment run (no recursion)")
def test_install_into_produces_a_green_standalone_harness(tmp_path):
    """The decisive packaging test: install into an empty directory, then run the
    installed copy's OWN gate in a fresh interpreter. Slow (~nested suite) but it
    is the definition of 'packaged properly'."""
    mod = _setup_mod()
    target = tmp_path / "newproject"
    target.mkdir()
    code = mod.install_into(target, verify=False)
    assert code == 0

    # dormant guarantee: a fresh install never arrives armed
    cfg = (target / ".claude" / "agent.config").read_text(encoding="utf-8")
    assert 'PANEL_ENABLED="0"' in cfg and 'ASSET_ENABLED="0"' in cfg
    # memory shipped as CLAUDE.md (target had none); secrets NOT shipped
    assert (target / "CLAUDE.md").exists()
    assert not (target / ".env").exists() and not (target / ".mcp.json").exists()
    assert ".mcp.json" in (target / ".gitignore").read_text(encoding="utf-8")
    # skills travel with the harness
    assert (target / ".claude" / "skills" / "asset-forge" / "SKILL.md").exists()

    # audit fix: the gate-hook wiring + permission deny-list must travel with the
    # harness (else installed copies have gate.sh but nothing fires it)
    settings = json.loads((target / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert settings["hooks"], "installed harness has no hooks"
    assert "Read(.env)" in settings["permissions"]["deny"]

    env = dict(os.environ, HARNESS_SELF_TEST="1")
    env.pop("PYTEST_CURRENT_TEST", None)
    r = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=str(target),
                       env=env, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, f"installed harness gate failed:\n{r.stdout[-3000:]}\n{r.stderr[-2000:]}"


@pytest.mark.skipif(os.environ.get("HARNESS_SELF_TEST") == "1",
                    reason="no nested install recursion")
def test_install_into_never_clobbers_a_targets_build_files(tmp_path):
    """audit fix: a target's pyproject.toml / conftest.py / settings.json are
    shipped as <name>.harness-template, never overwritten (was: unconditional
    copy2 destroyed them; only CLAUDE.md was guarded)."""
    mod = _setup_mod()
    target = tmp_path / "existing"
    (target / ".claude").mkdir(parents=True)
    sentinels = {
        "pyproject.toml": "# THE PROJECT'S OWN pyproject\n",
        "conftest.py": "# THE PROJECT'S OWN conftest\n",
        ".claude/settings.json": '{"mine": true}\n',
        "CLAUDE.md": "# the project's own memory\n",
    }
    for rel, body in sentinels.items():
        (target / rel).write_text(body, encoding="utf-8")

    assert mod.install_into(target, verify=False) == 0
    for rel, body in sentinels.items():
        assert (target / rel).read_text(encoding="utf-8") == body, f"{rel} was clobbered"
        assert (target / (rel + ".harness-template")).exists(), f"{rel} template not shipped"
