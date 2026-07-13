"""M4a test surface: value_score / grade / rated / reason.

See docs/specs/m4a_scoring_spec.md for the acceptance criteria (numbered
1-14 in comments below, matching the spec's own numbering) and its
"Hand-check worksheet" (items A-G) for the exact lead-verified values
asserted here. A new file (rather than editing test_compute.py) so "M3
suite green unmodified" is provable via ``git diff --stat`` showing zero
changes to tests/scraper/test_compute.py.
"""
import json
from pathlib import Path

import pytest
from jsonschema import validate

# Same harness-packaging-copy skip guard as test_compute.py / test_scrape.py:
# scraper/ is this project's own code, not part of the installable harness.
if not (Path(__file__).resolve().parents[2] / "scraper" / "compute.py").exists():
    pytest.skip(
        "scraper/ is this project's own code, not part of the installable harness",
        allow_module_level=True,
    )
from scraper.scrape import parse
from scraper.compute import (
    DEGENERATE_SCORE,
    GRADE_BANDS,
    GRADE_DEFAULT,
    REASONS,
    _grade_for_score,
    compute_latest,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "data" / "schema" / "latest.schema.json"
GAMES_PATH = REPO_ROOT / "data" / "games.json"
AS_OF = "2026-07-11"


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _games_meta() -> dict:
    return json.loads(GAMES_PATH.read_text(encoding="utf-8"))


def _doc(fixture_html) -> dict:
    snapshot = parse(fixture_html)
    return compute_latest(snapshot, _games_meta(), AS_OF)


def _find_game(doc: dict, game_no: int) -> dict:
    for g in doc["games"]:
        if g["game_no"] == game_no:
            return g
    raise AssertionError(f"game {game_no} not found in computed doc")


# --- 1. all 65 games carry the four fields, schema-valid, pinned order ------

def test_all_65_games_carry_new_fields_in_pinned_order(fixture_html):
    doc = _doc(fixture_html)
    assert len(doc["games"]) == 65
    validate(instance=doc, schema=_schema())
    for g in doc["games"]:
        keys = list(g.keys())
        confidence_idx = keys.index("confidence")
        assert keys[confidence_idx + 1 : confidence_idx + 5] == [
            "value_score",
            "grade",
            "rated",
            "reason",
        ]


# --- 2. exact rated set (38) -------------------------------------------------

RATED_GAME_NOS = {
    624, 630, 638, 647, 656, 661, 662, 674, 675, 677, 682, 685, 686, 687,
    690, 692, 693, 694, 695, 696, 699, 702, 703, 705, 706, 708, 709, 711,
    716, 717, 718, 720, 723, 725, 729, 730, 735, 737,
}


def test_exact_rated_set(fixture_html):
    doc = _doc(fixture_html)
    rated = {g["game_no"] for g in doc["games"] if g["rated"] is True}
    assert rated == RATED_GAME_NOS
    assert len(RATED_GAME_NOS) == 38


# --- 3. exact non-rated buckets (27) -----------------------------------------

DEAD_REASON_GAME_NOS = {
    617, 632, 651, 654, 655, 660, 663, 667, 670, 671, 673, 676, 680, 683,
    684, 691, 704, 707,
}
NO_PRINT_RUN_REASON_GAME_NOS = {586, 648, 664, 668, 669, 681, 689, 697, 710}


def test_exact_non_rated_buckets(fixture_html):
    doc = _doc(fixture_html)
    assert len(DEAD_REASON_GAME_NOS) == 18
    assert len(NO_PRINT_RUN_REASON_GAME_NOS) == 9

    dead_reason = set()
    no_print_run_reason = set()
    sold_out_reason = set()
    no_data_reason = set()
    for g in doc["games"]:
        if g["rated"]:
            continue
        assert g["value_score"] is None
        assert g["grade"] is None
        if g["reason"] == REASONS["dead"]:
            dead_reason.add(g["game_no"])
        elif g["reason"] == REASONS["sold_out"]:
            sold_out_reason.add(g["game_no"])
        elif g["reason"] == REASONS["no_print_run"]:
            no_print_run_reason.add(g["game_no"])
        elif g["reason"] == REASONS["no_data"]:
            no_data_reason.add(g["game_no"])
        else:
            raise AssertionError(f"unexpected non-rated reason: {g}")

    assert dead_reason == DEAD_REASON_GAME_NOS
    assert no_print_run_reason == NO_PRINT_RUN_REASON_GAME_NOS
    assert sold_out_reason == set()
    assert no_data_reason == set()
    non_rated_total = (
        dead_reason | sold_out_reason | no_print_run_reason | no_data_reason
    )
    assert len(non_rated_total) == 27


# --- 4. claim-lag set --------------------------------------------------------

CLAIM_LAG_GAME_NOS = {
    624, 638, 661, 690, 693, 694, 695, 696, 702, 703, 706,
}


def test_claim_lag_set(fixture_html):
    doc = _doc(fixture_html)
    assert len(CLAIM_LAG_GAME_NOS) == 11
    claim_lag = {
        g["game_no"]
        for g in doc["games"]
        if g["rated"] and g["reason"] == REASONS["claim_lag"]
    }
    assert claim_lag == CLAIM_LAG_GAME_NOS
    for game_no in CLAIM_LAG_GAME_NOS:
        g = _find_game(doc, game_no)
        assert g["value_score"] == 40
        assert g["grade"] == "F"
        assert g["reason"] == REASONS["claim_lag"]


# --- 5. hand-check worksheet A-G ---------------------------------------------

def test_worksheet_a_game_630_hero_curve_max(fixture_html):
    g = _find_game(_doc(fixture_html), 630)
    assert g["ev_ratio"] == 1.367541
    assert g["confidence"] == "medium"
    assert g["value_score"] == 95
    assert g["grade"] == "A"
    assert g["rated"] is True
    assert g["reason"] == REASONS["medium"]


def test_worksheet_b_game_662_mid_curve(fixture_html):
    g = _find_game(_doc(fixture_html), 662)
    assert g["ev_ratio"] == 1.287899
    assert g["confidence"] == "medium"
    assert g["value_score"] == 87
    assert g["grade"] == "A"
    assert g["rated"] is True
    assert g["reason"] == REASONS["medium"]


def test_worksheet_c_game_706_claim_lag_curve_min(fixture_html):
    g = _find_game(_doc(fixture_html), 706)
    assert g["ev_ratio"] == 32.538542
    assert g["confidence"] == "low"
    assert "ev_out_of_range" in g["flags"]
    assert g["value_score"] == 40
    assert g["grade"] == "F"
    assert g["rated"] is True
    assert g["reason"] == REASONS["claim_lag"]


def test_worksheet_d_game_675_lone_d(fixture_html):
    g = _find_game(_doc(fixture_html), 675)
    assert g["ev_ratio"] == 0.731252
    assert g["confidence"] == "high"
    assert g["value_score"] == 46
    assert g["grade"] == "D"
    assert g["rated"] is True
    assert g["reason"] == REASONS["high"]


def test_worksheet_e_game_617_dead_and_sold_out_precedence(fixture_html):
    g = _find_game(_doc(fixture_html), 617)
    assert g["dead_game"] is True
    assert "sold_out" in g["flags"]
    assert g["value_score"] is None
    assert g["grade"] is None
    assert g["rated"] is False
    assert g["reason"] == REASONS["dead"]


def test_worksheet_f_game_668_no_print_run(fixture_html):
    g = _find_game(_doc(fixture_html), 668)
    assert g["print_run"] is None
    assert g["value_score"] is None
    assert g["grade"] is None
    assert g["rated"] is False
    assert g["reason"] == REASONS["no_print_run"]


def test_worksheet_g_game_682_band_edge_rounding(fixture_html):
    g = _find_game(_doc(fixture_html), 682)
    assert g["ev_ratio"] == 0.921596
    assert g["confidence"] == "high"
    assert g["value_score"] == 68
    assert g["grade"] == "B"


# --- 6. pinned top of the curve ----------------------------------------------

PINNED_TOP = {
    630: (95, "A"),
    662: (87, "A"),
    708: (87, "A"),
    685: (85, "A"),
    647: (84, "A-"),
    699: (76, "B+"),
    709: (75, "B+"),
    687: (73, "B"),
    705: (73, "B"),
    730: (72, "B"),
    711: (70, "B"),
    674: (69, "B"),
    682: (68, "B"),
}


def test_pinned_top_of_curve(fixture_html):
    doc = _doc(fixture_html)
    for game_no, (score, grade) in PINNED_TOP.items():
        g = _find_game(doc, game_no)
        assert g["value_score"] == score, game_no
        assert g["grade"] == grade, game_no


# --- 7. grade distribution ----------------------------------------------------

def test_grade_distribution(fixture_html):
    doc = _doc(fixture_html)
    rated_games = [g for g in doc["games"] if g["rated"]]
    assert len(rated_games) == 38
    dist: dict[str, int] = {}
    for g in rated_games:
        dist[g["grade"]] = dist.get(g["grade"], 0) + 1
    assert dist == {
        "A": 4,
        "A-": 1,
        "B+": 2,
        "B": 6,
        "B-": 6,
        "C": 7,
        "D": 1,
        "F": 11,
    }


# --- 8. band-boundary unit test (synthetic, pure function) -------------------

def test_band_boundaries():
    for floor, letter in GRADE_BANDS:
        assert _grade_for_score(floor) == letter
        assert _grade_for_score(floor - 1) != letter
    # sanity: below the lowest band floor (42) is F
    assert _grade_for_score(41) == GRADE_DEFAULT
    assert _grade_for_score(0) == GRADE_DEFAULT


# --- 9. degenerate-curve unit test (synthetic) -------------------------------

def _base_game(**overrides) -> dict:
    game = {
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
        "top_prize_odds_now": None,
        "dead_game": False,
        "flags": [],
        "confidence": "high",
    }
    game.update(overrides)
    return game


def test_degenerate_curve_single_rateable_game():
    from scraper.compute import _apply_scoring

    games = [_base_game(game_no=1)]
    _apply_scoring(games)
    g = games[0]
    assert g["value_score"] == DEGENERATE_SCORE == 68
    assert g["grade"] == "B"
    assert g["rated"] is True


def test_degenerate_curve_sole_survivor_is_claim_lag():
    from scraper.compute import _apply_scoring

    games = [
        _base_game(
            game_no=1,
            ev_ratio=5.0,
            confidence="low",
            flags=["ev_out_of_range"],
        )
    ]
    _apply_scoring(games)
    g = games[0]
    assert g["value_score"] == DEGENERATE_SCORE
    assert g["grade"] == "B"
    assert g["reason"] == REASONS["claim_lag"]


# --- 10. low-confidence rateable branch (synthetic, no fixture coverage) ----

def test_low_confidence_rateable_no_oor_gets_low_reason():
    from scraper.compute import _apply_scoring

    games = [
        _base_game(game_no=1, ev_ratio=0.5, confidence="high", flags=[]),
        _base_game(game_no=2, ev_ratio=0.2, confidence="low", flags=[]),
    ]
    _apply_scoring(games)
    low_game = next(g for g in games if g["game_no"] == 2)
    assert low_game["rated"] is True
    assert "ev_out_of_range" not in low_game["flags"]
    assert low_game["reason"] == REASONS["low"]


# --- 11. type discipline ------------------------------------------------------

def test_type_discipline(fixture_html):
    doc = _doc(fixture_html)
    assert len(doc["games"]) == 65
    for g in doc["games"]:
        if g["value_score"] is not None:
            assert isinstance(g["value_score"], int)
            assert not isinstance(g["value_score"], bool)
        assert isinstance(g["rated"], bool)
        assert isinstance(g["reason"], str)
        assert len(g["reason"]) > 0
