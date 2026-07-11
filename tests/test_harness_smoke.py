"""Install-time regression floor for the routed agent harness.

Pins the CURRENT (v4) verdict_lint.py exit-code contract so the Wave 1 panel
extension cannot silently break the reviewer verdict path. Stdlib only; no deps
beyond pytest itself. These are honest invariants of what is installed today —
not a stand-in for the real panel tests, which Wave 1 adds under tests/panel/.
"""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LINT = REPO / ".claude" / "hooks" / "verdict_lint.py"


def run_lint(path: Path):
    return subprocess.run(
        [sys.executable, str(LINT), str(path)],
        capture_output=True, text=True,
    )


def test_verdict_lint_exists():
    assert LINT.is_file(), "verdict_lint.py must be installed"


def test_missing_verdict_exits_1(tmp_path):
    r = run_lint(tmp_path / "nope.json")
    assert r.returncode == 1, r.stderr


def test_valid_pass_verdict_exits_0(tmp_path):
    v = {
        "task": "smoke", "verdict": "PASS", "findings": [],
        "escalate": False, "escalate_reason": "",
        "gates_rerun": True, "review_cycle": 1,
    }
    p = tmp_path / "verdict.json"
    p.write_text(json.dumps(v), encoding="utf-8")
    r = run_lint(p)
    assert r.returncode == 0, r.stderr


def test_malformed_verdict_exits_2(tmp_path):
    p = tmp_path / "verdict.json"
    p.write_text('{"task": "smoke", "verdict": "MAYBE"}', encoding="utf-8")
    r = run_lint(p)
    assert r.returncode == 2, r.stderr
