"""Winner-location trend study (descriptive, empirical-Bayes shrunk).

Spec: docs/specs/winners_location_spec.md. DEV-ONLY analysis over
``data/winners/winners.jsonl`` (built by ``scraper/winners.py``). Produces
``data/insights/location_trends.json`` for the site's location panel.

What this is (and is honestly NOT):

- Maine's winner publicity means claimed prizes are public records, and the
  lottery's Winner Information page names the winner, hometown, game, prize
  and — the signal of record here — the RETAILER and TOWN where the ticket
  was sold. This module aggregates those into purchase-town and
  residence-town trends.
- The showcase is a CURATED sample (a rotating handful of recent claims,
  no dates, big-prize skew), not the statutory complete winner ledger. All
  outputs therefore describe *published winners*, never win probability.
  Every unsold ticket is uniformly random wherever it is sold — the §8
  framing is repeated in the artifact's caveats and must stay in the UI.
- Per-capita rates use an embedded 2020-Census-rounded town population
  table (approximate by design, source-labeled). Towns not in the table
  get counts but no rate. Empirical-Bayes Gamma-Poisson shrinkage pulls
  small-n towns toward the statewide mean so a single lucky gas station
  town cannot top the board on n=1; intervals are seeded posterior-draw
  percentiles. DESCRIPTIVE ONLY — no significance claims (M6b discipline).

CLI:
    python -m analysis.location_trends \
        --winners data/winners/winners.jsonl --as-of 2026-07-22 \
        --out data/insights/location_trends.json

Deterministic (seeded), offline, LF-only writes. Public API: :func:`run_trends`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

DEFAULT_SEED = 20260722
POSTERIOR_DRAWS = 4000
ROUND_DP = 4
SMALL_N = 3          # n < SMALL_N → flagged small-sample
INTERVAL = (5.0, 95.0)   # posterior percentile interval (90%)

# 2020 US Census populations, rounded to the nearest hundred — an embedded
# APPROXIMATE exposure table for per-capita rates (source: census.gov 2020
# redistricting counts; minor places rounded). Towns absent here still get
# counts, just no rate. Keys are lowercase.
TOWN_POP_2020 = {
    "portland": 68400, "lewiston": 37100, "bangor": 31800,
    "south portland": 26500, "auburn": 24100, "biddeford": 22600,
    "scarborough": 22600, "sanford": 21900, "brunswick": 21700,
    "saco": 20400, "westbrook": 20400, "augusta": 18900,
    "windham": 18400, "gorham": 18300, "york": 13700,
    "falmouth": 12400, "waterville": 15800, "kennebunk": 11500,
    "orono": 11200, "standish": 10200, "wells": 11300,
    "topsham": 9600, "kittery": 10100, "brewer": 9700,
    "cape elizabeth": 9500, "old orchard beach": 8900, "yarmouth": 8900,
    "bath": 8800, "freeport": 8700, "belfast": 6900, "ellsworth": 8400,
    "old town": 7400, "gray": 8300, "buxton": 8300, "cumberland": 8500,
    "lisbon": 9300, "skowhegan": 8600, "caribou": 7400,
    "presque isle": 8800, "hampden": 7700, "rockland": 6900,
    "gardiner": 5600, "farmington": 7600, "berwick": 7800,
    "south berwick": 7500, "north berwick": 5000, "eliot": 6700,
    "winslow": 7900, "waterboro": 8100, "harpswell": 5000,
    "raymond": 4500, "poland": 5900, "camden": 5200, "turner": 5800,
    "oakland": 6300, "sabattus": 5000, "winthrop": 5900,
    "fairfield": 6500, "houlton": 6100, "millinocket": 4100,
    "rumford": 5500, "mexico": 2700, "paris": 5200, "norway": 5100,
    "jay": 4700, "livermore falls": 3200, "livermore": 2200,
    "madawaska": 3900, "fort kent": 4100, "van buren": 1900,
    "calais": 3100, "machias": 2000, "dover-foxcroft": 4200,
    "dexter": 3800, "pittsfield": 3900, "newport": 3100,
    "hartland": 1800, "clinton": 3300, "glenburn": 4600,
    "hermon": 6400, "holden": 3100, "orrington": 3800, "bucksport": 4900,
    "thomaston": 2800, "warren": 4900, "waldoboro": 5200,
    "damariscotta": 2300, "wiscasset": 3700, "boothbay harbor": 2000,
    "jefferson": 2600, "phippsburg": 2200, "friendship": 1100,
    "dixfield": 2300, "carthage": 500, "andover": 700, "roxbury": 400,
    "shapleigh": 2900, "canaan": 2100, "corinth": 2900, "exeter": 1000,
    "monmouth": 4100, "richmond": 3600, "bowdoinham": 3100,
    "bridgton": 5400, "naples": 4100, "casco": 3600, "fryeburg": 3400,
    "bethel": 2500, "greenville": 1400, "lincoln": 4900, "milo": 2200,
    "east millinocket": 1500, "medway": 1200, "patten": 900,
    "ashland": 1200, "fort fairfield": 3200, "limestone": 1800,
    "mars hill": 1400, "washburn": 1500, "eagle lake": 800,
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_winners(path: Path) -> list[dict]:
    records = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


# --------------------------------------------------------------------------
# Empirical-Bayes Gamma-Poisson shrinkage
# --------------------------------------------------------------------------

def gamma_poisson_prior(counts: list[int], exposures: list[float]) -> tuple:
    """Method-of-moments Gamma(a, b) prior over per-10k rates.

    Degenerate data (no measurable between-town overdispersion) falls back
    to a WIDE unit-shape prior centered on the pooled mean — strong
    shrinkage with honestly wide intervals, rather than a crash or a fake
    tight spread.
    """
    counts_a = np.asarray(counts, dtype=float)
    expo_a = np.asarray(exposures, dtype=float)
    pooled = counts_a.sum() / expo_a.sum()
    rates = counts_a / expo_a
    mean = float(np.average(rates, weights=expo_a))
    var = float(np.average((rates - mean) ** 2, weights=expo_a))
    # subtract Poisson sampling noise to estimate between-town variance
    sampling = float(np.average(rates / expo_a, weights=expo_a))
    between = max(var - sampling, 0.0)
    if between <= 0 or mean <= 0:
        # No measurable between-town spread (typical at small n): fall back
        # to a WIDE unit-shape prior centered on the pooled mean (CV = 1)
        # so shrinkage is strong but intervals stay honestly wide.
        a = 1.0
        b = 1.0 / max(pooled, 1e-9)
    else:
        a = mean ** 2 / between
        b = mean / between
    return float(a), float(b)


def shrunk_rate(
    n: int, exposure: float, a: float, b: float,
    rng: np.random.Generator,
) -> dict:
    """Posterior Gamma(a+n, b+exposure) summary via seeded draws."""
    post_a, post_b = a + n, b + exposure
    draws = rng.gamma(post_a, 1.0 / post_b, POSTERIOR_DRAWS)
    lo, hi = np.percentile(draws, INTERVAL)
    return {
        "shrunk_rate_per_10k": round(post_a / post_b, ROUND_DP),
        "interval90_per_10k": [round(float(lo), ROUND_DP),
                               round(float(hi), ROUND_DP)],
    }


# --------------------------------------------------------------------------
# Study driver
# --------------------------------------------------------------------------

def _aggregate(records: list[dict], key_field: str) -> dict[str, dict]:
    towns: dict[str, dict] = defaultdict(
        lambda: {"n": 0, "total_prize": 0.0, "games": set(), "retailers": set()}
    )
    for rec in records:
        town = rec.get(key_field)
        if not town:
            continue
        t = towns[town.strip()]
        t["n"] += 1
        if rec.get("prize"):
            t["total_prize"] += rec["prize"]
        if rec.get("game"):
            t["games"].add(rec["game"])
        if rec.get("retailer"):
            t["retailers"].add(rec["retailer"])
    return towns


def _town_rows(
    towns: dict[str, dict], total_n: int, rng: np.random.Generator,
) -> list[dict]:
    known = {
        name: TOWN_POP_2020[name.lower()]
        for name in towns if name.lower() in TOWN_POP_2020
    }
    covered_pop = sum(known.values())
    rows = []

    counts = [towns[name]["n"] for name in known]
    exposures = [pop / 10000.0 for pop in known.values()]
    a = b = None
    if len(known) >= 3:
        a, b = gamma_poisson_prior(counts, exposures)

    for name in sorted(towns, key=lambda t: (-towns[t]["n"], t)):
        agg = towns[name]
        pop = known.get(name)
        row = {
            "town": name,
            "n": agg["n"],
            "total_prize": round(agg["total_prize"], 2),
            "n_games": len(agg["games"]),
            "n_retailers": len(agg["retailers"]),
            "pop_2020": pop,
            "small_n": agg["n"] < SMALL_N,
            "raw_rate_per_10k": (
                round(agg["n"] / (pop / 10000.0), ROUND_DP) if pop else None
            ),
            "expected_uniform": (
                round(total_n * pop / covered_pop, ROUND_DP)
                if pop and covered_pop else None
            ),
        }
        if pop and a is not None:
            row.update(shrunk_rate(agg["n"], pop / 10000.0, a, b, rng))
        else:
            row["shrunk_rate_per_10k"] = None
            row["interval90_per_10k"] = None
        rows.append(row)
    return rows


def run_trends(
    winners_path: Path, as_of: str, seed: int = DEFAULT_SEED,
) -> dict:
    records = load_winners(winners_path)
    instant = [r for r in records if r["game_type"] == "instant"]

    purchase = _aggregate(records, "retailer_town")
    residence = _aggregate(records, "town")

    rng = np.random.default_rng(seed)
    n_purchase = sum(t["n"] for t in purchase.values())
    n_residence = sum(t["n"] for t in residence.values())
    purchase_rows = _town_rows(purchase, n_purchase, rng)
    residence_rows = _town_rows(residence, n_residence, rng)

    retailers: dict[tuple, dict] = defaultdict(
        lambda: {"n": 0, "total_prize": 0.0}
    )
    for rec in records:
        if rec.get("retailer"):
            key = (rec["retailer"], rec.get("retailer_town") or "")
            retailers[key]["n"] += 1
            if rec.get("prize"):
                retailers[key]["total_prize"] += rec["prize"]
    retailer_rows = [
        {"retailer": name, "town": town or None, "n": agg["n"],
         "total_prize": round(agg["total_prize"], 2)}
        for (name, town), agg in sorted(
            retailers.items(), key=lambda kv: (-kv[1]["n"], kv[0])
        )
    ]

    return {
        "as_of": as_of,
        "params": {
            "seed": seed,
            "posterior_draws": POSTERIOR_DRAWS,
            "small_n_threshold": SMALL_N,
            "interval": "90% posterior percentile",
            "population_source": "US Census 2020, rounded (embedded table)",
        },
        "inputs": {
            "winners_path": str(winners_path).replace("\\", "/"),
            "winners_sha256": _sha256(winners_path),
            "n_records": len(records),
            "n_instant": len(instant),
            "sources": sorted({r["source"] for r in records}),
        },
        "caveats": [
            "DESCRIPTIVE ONLY. Winner locations describe where PUBLISHED "
            "winners bought or lived — they carry zero information about "
            "where future winning tickets will be sold. Every unsold "
            "ticket is uniformly random (§8 framing, binding).",
            "The Winner Information page is a curated rotating sample "
            "with no dates, skewed to larger prizes — not Maine's "
            "complete winner ledger.",
            "Purchase-town (where the ticket was sold) is the location "
            "signal of record; winner residence is secondary.",
            "Per-capita rates use an approximate embedded 2020 Census "
            "table; towns not in the table get counts only.",
            "Empirical-Bayes shrinkage pulls small samples toward the "
            "statewide mean; n < 3 rows are additionally flagged.",
            "The page publishes no dates, so identical repeat claims "
            "(same names, town, game, prize, retailer) collapse into one "
            "record — a conservative undercount by design.",
        ],
        "purchase_towns": purchase_rows,
        "residence_towns": residence_rows,
        "retailers": retailer_rows,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m analysis.location_trends",
        description="Winner-location descriptive trends "
                    "(offline, deterministic).",
    )
    ap.add_argument("--winners", type=Path, required=True)
    ap.add_argument("--as-of", required=True)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)

    try:
        doc = run_trends(args.winners, args.as_of, args.seed)
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    payload = json.dumps(doc, indent=1)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(payload + "\n")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
