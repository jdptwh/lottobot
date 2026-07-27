"""Fast Play extension test surface: parse/gate/compute/copy-bank/purity/
constants-parity + a hand-check worksheet (test_grading.py style).

See docs/specs/fastplay_extension_spec.md for the acceptance criteria
(numbered 1-14 in comments below, matching the spec's own numbering; AC-9
through AC-14 that are workflow/site/isolation surfaces are covered
elsewhere or not applicable to CP1-CP3). Runs under the autouse socket
guard in tests/scraper/conftest.py (same package, same fixture — AC-11).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import ValidationError, validate

# Same harness-packaging-copy skip guard as test_scrape.py/test_compute.py:
# scraper/ is this project's own code, not part of the installable harness.
if not (Path(__file__).resolve().parents[2] / "scraper" / "fastplay.py").exists():
    pytest.skip(
        "scraper/ is this project's own code, not part of the installable harness",
        allow_module_level=True,
    )

import scraper.fastplay as fastplay
from scraper.compute import (
    DEGENERATE_SCORE as COMPUTE_DEGENERATE_SCORE,
    GRADE_BANDS as COMPUTE_GRADE_BANDS,
    GRADE_DEFAULT as COMPUTE_GRADE_DEFAULT,
    SCORE_CURVE_FLOOR as COMPUTE_SCORE_CURVE_FLOOR,
    SCORE_CURVE_SPAN as COMPUTE_SCORE_CURVE_SPAN,
    SCORE_EV_RATIO_CLAMP as COMPUTE_SCORE_EV_RATIO_CLAMP,
    SCORE_WEIGHT as COMPUTE_SCORE_WEIGHT,
)
from scraper.fastplay import (
    DEGENERATE_SCORE,
    FASTPLAY_REASONS,
    GRADE_BANDS,
    GRADE_DEFAULT,
    MIN_GAMES_FASTPLAY,
    MIN_TOTAL_UNCLAIMED_FASTPLAY,
    SCORE_CURVE_FLOOR,
    SCORE_CURVE_SPAN,
    SCORE_EV_RATIO_CLAMP,
    SCORE_WEIGHT,
    GateError,
    ParseError,
    _apply_scoring,
    compute_fastplay,
    parse,
    parser_gate,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "data" / "schema" / "fastplay.schema.json"
GAMES_PATH = REPO_ROOT / "data" / "fastplay_games.json"
FIXTURE_PATH = (
    REPO_ROOT / "tests" / "scraper" / "fixtures" / "unclaimed_fastplay_2026-07-27.html"
)
# AC-14 / m5a rule: the exact regression pin targets a FROZEN copy under
# tests/, never data/fastplay.json's live path (the daily bot rewrites that
# once CP6 wires the workflow).
FROZEN_ARTIFACT_PATH = (
    REPO_ROOT / "tests" / "scraper" / "fixtures" / "fastplay_2026-07-27.json"
)
AS_OF = "2026-07-27"

MINIMAL_TABLE_HEAD = """
<p>Below is the list of unsold top prizes for current Fast Play games
as of July 27, 2026 5:00 AM
</p>
<table class="tbstriped">
<tr><th>Price Point</th><th>Game No.</th><th>Game Name</th><th>Percent Unsold</th>
<th>Total Unsold</th><th>Top Prize Level(s)</th><th>Top Prize(s) Unsold</th></tr>
"""


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _games_meta() -> dict:
    return json.loads(GAMES_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def fastplay_fixture_html() -> str:
    return FIXTURE_PATH.read_text(encoding="utf-8")


def _doc(html: str, games_meta: dict | None = None) -> dict:
    snapshot = parse(html)
    return compute_fastplay(snapshot, games_meta or _games_meta(), AS_OF)


def _find_game(doc: dict, game_no: int) -> dict:
    for g in doc["games"]:
        if g["game_no"] == game_no:
            return g
    raise AssertionError(f"game {game_no} not found in computed doc")


# ============================================================================
# AC-1: parse()
# ============================================================================

def test_parse_yields_at_least_20_games_in_page_order(fastplay_fixture_html):
    snapshot = parse(fastplay_fixture_html)
    assert len(snapshot["games"]) >= MIN_GAMES_FASTPLAY


def test_fixture_actually_holds_28_games(fastplay_fixture_html):
    snapshot = parse(fastplay_fixture_html)
    assert len(snapshot["games"]) == 28
    game_nos = [g["game_no"] for g in snapshot["games"]]
    assert game_nos[0] == 25  # page order preserved (first row of the table)


def test_every_game_has_required_non_null_fields_and_a_top_prize(fastplay_fixture_html):
    snapshot = parse(fastplay_fixture_html)
    assert snapshot["games"]
    for game in snapshot["games"]:
        for field in ("game_no", "name", "price", "percent_unsold", "total_unclaimed"):
            assert game[field] is not None, f"game {game.get('game_no')} missing {field}"
        assert len(game["top_prizes"]) >= 1


def test_source_timestamp_matches_page(fastplay_fixture_html):
    snapshot = parse(fastplay_fixture_html)
    assert snapshot["source_timestamp"] == "July 27, 2026 5:00 AM"


def test_parse_is_deterministic(fastplay_fixture_html):
    assert parse(fastplay_fixture_html) == parse(fastplay_fixture_html)


# --- D9: progressive rows yield level:null + level_label without raising ---

def test_progressive_row_yields_null_level_and_label(fastplay_fixture_html):
    snapshot = parse(fastplay_fixture_html)
    g = _find_game(snapshot, 25)
    assert g["name"] == "BLACKJACK PROGRESSIVE"
    assert g["top_prizes"] == [
        {"level": None, "level_label": "JACKPOT", "remaining": 3}
    ]


def test_multi_tier_progressive_game_keeps_cash_continuation_tiers(fastplay_fixture_html):
    # Game 26: CA$H BLAST PROGRESSIVE — jackpot row + two cash continuation
    # tiers, proving the tolerant jackpot cell never disturbs sibling tiers.
    snapshot = parse(fastplay_fixture_html)
    g = _find_game(snapshot, 26)
    assert g["top_prizes"] == [
        {"level": None, "level_label": "JACKPOT", "remaining": 2},
        {"level": 1000, "remaining": 6},
        {"level": 500, "remaining": 19},
    ]


# --- D9 fixture cross-check: every name-contains-PROGRESSIVE game DID get ---
# --- flagged (structurally, never by name) — a mismatch would be a finding --

PROGRESSIVE_NAME_GAME_NOS = {25, 26, 22, 27, 36, 48, 28, 30, 38, 31, 58, 40}


def test_every_progressive_named_game_has_a_null_level_top_prize(fastplay_fixture_html):
    snapshot = parse(fastplay_fixture_html)
    for g in snapshot["games"]:
        has_progress_in_name = "PROGRESS" in g["name"]  # covers the truncated
        # "MAINE CA$H MULTIPLIER PROGRESS" (games 30/31) as well as the
        # untruncated "...PROGRESSIVE" names.
        has_null_level = any(tp["level"] is None for tp in g["top_prizes"])
        assert has_progress_in_name == has_null_level, (
            f"game {g['game_no']} ({g['name']!r}): name-vs-flag mismatch — "
            "cross-check finding, do not silently patch"
        )
    progressive_game_nos = {
        g["game_no"] for g in snapshot["games"]
        if any(tp["level"] is None for tp in g["top_prizes"])
    }
    assert progressive_game_nos == PROGRESSIVE_NAME_GAME_NOS


# --- continuation rows / orphan / malformed cells ----------------------------

def test_continuation_row_attaches_to_preceding_game(fastplay_fixture_html):
    snapshot = parse(fastplay_fixture_html)
    g = _find_game(snapshot, 45)  # FARMERS MARKET: jackpot row + 1 continuation
    assert g["top_prizes"] == [
        {"level": 15000, "remaining": 1},
        {"level": 500, "remaining": 97},
    ]


def test_orphan_continuation_row_raises_parse_error():
    html = MINIMAL_TABLE_HEAD + (
        "<tr><td>   </td><td>   </td><td>   </td><td>   </td><td>   </td>"
        "<td>$1000</td><td>5</td></tr></table>"
    )
    with pytest.raises(ParseError):
        parse(html)


def test_malformed_game_no_cell_raises_parse_error():
    html = MINIMAL_TABLE_HEAD + (
        "<tr><td>$2.00</td><td>NOT_A_NUMBER</td><td>BAD GAME</td><td>6.1</td>"
        "<td>$96,620.00</td><td>$1000</td><td>5</td></tr></table>"
    )
    with pytest.raises(ParseError):
        parse(html)


def test_malformed_money_cell_raises_parse_error():
    html = MINIMAL_TABLE_HEAD + (
        "<tr><td>$2.00</td><td>25</td><td>BAD GAME</td><td>6.1</td>"
        "<td>NOT_MONEY</td><td>$1000</td><td>5</td></tr></table>"
    )
    with pytest.raises(ParseError):
        parse(html)


def test_wrong_cell_count_raises_parse_error():
    html = MINIMAL_TABLE_HEAD + (
        "<tr><td>$2.00</td><td>25</td><td>BAD GAME</td><td>6.1</td>"
        "<td>$96,620.00</td><td>$1000</td></tr></table>"
    )
    with pytest.raises(ParseError):
        parse(html)


def test_missing_table_raises_parse_error():
    html = "<p>as of July 27, 2026 5:00 AM</p>"
    with pytest.raises(ParseError):
        parse(html)


# ============================================================================
# AC-2 / D3: parser_gate() floors
# ============================================================================

def test_gate_rejects_below_20_game_snapshot():
    synthetic = {
        "source_timestamp": "July 27, 2026 5:00 AM",
        "games": [
            {
                "game_no": i,
                "name": f"GAME {i}",
                "price": 2.0,
                "percent_unsold": 50.0,
                "total_unclaimed": 10_000_000.0,
                "top_prizes": [{"level": 500, "remaining": 1}],
            }
            for i in range(10)
        ],
    }
    with pytest.raises(GateError, match=r"only 10 games"):
        parser_gate(synthetic)


def test_gate_rejects_missing_required_field(fastplay_fixture_html):
    snapshot = parse(fastplay_fixture_html)
    snapshot["games"][0]["price"] = None
    with pytest.raises(GateError, match=r"missing required field 'price'"):
        parser_gate(snapshot)


def test_gate_rejects_synthetic_below_floor_total_unclaimed():
    synthetic = {
        "source_timestamp": "July 27, 2026 5:00 AM",
        "games": [
            {
                "game_no": i,
                "name": f"GAME {i}",
                "price": 2.0,
                "percent_unsold": 50.0,
                "total_unclaimed": 1000.0,
                "top_prizes": [{"level": 500, "remaining": 1}],
            }
            for i in range(25)
        ],
    }
    # 25 games (>= 20) but sum(total_unclaimed) == 25,000 << floor.
    with pytest.raises(GateError, match=r"sanity floor"):
        parser_gate(synthetic)


def test_gate_accepts_the_real_fixture(fastplay_fixture_html):
    snapshot = parse(fastplay_fixture_html)
    parser_gate(snapshot)  # must not raise


# --- D3 constant derivation, pinned by test (spec's own binding rule) -------

def test_min_total_unclaimed_fastplay_matches_the_d3_formula(fastplay_fixture_html):
    snapshot = parse(fastplay_fixture_html)
    total = sum(g["total_unclaimed"] for g in snapshot["games"])
    assert total == 107_852_508.0

    quarter = 0.25 * total
    # round DOWN to one significant figure: floor to the leading digit at
    # the magnitude's own place value (10 ** floor(log10(quarter))).
    import math

    magnitude = 10 ** math.floor(math.log10(quarter))
    floored = math.floor(quarter / magnitude) * magnitude
    assert floored == 20_000_000
    assert MIN_TOTAL_UNCLAIMED_FASTPLAY == floored


def test_min_games_fastplay_is_20():
    assert MIN_GAMES_FASTPLAY == 20


# ============================================================================
# AC-3 / D2 / D9: progressive handling
# ============================================================================

def test_every_progressive_game_is_forced_non_rateable_with_exact_reason(
    fastplay_fixture_html,
):
    doc = _doc(fastplay_fixture_html)
    progressive_games = [
        g for g in doc["games"] if "progressive_jackpot" in g["flags"]
    ]
    assert {g["game_no"] for g in progressive_games} == PROGRESSIVE_NAME_GAME_NOS
    for g in progressive_games:
        assert g["ev_ratio"] is None
        assert g["ev_per_ticket"] is None
        assert g["rated"] is False
        assert g["value_score"] is None
        assert g["grade"] is None
        assert g["reason"] == FASTPLAY_REASONS["progressive_jackpot"]
        # still published (D2): raw arithmetic on published fields.
        assert g["percent_unsold"] is not None
        assert g["total_unclaimed"] is not None
        assert g["relative_score"] is not None


def test_progressive_guard_is_unconditional_even_with_synthetic_print_run(
    fastplay_fixture_html,
):
    # D2: "ev_ratio is forced null for them in code (guard, not just data)".
    # Prove the guard survives even a synthetic games_meta that supplies a
    # print_run for a progressive game — it must NOT light up EV.
    games_meta = {"games": {"25": {"print_run": 1_000_000, "top_prize_value": None}}}
    doc = _doc(fastplay_fixture_html, games_meta=games_meta)
    g = _find_game(doc, 25)
    assert g["print_run"] == 1_000_000
    assert g["remaining_tickets"] is not None  # inventory math is unguarded
    assert g["ev_per_ticket"] is None
    assert g["ev_ratio"] is None
    assert g["rated"] is False
    assert g["reason"] == FASTPLAY_REASONS["progressive_jackpot"]


# ============================================================================
# AC-4 / D1: v1 dormancy + full scoring path proof (synthetic)
# ============================================================================

def test_v1_dormancy_every_game_is_null_and_unrated(fastplay_fixture_html):
    doc = _doc(fastplay_fixture_html)  # committed empty fastplay_games.json
    assert len(doc["games"]) == 28
    for g in doc["games"]:
        assert g["print_run"] is None
        assert g["ev_ratio"] is None
        assert g["ev_per_ticket"] is None
        assert g["value_score"] is None
        assert g["grade"] is None
        assert g["rated"] is False
        assert g["reason"] in FASTPLAY_REASONS.values()
        if g["percent_unsold"] > 0:
            assert g["relative_score"] is not None
        else:
            assert g["relative_score"] is None


def test_v1_dormancy_reasons_follow_the_pinned_precedence(fastplay_fixture_html):
    doc = _doc(fastplay_fixture_html)
    for g in doc["games"]:
        if "progressive_jackpot" in g["flags"]:
            assert g["reason"] == FASTPLAY_REASONS["progressive_jackpot"]
        elif g["dead_game"]:
            assert g["reason"] == FASTPLAY_REASONS["dead"]
        elif "sold_out" in g["flags"]:
            assert g["reason"] == FASTPLAY_REASONS["sold_out"]
        elif g["print_run"] is None:
            assert g["reason"] == FASTPLAY_REASONS["no_print_run"]
        else:
            assert g["reason"] == FASTPLAY_REASONS["no_data"]


def test_synthetic_metadata_lights_up_the_full_scoring_path():
    # AC-4's second requirement: a follow-on task should light up EV/grades
    # with ZERO code change — prove the machinery (flags, confidence, curve,
    # degenerate case, grade bands) already works given non-null print_run.
    games_meta = {
        "games": {
            "25": {"print_run": None, "top_prize_value": None},  # stays progressive-guarded
            "56": {"print_run": 2_000_000, "top_prize_value": 500},
            "74": {"print_run": 2_000_000, "top_prize_value": 500},
        }
    }
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    doc = _doc(html, games_meta=games_meta)

    g56 = _find_game(doc, 56)
    g74 = _find_game(doc, 74)

    # Both now have print_run -> remaining_tickets/ev math flows.
    assert g56["remaining_tickets"] == round(5.1 * 2_000_000 / 100)
    assert g74["remaining_tickets"] == round(74.6 * 2_000_000 / 100)
    for g in (g56, g74):
        assert g["ev_ratio"] is not None
        assert g["rated"] is True
        assert isinstance(g["value_score"], int)
        assert g["grade"] in dict(GRADE_BANDS).values() or g["grade"] == GRADE_DEFAULT

    # Game 25 stays non-rateable (progressive) even in this synthetic run.
    g25 = _find_game(doc, 25)
    assert g25["rated"] is False
    assert g25["reason"] == FASTPLAY_REASONS["progressive_jackpot"]


def test_degenerate_curve_single_rateable_game():
    games = [
        {
            "game_no": 1,
            "name": "SYNTHETIC",
            "price": 5.0,
            "percent_unsold": 20.0,
            "total_unclaimed": 1000.0,
            "top_prizes": [],
            "print_run": 100000,
            "remaining_tickets": 20000,
            "ev_per_ticket": 1.0,
            "ev_ratio": 0.9,
            "ev_ratio_adjusted": None,
            "relative_score": 50.0,
            "dead_game": False,
            "flags": [],
            "confidence": "high",
        }
    ]
    _apply_scoring(games)
    g = games[0]
    assert g["value_score"] == DEGENERATE_SCORE == 68
    assert g["grade"] == "B"
    assert g["rated"] is True


# ============================================================================
# AC-5: schema
# ============================================================================

def test_computed_doc_validates_against_the_fastplay_schema(fastplay_fixture_html):
    doc = _doc(fastplay_fixture_html)
    validate(instance=doc, schema=_schema())


def test_schema_rejects_null_level_top_prize_without_level_label():
    example = {
        "as_of": "2026-07-27",
        "source_timestamp": "July 27, 2026 5:00 AM",
        "games": [
            {
                "game_no": 25,
                "name": "X",
                "price": 2.0,
                "percent_unsold": 22.0,
                "total_unclaimed": 632412.0,
                "top_prizes": [{"level": None, "remaining": 3}],
                "print_run": None,
                "remaining_tickets": None,
                "ev_per_ticket": None,
                "ev_ratio": None,
                "ev_ratio_adjusted": None,
                "relative_score": 28746.0,
                "dead_game": False,
                "flags": ["progressive_jackpot"],
                "confidence": "low",
                "value_score": None,
                "grade": None,
                "rated": False,
                "reason": FASTPLAY_REASONS["progressive_jackpot"],
            }
        ],
    }
    with pytest.raises(ValidationError):
        validate(instance=example, schema=_schema())


# ============================================================================
# AC-6 / D8: constants parity
# ============================================================================

def test_scoring_constants_match_scraper_compute_exactly():
    assert SCORE_WEIGHT == COMPUTE_SCORE_WEIGHT
    assert SCORE_EV_RATIO_CLAMP == COMPUTE_SCORE_EV_RATIO_CLAMP
    assert SCORE_CURVE_FLOOR == COMPUTE_SCORE_CURVE_FLOOR
    assert SCORE_CURVE_SPAN == COMPUTE_SCORE_CURVE_SPAN
    assert DEGENERATE_SCORE == COMPUTE_DEGENERATE_SCORE
    assert GRADE_BANDS == COMPUTE_GRADE_BANDS
    assert GRADE_DEFAULT == COMPUTE_GRADE_DEFAULT


# ============================================================================
# AC-7 / D8: copy bank byte-for-byte
# ============================================================================

def test_fastplay_reasons_matches_spec_byte_for_byte():
    assert FASTPLAY_REASONS == {
        "progressive_jackpot": (
            "Jackpot value isn't published on the state's Fast Play page — "
            "expected value can't be computed for this progressive game."
        ),
        "dead": (
            "Top prize already claimed — the biggest advertised win can no "
            "longer be won."
        ),
        "sold_out": (
            "Reported 0% unsold — effectively sold out; there is nothing left "
            "to buy."
        ),
        "no_print_run": (
            "Total ticket quantity unknown for this Fast Play game — expected "
            "value can't be computed; ranked by the relative unclaimed-money "
            "signal only."
        ),
        "no_data": "Not enough data to compute an expected value for this game.",
    }


# ============================================================================
# AC-8 / D6: CLI orchestration failure semantics
# ============================================================================

def _run_cli(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "scraper.fastplay", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_cli_fixture_happy_path_writes_valid_schema_conformant_doc(tmp_path):
    out_path = tmp_path / "fastplay.json"
    history_dir = tmp_path / "fastplay_history"

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
    history_path = history_dir / f"{AS_OF}.json"
    assert history_path.read_bytes() == out_path.read_bytes()
    assert out_path.read_bytes().endswith(b"}")  # no trailing CR/CRLF artifact
    assert b"\r\n" not in out_path.read_bytes()


def test_cli_regeneration_is_byte_identical_to_the_committed_artifact(tmp_path):
    out_path = tmp_path / "fastplay.json"
    history_dir = tmp_path / "fastplay_history"

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


def test_cli_parser_gate_failure_writes_nothing_and_leaves_mtime_unchanged(tmp_path):
    truncated_html = MINIMAL_TABLE_HEAD + (
        "<tr><td>$2.00</td><td>25</td><td>BLACKJACK PROGRESSIVE</td><td>22.0</td>"
        "<td>$632,412.00</td><td>JACKPOT</td><td>3</td></tr></table>"
    )
    truncated_path = tmp_path / "truncated.html"
    truncated_path.write_text(truncated_html, encoding="utf-8")

    out_path = tmp_path / "fastplay.json"
    history_dir = tmp_path / "fastplay_history"
    # Pre-seed --out so we can assert its mtime/bytes survive the failed run.
    out_path.write_text('{"pre-existing": true}', encoding="utf-8")
    pre_mtime = out_path.stat().st_mtime
    pre_bytes = out_path.read_bytes()

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
    assert out_path.stat().st_mtime == pre_mtime
    assert out_path.read_bytes() == pre_bytes
    assert not history_dir.exists()


def test_cli_parse_failure_is_nonzero_exit_and_writes_nothing(tmp_path):
    bad_path = tmp_path / "bad.html"
    bad_path.write_text("<p>as of July 27, 2026 5:00 AM</p>", encoding="utf-8")
    out_path = tmp_path / "fastplay.json"
    history_dir = tmp_path / "fastplay_history"

    result = _run_cli(
        [
            "--fixture", str(bad_path),
            "--games", str(GAMES_PATH),
            "--as-of", AS_OF,
            "--out", str(out_path),
            "--history-dir", str(history_dir),
        ]
    )

    assert result.returncode != 0
    assert not out_path.exists()
    assert not history_dir.exists()


def test_cli_schema_gate_failure_writes_nothing(tmp_path):
    bad_schema = {
        "type": "object",
        "required": ["as_of"],
        "properties": {"as_of": {"type": "integer"}},
    }
    schema_path = tmp_path / "bad_schema.json"
    schema_path.write_text(json.dumps(bad_schema), encoding="utf-8")
    out_path = tmp_path / "fastplay.json"
    history_dir = tmp_path / "fastplay_history"

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


def test_as_of_defaults_to_utc_today(tmp_path):
    from datetime import datetime, timezone

    out_path = tmp_path / "fastplay.json"
    history_dir = tmp_path / "fastplay_history"

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


# ============================================================================
# AC-11: politeness — exactly one request per --live run
# ============================================================================

def test_live_calls_fetch_exactly_once(tmp_path, monkeypatch):
    fixture_html_text = FIXTURE_PATH.read_text(encoding="utf-8")
    calls = {"n": 0}

    def fake_fetch(*a, **k):
        calls["n"] += 1
        return fixture_html_text

    monkeypatch.setattr(fastplay, "fetch", fake_fetch)

    out_path = tmp_path / "fastplay.json"
    history_dir = tmp_path / "fastplay_history"

    rc = fastplay.main(
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
    import requests

    def raising_fetch(*a, **k):
        raise requests.RequestException("boom")

    monkeypatch.setattr(fastplay, "fetch", raising_fetch)

    out_path = tmp_path / "fastplay.json"
    history_dir = tmp_path / "fastplay_history"

    rc = fastplay.main(
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


# --- fetch()'s robots-check + single GET (unit-level, no live network) -----

def test_fetch_checks_robots_then_makes_exactly_one_get(monkeypatch):
    calls = {"get": 0}

    class _FakeRobotParser:
        def set_url(self, url):
            self.url = url

        def read(self):
            pass

        def can_fetch(self, ua, url):
            return True

    class _FakeResponse:
        text = "<html></html>"

        def raise_for_status(self):
            pass

    def fake_get(url, headers=None, timeout=None):
        calls["get"] += 1
        assert "User-Agent" in headers
        return _FakeResponse()

    monkeypatch.setattr(fastplay.urllib.robotparser, "RobotFileParser", _FakeRobotParser)
    monkeypatch.setattr(fastplay.requests, "get", fake_get)

    result = fastplay.fetch()
    assert result == "<html></html>"
    assert calls["get"] == 1


def test_fetch_raises_robots_disallowed(monkeypatch):
    from scraper.scrape import RobotsDisallowed

    class _FakeRobotParser:
        def set_url(self, url):
            pass

        def read(self):
            pass

        def can_fetch(self, ua, url):
            return False

    monkeypatch.setattr(fastplay.urllib.robotparser, "RobotFileParser", _FakeRobotParser)

    with pytest.raises(RobotsDisallowed):
        fastplay.fetch()


# ============================================================================
# D8: import purity — fastplay.py imports ONLY the pinned four names from
# scraper.scrape, and never imports scraper.compute at all.
# ============================================================================

def test_fastplay_module_never_imports_scraper_compute():
    import ast

    tree = ast.parse((REPO_ROOT / "scraper" / "fastplay.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not any(
                alias.name == "scraper.compute" or alias.name.startswith("scraper.compute.")
                for alias in node.names
            )
        if isinstance(node, ast.ImportFrom):
            assert node.module != "scraper.compute"
            assert not (node.module == "scraper" and any(a.name == "compute" for a in node.names))


def test_fastplay_module_imports_only_the_pinned_names_from_scrape():
    import ast

    tree = ast.parse((REPO_ROOT / "scraper" / "fastplay.py").read_text(encoding="utf-8"))
    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "scraper.scrape":
            imported_names.update(alias.name for alias in node.names)
    assert imported_names == {
        "USER_AGENT", "FETCH_TIMEOUT_S", "ParseError", "GateError", "RobotsDisallowed",
    }


# ============================================================================
# Hand-check worksheet (test_grading.py style): 3 fixture games incl. one
# progressive; math reproducible from a fresh fixture-derived doc alone.
# ============================================================================

def test_worksheet_a_game_25_progressive_blackjack(fastplay_fixture_html):
    g = _find_game(_doc(fastplay_fixture_html), 25)
    assert g["name"] == "BLACKJACK PROGRESSIVE"
    assert g["price"] == 2.0
    assert g["percent_unsold"] == 22.0
    assert g["total_unclaimed"] == 632412.0
    assert g["relative_score"] == 28746.0
    assert g["flags"] == ["no_print_run", "progressive_jackpot"]
    assert g["ev_ratio"] is None
    assert g["value_score"] is None
    assert g["grade"] is None
    assert g["rated"] is False
    assert g["reason"] == FASTPLAY_REASONS["progressive_jackpot"]


def test_worksheet_b_game_56_cha_ching_no_print_run(fastplay_fixture_html):
    g = _find_game(_doc(fastplay_fixture_html), 56)
    assert g["name"] == "CHA-CHING!"
    assert g["price"] == 10.0
    assert g["percent_unsold"] == 5.1
    assert g["total_unclaimed"] == 128650.0
    assert g["relative_score"] == 25225.490196
    assert g["flags"] == ["no_print_run"]
    assert g["confidence"] == "low"
    assert g["ev_ratio"] is None
    assert g["rated"] is False
    assert g["reason"] == FASTPLAY_REASONS["no_print_run"]


def test_worksheet_c_game_74_fast_500s_no_print_run(fastplay_fixture_html):
    g = _find_game(_doc(fastplay_fixture_html), 74)
    assert g["name"] == "FAST $500S"
    assert g["price"] == 10.0
    assert g["percent_unsold"] == 74.6
    assert g["total_unclaimed"] == 1492340.0
    assert g["relative_score"] == 20004.557641
    assert g["flags"] == ["no_print_run"]
    assert g["ev_ratio"] is None
    assert g["rated"] is False
    assert g["reason"] == FASTPLAY_REASONS["no_print_run"]


# --- relative_score null-at-0 (synthetic — the real fixture has no 0% row) --

def test_relative_score_is_null_at_zero_percent_unsold():
    # Padded to clear the D3 floors (>= 20 games, sum(total_unclaimed) above
    # the sanity floor) — the real fixture has no 0%-unsold row to hand-check
    # against, so this is a synthetic snapshot, mirroring scratch's own
    # zero-guard convention (test_compute.py's game 617 hand-check).
    games = [
        {
            "game_no": i,
            "name": f"GAME {i}",
            "price": 2.0,
            "percent_unsold": 50.0,
            "total_unclaimed": 2_000_000.0,
            "top_prizes": [{"level": 500, "remaining": 1}],
        }
        for i in range(19)
    ]
    games.append(
        {
            "game_no": 999,
            "name": "SYNTHETIC SOLD OUT",
            "price": 2.0,
            "percent_unsold": 0.0,
            "total_unclaimed": 5000.0,
            "top_prizes": [{"level": 500, "remaining": 1}],
        }
    )
    synthetic_snapshot = {"source_timestamp": "July 27, 2026 5:00 AM", "games": games}
    doc = compute_fastplay(synthetic_snapshot, {"games": {}}, AS_OF)
    g = _find_game(doc, 999)
    assert g["relative_score"] is None
    assert "sold_out" in g["flags"]
    assert g["reason"] == FASTPLAY_REASONS["sold_out"]
