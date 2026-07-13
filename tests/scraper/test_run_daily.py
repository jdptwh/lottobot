"""M5 test surface: `scraper/run_daily.py` orchestration + gate wiring.

See docs/specs/m5_daily_action_spec.md for the acceptance criteria (numbered
1-7 + 9 in comments below, matching the spec's own numbering; AC-8/AC-11/
AC-12 are out of scope for this file per the spec's tier assignment). All
tests are offline (frozen fixtures only) and run under the autouse socket
guard in tests/scraper/conftest.py. Every invocation passes `--as-of`
explicitly except the AC-7 default test (determinism).
"""
from __future__ import annotations

import copy
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
import requests
from jsonschema import validate

# Same harness-packaging-copy skip guard as test_scrape.py/test_compute.py:
# scraper/ is this project's own code, not part of the installable harness.
if not (Path(__file__).resolve().parents[2] / "scraper" / "run_daily.py").exists():
    pytest.skip(
        "scraper/ is this project's own code, not part of the installable harness",
        allow_module_level=True,
    )

import scraper.run_daily as run_daily
from scraper.compute import compute_latest
from scraper.scrape import parse

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "data" / "schema" / "latest.schema.json"
GAMES_PATH = REPO_ROOT / "data" / "games.json"
FROZEN_ARTIFACT_PATH = (
    REPO_ROOT / "tests" / "scraper" / "fixtures" / "latest_2026-07-11.json"
)
FIXTURE_PATH = (
    REPO_ROOT / "tests" / "scraper" / "fixtures" / "unclaimed_prizes_2026-07-11.html"
)
AS_OF = "2026-07-11"

MINIMAL_TABLE_HEAD = """
<p>Below is the list of top unclaimed prizes for current instant games
as of July 10, 2026 5:00 AM
</p>
<table class="tbstriped">
<tr><th>Price Point</th><th>Game No.</th><th>Game Name</th><th>Percent Unsold</th>
<th>Total Unclaimed</th><th>Top Prize Level(s)</th><th>Top Prize(s) Unclaimed</th></tr>
"""


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _games_meta() -> dict:
    return json.loads(GAMES_PATH.read_text(encoding="utf-8"))


def _real_doc() -> dict:
    snapshot = parse(FIXTURE_PATH.read_text(encoding="utf-8"))
    return compute_latest(snapshot, _games_meta(), AS_OF)


def _run_cli(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "scraper.run_daily", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


# --- 1. Fixture happy path + zero-reimplementation proof --------------------

def test_fixture_happy_path_byte_identical_to_frozen_regression_artifact(tmp_path):
    # data/latest.json is now overwritten daily by the M5 bot (live data), so
    # this regression check compares against a frozen artifact captured from
    # the fixture pipeline instead (tests/scraper/fixtures/latest_2026-07-11.json,
    # the exact bytes of the pre-bot committed data/latest.json at e4a8b7a).
    out_path = tmp_path / "latest.json"
    history_dir = tmp_path / "history"

    result = _run_cli(
        [
            "--fixture", str(FIXTURE_PATH),
            "--games", str(GAMES_PATH),
            "--as-of", AS_OF,
            "--out", str(out_path),
            "--history-dir", str(history_dir),
        ]
    )

    assert result.returncode == 0, result.stderr
    assert out_path.read_bytes() == FROZEN_ARTIFACT_PATH.read_bytes()
    history_path = history_dir / f"{AS_OF}.json"
    assert history_path.read_bytes() == out_path.read_bytes()


# --- 2. Parser-gate failure --------------------------------------------------

def test_parser_gate_failure_writes_nothing(tmp_path):
    truncated_html = MINIMAL_TABLE_HEAD + (
        "<tr><td>$1.00</td><td>668</td><td>CA$H CRU$H</td><td>6.1</td>"
        "<td>$96,620.00</td><td>$1000</td><td>5</td></tr></table>"
    )
    truncated_path = tmp_path / "truncated.html"
    truncated_path.write_text(truncated_html, encoding="utf-8")
    out_path = tmp_path / "latest.json"
    history_dir = tmp_path / "history"

    result = _run_cli(
        [
            "--fixture", str(truncated_path),
            "--games", str(GAMES_PATH),
            "--as-of", AS_OF,
            "--out", str(out_path),
            "--history-dir", str(history_dir),
        ]
    )

    assert result.returncode != 0
    assert "parser gate" in result.stderr
    assert not out_path.exists()
    assert not history_dir.exists()


# --- 3. Schema-gate failure (first runtime §6.3 enforcement) ----------------

def test_schema_gate_failure_writes_nothing(tmp_path):
    bad_schema = {
        "type": "object",
        "required": ["as_of"],
        "properties": {"as_of": {"type": "integer"}},
    }
    schema_path = tmp_path / "bad_schema.json"
    schema_path.write_text(json.dumps(bad_schema), encoding="utf-8")
    out_path = tmp_path / "latest.json"
    history_dir = tmp_path / "history"

    result = _run_cli(
        [
            "--fixture", str(FIXTURE_PATH),
            "--games", str(GAMES_PATH),
            "--as-of", AS_OF,
            "--schema", str(schema_path),
            "--out", str(out_path),
            "--history-dir", str(history_dir),
        ]
    )

    assert result.returncode != 0
    assert not out_path.exists()
    assert not history_dir.exists()


def test_happy_path_validates_against_real_schema(tmp_path):
    # Companion positive assertion: the happy-path output validates against
    # the real, committed schema (already exercised implicitly by the AC-1
    # default --schema, asserted explicitly here).
    out_path = tmp_path / "latest.json"
    history_dir = tmp_path / "history"

    result = _run_cli(
        [
            "--fixture", str(FIXTURE_PATH),
            "--games", str(GAMES_PATH),
            "--as-of", AS_OF,
            "--out", str(out_path),
            "--history-dir", str(history_dir),
        ]
    )

    assert result.returncode == 0, result.stderr
    data = json.loads(out_path.read_text(encoding="utf-8"))
    validate(instance=data, schema=_schema())


# --- 4. Diff-gate failure holds the commit -----------------------------------

def test_diff_gate_failure_holds_commit_and_leaves_prior_untouched(tmp_path):
    real_doc = _real_doc()
    doctored_prior = copy.deepcopy(real_doc)
    for g in doctored_prior["games"]:
        if g["ev_ratio"] is not None:
            g["ev_ratio"] = g["ev_ratio"] + 50.0

    prior_path = tmp_path / "prior.json"
    prior_bytes = json.dumps(doctored_prior, indent=2).encode("utf-8")
    prior_path.write_bytes(prior_bytes)
    out_path = tmp_path / "latest.json"
    history_dir = tmp_path / "history"

    result = _run_cli(
        [
            "--fixture", str(FIXTURE_PATH),
            "--games", str(GAMES_PATH),
            "--as-of", AS_OF,
            "--prior", str(prior_path),
            "--out", str(out_path),
            "--history-dir", str(history_dir),
        ]
    )

    assert result.returncode != 0
    assert "diff gate" in result.stderr
    assert not out_path.exists()
    assert not history_dir.exists()
    assert prior_path.read_bytes() == prior_bytes


# --- 5. `--prior` default semantics ------------------------------------------

def test_prior_default_is_resolved_out_path(tmp_path):
    out_path = tmp_path / "latest.json"
    history_dir = tmp_path / "history"

    # First run: no prior file exists yet -> inert first run, exits 0.
    first = _run_cli(
        [
            "--fixture", str(FIXTURE_PATH),
            "--games", str(GAMES_PATH),
            "--as-of", AS_OF,
            "--out", str(out_path),
            "--history-dir", str(history_dir),
        ]
    )
    assert first.returncode == 0, first.stderr
    assert "no prior latest.json" in first.stderr
    first_output_bytes = out_path.read_bytes()

    # Second run: same --out, no --prior passed, but a doctored games.json
    # (print_run slashed) trips the diff gate against the first run's
    # output, proving the default prior IS the previous --out content.
    doctored_meta = copy.deepcopy(_games_meta())
    for meta in doctored_meta["games"].values():
        if meta.get("print_run"):
            meta["print_run"] = 1000
    doctored_games_path = tmp_path / "doctored_games.json"
    doctored_games_path.write_text(json.dumps(doctored_meta), encoding="utf-8")

    second = _run_cli(
        [
            "--fixture", str(FIXTURE_PATH),
            "--games", str(doctored_games_path),
            "--as-of", AS_OF,
            "--out", str(out_path),
            "--history-dir", str(history_dir),
        ]
    )
    assert second.returncode != 0
    assert "diff gate" in second.stderr
    assert out_path.read_bytes() == first_output_bytes


# --- 6. Single-fetch politeness ----------------------------------------------

def test_live_calls_fetch_exactly_once(tmp_path, monkeypatch):
    fixture_html = FIXTURE_PATH.read_text(encoding="utf-8")
    calls = {"n": 0}

    def fake_fetch(*a, **k):
        calls["n"] += 1
        return fixture_html

    monkeypatch.setattr(run_daily, "fetch", fake_fetch)

    out_path = tmp_path / "latest.json"
    history_dir = tmp_path / "history"

    rc = run_daily.main(
        [
            "--live",
            "--games", str(GAMES_PATH),
            "--as-of", AS_OF,
            "--out", str(out_path),
            "--history-dir", str(history_dir),
        ]
    )

    assert rc == 0
    assert calls["n"] == 1
    assert out_path.exists()


def test_live_fetch_failure_writes_nothing(tmp_path, monkeypatch):
    def raising_fetch(*a, **k):
        raise requests.RequestException("boom")

    monkeypatch.setattr(run_daily, "fetch", raising_fetch)

    out_path = tmp_path / "latest.json"
    history_dir = tmp_path / "history"

    rc = run_daily.main(
        [
            "--live",
            "--games", str(GAMES_PATH),
            "--as-of", AS_OF,
            "--out", str(out_path),
            "--history-dir", str(history_dir),
        ]
    )

    assert rc == 1
    assert not out_path.exists()
    assert not history_dir.exists()


# --- 7. `--as-of` default -----------------------------------------------------

def test_as_of_defaults_to_utc_today(tmp_path):
    from datetime import datetime, timezone

    out_path = tmp_path / "latest.json"
    history_dir = tmp_path / "history"

    before = datetime.now(timezone.utc).date().isoformat()
    result = _run_cli(
        [
            "--fixture", str(FIXTURE_PATH),
            "--games", str(GAMES_PATH),
            "--out", str(out_path),
            "--history-dir", str(history_dir),
        ]
    )
    after = datetime.now(timezone.utc).date().isoformat()

    assert result.returncode == 0, result.stderr
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["as_of"] in {before, after}


# --- 9. Runtime purity -------------------------------------------------------

def test_no_yaml_import_under_scraper():
    pattern = re.compile(r"^\s*(import|from)\s+yaml\b", re.MULTILINE)
    scraper_dir = REPO_ROOT / "scraper"
    for path in scraper_dir.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert not pattern.search(text), f"yaml import found in {path}"


def test_requirements_txt_byte_unchanged():
    result = subprocess.run(
        ["git", "diff", "--quiet", "--", "requirements.txt"],
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0
