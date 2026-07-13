"""M6a (Phase 0) CP1 test surface: scraper/wayback_backfill.py.

Offline only — the socket-blocking autouse fixture in tests/scraper/conftest.py
applies here too. See docs/specs/m6_v2_program_spec.md Phase 0, design rules
1-6 and acceptance criteria 1-6 (this dispatch's scope; AC 7-9 are CP2/CP3,
the live-run and semantics-note deliverables, not covered here).
"""
import datetime as _dt
import json
from pathlib import Path

import pytest
from jsonschema import validate

# See tests/scraper/test_scrape.py for why this guard exists (harness
# packaging self-test collects tests/ without this project's scraper/).
if not (Path(__file__).resolve().parents[2] / "scraper" / "scrape.py").exists():
    pytest.skip(
        "scraper/ is this project's own code, not part of the installable harness",
        allow_module_level=True,
    )

from scraper import wayback_backfill as wb

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "data" / "schema" / "panel_record.schema.json"
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "wayback"
DAILY_YML_PATH = REPO_ROOT / ".github" / "workflows" / "daily.yml"


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _html(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


# --- AC1: fixture captures for each era parse into schema-valid records -----

@pytest.mark.parametrize(
    "fixture_name",
    [
        "unclaimed_prizes_2026_current_era.html",
        "unclaimed_prizes_2017_era.html",
        "unclaimed_prizes_2019_era.html",
    ],
)
def test_era_fixtures_parse_into_schema_valid_records(fixture_name):
    html = _html(fixture_name)
    records = wb.build_records_from_html(
        html,
        capture_ts="2017-03-03T05:00:00+00:00",
        capture_url="https://web.archive.org/web/20170303050000id_/x",
        retrieved_at="2026-07-13T00:00:00+00:00",
        content_hash="deadbeef",
    )
    assert records, "expected at least one parsed game record"
    schema = _schema()
    for rec in records:
        validate(instance=rec, schema=schema)
        assert rec["source"] == "wayback"
        assert rec["lifecycle_status"] is None  # assigned later, at merge time


# --- AC1 (era guard): pre-2015 capture is skipped by CDX timestamp, never parsed --

def test_pre_2015_capture_is_era_skipped_not_an_error(tmp_path):
    # A cache dir that does NOT contain this capture — if the era guard did
    # not short-circuit, process_capture would try to fetch it (and the
    # socket guard would fail the test loudly).
    cdx_row = {
        "timestamp": "20130615120000",
        "original": wb.TARGET_URL,
        "digest": "PREERADIGEST",
        "statuscode": "200",
    }
    status, records, detail = wb.process_capture(cdx_row, cache_dir=tmp_path / "raw_cache")
    assert status == "era_skipped"
    assert records == []
    assert detail is None
    # never touched the cache dir at all (never fetched, so never created it)
    assert not (tmp_path / "raw_cache").exists()


def test_is_pre_era_boundary():
    assert wb.is_pre_era("20141231235959") is True
    assert wb.is_pre_era("20150101000000") is False


def test_era_skip_is_counted_in_run_backfill_summary(tmp_path):
    cdx_rows = [
        {"timestamp": "20130615120000", "original": wb.TARGET_URL, "digest": "d1", "statuscode": "200"},
    ]
    summary = wb.run_backfill(
        cdx_rows, cache_dir=tmp_path / "raw_cache", out_path=tmp_path / "obs.jsonl"
    )
    assert summary["era_skipped"] == 1
    assert summary["parsed"] == 0
    assert summary["parse_failed"] == 0
    assert summary["failures"] == []


# --- reviewer hardening nit 1: a malformed CDX row is logged + counted, ------
# --- never aborts the run (the resumable cache would otherwise re-hit it
# --- forever) --------------------------------------------------------------

def test_malformed_cdx_row_is_skipped_and_counted_not_fatal(tmp_path):
    cdx_rows = [
        # not a 14-digit timestamp -> cdx_timestamp_to_datetime raises
        # ValueError inside is_pre_era/process_capture.
        {"timestamp": "not-a-timestamp", "original": wb.TARGET_URL, "digest": "bad", "statuscode": "200"},
        {"timestamp": "20130615120000", "original": wb.TARGET_URL, "digest": "pre", "statuscode": "200"},
    ]
    summary = wb.run_backfill(
        cdx_rows, cache_dir=tmp_path / "raw_cache", out_path=tmp_path / "obs.jsonl"
    )
    # the run completed (did not raise) and accounted for both rows
    assert summary["captures_total"] == 2
    assert summary["parse_failed"] == 1
    assert summary["era_skipped"] == 1
    assert len(summary["failures"]) == 1
    assert "not-a-timestamp" in summary["failures"][0]


def test_malformed_cdx_row_missing_required_key_is_skipped_and_counted(tmp_path):
    cdx_rows = [{"digest": "no-timestamp-key", "statuscode": "200"}]
    summary = wb.run_backfill(
        cdx_rows, cache_dir=tmp_path / "raw_cache", out_path=tmp_path / "obs.jsonl"
    )
    assert summary["captures_total"] == 1
    assert summary["parse_failed"] == 1
    assert "no-timestamp-key" in summary["failures"][0]


# --- reviewer hardening nit 2: a non-JSON CDX response (throttle/503/HTML) --
# --- produces a clean, diagnosable error instead of an opaque resp.json() ---
# --- traceback ---------------------------------------------------------------

class _FakeResponse:
    def __init__(self, status_code, text):
        self.status_code = status_code
        self.text = text

    def raise_for_status(self):
        pass

    def json(self):
        raise ValueError("Expecting value: line 1 column 1 (char 0)")


class _FakeSession:
    def __init__(self, response):
        self._response = response

    def get(self, *a, **k):
        return self._response


def test_query_cdx_non_json_response_raises_clean_cdx_error():
    fake_session = _FakeSession(_FakeResponse(503, "<html>Service Unavailable</html>" * 10))
    with pytest.raises(wb.CDXError) as excinfo:
        wb.query_cdx(session=fake_session)
    message = str(excinfo.value)
    assert "503" in message
    assert "<html>Service Unavailable</html>" in message  # first ~100 chars of body present


def test_main_exits_cleanly_on_non_json_cdx_response(tmp_path, monkeypatch):
    def fake_query_cdx(*a, **k):
        raise wb.CDXError("CDX API returned a non-JSON response (status 503): '<html>...'")

    monkeypatch.setattr(wb, "query_cdx", fake_query_cdx)
    rc = wb.main(["--out", str(tmp_path / "obs.jsonl"), "--cache-dir", str(tmp_path / "cache")])
    assert rc == 1
    assert not (tmp_path / "obs.jsonl").exists()


# --- AC2: pu_interval present and correct on every record -------------------

def test_pu_interval_formula():
    assert wb.pu_interval(6.1) == [6.05, 6.15]


def test_pu_interval_zero_percent_floors_at_zero():
    assert wb.pu_interval(0.0) == [0, 0.05]


def test_every_record_carries_pu_interval_matching_percent_unsold():
    html = _html("unclaimed_prizes_2026_current_era.html")
    records = wb.build_records_from_html(
        html,
        capture_ts="2026-07-06T05:00:00+00:00",
        capture_url="https://web.archive.org/web/20260706050000id_/x",
        retrieved_at="2026-07-13T00:00:00+00:00",
        content_hash="abc123",
    )
    for rec in records:
        expected = wb.pu_interval(rec["percent_unsold"])
        assert rec["pu_interval"] == expected
        assert rec["pu_interval"][0] >= 0


# --- obs_date is page truth, parsed from "as of", never the capture ts -----

def test_obs_date_is_page_truth_not_capture_timestamp():
    html = _html("unclaimed_prizes_2019_era.html")
    records = wb.build_records_from_html(
        html,
        capture_ts="2019-08-20T00:00:00+00:00",  # deliberately NOT June 5 2019
        capture_url="https://web.archive.org/web/20190820000000id_/x",
        retrieved_at="2026-07-13T00:00:00+00:00",
        content_hash="x",
    )
    assert all(r["obs_date"] == "2019-06-05" for r in records)
    assert all(r["capture_ts"] == "2019-08-20T00:00:00+00:00" for r in records)


def test_parse_obs_date_rejects_unrecognized_format():
    with pytest.raises(Exception):
        wb.parse_obs_date("not a real timestamp")


# --- parse failures inside the era are logged, never fatal ------------------

def test_in_era_parse_failure_is_logged_not_raised(tmp_path):
    cache_dir = tmp_path / "raw_cache"
    cache_dir.mkdir(parents=True)
    ts = "20160101000000"
    # No "as of" line and no tbstriped table -> ParseError inside parse().
    (cache_dir / f"{ts}.html").write_text("<html><body>nothing here</body></html>", encoding="utf-8")

    cdx_row = {"timestamp": ts, "original": wb.TARGET_URL, "digest": "d", "statuscode": "200"}
    status, records, detail = wb.process_capture(cdx_row, cache_dir=cache_dir)
    assert status == "parse_failed"
    assert records == []
    assert detail is not None
    assert "web.archive.org" in detail


def test_run_backfill_summary_accounts_for_every_capture(tmp_path):
    cache_dir = tmp_path / "raw_cache"
    cache_dir.mkdir(parents=True)
    ok_ts = "20170303050000"
    (cache_dir / f"{ok_ts}.html").write_text(
        _html("unclaimed_prizes_2017_era.html"), encoding="utf-8"
    )
    bad_ts = "20160101000000"
    (cache_dir / f"{bad_ts}.html").write_text("<html>no table</html>", encoding="utf-8")

    cdx_rows = [
        {"timestamp": "20130615120000", "original": wb.TARGET_URL, "digest": "pre", "statuscode": "200"},
        {"timestamp": ok_ts, "original": wb.TARGET_URL, "digest": "ok", "statuscode": "200"},
        {"timestamp": bad_ts, "original": wb.TARGET_URL, "digest": "bad", "statuscode": "200"},
    ]
    out_path = tmp_path / "wayback_observations.jsonl"
    summary = wb.run_backfill(
        cdx_rows, cache_dir=cache_dir, out_path=out_path,
        now=_dt.datetime(2026, 7, 13, tzinfo=_dt.timezone.utc),
    )
    assert summary["captures_total"] == 3
    assert summary["era_skipped"] == 1
    assert summary["parsed"] == 1
    assert summary["parse_failed"] == 1
    assert len(summary["failures"]) == 1
    assert out_path.exists()

    lines = out_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) >= 1
    for line in lines:
        rec = json.loads(line)
        validate(instance=rec, schema=_schema())


# --- resumability: a cache hit never touches the network --------------------

def test_cache_hit_never_touches_network(tmp_path):
    cache_dir = tmp_path / "raw_cache"
    cache_dir.mkdir(parents=True)
    ts = "20260706050000"
    (cache_dir / f"{ts}.html").write_text(
        _html("unclaimed_prizes_2026_current_era.html"), encoding="utf-8"
    )
    # No `session` is provided; if this ever fell through to a real network
    # fetch, the autouse socket guard (tests/scraper/conftest.py) would raise.
    html = wb.fetch_capture_html(ts, wb.TARGET_URL, cache_dir=cache_dir, delay_s=0)
    assert "DOUBLE YOUR DOLLARS" in html


# --- LF-only output ----------------------------------------------------------

def test_run_backfill_output_is_lf_only(tmp_path):
    cache_dir = tmp_path / "raw_cache"
    cache_dir.mkdir(parents=True)
    ts = "20170303050000"
    (cache_dir / f"{ts}.html").write_text(_html("unclaimed_prizes_2017_era.html"), encoding="utf-8")
    out_path = tmp_path / "obs.jsonl"
    wb.run_backfill(
        [{"timestamp": ts, "original": wb.TARGET_URL, "digest": "d", "statuscode": "200"}],
        cache_dir=cache_dir,
        out_path=out_path,
        now=_dt.datetime(2026, 7, 13, tzinfo=_dt.timezone.utc),
    )
    raw = out_path.read_bytes()
    assert b"\r" not in raw


# --- game_key --------------------------------------------------------------

def test_game_key_shape():
    assert wb.game_key(706, "DOUBLE YOUR DOLLARS") == "706:double-your-dollars"


def test_game_key_differs_across_eras_for_reused_game_no():
    old = wb.game_key(399, "WILD 8`S")
    new = wb.game_key(399, "SOMETHING ELSE ENTIRELY")
    assert old != new


# --- design rule 3a / 4: one-time manual CLI, never wired into daily.yml ----

def test_never_imported_by_run_daily_source():
    src = (REPO_ROOT / "scraper" / "run_daily.py").read_text(encoding="utf-8")
    assert "wayback_backfill" not in src


def test_not_imported_by_any_other_scraper_module():
    """No module under scraper/ (other than wayback_backfill.py itself)
    actually IMPORTS it. (Design rule 3a/4 — a docstring cross-reference,
    e.g. in build_panel.py's module docstring, is fine; an import is not.)"""
    scraper_dir = REPO_ROOT / "scraper"
    for path in scraper_dir.glob("*.py"):
        if path.name == "wayback_backfill.py":
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for lineno, line in enumerate(lines, start=1):
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")):
                assert "wayback_backfill" not in stripped, (
                    f"{path}:{lineno}: imports wayback_backfill"
                )


def test_daily_yml_never_references_wayback_backfill():
    assert DAILY_YML_PATH.exists()
    src = DAILY_YML_PATH.read_text(encoding="utf-8")
    assert "wayback_backfill" not in src
    assert "build_panel" not in src


# --- design rule 5: runtime purity ------------------------------------------

def test_requirements_txt_byte_unchanged():
    req_path = REPO_ROOT / "requirements.txt"
    assert req_path.read_bytes() == b"requests\nbeautifulsoup4\njsonschema\n"


# --- no-network guard sanity (mirrors tests/scraper/conftest.py's pattern) --

def test_socket_connect_is_blocked_by_the_guard():
    import socket

    with pytest.raises(AssertionError):
        socket.socket().connect(("example.com", 80))


# ============================================================================
# M6a noncash addendum (docs/specs/m6a_noncash_addendum.md): tolerant record
# shape, has_noncash_prize, parser_version bump, schema validation.
# ============================================================================

VEHICLE_FIXTURE_HTML = "unclaimed_prizes_2015-01-01_vehicle_prize.html"


def test_parser_version_is_bumped_to_v2():
    assert wb.PARSER_VERSION == "scraper.scrape@2"


def test_build_records_from_html_calls_parse_in_tolerant_mode():
    # The real vehicle-prize capture would raise ParseError under the old
    # (non-tolerant) call; build_records_from_html must not raise.
    html = _html(VEHICLE_FIXTURE_HTML)
    records = wb.build_records_from_html(
        html,
        capture_ts="2015-01-01T19:31:27+00:00",
        capture_url="https://web.archive.org/web/20150101193127id_/x",
        retrieved_at="2026-07-13T00:00:00+00:00",
        content_hash="deadbeef",
    )
    assert records, "expected at least one parsed game record"


def test_vehicle_game_record_has_noncash_prize_true_and_schema_valid():
    html = _html(VEHICLE_FIXTURE_HTML)
    records = wb.build_records_from_html(
        html,
        capture_ts="2015-01-01T19:31:27+00:00",
        capture_url="https://web.archive.org/web/20150101193127id_/x",
        retrieved_at="2026-07-13T00:00:00+00:00",
        content_hash="deadbeef",
    )
    by_game_no = {r["game_no"]: r for r in records}
    vehicle_rec = by_game_no[229]
    assert vehicle_rec["has_noncash_prize"] is True
    vehicle_items = [tp for tp in vehicle_rec["top_prizes"] if tp["level"] is None]
    assert len(vehicle_items) == 1
    assert vehicle_items[0]["level_label"] == "CHEVROLET CAMARO 2SS"

    schema = _schema()
    for rec in records:
        validate(instance=rec, schema=schema)


def test_non_vehicle_records_have_has_noncash_prize_false():
    html = _html(VEHICLE_FIXTURE_HTML)
    records = wb.build_records_from_html(
        html,
        capture_ts="2015-01-01T19:31:27+00:00",
        capture_url="https://web.archive.org/web/20150101193127id_/x",
        retrieved_at="2026-07-13T00:00:00+00:00",
        content_hash="deadbeef",
    )
    non_vehicle = [r for r in records if r["game_no"] != 229]
    assert non_vehicle, "expected at least one non-vehicle game in the capture"
    assert all(r["has_noncash_prize"] is False for r in non_vehicle)
    assert all(r["has_noncash_prize"] is True for r in records if r["game_no"] == 229)


# --- schema: level:null requires level_label; has_noncash_prize required ----

def test_schema_rejects_null_level_item_without_level_label():
    schema = _schema()
    bad_record = {
        "game_no": 229,
        "game_key": "229:camaro",
        "obs_date": "2015-01-01",
        "capture_ts": "2015-01-01T19:31:27+00:00",
        "source": "wayback",
        "capture_url": "https://web.archive.org/web/x",
        "retrieved_at": "2026-07-13T00:00:00+00:00",
        "content_hash": "hash",
        "parser_version": wb.PARSER_VERSION,
        "percent_unsold": 7.5,
        "pu_interval": wb.pu_interval(7.5),
        "total_unclaimed": 524255.0,
        "top_prizes": [{"level": None, "remaining": 1}],  # missing level_label
        "price": 5.0,
        "name": "CAMARO",
        "lifecycle_status": None,
        "has_noncash_prize": True,
    }
    from jsonschema import ValidationError

    with pytest.raises(ValidationError):
        validate(instance=bad_record, schema=schema)


def test_schema_requires_has_noncash_prize_field():
    schema = _schema()
    record_without_flag = {
        "game_no": 706,
        "game_key": "706:double-your-dollars",
        "obs_date": "2026-01-01",
        "capture_ts": "2026-01-01T00:00:00+00:00",
        "source": "wayback",
        "capture_url": "https://web.archive.org/web/x",
        "retrieved_at": "2026-07-13T00:00:00+00:00",
        "content_hash": "hash",
        "parser_version": wb.PARSER_VERSION,
        "percent_unsold": 0.3,
        "pu_interval": wb.pu_interval(0.3),
        "total_unclaimed": 468555.0,
        "top_prizes": [{"level": 100000, "remaining": 1}],
        "price": 5.0,
        "name": "DOUBLE YOUR DOLLARS",
        "lifecycle_status": None,
        # has_noncash_prize deliberately omitted
    }
    from jsonschema import ValidationError

    with pytest.raises(ValidationError):
        validate(instance=record_without_flag, schema=schema)
