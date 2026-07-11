"""Wave 5 dashboard test fixtures. Tests never mutate the repo's real agent.config —
they operate on a temp copy."""
import json
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
FIX = REPO / "tests" / "panel" / "fixtures"


@pytest.fixture
def real_config():
    return REPO / ".claude" / "agent.config"


@pytest.fixture
def tmp_config(tmp_path, real_config):
    dst = tmp_path / "agent.config"
    shutil.copy(real_config, dst)
    return dst


@pytest.fixture
def sample_verdict():
    return json.loads((FIX / "plan_pass.json").read_text())


@pytest.fixture
def tmp_verdict(tmp_path, sample_verdict):
    p = tmp_path / "panel_verdict.json"
    p.write_text(json.dumps(sample_verdict), encoding="utf-8")
    return p


@pytest.fixture
def cost_log(tmp_path):
    return tmp_path / "cost.jsonl"


@pytest.fixture
def xss_verdict(tmp_path, sample_verdict):
    v = json.loads(json.dumps(sample_verdict))
    v["synthesis"]["artifact"] = "<script>alert(1)</script>"
    v["expert_opinions"][0]["summary"] = "<img src=x onerror=alert(2)>"
    p = tmp_path / "xss_verdict.json"
    p.write_text(json.dumps(v), encoding="utf-8")
    return p
