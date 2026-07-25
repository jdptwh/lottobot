"""Tests for scraper/winners.py — offline only (parse/merge layer).

The network commands (fetch/wayback) are owner-machine CLIs; the socket
guard in tests/scraper/conftest.py enforces that nothing here ever dials.
Fixture: tests/scraper/fixtures/winners_showcase_2026-07-22.html — entry
text transcribed verbatim from the live page (see the fixture's header),
covering the page's real variance: missing prize/town/retailer-town,
split claims, draw-game phrasing, typos, mangled apostrophes.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

# Same harness-packaging-copy skip guard as test_compute.py: scraper/ is this
# project's own code, not part of the installable harness, and is not copied
# into the nested self-test directory (scripts/harness.manifest.json).
if not (Path(__file__).resolve().parents[2] / "scraper" / "winners.py").exists():
    pytest.skip(
        "scraper/ is this project's own code, not part of the installable harness",
        allow_module_level=True,
    )

from scraper.winners import (
    merge_winners,
    parse_winners,
    records_from_html,
    winner_key,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = (
    REPO_ROOT / "tests" / "scraper" / "fixtures"
    / "winners_showcase_2026-07-22.html"
)
SCHEMA = REPO_ROOT / "data" / "schema" / "winner_record.schema.json"


@pytest.fixture(scope="module")
def entries():
    return parse_winners(FIXTURE.read_text(encoding="utf-8"))


def _by_first_name(entries, name):
    for e in entries:
        if e["names"][0].startswith(name):
            return e
    raise AssertionError(f"no entry for {name}")


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------

def test_all_fixture_entries_parse(entries):
    assert len(entries) == 19


def test_full_entry(entries):
    e = _by_first_name(entries, "Muriel")
    assert e["town"] == "Windham"
    assert e["prize"] == 100000.0
    assert e["game"] == "Wheel of Fortune"
    assert e["game_type"] == "instant"
    assert e["retailer"] == "Cigaret Shopper"
    assert e["retailer_town"] == "Windham"


def test_missing_fields_stay_null_never_guessed(entries):
    e = _by_first_name(entries, "Timothy")     # no town, no retailer
    assert e["town"] is None
    assert e["retailer"] is None
    assert e["prize"] == 20000.0
    e2 = _by_first_name(entries, "Steven")     # retailer without a town
    assert e2["retailer"] == "Warren Farms"
    assert e2["retailer_town"] is None
    assert e2["prize"] is None


def test_split_claim_two_names(entries):
    e = _by_first_name(entries, "Carol")
    assert e["names"] == ["Carol Daniell", "Judy Beaupain"]
    assert e["game"] == "Lady Luck"
    assert e["game_type"] == "instant"


def test_draw_game_classified_conservatively(entries):
    e = _by_first_name(entries, "Norman W")
    assert e["game"] == "Megabucks"
    assert e["game_type"] == "draw"
    # "bought her Lady Luck ticket" with no 'instant' wording → unknown
    e2 = _by_first_name(entries, "Liane")
    assert e2["game"] == "Lady Luck"
    assert e2["game_type"] == "unknown"


def test_mangled_apostrophe_repaired(entries):
    e = _by_first_name(entries, "Gretchen")
    assert e["retailer"] == "Bradbury's Market and Diner"
    assert e["retailer_town"] == "Carthage"


def test_page_noise_is_ignored():
    noise = "<html><h2>Congratulations!</h2><p>Buy tickets today.</p></html>"
    assert parse_winners(noise) == []


# ---------------------------------------------------------------------------
# records + schema + merge
# ---------------------------------------------------------------------------

def _records(first_seen="2026-07-22"):
    return records_from_html(
        FIXTURE.read_text(encoding="utf-8"),
        source="seed",
        capture_url="https://www.mainelottery.com/players_info/winners_showcase.html",
        capture_ts="2026-07-22T18:30:00+00:00",
        first_seen=first_seen,
    )


def test_records_validate_against_schema():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    for rec in _records():
        jsonschema.validate(rec, schema)


def test_winner_key_stable_and_distinct(entries):
    keys = {winner_key(e) for e in entries}
    assert len(keys) == len(entries)          # all distinct on this fixture
    assert winner_key(entries[0]) == winner_key(dict(entries[0]))


def test_merge_idempotent_and_lf_only(tmp_path):
    out = tmp_path / "winners.jsonl"
    added1, total1 = merge_winners(out, _records())
    assert (added1, total1) == (19, 19)
    added2, total2 = merge_winners(out, _records())
    assert (added2, total2) == (0, 19)        # idempotent
    raw = out.read_bytes()
    assert b"\r" not in raw                   # LF-only (M5a rule)
    lines = [json.loads(l) for l in raw.decode("utf-8").splitlines()]
    keys = [(r["first_seen"], r["winner_key"]) for r in lines]
    assert keys == sorted(keys)               # canonical order


def test_merge_keeps_earliest_first_seen(tmp_path):
    out = tmp_path / "winners.jsonl"
    merge_winners(out, _records(first_seen="2026-07-22"))
    merge_winners(out, _records(first_seen="2020-01-01"))
    lines = [json.loads(l) for l in out.read_text().splitlines()]
    assert all(r["first_seen"] == "2020-01-01" for r in lines)


# ---------------------------------------------------------------------------
# purity: never wired into the daily pipeline
# ---------------------------------------------------------------------------

def test_never_imported_by_run_daily_or_daily_yml():
    run_daily = (REPO_ROOT / "scraper" / "run_daily.py").read_text(
        encoding="utf-8")
    assert "winners" not in run_daily
    daily_yml = (REPO_ROOT / ".github" / "workflows" / "daily.yml").read_text(
        encoding="utf-8")
    assert "winners" not in daily_yml


def test_does_not_import_wayback_backfill():
    src = (REPO_ROOT / "scraper" / "winners.py").read_text(encoding="utf-8")
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith(("import ", "from ")):
            assert "wayback_backfill" not in stripped


def test_cli_parse_offline(tmp_path):
    out = tmp_path / "w.jsonl"
    r = subprocess.run(
        [sys.executable, "-m", "scraper.winners", "parse",
         "--html", str(FIXTURE), "--source", "seed",
         "--capture-ts", "2026-07-22T18:30:00+00:00",
         "--first-seen", "2026-07-22", "--out", str(out)],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert r.returncode == 0, r.stderr
    assert "added 19" in r.stderr
