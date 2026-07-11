"""Wave 3 orchestrator test fixtures (auto-discovered by pytest).

Also puts this directory on sys.path so sibling test modules can
`import orch_fakes` (the shared fakes module). Reusable fakes/builders live in
tests/panel/orch_fakes.py; this keeps the protected repo-root conftest.py untouched.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(__file__))

REPO = Path(__file__).resolve().parents[2]
LINT = REPO / ".claude" / "hooks" / "verdict_lint.py"


@pytest.fixture
def lint_exit(tmp_path):
    """Write a verdict dict to disk and return (verdict_lint exit code, stderr)."""
    def _run(verdict_dict):
        p = tmp_path / "panel_verdict.json"
        p.write_text(json.dumps(verdict_dict), encoding="utf-8")
        r = subprocess.run([sys.executable, str(LINT), str(p)],
                           capture_output=True, text=True)
        return r.returncode, r.stderr
    return _run
