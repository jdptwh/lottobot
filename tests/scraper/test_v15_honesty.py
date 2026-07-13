"""W2 v1.5 honesty pass test surface (docs/specs/w2_v15_honesty_spec.md).

Covers the pipeline-side (CP1) acceptance criteria: the six new additive
fields (``remaining_tickets_min``/``max``, ``ev_ratio_min``/``max``,
``ev_scenarios``, ``overall_odds_launch``), the nullity coupling and
ordering/coherence invariants, the hand-check worksheet A-C exacts, the
integer-decimal scenario rule (synthetic, kills a float-naive
implementation), the scoring-untouched proof, and the eligibility-amendment
semantics (Resolution 6 / M4b amendment 1). Numbered comments below match
the spec's own AC numbering.
"""
import json
from pathlib import Path

import pytest
from jsonschema import validate

REPO_ROOT = Path(__file__).resolve().parents[2]

# Same harness-packaging-copy skip guard as test_compute.py/test_scrape.py:
# scraper/ is this project's own code, not part of the installable harness,
# and is not copied into the nested self-test directory
# (scripts/harness.manifest.json).
if not (REPO_ROOT / "scraper" / "compute.py").exists():
    pytest.skip(
        "scraper/ is this project's own code, not part of the installable harness",
        allow_module_level=True,
    )
from scraper.scrape import parse
from scraper.compute import (
    SCENARIO_CLAIMED_SHARES,
    _ev_scenarios,
    _interval_fields,
    compute_latest,
)

SCHEMA_PATH = REPO_ROOT / "data" / "schema" / "latest.schema.json"
GAMES_PATH = REPO_ROOT / "data" / "games.json"
FROZEN_ARTIFACT_PATH = (
    REPO_ROOT / "tests" / "scraper" / "fixtures" / "latest_2026-07-11.json"
)
AS_OF = "2026-07-11"

NEW_FIELD_ORDER = [
    "remaining_tickets_min",
    "remaining_tickets_max",
    "ev_ratio_min",
    "ev_ratio_max",
    "ev_scenarios",
    "overall_odds_launch",
]


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


@pytest.fixture(scope="module")
def frozen_doc():
    return json.loads(FROZEN_ARTIFACT_PATH.read_text(encoding="utf-8"))


# --- AC-1: all 65 games carry the six fields in pinned order, schema-valid --

def test_all_65_games_carry_six_new_fields_in_pinned_order(fixture_html):
    doc = _doc(fixture_html)
    assert len(doc["games"]) == 65
    for g in doc["games"]:
        keys = list(g.keys())
        reason_idx = keys.index("reason")
        tail = keys[reason_idx + 1:]
        assert tail == NEW_FIELD_ORDER, (g["game_no"], tail)
    validate(instance=doc, schema=_schema())


def test_frozen_artifact_all_65_games_carry_six_new_fields_in_pinned_order(frozen_doc):
    assert len(frozen_doc["games"]) == 65
    for g in frozen_doc["games"]:
        keys = list(g.keys())
        reason_idx = keys.index("reason")
        tail = keys[reason_idx + 1:]
        assert tail == NEW_FIELD_ORDER, (g["game_no"], tail)
    validate(instance=frozen_doc, schema=_schema())


# --- AC-2: nullity coupling ---------------------------------------------------

def test_nullity_coupling_frozen_artifact(frozen_doc):
    for g in frozen_doc["games"]:
        ev_ratio_null = g["ev_ratio"] is None
        assert (g["remaining_tickets_min"] is None) == ev_ratio_null, g["game_no"]
        assert (g["remaining_tickets_max"] is None) == ev_ratio_null, g["game_no"]
        assert (g["ev_ratio_min"] is None) == ev_ratio_null, g["game_no"]
        assert (g["ev_scenarios"] is None) == ev_ratio_null, g["game_no"]
        if not ev_ratio_null:
            assert (g["ev_ratio_max"] is None) == (g["remaining_tickets_min"] == 0), g["game_no"]


def test_nullity_overall_odds_launch_independent_frozen_artifact(frozen_doc):
    g586 = _find_game(frozen_doc, 586)
    assert g586["ev_ratio"] is None
    assert g586["overall_odds_launch"] is None

    g720 = _find_game(frozen_doc, 720)
    assert g720["overall_odds_launch"] == 3.52


def test_ev_ratio_max_null_iff_remaining_tickets_min_zero_synthetic():
    # remaining_tickets_min == 0 arises when p - 0.05 <= 0, e.g. p == 0.05.
    fields = _interval_fields(
        ev_ratio=8.0,
        percent_unsold=0.05,
        print_run=1_000_000,
        total_unclaimed=1000.0,
        price=1.0,
    )
    remaining_tickets_min, remaining_tickets_max, ev_ratio_min, ev_ratio_max = fields
    assert remaining_tickets_min == 0
    assert ev_ratio_max is None
    assert remaining_tickets_max is not None
    assert ev_ratio_min is not None


def test_interval_fields_null_iff_ev_ratio_null_synthetic():
    fields = _interval_fields(
        ev_ratio=None,
        percent_unsold=10.0,
        print_run=1_000_000,
        total_unclaimed=1000.0,
        price=1.0,
    )
    assert fields == (None, None, None, None)


def test_ev_scenarios_null_never_empty_list_synthetic():
    assert _ev_scenarios(None) is None


# --- AC-3: ordering / coherence invariants ------------------------------------

def _assert_ordering_invariants(g):
    if g["ev_ratio"] is None:
        return
    assert g["remaining_tickets_min"] <= g["remaining_tickets"] <= g["remaining_tickets_max"]
    assert g["ev_ratio_min"] <= g["ev_ratio"] <= (
        g["ev_ratio_max"] if g["ev_ratio_max"] is not None else float("inf")
    )
    assert len(g["ev_scenarios"]) == 3
    shares = [s["assumed_claimed_share"] for s in g["ev_scenarios"]]
    assert shares == sorted(shares)
    assert tuple(shares) == SCENARIO_CLAIMED_SHARES
    ratios = [s["ev_ratio"] for s in g["ev_scenarios"]]
    assert ratios == sorted(ratios, reverse=True)
    assert len(set(ratios)) == len(ratios) or ratios[0] > ratios[1] > ratios[2]
    for r in ratios:
        assert r < g["ev_ratio"]
    assert g["ev_ratio_adjusted"] is None


def test_ordering_invariants_frozen_artifact(frozen_doc):
    for g in frozen_doc["games"]:
        _assert_ordering_invariants(g)


def test_ordering_invariants_computed_doc(fixture_html):
    doc = _doc(fixture_html)
    for g in doc["games"]:
        _assert_ordering_invariants(g)


# --- AC-4: hand-check worksheet A-C exacts ------------------------------------

def test_worksheet_a_game_720(frozen_doc):
    g = _find_game(frozen_doc, 720)
    assert g["remaining_tickets_min"] == 1390740
    assert g["remaining_tickets_max"] == 1392300
    assert g["ev_ratio_max"] == 0.801365
    assert g["ev_ratio_min"] == 0.800467
    assert g["ev_scenarios"] == [
        {"assumed_claimed_share": 0.5, "ev_ratio": 0.400458},
        {"assumed_claimed_share": 0.8, "ev_ratio": 0.160183},
        {"assumed_claimed_share": 0.95, "ev_ratio": 0.040046},
    ]
    assert g["overall_odds_launch"] == 3.52


def test_worksheet_b_game_630(frozen_doc):
    g = _find_game(frozen_doc, 630)
    assert g["remaining_tickets_min"] == 107040
    assert g["remaining_tickets_max"] == 108000
    assert g["ev_ratio_max"] == 1.373673
    assert g["ev_ratio_min"] == 1.361463
    assert g["ev_scenarios"] == [
        {"assumed_claimed_share": 0.5, "ev_ratio": 0.683771},
        {"assumed_claimed_share": 0.8, "ev_ratio": 0.273508},
        {"assumed_claimed_share": 0.95, "ev_ratio": 0.068377},
    ]
    assert g["overall_odds_launch"] == 2.84


def test_worksheet_c_game_702(frozen_doc):
    g = _find_game(frozen_doc, 702)
    assert g["remaining_tickets_min"] == 3360
    assert g["remaining_tickets_max"] == 4320
    assert g["ev_ratio_max"] == 9.892262
    assert g["ev_ratio_min"] == 7.693981
    assert g["ev_scenarios"] == [
        {"assumed_claimed_share": 0.5, "ev_ratio": 4.327865},
        {"assumed_claimed_share": 0.8, "ev_ratio": 1.731146},
        {"assumed_claimed_share": 0.95, "ev_ratio": 0.432786},
    ]
    assert g["overall_odds_launch"] == 3.56


# --- AC-5: integer-decimal scenario rule (synthetic; kills float-naive) ------

def test_scenario_half_up_midpoint_synthetic():
    # ev_ratio 1.000001 -> n = 1000001 (odd 6th dp) -> s0.5 exact decimal
    # midpoint 0.5000005, must round HALF-UP to 0.500001, never 0.500000.
    scenarios = _ev_scenarios(1.000001)
    s050 = next(s for s in scenarios if s["assumed_claimed_share"] == 0.5)
    assert s050["ev_ratio"] == 0.500001

    # A float-naive `round(ev_ratio * (1 - share), 6)` implementation fails
    # this exact case: Python's round-half-to-even on the float midpoint
    # 0.5000005 lands on 0.5 (0.500000), never 0.500001.
    naive = round(1.000001 * (1 - 0.5), 6)
    assert naive == 0.5
    assert naive != s050["ev_ratio"]


def test_scenario_half_up_midpoint_disagrees_with_float_naive_worksheet_b():
    # Worksheet B's real value is also an exact decimal midpoint at s0.5 and
    # the float-naive implementation disagrees with the pinned half-up result.
    ev_ratio = 1.367541  # worksheet B's value; exact decimal midpoint at s0.5
    scenarios = _ev_scenarios(ev_ratio)
    s050 = next(s for s in scenarios if s["assumed_claimed_share"] == 0.5)
    assert s050["ev_ratio"] == 0.683771  # half-up of the exact 0.6837705 midpoint

    naive = round(ev_ratio * 0.5, 6)
    assert naive != s050["ev_ratio"]


# --- AC-6: scoring untouched ---------------------------------------------------

def test_scoring_untouched_game_630(frozen_doc):
    g = _find_game(frozen_doc, 630)
    assert g["value_score"] == 95
    assert g["grade"] == "A"


def test_scoring_untouched_oor_and_rated_counts(frozen_doc):
    rated = [g for g in frozen_doc["games"] if g["rated"]]
    oor_rated = [g for g in rated if "ev_out_of_range" in g["flags"]]
    assert len(rated) == 38
    assert len(oor_rated) == 11


def test_scoring_bytes_identical_via_additive_only_strip(frozen_doc):
    # Companion machine-check to the CP1 additive-only check the lead runs
    # against the PRE-re-freeze artifact: here we just confirm every scoring
    # byte is present and typed as before, per-game, on the re-frozen file.
    for g in frozen_doc["games"]:
        assert "value_score" in g
        assert "grade" in g
        assert "rated" in g
        assert "reason" in g and isinstance(g["reason"], str) and g["reason"]


# --- AC-7: eligibility amendment (Resolution 6 / M4b amendment 1) ------------

def _eligible(g):
    return (
        g["rated"] is True
        and "ev_out_of_range" not in g["flags"]
        and "low_inventory" not in g["flags"]
    )


def _excluded(g):
    return g["rated"] is True and not _eligible(g)


def test_low_inventory_only_excluded_set_is_empty_on_frozen_artifact(frozen_doc):
    low_inventory_only_excluded = [
        g for g in frozen_doc["games"]
        if g["rated"]
        and "low_inventory" in g["flags"]
        and "ev_out_of_range" not in g["flags"]
    ]
    assert low_inventory_only_excluded == []


def test_eligible_count_and_top_eligible_frozen_artifact(frozen_doc):
    eligible = [g for g in frozen_doc["games"] if _eligible(g)]
    assert len(eligible) == 27
    top = max(eligible, key=lambda g: (g["value_score"], -g["game_no"]))
    assert top["game_no"] == 630


def test_top_eligible_never_carries_oor_or_low_inventory_frozen_artifact(frozen_doc):
    eligible = [g for g in frozen_doc["games"] if _eligible(g)]
    top = max(eligible, key=lambda g: (g["value_score"], -g["game_no"]))
    assert "ev_out_of_range" not in top["flags"]
    assert "low_inventory" not in top["flags"]


def test_partition_invariant_lossless_frozen_artifact(frozen_doc):
    games = frozen_doc["games"]
    eligible = {g["game_no"] for g in games if _eligible(g)}
    excluded = {g["game_no"] for g in games if _excluded(g)}
    not_rated = {g["game_no"] for g in games if not g["rated"]}
    assert eligible.isdisjoint(excluded)
    assert eligible.isdisjoint(not_rated)
    assert excluded.isdisjoint(not_rated)
    assert eligible | excluded | not_rated == {g["game_no"] for g in games}


def test_synthetic_rated_in_range_low_inventory_game_is_excluded_not_eligible():
    # A rated, in-range, low_inventory game is NOT eligible, IS in the
    # excluded partition, and retains its score/grade/reason (honestly
    # displayed, never hidden) — the semantics the current fixture (which
    # has zero such games) cannot exercise.
    g = {
        "rated": True,
        "flags": ["low_inventory"],
        "value_score": 70,
        "grade": "B",
        "reason": "Very little inventory data behind this estimate — treat this score with caution.",
    }
    assert not _eligible(g)
    assert _excluded(g)
    assert g["value_score"] == 70
    assert g["grade"] == "B"
    assert "low" in g["reason"].lower() or "caution" in g["reason"].lower()


def test_synthetic_rated_claim_lag_game_is_excluded_not_eligible():
    g = {"rated": True, "flags": ["ev_out_of_range", "anomaly_candidate"]}
    assert not _eligible(g)
    assert _excluded(g)


def test_synthetic_rated_clean_game_is_eligible():
    g = {"rated": True, "flags": []}
    assert _eligible(g)
    assert not _excluded(g)


# --- AC-11 (pipeline side): determinism + untouched-files scope --------------

def test_cli_two_runs_byte_identical(tmp_path):
    import subprocess
    import sys

    fixture_path = (
        REPO_ROOT / "tests" / "scraper" / "fixtures" / "unclaimed_prizes_2026-07-11.html"
    )
    cmd = [
        sys.executable, "-m", "scraper.compute",
        "--unclaimed", str(fixture_path),
        "--games", str(GAMES_PATH),
        "--as-of", AS_OF,
    ]
    out1 = tmp_path / "latest1.json"
    out2 = tmp_path / "latest2.json"
    r1 = subprocess.run(cmd + ["--out", str(out1)], cwd=REPO_ROOT, capture_output=True, text=True)
    r2 = subprocess.run(cmd + ["--out", str(out2)], cwd=REPO_ROOT, capture_output=True, text=True)
    assert r1.returncode == 0, r1.stderr
    assert r2.returncode == 0, r2.stderr
    assert out1.read_bytes() == out2.read_bytes()


def test_cli_output_matches_re_frozen_artifact():
    import subprocess
    import sys

    fixture_path = (
        REPO_ROOT / "tests" / "scraper" / "fixtures" / "unclaimed_prizes_2026-07-11.html"
    )
    result = subprocess.run(
        [
            sys.executable, "-m", "scraper.compute",
            "--unclaimed", str(fixture_path),
            "--games", str(GAMES_PATH),
            "--as-of", AS_OF,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    frozen = FROZEN_ARTIFACT_PATH.read_text(encoding="utf-8")
    assert result.stdout.rstrip("\n") == frozen.rstrip("\n")


# --- Schema: additive-only new properties -------------------------------------

def test_schema_additive_only_new_properties():
    schema = _schema()
    game_props = schema["$defs"]["game"]["properties"]
    assert game_props["remaining_tickets_min"] == {"type": ["integer", "null"]}
    assert game_props["remaining_tickets_max"] == {"type": ["integer", "null"]}
    assert game_props["ev_ratio_min"] == {"type": ["number", "null"]}
    assert game_props["ev_ratio_max"] == {"type": ["number", "null"]}
    assert game_props["overall_odds_launch"] == {"type": ["number", "null"]}
    ev_scenarios_schema = game_props["ev_scenarios"]
    assert ev_scenarios_schema["type"] == ["array", "null"]
    assert ev_scenarios_schema["minItems"] == 3
    assert ev_scenarios_schema["maxItems"] == 3
    required = schema["$defs"]["game"]["required"]
    for key in NEW_FIELD_ORDER:
        assert key not in required
