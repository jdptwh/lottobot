"""M3 test surface: EV computation, hand-checks, math/dead/diff gates, CLI.

See docs/specs/m3_ev_spec.md for the acceptance criteria (numbered 1-12 in
comments below, matching the spec's own numbering) and its "Hand-check
worksheet" section for the exact lead-verified values asserted here.
"""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import validate

# Same harness-packaging-copy skip guard as test_scrape.py: scraper/ is this
# project's own code, not part of the installable harness, and is not copied
# into the nested self-test directory (scripts/harness.manifest.json).
if not (Path(__file__).resolve().parents[2] / "scraper" / "compute.py").exists():
    pytest.skip(
        "scraper/ is this project's own code, not part of the installable harness",
        allow_module_level=True,
    )
from scraper.scrape import GateError, parse
from scraper.compute import compute_latest, diff_gate

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


# --- 1. all 65 active games, sorted, schema-valid ---------------------------

def test_compute_latest_returns_all_65_games_sorted_and_schema_valid(fixture_html):
    doc = _doc(fixture_html)
    assert len(doc["games"]) == 65
    game_nos = [g["game_no"] for g in doc["games"]]
    assert game_nos == sorted(game_nos)
    validate(instance=doc, schema=_schema())


# --- 2. Hand-check A (720) CROSSWORD: clean, high confidence ----------------

def test_hand_check_a_game_720(fixture_html):
    g = _find_game(_doc(fixture_html), 720)
    assert g["remaining_tickets"] == 1391520
    assert g["ev_per_ticket"] == 4.004578
    assert g["ev_ratio"] == 0.800916
    assert g["top_prize_odds_now"] == 278304.0
    assert g["relative_score"] == 62471.412556
    assert g["dead_game"] is False
    assert g["flags"] == []
    assert g["confidence"] == "high"
    assert "anomaly_candidate" not in g["flags"]


# --- 3. Hand-check B (702) HOLIDAY $500S: anomaly, math-gate case -----------

def test_hand_check_b_game_702(fixture_html):
    g = _find_game(_doc(fixture_html), 702)
    assert g["remaining_tickets"] == 3840
    assert g["ev_per_ticket"] == 43.278646
    assert g["ev_ratio"] == 8.655729  # published as computed, NOT clamped
    assert g["top_prize_odds_now"] == 106.666667
    assert g["relative_score"] == 415475.0
    assert g["dead_game"] is False
    assert g["flags"] == ["anomaly_candidate", "ev_out_of_range", "low_inventory"]
    assert g["confidence"] == "low"


# --- 4. Hand-check C (668) CA$H CRU$H: null-print-run fallback --------------

def test_hand_check_c_game_668(fixture_html):
    g = _find_game(_doc(fixture_html), 668)
    assert g["remaining_tickets"] is None
    assert g["ev_per_ticket"] is None
    assert g["ev_ratio"] is None
    assert g["relative_score"] == 15839.344262
    assert g["top_prize_odds_now"] is None
    assert g["dead_game"] is False
    assert g["flags"] == ["no_print_run"]
    assert g["confidence"] == "low"


# --- 5. Zero guard D (617) HIGH ROLLER: 0% unsold + dead game ---------------

def test_zero_guard_d_game_617(fixture_html):
    g = _find_game(_doc(fixture_html), 617)
    assert g["remaining_tickets"] == 0
    assert g["ev_per_ticket"] is None
    assert g["ev_ratio"] is None
    assert g["relative_score"] is None
    assert g["top_prize_odds_now"] is None
    assert g["flags"] == ["sold_out"]
    assert g["dead_game"] is True


# --- 6. all 9 null-print-run games ------------------------------------------

NULL_PRINT_RUN_GAME_NOS = (586, 648, 664, 668, 669, 681, 689, 697, 710)


def test_all_null_print_run_games_take_the_fallback(fixture_html):
    doc = _doc(fixture_html)
    for game_no in NULL_PRINT_RUN_GAME_NOS:
        g = _find_game(doc, game_no)
        assert g["print_run"] is None
        assert g["ev_ratio"] is None
        assert "no_print_run" in g["flags"]
        assert g["confidence"] == "low"
        if g["percent_unsold"] > 0:
            assert g["relative_score"] is not None
        else:
            assert g["relative_score"] is None


# --- 7. Math gate (§6.2): every non-null ev_ratio in range or flagged -------

def test_math_gate_every_ev_ratio_in_range_or_flagged(fixture_html):
    doc = _doc(fixture_html)
    in_range_count = 0
    for g in doc["games"]:
        ratio = g["ev_ratio"]
        if ratio is None:
            continue
        in_range = 0 < ratio < 1.5
        if in_range:
            in_range_count += 1
        else:
            assert "ev_out_of_range" in g["flags"], g
            assert "anomaly_candidate" in g["flags"], g
            assert g["confidence"] == "low", g
    # Escalation trigger: fewer than 20 in-range games is a data surprise,
    # not a threshold to weaken (spec instructs STOP and escalate if so).
    assert in_range_count >= 20, (
        f"only {in_range_count} games have ev_ratio in (0, 1.5); "
        "spec requires >= 20 — this would be a data surprise, escalate "
        "to the planner rather than weakening the gate"
    )


# --- 8. dead_game rule -------------------------------------------------------

def test_dead_game_rule(fixture_html):
    doc = _doc(fixture_html)
    assert _find_game(doc, 617)["dead_game"] is True
    assert _find_game(doc, 720)["dead_game"] is False
    assert _find_game(doc, 702)["dead_game"] is False

    meta = _games_meta()["games"]
    for g in doc["games"]:
        game_meta = meta.get(str(g["game_no"])) or {}
        if game_meta.get("top_prize_value") is None:
            assert g["dead_game"] is False, g


# --- 9. Diff gate (§6.4) -----------------------------------------------------

def test_diff_gate_prior_absent_cli_succeeds_with_stderr_note(tmp_path):
    out_path = tmp_path / "latest.json"
    result = subprocess.run(
        [
            sys.executable, "-m", "scraper.compute",
            "--unclaimed", str(FIXTURE_PATH),
            "--games", str(GAMES_PATH),
            "--as-of", AS_OF,
            "--out", str(out_path),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "diff gate skipped" in result.stderr
    assert out_path.exists()


def test_diff_gate_prior_omitted_path_that_does_not_exist_is_inert(tmp_path):
    missing_prior = tmp_path / "does_not_exist.json"
    out_path = tmp_path / "latest.json"
    result = subprocess.run(
        [
            sys.executable, "-m", "scraper.compute",
            "--unclaimed", str(FIXTURE_PATH),
            "--games", str(GAMES_PATH),
            "--as-of", AS_OF,
            "--prior", str(missing_prior),
            "--out", str(out_path),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "diff gate skipped" in result.stderr
    assert out_path.exists()


def test_diff_gate_passes_under_30_percent_moved(fixture_html):
    new_doc = _doc(fixture_html)
    prior_doc = copy.deepcopy(new_doc)
    # Nudge exactly one paired, non-null-ev_ratio game by > 0.2 (the fixture
    # has 38 in-range games; 1/38 ≈ 2.6% << 30%).
    nudged = False
    for g in prior_doc["games"]:
        if g["ev_ratio"] is not None:
            g["ev_ratio"] = g["ev_ratio"] + 10.0
            nudged = True
            break
    assert nudged
    diff_gate(new_doc, prior_doc)  # must not raise


def test_diff_gate_raises_over_30_percent_moved(fixture_html):
    new_doc = _doc(fixture_html)
    prior_doc = copy.deepcopy(new_doc)
    # Nudge every paired, non-null-ev_ratio game by > 0.2 (100% > 30%).
    for g in prior_doc["games"]:
        if g["ev_ratio"] is not None:
            g["ev_ratio"] = g["ev_ratio"] + 10.0
    with pytest.raises(GateError):
        diff_gate(new_doc, prior_doc)


def test_diff_gate_excludes_null_ev_ratio_pairs():
    new_doc = {
        "games": [
            {"game_no": 1, "ev_ratio": 0.5},
            {"game_no": 2, "ev_ratio": None},
            {"game_no": 3, "ev_ratio": 0.5},
        ]
    }
    prior_doc = {
        "games": [
            {"game_no": 1, "ev_ratio": 5.0},  # non-null pair, moves > 0.2
            {"game_no": 2, "ev_ratio": 5.0},  # new is null -> excluded
            {"game_no": 3, "ev_ratio": None},  # prior is null -> excluded
        ]
    }
    # Only game 1 is a valid pair, and it moved > 0.2: 1/1 = 100% > 30%.
    with pytest.raises(GateError):
        diff_gate(new_doc, prior_doc)


def test_diff_gate_zero_pairs_passes():
    new_doc = {"games": [{"game_no": 1, "ev_ratio": 0.5}]}
    prior_doc = {"games": [{"game_no": 2, "ev_ratio": 0.5}]}  # no shared game_no
    diff_gate(new_doc, prior_doc)  # must not raise


def test_cli_diff_gate_failure_writes_nothing_and_nonzero_exit(tmp_path):
    # Build a synthetic prior with every currently-computed non-null
    # ev_ratio shifted far away, so > 30% of paired games move > 0.2.
    with FIXTURE_PATH.open(encoding="utf-8") as f:
        snapshot = parse(f.read())
    real_doc = compute_latest(snapshot, _games_meta(), AS_OF)
    prior_doc = copy.deepcopy(real_doc)
    for g in prior_doc["games"]:
        if g["ev_ratio"] is not None:
            g["ev_ratio"] = g["ev_ratio"] + 50.0

    prior_path = tmp_path / "prior_latest.json"
    prior_path.write_text(json.dumps(prior_doc), encoding="utf-8")
    out_path = tmp_path / "latest.json"

    result = subprocess.run(
        [
            sys.executable, "-m", "scraper.compute",
            "--unclaimed", str(FIXTURE_PATH),
            "--games", str(GAMES_PATH),
            "--as-of", AS_OF,
            "--prior", str(prior_path),
            "--out", str(out_path),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert not out_path.exists()
    assert "diff gate" in result.stderr


# --- 10. Determinism ----------------------------------------------------------

def test_cli_two_runs_are_byte_identical(tmp_path):
    out1 = tmp_path / "latest1.json"
    out2 = tmp_path / "latest2.json"
    cmd = [
        sys.executable, "-m", "scraper.compute",
        "--unclaimed", str(FIXTURE_PATH),
        "--games", str(GAMES_PATH),
        "--as-of", AS_OF,
    ]
    result1 = subprocess.run(cmd + ["--out", str(out1)], cwd=REPO_ROOT, capture_output=True, text=True)
    result2 = subprocess.run(cmd + ["--out", str(out2)], cwd=REPO_ROOT, capture_output=True, text=True)
    assert result1.returncode == 0, result1.stderr
    assert result2.returncode == 0, result2.stderr
    assert out1.read_bytes() == out2.read_bytes()


def test_cli_reproduces_the_frozen_regression_artifact_exactly():
    # data/latest.json is now overwritten daily by the M5 bot (live data), so
    # this regression check compares against a frozen artifact captured from
    # the fixture pipeline instead (tests/scraper/fixtures/latest_2026-07-11.json,
    # the exact bytes of the pre-bot committed data/latest.json at e4a8b7a).
    result = subprocess.run(
        [
            sys.executable, "-m", "scraper.compute",
            "--unclaimed", str(FIXTURE_PATH),
            "--games", str(GAMES_PATH),
            "--as-of", AS_OF,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    frozen = FROZEN_ARTIFACT_PATH.read_text(encoding="utf-8")
    # The CLI prints to stdout without a trailing newline appended by json.dumps;
    # subprocess capture may add a trailing newline via the print() call.
    assert result.stdout.rstrip("\n") == frozen.rstrip("\n")


# --- 11. Schema additive-only ------------------------------------------------

def test_schema_additive_only_new_properties():
    schema = _schema()
    game_props = schema["$defs"]["game"]["properties"]
    assert game_props["relative_score"] == {"type": ["number", "null"]}
    assert game_props["top_prize_odds_now"] == {"type": ["number", "null"]}
    required = schema["$defs"]["game"]["required"]
    assert "relative_score" not in required
    assert "top_prize_odds_now" not in required


def test_computed_doc_with_new_fields_validates(fixture_html):
    doc = _doc(fixture_html)
    validate(instance=doc, schema=_schema())
