"""gate.sh v5.1 anti-wedge hardening (CLAUDE.md landmines, 2026-07-22 audit).

Pins the two new behaviors:

1. `stop_hook_active` honor — when the hook payload on stdin says this stop is
   ALREADY a hook-forced continuation, a red gate WARNS (exit 0, loud stderr)
   instead of blocking again. This bounds the bounce loop that wedged read-only
   agents (planner/drafter) against a red repo gate. No payload, or a payload
   with the flag false, preserves the strict v5 blocking contract exactly.

2. `GATE_TIMEOUT_SECS` — gate commands run under `timeout`; a hung command is
   killed and treated as FAIL rather than wedging the stop forever.

Same shell-out pattern and bash guard as tests/panel/test_gate_panel_path.py.
"""
import shutil
import subprocess
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
GATE = REPO / ".claude" / "hooks" / "gate.sh"
PANEL_FIX = REPO / "tests" / "panel" / "fixtures"


def _bash_works():
    if shutil.which("bash") is None:
        return False
    try:
        r = subprocess.run(["bash", "-c", "echo ok"], capture_output=True,
                           text=True, timeout=15)
        return r.returncode == 0 and "ok" in r.stdout
    except (OSError, subprocess.TimeoutExpired):
        return False


pytestmark = pytest.mark.skipif(not _bash_works(), reason="no functional bash")

ENV_BASE = {"PATH": "/usr/bin:/bin"}

ACTIVE_PAYLOAD = '{"hook_event_name": "SubagentStop", "stop_hook_active": true}'
INACTIVE_PAYLOAD = '{"hook_event_name": "Stop", "stop_hook_active": false}'


def run_gate(cwd, env, payload=""):
    return subprocess.run(["bash", str(GATE)], cwd=str(cwd), input=payload,
                          capture_output=True, text=True, env=env, timeout=120)


def make_repo(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# sentinel\n")
    (tmp_path / ".claude" / "hooks").mkdir(parents=True)
    shutil.copy(GATE, tmp_path / ".claude" / "hooks" / "gate.sh")
    shutil.copy(REPO / ".claude" / "hooks" / "verdict_lint.py",
                tmp_path / ".claude" / "hooks" / "verdict_lint.py")
    (tmp_path / ".claude" / "state").mkdir(parents=True)
    return tmp_path


# ---------------------------------------------------------------------------
# 1. stop_hook_active honor
# ---------------------------------------------------------------------------

def test_red_gate_blocks_without_payload(tmp_path):
    # The strict v5 contract is untouched when stdin carries no payload.
    repo = make_repo(tmp_path)
    env = dict(ENV_BASE, CLAUDE_VERIFY_CMD="false")
    r = run_gate(repo, env)
    assert r.returncode == 2, r.stderr
    assert "FAIL" in r.stderr


def test_red_gate_blocks_when_flag_false(tmp_path):
    repo = make_repo(tmp_path)
    env = dict(ENV_BASE, CLAUDE_VERIFY_CMD="false")
    r = run_gate(repo, env, payload=INACTIVE_PAYLOAD)
    assert r.returncode == 2, r.stderr


def test_red_gate_warns_not_blocks_when_stop_hook_active(tmp_path):
    # The anti-wedge release: red gate + active flag -> exit 0 with a LOUD
    # warning, never a second block (bounded bounce, no deadlock).
    repo = make_repo(tmp_path)
    env = dict(ENV_BASE, CLAUDE_VERIFY_CMD="false")
    r = run_gate(repo, env, payload=ACTIVE_PAYLOAD)
    assert r.returncode == 0, r.stderr
    assert "anti-wedge" in r.stderr
    assert "RED" in r.stderr            # the release is loud, never silent


def test_spurious_true_tokens_do_not_release(tmp_path):
    # Reviewer cycle-2 nit: pin the exact-match payload contract — a false
    # flag followed by an unrelated true-valued token must NOT release.
    repo = make_repo(tmp_path)
    env = dict(ENV_BASE, CLAUDE_VERIFY_CMD="false")
    spurious = '{"stop_hook_active": false, "other_flag": true}'
    r = run_gate(repo, env, payload=spurious)
    assert r.returncode == 2, r.stderr
    in_path = '{"transcript_path": "/tmp/true/x.json", "stop_hook_active": false}'
    r2 = run_gate(repo, env, payload=in_path)
    assert r2.returncode == 2, r2.stderr


def test_green_gate_unaffected_by_active_flag(tmp_path):
    repo = make_repo(tmp_path)
    env = dict(ENV_BASE, CLAUDE_VERIFY_CMD="true")
    r = run_gate(repo, env, payload=ACTIVE_PAYLOAD)
    assert r.returncode == 0, r.stderr
    assert "ALL PASS" in r.stderr
    assert "anti-wedge" not in r.stderr


def test_fresh_panel_fail_downgrades_when_stop_hook_active(tmp_path):
    # GATE 4 gets the same release: a fresh non-PASS panel verdict warns
    # instead of blocking when the stop is already hook-forced.
    repo = make_repo(tmp_path)
    (repo / ".claude" / "state" / "panel_verdict.json").write_text(
        (PANEL_FIX / "plan_fail.json").read_text())
    env = dict(ENV_BASE, CLAUDE_VERIFY_CMD="true")
    blocked = run_gate(repo, env)
    assert blocked.returncode == 2, blocked.stderr          # strict path intact
    released = run_gate(repo, env, payload=ACTIVE_PAYLOAD)
    assert released.returncode == 0, released.stderr
    assert "anti-wedge" in released.stderr


# ---------------------------------------------------------------------------
# 2. GATE_TIMEOUT_SECS
# ---------------------------------------------------------------------------

def test_hung_gate_command_is_killed_and_fails(tmp_path):
    if shutil.which("timeout") is None:
        pytest.skip("no timeout binary")
    repo = make_repo(tmp_path)
    env = dict(ENV_BASE, CLAUDE_VERIFY_CMD="sleep 300", GATE_TIMEOUT_SECS="1")
    t0 = time.monotonic()
    r = run_gate(repo, env)
    elapsed = time.monotonic() - t0
    assert r.returncode == 2, r.stderr
    assert "TIMEOUT" in r.stderr
    assert elapsed < 60, f"hung-command kill took {elapsed:.0f}s"


def test_timeout_env_overrides_config(tmp_path):
    if shutil.which("timeout") is None:
        pytest.skip("no timeout binary")
    repo = make_repo(tmp_path)
    (repo / ".claude" / "agent.config").write_text('GATE_TIMEOUT_SECS="300"\n')
    env = dict(ENV_BASE, CLAUDE_VERIFY_CMD="sleep 300", GATE_TIMEOUT_SECS="1")
    t0 = time.monotonic()
    r = run_gate(repo, env)
    assert r.returncode == 2, r.stderr
    assert time.monotonic() - t0 < 60
