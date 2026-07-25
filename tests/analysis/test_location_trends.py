"""Tests for analysis/location_trends.py — offline, seeded, fast."""
import json
from pathlib import Path

import numpy as np
import pytest

# Harness-packaging-copy skip guard (test_compute.py pattern): analysis/ is
# this project's own code, not part of the installable harness.
if not (Path(__file__).resolve().parents[2] / "analysis" / "location_trends.py").exists():
    pytest.skip(
        "analysis/ is this project's own code, not part of the installable harness",
        allow_module_level=True,
    )

from analysis.location_trends import (
    TOWN_POP_2020,
    gamma_poisson_prior,
    run_trends,
    shrunk_rate,
)


def _winner(key, town, rtown, prize=10000.0, game="SYNTH", gtype="instant",
            retailer="Test Store"):
    return {
        "winner_key": key, "names": ["Test Person"], "town": town,
        "prize": prize, "game": game, "game_type": gtype,
        "retailer": retailer, "retailer_town": rtown,
        "first_seen": "2026-01-01", "source": "seed",
        "capture_url": "x", "capture_ts": "2026-01-01T00:00:00+00:00",
        "content_hash": "0" * 64, "parser_version": "test",
    }


def _write(tmp_path, records):
    p = tmp_path / "winners.jsonl"
    with p.open("w", encoding="utf-8", newline="\n") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")
    return p


# ---------------------------------------------------------------------------
# shrinkage machinery
# ---------------------------------------------------------------------------

def test_prior_recovers_overdispersion():
    # towns with clearly different true rates -> finite a, b with a/b near
    # the exposure-weighted mean rate
    counts = [50, 5, 30, 2, 40, 1]
    expos = [10.0, 10.0, 10.0, 10.0, 10.0, 10.0]
    a, b = gamma_poisson_prior(counts, expos)
    assert a > 0 and b > 0
    assert a / b == pytest.approx(np.mean([c / e for c, e in zip(counts, expos)]),
                                  rel=0.15)


def test_small_n_shrinks_harder_than_large_n():
    a, b = 2.0, 1.0        # prior mean 2 per 10k
    rng = np.random.default_rng(0)
    small = shrunk_rate(6, 0.3, a, b, rng)      # raw rate 20/10k on tiny expo
    rng = np.random.default_rng(0)
    large = shrunk_rate(200, 10.0, a, b, rng)   # raw rate 20/10k on big expo
    # both pulled toward 2, but the small-exposure town far more
    assert small["shrunk_rate_per_10k"] < large["shrunk_rate_per_10k"]
    assert large["shrunk_rate_per_10k"] > 15.0


def test_shrunk_rate_deterministic_given_seed():
    r1 = shrunk_rate(3, 1.0, 2.0, 1.0, np.random.default_rng(9))
    r2 = shrunk_rate(3, 1.0, 2.0, 1.0, np.random.default_rng(9))
    assert r1 == r2


# ---------------------------------------------------------------------------
# end-to-end
# ---------------------------------------------------------------------------

def test_run_trends_end_to_end(tmp_path):
    records = (
        [_winner(f"k{i:02d}", "Portland", "Portland") for i in range(6)]
        + [_winner("k90", "Carthage", "Carthage")]        # n=1, tiny town
        + [_winner("k91", None, "Bangor", gtype="draw")]  # no residence town
        + [_winner("k92", "Nowhereville", "Nowhereville")]  # not in pop table
    )
    path = _write(tmp_path, records)
    doc = run_trends(path, as_of="2026-07-22", seed=5)

    assert doc["inputs"]["n_records"] == 9
    ptowns = {r["town"]: r for r in doc["purchase_towns"]}
    assert ptowns["Portland"]["n"] == 6
    assert ptowns["Portland"]["small_n"] is False
    assert ptowns["Carthage"]["small_n"] is True
    # shrinkage: Carthage n=1 in a 500-person town must NOT top Portland's
    # shrunk rate by the raw-rate ratio (raw would be ~20x Portland's)
    assert (ptowns["Carthage"]["shrunk_rate_per_10k"]
            < ptowns["Carthage"]["raw_rate_per_10k"])
    # unknown town: counts, no rate
    assert ptowns["Nowhereville"]["pop_2020"] is None
    assert ptowns["Nowhereville"]["shrunk_rate_per_10k"] is None
    # residence aggregation excludes the null-town record: Bangor appears
    # only as a PURCHASE town (k91's residence is null), never a residence
    rtowns = {r["town"]: r for r in doc["residence_towns"]}
    assert "Bangor" not in rtowns
    assert sum(r["n"] for r in doc["residence_towns"]) == 8
    # caveats contract: §8 honesty framing always present
    assert any("uniformly random" in c for c in doc["caveats"])
    # determinism
    assert doc == run_trends(path, as_of="2026-07-22", seed=5)


def test_pop_table_is_lowercase_keyed():
    assert all(k == k.lower() for k in TOWN_POP_2020)
    assert TOWN_POP_2020["portland"] > 60000
