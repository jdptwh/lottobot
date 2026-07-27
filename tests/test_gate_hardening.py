"""gate.sh v5.1/v5.2 anti-wedge + clean-skip hardening (CLAUDE.md landmines,
2026-07-22 audit; 2026-07-25 owner "spinning lead" incident).

Pins the hardening behaviors:

1. `stop_hook_active` honor — when the hook payload on stdin says this stop is
   ALREADY a hook-forced continuation, a red gate WARNS (exit 0, loud stderr)
   instead of blocking again. This bounds the bounce loop that wedged read-only
   agents (planner/drafter) against a red repo gate. No payload, or a payload
   with the flag false, preserves the strict v5 blocking contract exactly.

2. `GATE_TIMEOUT_SECS` — gate commands run under `timeout`; a hung command is
   killed and treated as FAIL rather than wedging the stop forever.

3. v5.2 clean-skip — after an ALL-PASS the gate records a tree fingerprint;
   a later stop with a byte-identical tree exits 0 immediately instead of
   re-running the (multi-minute) verify surface. Any change, a red gate, a
   pending panel verdict, or GATE_SKIP_CLEAN=0 forces the full v5.1 path.
   Regression guard: fingerprinting must work on a repo with ZERO untracked
   files (the grep-on-empty-input pipefail bug that silently disarmed the
   skip on first deploy, 2026-07-26).

Same shell-out pattern and bash guard as tests/panel/test_gate_panel_path.py.
"""
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
GATE = REPO / ".claude" / "hooks" / "gate.sh"
PANEL_FIX = REPO / "tests" / "panel" / "fixtures"


def _find_bash():
    """A FUNCTIONAL bash, by full path. On Windows, CreateProcess resolves a
    bare "bash" via System32 BEFORE PATH — hitting the WSL stub, which errors
    out where WSL isn't set up. That made every test here silently skip on
    the owner's machine (2026-07-26 incident) while the gate itself ran fine
    (Claude Code hooks invoke Git bash). Probe which() plus the standard Git
    for Windows locations and return the first bash that actually works."""
    candidates = [shutil.which("bash"),
                  r"C:\Program Files\Git\usr\bin\bash.exe",
                  r"C:\Program Files\Git\bin\bash.exe"]
    for cand in candidates:
        if not cand:
            continue
        try:
            r = subprocess.run([cand, "-c", "echo ok"], capture_output=True,
                               text=True, timeout=15)
            if r.returncode == 0 and "ok" in r.stdout:
                return cand
        except (OSError, subprocess.TimeoutExpired):
            continue
    return None


BASH = _find_bash()
pytestmark = [pytest.mark.subproc,
              pytest.mark.skipif(BASH is None, reason="no functional bash")]

ENV_BASE = {"PATH": "/usr/bin:/bin"}

ACTIVE_PAYLOAD = '{"hook_event_name": "SubagentStop", "stop_hook_active": true}'
INACTIVE_PAYLOAD = '{"hook_event_name": "Stop", "stop_hook_active": false}'


def run_gate(cwd, env, payload=""):
    return subprocess.run([BASH, str(GATE)], cwd=str(cwd), input=payload,
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


# ---------------------------------------------------------------------------
# 3. v5.2 clean-skip
# ---------------------------------------------------------------------------
# These need git + sha256sum reachable from bash, so they run with the real
# environment PATH (ENV_BASE's stripped PATH is for degradation tests). The
# marker file the verify command appends to lives OUTSIDE the repo — writing
# it inside would change the tree and defeat the very skip being tested.

FP_REL = Path(".claude") / "state" / "gate_green.fp"


def _skip_unless_git_tools():
    probe = subprocess.run(
        [BASH, "-c", "command -v git && command -v sha256sum"],
        capture_output=True, text=True, env=dict(os.environ), timeout=15)
    if probe.returncode != 0:
        pytest.skip("git/sha256sum not reachable from bash")


def make_git_repo(tmp_path):
    # Repo in a SUBDIR so the marker can live beside it, outside the tree.
    # Everything committed, nothing untracked — the fingerprint's hardest case.
    (tmp_path / "repo").mkdir()
    repo = make_repo(tmp_path / "repo")
    for args in (["git", "init", "-q"], ["git", "add", "-A"],
                 ["git", "-c", "user.name=t", "-c", "user.email=t@t",
                  "commit", "-qm", "init"]):
        subprocess.run(args, cwd=repo, check=True, capture_output=True,
                       env=dict(os.environ), timeout=60)
    return repo


def _marker_env(tmp_path, **extra):
    marker = tmp_path / "marker.txt"
    env = dict(os.environ,
               CLAUDE_VERIFY_CMD=f"echo ran >> ../marker.txt")
    env.update(extra)
    return env, marker


def _lines(marker):
    return len(marker.read_text().splitlines()) if marker.exists() else 0


def test_green_run_records_fingerprint_and_next_stop_skips(tmp_path):
    _skip_unless_git_tools()
    repo = make_git_repo(tmp_path)
    env, marker = _marker_env(tmp_path)
    first = run_gate(repo, env)
    assert first.returncode == 0, first.stderr
    assert "ALL PASS" in first.stderr
    assert _lines(marker) == 1
    # Regression: fp must record on a tree with NO untracked files.
    assert (repo / FP_REL).is_file(), "fingerprint not recorded on clean tree"
    second = run_gate(repo, env)
    assert second.returncode == 0, second.stderr
    assert "SKIP" in second.stderr
    assert _lines(marker) == 1, "verify command re-ran on identical tree"


def test_any_tree_change_forces_full_run(tmp_path):
    _skip_unless_git_tools()
    repo = make_git_repo(tmp_path)
    env, marker = _marker_env(tmp_path)
    assert run_gate(repo, env).returncode == 0
    (repo / "newfile.txt").write_text("changed\n")
    third = run_gate(repo, env)
    assert third.returncode == 0, third.stderr
    assert "SKIP" not in third.stderr
    assert _lines(marker) == 2


def test_kill_switch_disables_skip(tmp_path):
    _skip_unless_git_tools()
    repo = make_git_repo(tmp_path)
    env, marker = _marker_env(tmp_path, GATE_SKIP_CLEAN="0")
    assert run_gate(repo, env).returncode == 0
    again = run_gate(repo, env)
    assert again.returncode == 0, again.stderr
    assert "SKIP" not in again.stderr
    assert _lines(marker) == 2


def test_red_gate_never_records_fingerprint(tmp_path):
    _skip_unless_git_tools()
    repo = make_git_repo(tmp_path)
    env = dict(os.environ, CLAUDE_VERIFY_CMD="false")
    r = run_gate(repo, env)
    assert r.returncode == 2, r.stderr
    assert not (repo / FP_REL).exists(), "red gate must not arm the skip"


def test_pending_panel_verdict_prevents_skip(tmp_path):
    _skip_unless_git_tools()
    repo = make_git_repo(tmp_path)
    env, marker = _marker_env(tmp_path)
    assert run_gate(repo, env).returncode == 0        # green, skip armed
    (repo / ".claude" / "state" / "panel_verdict.json").write_text(
        (PANEL_FIX / "plan_fail.json").read_text())
    blocked = run_gate(repo, env)                     # .claude/state is outside
    assert blocked.returncode == 2, blocked.stderr    # the fingerprint, so only
    assert "SKIP" not in blocked.stderr               # the verdict guard saves us
