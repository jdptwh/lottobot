"""tests/workflow/test_winners_workflow.py — winners-refresh workflow rules.

Pins the hard rules from docs/specs/winners_location_spec.md: the winner
refresh is OWNER-TRIGGERED ONLY (workflow_dispatch, no schedule — fetch
cadence is an owner decision), it never touches the daily pipeline, and the
daily pipeline never references it. Same yaml.safe_load + boolean-True
`on:` resolution pattern as test_daily_workflow.py.
"""
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "winners.yml"
DAILY_PATH = REPO_ROOT / ".github" / "workflows" / "daily.yml"

if not WORKFLOW_PATH.exists():
    pytest.skip(
        ".github/workflows/ is this project's own artifact, not part of the installable harness",
        allow_module_level=True,
    )


@pytest.fixture(scope="module")
def doc():
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def text():
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def _triggers(doc):
    return doc.get("on", doc.get(True))


def test_manual_only_no_schedule(doc):
    triggers = _triggers(doc)
    assert set(triggers) == {"workflow_dispatch"}, (
        "winners-refresh must be owner-triggered ONLY — adding a schedule "
        "is a spec change (winners_location_spec.md out-of-scope list)"
    )


def test_no_cron_anywhere(text):
    assert "cron" not in text
    assert "schedule" not in text.replace("workflow_dispatch", "")


def test_offline_gate_runs_before_fetch(text):
    gate_pos = text.find("tests/scraper/test_winners.py")
    fetch_pos = text.find("scraper.winners fetch")
    assert gate_pos != -1 and fetch_pos != -1
    assert gate_pos < fetch_pos, "offline gate must precede the network fetch"


def test_exactly_one_fetch_invocation(text):
    assert text.count("scraper.winners fetch") == 1
    assert "scraper.winners wayback" not in text, (
        "the wayback backfill is a local owner CLI, never CI"
    )


def test_schema_validation_before_commit(text):
    validate_pos = text.find("winner_record.schema.json")
    commit_pos = text.find("git commit")
    assert validate_pos != -1 and commit_pos != -1
    assert validate_pos < commit_pos


def test_commits_only_the_two_artifacts(text):
    assert "git add data/winners/winners.jsonl data/insights/location_trends.json" in text
    assert "--force" not in text


def test_daily_pipeline_isolation():
    daily = DAILY_PATH.read_text(encoding="utf-8")
    assert "winners" not in daily
    run_daily = (REPO_ROOT / "scraper" / "run_daily.py").read_text(encoding="utf-8")
    assert "winners" not in run_daily


def test_permissions_are_contents_write_only(doc):
    assert doc.get("permissions") == {"contents": "write"}
