"""Wave 4 — gate.sh honors PANEL_VERDICT_PATH (env>config>default) and stays a v4
no-op when the resolved file is absent. Shells out to bash; skipped where bash absent."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
GATE = REPO / ".claude" / "hooks" / "gate.sh"
FIX = Path(__file__).resolve().parent / "fixtures"

def _find_bash():
    """A FUNCTIONAL bash, by full path. which() finding bash is not enough on
    Windows — and neither is spawning a bare "bash": CreateProcess resolves it
    via System32 BEFORE PATH, hitting the WSL stub, which fails where no
    distro is set up. That silently skipped this whole file on the owner's
    machine (2026-07-26). Probe which() plus the standard Git for Windows
    locations and return the first bash that actually works."""
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

def _posix(p):
    """C:\\x\\y -> /c/x/y so a Windows dir can ride a POSIX PATH string."""
    p = str(p).replace("\\", "/")
    if len(p) > 1 and p[1] == ":":
        p = "/" + p[0].lower() + p[2:]
    return p


# A no-op primary gate so we isolate GATE 4 behavior. The GATE 4 branch needs
# a python on PATH for verdict_lint; Git bash's /usr/bin has none on Windows,
# so append the running interpreter's dir (harmless no-op on Linux/CI).
ENV_BASE = {"CLAUDE_VERIFY_CMD": "true",
            "PATH": f"/usr/bin:/bin:{_posix(Path(sys.executable).parent)}"}


def run_gate(cwd, env):
    return subprocess.run([BASH, str(GATE)], cwd=str(cwd),
                          capture_output=True, text=True, env=env)


def make_repo(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# sentinel\n")            # gate opt-in guard
    (tmp_path / ".claude" / "hooks").mkdir(parents=True)
    shutil.copy(GATE, tmp_path / ".claude" / "hooks" / "gate.sh")
    shutil.copy(REPO / ".claude" / "hooks" / "verdict_lint.py",
                tmp_path / ".claude" / "hooks" / "verdict_lint.py")
    (tmp_path / ".claude" / "state").mkdir(parents=True)
    return tmp_path


def test_custom_path_pass_verdict_passes(tmp_path):
    repo = make_repo(tmp_path)
    dst = repo / ".claude" / "state" / "custom.json"
    dst.write_text((FIX / "plan_pass.json").read_text())
    env = dict(ENV_BASE, PANEL_VERDICT_PATH=".claude/state/custom.json")
    r = run_gate(repo, env)
    assert r.returncode == 0, r.stderr
    assert "[gate:panel]" in r.stderr and "PASS" in r.stderr


def test_custom_path_fail_verdict_blocks(tmp_path):
    repo = make_repo(tmp_path)
    dst = repo / ".claude" / "state" / "custom.json"
    dst.write_text((FIX / "plan_fail.json").read_text())
    env = dict(ENV_BASE, PANEL_VERDICT_PATH=".claude/state/custom.json")
    r = run_gate(repo, env)
    assert r.returncode == 2, r.stderr


def test_absent_file_is_v4_noop(tmp_path):
    repo = make_repo(tmp_path)
    # PANEL_VERDICT_PATH set but the file does not exist -> GATE 4 skipped entirely
    env = dict(ENV_BASE, PANEL_VERDICT_PATH=".claude/state/does_not_exist.json")
    r = run_gate(repo, env)
    assert r.returncode == 0, r.stderr
    assert "[gate:panel]" not in r.stderr        # branch never entered


def test_default_path_when_unset(tmp_path):
    repo = make_repo(tmp_path)
    (repo / ".claude" / "state" / "panel_verdict.json").write_text(
        (FIX / "plan_revise.json").read_text())
    r = run_gate(repo, dict(ENV_BASE))           # no PANEL_VERDICT_PATH -> default path
    assert r.returncode == 2, r.stderr           # fresh REVISE -> block


def test_stale_nonpass_verdict_superseded_by_reviewer_record_does_not_block(tmp_path):
    # freshness fix: a non-PASS panel verdict OLDER than the reviewer verdict of
    # record is consumed -> warn, not a perpetual block.
    import os
    import time
    repo = make_repo(tmp_path)
    pv = repo / ".claude" / "state" / "panel_verdict.json"
    pv.write_text((FIX / "plan_fail.json").read_text())
    record = repo / ".claude" / "state" / "verdict.json"
    record.write_text('{"task":"x","verdict":"PASS","findings":[],"escalate":false,'
                      '"escalate_reason":"","gates_rerun":true,"review_cycle":1}')
    # make the reviewer record decisively newer than the panel verdict
    now = time.time()
    os.utime(pv, (now - 10, now - 10))
    os.utime(record, (now, now))
    r = run_gate(repo, dict(ENV_BASE))
    assert r.returncode == 0, r.stderr           # consumed -> not blocking
    assert "consumed" in r.stderr or "superseded" in r.stderr


def test_fresh_nonpass_verdict_blocks_even_with_older_record(tmp_path):
    import os
    import time
    repo = make_repo(tmp_path)
    pv = repo / ".claude" / "state" / "panel_verdict.json"
    pv.write_text((FIX / "plan_fail.json").read_text())
    record = repo / ".claude" / "state" / "verdict.json"
    record.write_text('{"task":"x","verdict":"PASS","findings":[],"escalate":false,'
                      '"escalate_reason":"","gates_rerun":true,"review_cycle":1}')
    now = time.time()
    os.utime(record, (now - 10, now - 10))       # record OLDER than the panel verdict
    os.utime(pv, (now, now))
    r = run_gate(repo, dict(ENV_BASE))
    assert r.returncode == 2, r.stderr           # fresh advice, not yet incorporated -> block
