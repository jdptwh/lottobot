"""M1 test surface: parser, gate, latest-builder, schema, CLI, no-network guard.

See docs/specs/m1_scraper_spec.md for the acceptance criteria (numbered 1-10
in comments below) and maine-scratch-ev-spec.md §4/§6 for the contract.
"""
import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import ValidationError, validate

# `tests/` is copied wholesale into a fresh directory by the harness packaging
# self-test (tests/test_packaging.py, via scripts/harness.manifest.json's
# copy_dirs), which proves the *installable agent-system harness* is green in
# isolation. That manifest is a harness file this task may not touch, and it
# intentionally does not ship this project's own `scraper/`/`data/` — those
# are project code, not part of the reusable harness. So this module must
# degrade to a clean skip (not a collection error) inside that nested
# harness-only copy — but ONLY there: when scraper/ exists on disk (this repo),
# an import failure must fail loudly, never silently skip the M1 surface.
if not (Path(__file__).resolve().parents[2] / "scraper" / "scrape.py").exists():
    pytest.skip(
        "scraper/ is this project's own code, not part of the installable harness",
        allow_module_level=True,
    )
from scraper.scrape import GateError, ParseError, build_latest, parse, parser_gate

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "data" / "schema" / "latest.schema.json"
FIXTURE_PATH = REPO_ROOT / "tests" / "scraper" / "fixtures" / "unclaimed_prizes_2026-07-11.html"

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


def _find_game(snapshot: dict, game_no: int) -> dict:
    for g in snapshot["games"]:
        if g["game_no"] == game_no:
            return g
    raise AssertionError(f"game {game_no} not found in parsed snapshot")


# --- 1. >= 40 games (fixture holds 60+) -------------------------------------

def test_parse_yields_at_least_40_games(fixture_html):
    snapshot = parse(fixture_html)
    assert len(snapshot["games"]) >= 40


def test_fixture_actually_holds_60_plus_games(fixture_html):
    snapshot = parse(fixture_html)
    assert len(snapshot["games"]) >= 60


# --- 2. every parsed game has non-null required fields (gate 1) ------------

def test_every_game_has_required_non_null_fields(fixture_html):
    snapshot = parse(fixture_html)
    assert snapshot["games"], "expected at least one parsed game"
    for game in snapshot["games"]:
        for field in ("price", "game_no", "percent_unsold", "total_unclaimed"):
            assert game[field] is not None, f"game {game.get('game_no')} missing {field}"


# --- 3. sum(total_unclaimed) > $50M on the fixture (gate 1) -----------------

def test_total_unclaimed_sum_exceeds_50_million(fixture_html):
    snapshot = parse(fixture_html)
    total = sum(g["total_unclaimed"] for g in snapshot["games"])
    assert total > 50_000_000


def test_game_718_alone_is_58_5_million(fixture_html):
    snapshot = parse(fixture_html)
    g = _find_game(snapshot, 718)
    assert g["total_unclaimed"] == 58_543_650.0


# --- 4. spec §4 example cross-check: game 706 -------------------------------

def test_game_706_matches_spec_example(fixture_html):
    snapshot = parse(fixture_html)
    g = _find_game(snapshot, 706)
    assert g["price"] == 5.0
    assert g["percent_unsold"] == 0.3
    assert g["total_unclaimed"] == 468555.0
    assert g["top_prizes"] == [
        {"level": 100000, "remaining": 1},
        {"level": 10000, "remaining": 1},
        {"level": 1000, "remaining": 1},
    ]


# --- 5. edge cases -----------------------------------------------------------

def test_game_690_name_is_literal_dollar_sign(fixture_html):
    snapshot = parse(fixture_html)
    g = _find_game(snapshot, 690)
    assert g["name"] == "$"
    assert g["top_prizes"] == [{"level": 2000, "remaining": 1}]


def test_game_718_folds_to_exactly_seven_tiers(fixture_html):
    snapshot = parse(fixture_html)
    g = _find_game(snapshot, 718)
    assert len(g["top_prizes"]) == 7
    assert {"level": 1000000, "remaining": 4} in g["top_prizes"]
    assert {"level": 500, "remaining": 6325} in g["top_prizes"]


def test_names_with_dollar_signs_and_backticks_parse_intact(fixture_html):
    snapshot = parse(fixture_html)
    names = {g["game_no"]: g["name"] for g in snapshot["games"]}
    assert names[668] == "CA$H CRU$H"
    assert names[662] == "COUNT `EM UP"


# --- 6. source_timestamp + determinism --------------------------------------

def test_source_timestamp_matches_page(fixture_html):
    snapshot = parse(fixture_html)
    assert snapshot["source_timestamp"] == "July 10, 2026 5:00 AM"


def test_parse_is_deterministic(fixture_html):
    assert parse(fixture_html) == parse(fixture_html)


# --- 7. gate/parse failures --------------------------------------------------

def test_gate_rejects_truncated_table(fixture_html):
    snapshot = parse(fixture_html)
    truncated = {**snapshot, "games": snapshot["games"][:10]}
    with pytest.raises(GateError):
        parser_gate(truncated)


def test_gate_rejects_synthetic_below_floor_snapshot():
    synthetic = {
        "source_timestamp": "July 10, 2026 5:00 AM",
        "games": [
            {
                "game_no": i,
                "name": f"GAME {i}",
                "price": 1.0,
                "percent_unsold": 5.0,
                "total_unclaimed": 1000.0,
                "top_prizes": [{"level": 500, "remaining": 1}],
            }
            for i in range(50)
        ],
    }
    # 50 games (>= 40) but sum(total_unclaimed) == 50,000 << floor.
    with pytest.raises(GateError):
        parser_gate(synthetic)


def test_gate_rejects_missing_required_field(fixture_html):
    snapshot = parse(fixture_html)
    snapshot["games"][0]["price"] = None
    with pytest.raises(GateError):
        parser_gate(snapshot)


def test_orphan_continuation_row_raises_parse_error():
    html = MINIMAL_TABLE_HEAD + (
        "<tr><td>   </td><td>   </td><td>   </td><td>   </td><td>   </td>"
        "<td>$1000</td><td>5</td></tr></table>"
    )
    with pytest.raises(ParseError):
        parse(html)


def test_malformed_game_no_cell_raises_parse_error():
    html = MINIMAL_TABLE_HEAD + (
        "<tr><td>$1.00</td><td>NOT_A_NUMBER</td><td>BAD GAME</td><td>6.1</td>"
        "<td>$96,620.00</td><td>$1000</td><td>5</td></tr></table>"
    )
    with pytest.raises(ParseError):
        parse(html)


def test_malformed_money_cell_raises_parse_error():
    html = MINIMAL_TABLE_HEAD + (
        "<tr><td>$1.00</td><td>668</td><td>BAD GAME</td><td>6.1</td>"
        "<td>NOT_MONEY</td><td>$1000</td><td>5</td></tr></table>"
    )
    with pytest.raises(ParseError):
        parse(html)


def test_wrong_cell_count_raises_parse_error():
    html = MINIMAL_TABLE_HEAD + (
        "<tr><td>$1.00</td><td>668</td><td>CA$H CRU$H</td><td>6.1</td>"
        "<td>$96,620.00</td><td>$1000</td></tr></table>"
    )
    with pytest.raises(ParseError):
        parse(html)


def test_missing_table_raises_parse_error():
    html = "<p>as of July 10, 2026 5:00 AM</p>"
    with pytest.raises(ParseError):
        parse(html)


# --- 8. build_latest validates against the §4 schema ------------------------

def test_build_latest_validates_against_schema(fixture_html):
    snapshot = parse(fixture_html)
    latest = build_latest(snapshot, as_of="2026-07-11")
    validate(instance=latest, schema=_schema())


def test_build_latest_top_level_and_game_shape(fixture_html):
    snapshot = parse(fixture_html)
    latest = build_latest(snapshot, as_of="2026-07-11")
    assert latest["as_of"] == "2026-07-11"
    assert latest["source_timestamp"] == "July 10, 2026 5:00 AM"
    g = _find_game(latest, 706)
    for field in (
        "print_run", "remaining_tickets", "ev_per_ticket",
        "ev_ratio", "ev_ratio_adjusted",
    ):
        assert g[field] is None
    assert g["dead_game"] is False
    assert g["flags"] == []
    assert g["confidence"] == "low"


def test_spec_section4_example_validates_against_schema():
    example = {
        "as_of": "2026-07-10",
        "source_timestamp": "July 10, 2026 5:00 AM",
        "games": [
            {
                "game_no": 706,
                "name": "DOUBLE YOUR DOLLARS",
                "price": 5.00,
                "percent_unsold": 0.3,
                "total_unclaimed": 468555,
                "top_prizes": [
                    {"level": 100000, "remaining": 1},
                    {"level": 10000, "remaining": 1},
                ],
                "print_run": 1200000,
                "remaining_tickets": 3600,
                "ev_per_ticket": None,
                "ev_ratio": None,
                "ev_ratio_adjusted": None,
                "dead_game": False,
                "flags": ["low_inventory", "anomaly_candidate"],
                "confidence": "low",
            }
        ],
    }
    validate(instance=example, schema=_schema())


def test_schema_restricts_confidence_to_allowed_values():
    example = {
        "as_of": "2026-07-10",
        "source_timestamp": "July 10, 2026 5:00 AM",
        "games": [
            {
                "game_no": 706,
                "name": "X",
                "price": 5.0,
                "percent_unsold": 0.3,
                "total_unclaimed": 468555,
                "top_prizes": [],
                "print_run": None,
                "remaining_tickets": None,
                "ev_per_ticket": None,
                "ev_ratio": None,
                "ev_ratio_adjusted": None,
                "dead_game": False,
                "flags": [],
                "confidence": "medium-ish",
            }
        ],
    }
    with pytest.raises(ValidationError):
        validate(instance=example, schema=_schema())


def test_schema_permits_additional_properties(fixture_html):
    snapshot = parse(fixture_html)
    latest = build_latest(snapshot, as_of="2026-07-11")
    latest["future_top_level_field"] = "additive-only"
    latest["games"][0]["future_game_field"] = "additive-only"
    validate(instance=latest, schema=_schema())


# --- 9. no test touches the network; one live smoke test --------------------

def test_socket_connect_is_blocked_by_the_guard():
    with pytest.raises(AssertionError):
        socket.socket().connect(("example.com", 80))


def test_urlopen_is_blocked_by_the_guard():
    import urllib.request

    with pytest.raises(AssertionError):
        urllib.request.urlopen("http://example.com")


@pytest.mark.live
def test_live_page_parses_and_passes_gate():
    """Opt-in, real network call: excluded by default (`-m 'not live'`).

    Run manually at most once/day: `python -m pytest -q -m live tests/scraper`.
    """
    from scraper.scrape import fetch

    html = fetch()
    snapshot = parse(html)
    parser_gate(snapshot)


# --- CLI ---------------------------------------------------------------------

def test_cli_writes_valid_latest_json_from_fixture(tmp_path):
    out_path = tmp_path / "latest.json"
    result = subprocess.run(
        [
            sys.executable, "-m", "scraper.scrape",
            "--fixture", str(FIXTURE_PATH),
            "--out", str(out_path),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(out_path.read_text(encoding="utf-8"))
    validate(instance=data, schema=_schema())
    assert len(data["games"]) >= 40


def test_cli_stdout_when_no_out_given():
    result = subprocess.run(
        [sys.executable, "-m", "scraper.scrape", "--fixture", str(FIXTURE_PATH)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    validate(instance=data, schema=_schema())


def test_cli_gate_failure_is_nonzero_exit_and_writes_nothing(tmp_path):
    # A well-formed but truncated table: passes parse(), fails parser_gate()
    # (< 40 games), so the CLI must exit nonzero and must not write --out.
    truncated_html = MINIMAL_TABLE_HEAD + (
        "<tr><td>$1.00</td><td>668</td><td>CA$H CRU$H</td><td>6.1</td>"
        "<td>$96,620.00</td><td>$1000</td><td>5</td></tr></table>"
    )
    truncated_path = tmp_path / "truncated.html"
    truncated_path.write_text(truncated_html, encoding="utf-8")
    out_path = tmp_path / "latest.json"

    result = subprocess.run(
        [
            sys.executable, "-m", "scraper.scrape",
            "--fixture", str(truncated_path),
            "--out", str(out_path),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert not out_path.exists()


def test_cli_parse_failure_is_nonzero_exit_and_writes_nothing(tmp_path):
    bad_path = tmp_path / "bad.html"
    bad_path.write_text("<p>as of July 10, 2026 5:00 AM</p>", encoding="utf-8")
    out_path = tmp_path / "latest.json"

    result = subprocess.run(
        [
            sys.executable, "-m", "scraper.scrape",
            "--fixture", str(bad_path),
            "--out", str(out_path),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert not out_path.exists()


# ============================================================================
# M6a noncash addendum (docs/specs/m6a_noncash_addendum.md): prize_level_tolerant
# opt-in on parse(). NEW tests only, zero edits above this marker.
# ============================================================================

VEHICLE_FIXTURE_PATH = (
    REPO_ROOT / "tests" / "scraper" / "fixtures" / "wayback"
    / "unclaimed_prizes_2015-01-01_vehicle_prize.html"
)


def _vehicle_fixture_html() -> str:
    return VEHICLE_FIXTURE_PATH.read_text(encoding="utf-8")


# --- AC1: production invariance — default mode still raises the existing ---
# --- ParseError message on the real vehicle-prize capture -------------------

def test_default_mode_still_raises_on_vehicle_fixture():
    with pytest.raises(ParseError, match=r"malformed prize-level cell"):
        parse(_vehicle_fixture_html())


def test_default_mode_error_message_names_the_vehicle_cell():
    with pytest.raises(ParseError) as excinfo:
        parse(_vehicle_fixture_html())
    assert "CHEVROLET CAMARO 2SS" in str(excinfo.value)


# --- AC2: tolerant equivalence — on an all-cash fixture, tolerant and -------
# --- default output are structurally equal -----------------------------------

def test_tolerant_mode_equals_default_mode_on_an_all_cash_fixture(fixture_html):
    default_snapshot = parse(fixture_html)
    tolerant_snapshot = parse(fixture_html, prize_level_tolerant=True)
    assert default_snapshot == tolerant_snapshot


def test_tolerant_mode_default_is_false():
    # prize_level_tolerant is keyword-only and defaults to False: calling
    # parse(html) unchanged must be identical to parse(html, prize_level_tolerant=False).
    html = _vehicle_fixture_html()
    with pytest.raises(ParseError):
        parse(html)
    with pytest.raises(ParseError):
        parse(html, prize_level_tolerant=False)


# --- AC3: tolerant parse of the vehicle fixture -----------------------------

def test_tolerant_mode_parses_the_vehicle_game_with_null_level_and_label():
    snapshot = parse(_vehicle_fixture_html(), prize_level_tolerant=True)
    g = _find_game(snapshot, 229)
    assert g["name"] == "CAMARO"
    vehicle_items = [tp for tp in g["top_prizes"] if tp["level"] is None]
    assert len(vehicle_items) == 1
    vehicle_item = vehicle_items[0]
    assert vehicle_item["level_label"] == "CHEVROLET CAMARO 2SS"
    assert isinstance(vehicle_item["remaining"], int)
    assert vehicle_item["remaining"] == 1


def test_tolerant_mode_other_games_in_the_capture_are_unaffected():
    snapshot = parse(_vehicle_fixture_html(), prize_level_tolerant=True)
    assert len(snapshot["games"]) >= 60  # the real capture holds ~65 games
    # every OTHER game's top_prizes items are all-cash: plain int levels,
    # no level_label key at all (structurally identical to the non-tolerant shape).
    for g in snapshot["games"]:
        if g["game_no"] == 229:
            continue
        for tp in g["top_prizes"]:
            assert isinstance(tp["level"], int)
            assert "level_label" not in tp


def test_tolerant_mode_cash_items_never_carry_a_level_label_key():
    snapshot = parse(_vehicle_fixture_html(), prize_level_tolerant=True)
    g = _find_game(snapshot, 229)
    cash_items = [tp for tp in g["top_prizes"] if tp["level"] is not None]
    assert cash_items  # game 229 has other, cash, prize tiers too
    for tp in cash_items:
        assert "level_label" not in tp


# --- continuation-row call site: parse threads prize_level_tolerant there ---
# --- too (design rule 1), via a synthetic minimal snippet -------------------

def test_tolerant_mode_handles_a_non_numeric_continuation_row_cell():
    html = MINIMAL_TABLE_HEAD + (
        "<tr><td>$5.00</td><td>900</td><td>SYNTHETIC VEHICLE GAME</td><td>10.0</td>"
        "<td>$50,000.00</td><td>$1000</td><td>2</td></tr>"
        "<tr><td>           </td><td>        </td><td>         </td>"
        "<td>              </td><td>               </td>"
        "<td>TOYOTA TACOMA</td><td>1</td></tr></table>"
    )
    snapshot = parse(html, prize_level_tolerant=True)
    g = _find_game(snapshot, 900)
    assert g["top_prizes"] == [
        {"level": 1000, "remaining": 2},
        {"level": None, "level_label": "TOYOTA TACOMA", "remaining": 1},
    ]
    with pytest.raises(ParseError, match=r"malformed prize-level cell"):
        parse(html)
