"""M6a (Phase 0) CP1 test surface: scraper/build_panel.py.

Offline, deterministic merge tests. See docs/specs/m6_v2_program_spec.md
Phase 0, design rules 1-6 and acceptance criteria 1-6 (this dispatch's scope).
"""
import json
from pathlib import Path

import pytest
from jsonschema import validate

if not (Path(__file__).resolve().parents[2] / "scraper" / "scrape.py").exists():
    pytest.skip(
        "scraper/ is this project's own code, not part of the installable harness",
        allow_module_level=True,
    )

from scraper import build_panel as bp

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "data" / "schema" / "panel_record.schema.json"


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")


def _daily_snapshot(as_of: str, games: list[dict]) -> dict:
    return {
        "as_of": as_of,
        "source_timestamp": f"{as_of} 5:00 AM",
        "games": games,
    }


def _wb_record(game_no, name, obs_date, capture_ts, percent_unsold, total_unclaimed=1000.0, price=5.0):
    return {
        "game_no": game_no,
        "game_key": bp.game_key(game_no, name),
        "obs_date": obs_date,
        "capture_ts": capture_ts,
        "source": "wayback",
        "capture_url": f"https://web.archive.org/web/x/{game_no}",
        "retrieved_at": "2026-07-13T00:00:00+00:00",
        "content_hash": "hash",
        "parser_version": bp.PARSER_VERSION,
        "percent_unsold": percent_unsold,
        "pu_interval": bp.pu_interval(percent_unsold),
        "total_unclaimed": total_unclaimed,
        "top_prizes": [{"level": 1000, "remaining": 1}],
        "price": price,
        "name": name,
        "lifecycle_status": None,
    }


# --- AC3: daily records carry source/capture_url/content_hash --------------

def test_load_daily_observations_shape(tmp_path):
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    snap = _daily_snapshot(
        "2026-07-13",
        [
            {
                "game_no": 706,
                "name": "DOUBLE YOUR DOLLARS",
                "price": 5.0,
                "percent_unsold": 0.3,
                "total_unclaimed": 468555.0,
                "top_prizes": [{"level": 100000, "remaining": 1}],
            }
        ],
    )
    path = history_dir / "2026-07-13.json"
    raw = json.dumps(snap).encode("utf-8")
    path.write_bytes(raw)

    import hashlib

    records = bp.load_daily_observations(history_dir)
    assert len(records) == 1
    rec = records[0]
    assert rec["source"] == "daily"
    assert rec["obs_date"] == "2026-07-13"
    # Not under REPO_ROOT in this test (tmp_path), so we only assert the
    # relative-path *shape* the real (in-repo) call produces: history/<file>.
    assert rec["capture_url"].replace("\\", "/").endswith("history/2026-07-13.json")
    assert rec["content_hash"] == hashlib.sha256(raw).hexdigest()
    validate(instance={**rec, "lifecycle_status": "active"}, schema=_schema())


# --- AC3: merge is deterministic, sorted, LF-only ---------------------------

def test_build_panel_is_byte_identical_across_two_runs(tmp_path):
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    (history_dir / "2026-07-13.json").write_bytes(
        json.dumps(
            _daily_snapshot(
                "2026-07-13",
                [
                    {
                        "game_no": 706, "name": "DOUBLE YOUR DOLLARS", "price": 5.0,
                        "percent_unsold": 0.3, "total_unclaimed": 468555.0,
                        "top_prizes": [{"level": 100000, "remaining": 1}],
                    }
                ],
            )
        ).encode("utf-8")
    )
    wayback_path = tmp_path / "wayback_observations.jsonl"
    _write_jsonl(wayback_path, [_wb_record(706, "DOUBLE YOUR DOLLARS", "2026-06-01", "2026-06-01T00:00:00+00:00", 5.0)])

    out1 = tmp_path / "panel1.jsonl"
    out2 = tmp_path / "panel2.jsonl"
    bp.build_panel(wayback_path=wayback_path, history_dir=history_dir, out_path=out1)
    bp.build_panel(wayback_path=wayback_path, history_dir=history_dir, out_path=out2)

    assert out1.read_bytes() == out2.read_bytes()
    assert b"\r" not in out1.read_bytes()


def test_build_panel_output_sorted_by_obs_date_then_game_no(tmp_path):
    wayback_path = tmp_path / "wayback_observations.jsonl"
    _write_jsonl(
        wayback_path,
        [
            _wb_record(700, "B GAME", "2026-02-01", "2026-02-01T00:00:00+00:00", 10.0),
            _wb_record(600, "A GAME", "2026-01-01", "2026-01-01T00:00:00+00:00", 10.0),
            _wb_record(650, "C GAME", "2026-01-01", "2026-01-01T00:00:00+00:00", 10.0),
        ],
    )
    out_path = tmp_path / "panel.jsonl"
    bp.build_panel(wayback_path=wayback_path, history_dir=tmp_path / "no_history", out_path=out_path)
    records = [json.loads(l) for l in out_path.read_text(encoding="utf-8").splitlines()]
    keys = [(r["obs_date"], r["game_no"]) for r in records]
    assert keys == sorted(keys)


# --- AC3: dedup + supersession log -------------------------------------------

def test_dedup_keeps_later_capture_ts_and_logs_supersession():
    older = _wb_record(706, "DOUBLE YOUR DOLLARS", "2026-06-01", "2026-06-01T00:00:00+00:00", 5.0)
    newer = _wb_record(706, "DOUBLE YOUR DOLLARS", "2026-06-01", "2026-06-01T12:00:00+00:00", 4.5)
    merged, superseded = bp.merge_panel([older, newer], [])
    assert len(merged) == 1
    assert merged[0]["capture_ts"] == "2026-06-01T12:00:00+00:00"
    assert merged[0]["percent_unsold"] == 4.5
    assert len(superseded) == 1
    assert superseded[0]["superseded_capture_ts"] == "2026-06-01T00:00:00+00:00"
    assert superseded[0]["kept_capture_ts"] == "2026-06-01T12:00:00+00:00"


# --- AC2: pu_interval on a synthetic 0.0% record -----------------------------

def test_pu_interval_zero_percent_record():
    rec = _wb_record(651, "MONEY CRAZE", "2026-01-01", "2026-01-01T00:00:00+00:00", 0.0)
    assert rec["pu_interval"] == [0, 0.05]


# --- AC4: lifecycle labeling: all three statuses -----------------------------

def test_lifecycle_active_when_last_obs_is_the_panels_most_recent_date():
    recs = [
        _wb_record(706, "DOUBLE YOUR DOLLARS", "2026-01-01", "2026-01-01T00:00:00+00:00", 10.0),
        _wb_record(706, "DOUBLE YOUR DOLLARS", "2026-02-01", "2026-02-01T00:00:00+00:00", 8.0),
    ]
    merged, _ = bp.merge_panel(recs, [])
    by_date = {r["obs_date"]: r for r in merged}
    assert by_date["2026-01-01"]["lifecycle_status"] == "active"
    assert by_date["2026-02-01"]["lifecycle_status"] == "active"


def test_lifecycle_exited_observed_on_zero_percent_unsold_last_record():
    recs = [
        _wb_record(651, "MONEY CRAZE", "2026-01-01", "2026-01-01T00:00:00+00:00", 10.0),
        _wb_record(651, "MONEY CRAZE", "2026-02-01", "2026-02-01T00:00:00+00:00", 0.0),
    ]
    merged, _ = bp.merge_panel(recs, [])
    by_date = {r["obs_date"]: r for r in merged}
    assert by_date["2026-01-01"]["lifecycle_status"] == "active"
    assert by_date["2026-02-01"]["lifecycle_status"] == "exited_observed"


def test_lifecycle_exited_unobserved_when_game_vanishes_between_captures():
    # game 800 is last seen 2026-01-01; other games are observed later
    # (2026-02-01), proving the page itself kept being captured after game
    # 800 disappeared -> its exit is interval-censored, never "observed".
    recs = [
        _wb_record(800, "GHOST GAME", "2026-01-01", "2026-01-01T00:00:00+00:00", 40.0),
        _wb_record(801, "OTHER GAME", "2026-01-01", "2026-01-01T00:00:00+00:00", 40.0),
        _wb_record(801, "OTHER GAME", "2026-02-01", "2026-02-01T00:00:00+00:00", 30.0),
    ]
    merged, _ = bp.merge_panel(recs, [])
    ghost = [r for r in merged if r["game_no"] == 800][0]
    assert ghost["lifecycle_status"] == "exited_unobserved"
    # never dropped
    assert any(r["game_no"] == 800 for r in merged)


def test_lifecycle_never_drops_a_record():
    recs = [
        _wb_record(800, "GHOST GAME", "2026-01-01", "2026-01-01T00:00:00+00:00", 40.0),
        _wb_record(801, "OTHER GAME", "2026-02-01", "2026-02-01T00:00:00+00:00", 30.0),
    ]
    merged, _ = bp.merge_panel(recs, [])
    assert len(merged) == 2


# --- AC5: game_key collision -------------------------------------------------

def test_game_key_collision_two_distinct_lifecycles():
    era_a = bp.game_key(399, "WILD 8`S")
    era_b = bp.game_key(399, "A WHOLE NEW GAME")
    assert era_a != era_b

    recs = [
        _wb_record(399, "WILD 8`S", "2017-01-01", "2017-01-01T00:00:00+00:00", 20.0),
        _wb_record(399, "A WHOLE NEW GAME", "2021-01-01", "2021-01-01T00:00:00+00:00", 20.0),
    ]
    merged, _ = bp.merge_panel(recs, [])
    keys = {r["game_key"] for r in merged}
    assert keys == {era_a, era_b}
    by_key = {r["game_key"]: r for r in merged}
    # era_a's only observation (2017) predates era_b's (2021) — from the
    # panel's point of view that reads as era_a exiting unobserved by the
    # time era_b's game_no reuse was captured; era_b is still the panel's
    # most recent observation of game_no 399, so it reads as active.
    assert by_key[era_a]["lifecycle_status"] == "exited_unobserved"
    assert by_key[era_b]["lifecycle_status"] == "active"


# --- schema validation of merged output --------------------------------------

def test_merged_records_validate_against_schema(tmp_path):
    wayback_path = tmp_path / "wayback_observations.jsonl"
    _write_jsonl(
        wayback_path,
        [_wb_record(706, "DOUBLE YOUR DOLLARS", "2026-01-01", "2026-01-01T00:00:00+00:00", 10.0)],
    )
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    (history_dir / "2026-07-13.json").write_bytes(
        json.dumps(
            _daily_snapshot(
                "2026-07-13",
                [
                    {
                        "game_no": 706, "name": "DOUBLE YOUR DOLLARS", "price": 5.0,
                        "percent_unsold": 0.3, "total_unclaimed": 468555.0,
                        "top_prizes": [{"level": 100000, "remaining": 1}],
                    }
                ],
            )
        ).encode("utf-8")
    )
    out_path = tmp_path / "panel.jsonl"
    bp.build_panel(wayback_path=wayback_path, history_dir=history_dir, out_path=out_path)
    schema = _schema()
    for line in out_path.read_text(encoding="utf-8").splitlines():
        validate(instance=json.loads(line), schema=schema)


# --- design rule 3b: never modifies data/history/ ---------------------------

def test_load_daily_observations_does_not_modify_source_files(tmp_path):
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    path = history_dir / "2026-07-13.json"
    raw = json.dumps(_daily_snapshot("2026-07-13", [])).encode("utf-8")
    path.write_bytes(raw)
    bp.load_daily_observations(history_dir)
    assert path.read_bytes() == raw


def test_load_daily_observations_missing_dir_returns_empty(tmp_path):
    assert bp.load_daily_observations(tmp_path / "does_not_exist") == []


def test_load_wayback_observations_missing_file_returns_empty(tmp_path):
    assert bp.load_wayback_observations(tmp_path / "does_not_exist.jsonl") == []


# --- design rule 3b: no network (offline, deterministic) --------------------

def test_socket_connect_is_blocked_by_the_guard():
    import socket

    with pytest.raises(AssertionError):
        socket.socket().connect(("example.com", 80))
