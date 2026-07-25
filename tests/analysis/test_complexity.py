"""Tests for analysis/complexity.py — offline, seeded, fast (no real panel).

Machine gate for the complexity/burn-rate study per ROUTING.md Rule 2/4:
synthetic arcs with KNOWN burn shapes must produce metrics of the right sign
and magnitude before the study touches real data.
"""
import json
from pathlib import Path

import numpy as np
import pytest

# Harness-packaging-copy skip guard (test_compute.py pattern): analysis/ is
# this project's own code, not part of the installable harness.
if not (Path(__file__).resolve().parents[2] / "analysis" / "complexity.py").exists():
    pytest.skip(
        "analysis/ is this project's own code, not part of the installable harness",
        allow_module_level=True,
    )

from analysis.complexity import (
    arc_burn_metrics,
    complexity_index,
    load_mechanics,
    parse_article_mechanics,
    run_study,
    spearman,
    spearman_with_ci,
    structural_components,
    _top_value,
    _zscore_matrix,
)


def _rec(obs_date, pu, unclaimed, tops=None, status="active", price=5.0,
         game_no=900, name="SYNTH"):
    return {
        "game_key": f"{game_no}:synth",
        "game_no": game_no,
        "name": name,
        "obs_date": obs_date,
        "capture_ts": obs_date + "T00:00:00+00:00",
        "source": "daily",
        "percent_unsold": pu,
        "total_unclaimed": unclaimed,
        "top_prizes": tops if tops is not None
        else [{"level": 100000, "remaining": 2}],
        "price": price,
        "lifecycle_status": status,
    }


# ---------------------------------------------------------------------------
# arc_burn_metrics
# ---------------------------------------------------------------------------

def test_uniform_burn_gap_near_zero():
    # u falls exactly with the instant-claim diagonal -> burn_gap ~ 0
    arc = [
        _rec(f"2020-01-{d:02d}", pu, pu / 100 * 500000)
        for d, pu in zip(range(1, 12), range(100, 45, -5))
    ]
    m = arc_burn_metrics(arc)
    assert m is not None
    assert abs(m["burn_gap"]) < 1e-9


def test_slow_burner_positive_gap_and_outstanding_end():
    # unclaimed money lingers (claim lag): u stays at 1.0 while pu falls
    arc = [
        _rec(f"2020-02-{d:02d}", pu, 500000.0,
             status="exited_observed" if pu == 0 else "active")
        for d, pu in zip(range(1, 12), range(100, -1, -10))
    ]
    m = arc_burn_metrics(arc)
    assert m["burn_gap"] > 0.4
    assert m["u_last"] == 1.0
    assert m["exited"] is True and m["near_complete"] is True
    assert m["s_span"] == 1.0


def test_fast_burner_negative_gap():
    # prize money exits ahead of sales (front-loaded wins claimed early)
    pus = list(range(100, 45, -5))
    arc = [
        _rec(f"2020-03-{d:02d}", pu, max((pu / 100) ** 3, 0.001) * 500000)
        for d, pu in zip(range(1, 13), pus)
    ]
    m = arc_burn_metrics(arc)
    assert m["burn_gap"] < -0.05


def test_unusable_arcs_return_none():
    short = [_rec("2020-01-01", 90.0, 1000.0)] * 3
    assert arc_burn_metrics(short) is None
    late_start = [
        _rec(f"2020-01-{d:02d}", pu, 1000.0)
        for d, pu in zip(range(1, 8), range(40, 5, -5))
    ]
    assert arc_burn_metrics(late_start) is None   # first pu < MIN_FIRST_PU


def test_page_correction_upward_is_guarded():
    # a pu correction UP mid-arc must not produce negative sales shares
    arc = [
        _rec("2020-01-01", 90.0, 900.0),
        _rec("2020-01-02", 70.0, 800.0),
        _rec("2020-01-03", 75.0, 780.0),   # correction upward
        _rec("2020-01-04", 60.0, 700.0),
        _rec("2020-01-05", 50.0, 600.0),
    ]
    m = arc_burn_metrics(arc)
    assert m is not None
    assert 0 < m["s_span"] <= 1.0


def test_noncash_null_levels_do_not_crash():
    tops = [{"level": None, "remaining": 3}, {"level": 1000, "remaining": 2}]
    rec = _rec("2020-01-01", 90.0, 900.0, tops=tops)
    assert _top_value(rec) == 2000.0
    s = structural_components([rec], {})
    assert s["log10_top_prize"] == 3.0
    assert s["n_top_tiers"] == 2


# ---------------------------------------------------------------------------
# mechanics parsing
# ---------------------------------------------------------------------------

ARTICLE = """
<html><body><h1>WILD NUMBERS</h1>
<p>Maximum Award: $50,000 Game #777</p>
<p>Match any of YOUR NUMBERS to any of the WINNING NUMBERS, win prize shown.
Reveal a "COIN" symbol, win prize shown instantly.
Get a "10X" symbol, win 10 TIMES the prize shown.</p>
<p>Instructions for ticket back: Match 3 amounts, win that amount.</p>
<p>OVERALL ODDS OF WINNING 1:4.05</p></body></html>
"""


def test_parse_article_mechanics():
    m = parse_article_mechanics(ARTICLE)
    assert m["game_no"] == 777
    assert m["match_rules"] >= 2
    assert m["reveal_rules"] >= 2
    assert m["max_multiplier"] == 10
    assert m["two_sided"] is True
    assert m["instruction_words"] > 10


def test_parse_article_without_game_no_returns_none():
    assert parse_article_mechanics("<html><body>nothing</body></html>") is None


def test_load_mechanics_is_deterministic(tmp_path):
    (tmp_path / "article_b.html").write_text(ARTICLE, encoding="utf-8")
    (tmp_path / "article_a.html").write_text(
        ARTICLE.replace("10X", "5X"), encoding="utf-8")
    out = load_mechanics(tmp_path)
    # sorted order -> article_b (lexically last) wins the duplicate game_no
    assert out[777]["max_multiplier"] == 10


# ---------------------------------------------------------------------------
# spearman + index
# ---------------------------------------------------------------------------

def test_spearman_monotone():
    x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    assert spearman(x, x * 3 + 1) == pytest.approx(1.0)
    assert spearman(x, -x) == pytest.approx(-1.0)


def test_spearman_ci_is_seeded_deterministic():
    rng1 = np.random.default_rng(7)
    rng2 = np.random.default_rng(7)
    x = list(np.linspace(0, 1, 40))
    y = [v + ((i % 5) - 2) * 0.05 for i, v in enumerate(x)]
    assert (spearman_with_ci(x, y, rng1, reps=200)
            == spearman_with_ci(x, y, rng2, reps=200))


def test_complexity_index_range_and_null():
    rows = [{"price": p, "n_top_tiers": 2, "log10_top_prize": 5.0,
             "top_prize_to_price": 100.0, "overall_odds": None}
            for p in (1.0, 2.0, 5.0, 10.0)]
    stats = _zscore_matrix(rows, ("price",))
    idx = complexity_index(rows[-1], None, stats, {})
    assert idx is not None and 0.0 <= idx <= 100.0
    assert complexity_index({"price": None}, None, {}, {}) is None


# ---------------------------------------------------------------------------
# end-to-end on a synthetic panel
# ---------------------------------------------------------------------------

def _write_inputs(tmp_path):
    recs = []
    for g, (price, shape) in enumerate(
        [(1.0, "slow"), (5.0, "uniform"), (10.0, "fast")] * 5
    ):
        game_no = 800 + g
        for d, pu in zip(range(1, 12), range(100, -1, -10)):
            if shape == "slow":
                u = 900000.0
            elif shape == "uniform":
                u = max(pu / 100, 0.001) * 900000
            else:
                u = max((pu / 100) ** 3, 0.001) * 900000
            recs.append(_rec(
                f"2021-03-{d:02d}", float(pu), u, price=price,
                game_no=game_no, name=f"G{game_no}",
                status="exited_observed" if pu == 0 else "active",
            ))
            recs[-1]["game_key"] = f"{game_no}:g{game_no}"
    panel = tmp_path / "panel.jsonl"
    with panel.open("w", encoding="utf-8", newline="\n") as fh:
        for r in recs:
            fh.write(json.dumps(r) + "\n")
    games = tmp_path / "games.json"
    games.write_text(json.dumps({"games": {}}), encoding="utf-8")
    return panel, games


def test_run_study_end_to_end(tmp_path):
    panel, games = _write_inputs(tmp_path)
    doc = run_study(panel, games, None, as_of="2021-04-01", seed=11)
    assert doc["as_of"] == "2021-04-01"
    assert doc["cohorts"]["usable_arcs"] == 15
    assert doc["cohorts"]["near_complete"] == 15
    assert doc["cohorts"]["with_mechanics"] == 0
    assert len(doc["games"]) == 15
    for row in doc["games"]:
        assert row["mechanics"] is None
        assert row["complexity_index"] is not None
    ids = {c["id"] for c in doc["correlations"]}
    assert "complexity_vs_burn_gap" in ids
    # descriptive-honesty contract: caveats always present
    assert any("DESCRIPTIVE" in c for c in doc["caveats"])
    # determinism
    doc2 = run_study(panel, games, None, as_of="2021-04-01", seed=11)
    assert doc == doc2
