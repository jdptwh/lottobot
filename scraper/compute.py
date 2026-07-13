"""Maine Lottery naive EV computation (M3, satellite S2) + M4a scoring.

Joins the M1 unclaimed-prizes snapshot (``scraper.scrape.parse`` output) with
the M2 per-game metadata (``data/games.json``: ``print_run`` and
``top_prize_value`` only) and computes v1 naive EV per
maine-scratch-ev-spec.md §3, producing the first REAL ``data/latest.json``
(M1 defined the shape with the EV fields left null). All computation is
offline and deterministic; this module never fetches.
``ev_ratio_adjusted`` stays ``null`` until M6 (the claim-lag model).

M4a (docs/specs/m4a_scoring_spec.md) additively extends every game with
``value_score`` / ``grade`` / ``rated`` / ``reason``. The daily-relative
score is deliberately computed from the PUBLISHED 6-dp ``ev_ratio`` — not
the raw, unrounded intermediate that M3 used internally — so a human (and
the M4b UI) can reproduce every score from ``latest.json`` alone. Worst-case
drift vs. the raw intermediate is ~1e-4 of a point; immaterial. This is a
documented, pinned deviation from M3's "never compute from an already-
rounded value" rule, scoped to ``value_score`` only — ``ev_ratio`` itself
is still never clamped or recomputed.

W2 (docs/specs/w2_v15_honesty_spec.md) additively extends every game with
six more fields, appended after ``reason`` in this pinned order:
``remaining_tickets_min``, ``remaining_tickets_max``, ``ev_ratio_min``,
``ev_ratio_max``, ``ev_scenarios``, ``overall_odds_launch``.

- **Interval propagation** (documented deviation, M4a-style, scoped to these
  four fields only): the published ``percent_unsold`` is 1 dp, so the true
  percent lies in ``[p - 0.05, p + 0.05]`` (closed, clipped to
  ``[0, 100]``). ``remaining_tickets_min``/``max`` are the int ticket counts
  at those interval ends. ``ev_ratio_max``/``min`` are computed FROM those
  published int ticket ends (not from a raw unrounded intermediate) so a
  human can reproduce both ends from ``latest.json`` alone — fewer tickets
  means higher EV, hence ``ev_ratio_max`` uses ``remaining_tickets_min`` and
  vice versa. All four are ``null`` iff ``ev_ratio`` is ``null`` (pure math
  propagation — they ARE computed for dead/OOR games with a non-null
  ``ev_ratio``). Guard: if ``remaining_tickets_min == 0``, ``ev_ratio_max``
  is ``null`` (unbounded above; never publish infinity or a fake cap).
- **Sensitivity scenarios**: ``SCENARIO_CLAIMED_SHARES`` pins three
  claim-lag what-if shares. For each game with non-null ``ev_ratio``,
  ``ev_scenarios`` is computed via EXACT INTEGER-DECIMAL arithmetic (never
  float) to kill the half-up-midpoint ambiguity that a naive
  ``ev_ratio * (1 - share)`` float computation hits whenever the 6th dp of
  ``ev_ratio`` is odd and share is 0.5. ``ev_scenarios`` is ``null`` (never
  ``[]``) when ``ev_ratio`` is ``null``. These are illustrative scenarios,
  never bounds, never a fitted correction — ``ev_ratio_adjusted`` stays
  ``null`` everywhere; no code path here may write it.
- **Launch odds anchor**: ``overall_odds_launch`` is ``games.json``'s
  ``overall_odds`` for the game_no, carried verbatim (never computed),
  ``null`` when absent.

Public API: :func:`compute_latest`, :func:`diff_gate`, and the
``python -m scraper.compute`` CLI. docs/specs/m3_ev_spec.md is the binding
spec for the M3 fields; docs/specs/m4a_scoring_spec.md is the binding spec
for scoring; docs/specs/w2_v15_honesty_spec.md is the binding spec for the
interval/scenario/launch-odds fields. Their "field semantics" / "hand-check
worksheet" sections are the rules of record reproduced in the
docstrings/comments below.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scraper.scrape import GateError, ParseError, parse, parser_gate

# --------------------------------------------------------------------------
# Module constants (spec: "tunable constants, not schema")
# --------------------------------------------------------------------------

PCT_LOW_INVENTORY = 5.0
PCT_HIGH_CONFIDENCE = 15.0
EV_RATIO_ANOMALY = 0.85
EV_RATIO_RANGE = (0.0, 1.5)
DIFF_MOVE = 0.2
DIFF_SHARE = 0.30

# --------------------------------------------------------------------------
# M4a scoring constants (docs/specs/m4a_scoring_spec.md)
# --------------------------------------------------------------------------

# Value index weighting, keyed off the existing M3 `confidence` field
# (never recomputed here).
SCORE_WEIGHT = {"high": 1.0, "medium": 0.85, "low": 0.45}

# The clamp on ev_ratio applies ONLY inside the value index below; it never
# touches the published `ev_ratio` field (M3's never-clamp rule is unchanged).
SCORE_EV_RATIO_CLAMP = (0.0, 1.5)

# Daily-relative curve: value_score = round(40 + 55 * (idx - idx_min) / span).
SCORE_CURVE_FLOOR = 40
SCORE_CURVE_SPAN = 55

# Degenerate curve (idx_max == idx_min, e.g. exactly one rateable game):
# every rateable game gets this score (the curve's rounded midpoint) rather
# than a promotional 95 — see spec §"Degenerate curve" for the §8 rationale.
DEGENERATE_SCORE = 68

# Grade bands on the rounded int score, checked high-to-low.
GRADE_BANDS = (
    (85, "A"),
    (80, "A-"),
    (75, "B+"),
    (68, "B"),
    (62, "B-"),
    (52, "C"),
    (42, "D"),
)
GRADE_DEFAULT = "F"

# --------------------------------------------------------------------------
# W2 v1.5 honesty constants (docs/specs/w2_v15_honesty_spec.md)
# --------------------------------------------------------------------------

# Pinned claim-lag "what-if" shares (planner's defaults) — illustrative
# scenarios, never bounds, never a fitted correction.
SCENARIO_CLAIMED_SHARES = (0.5, 0.8, 0.95)

# Half of the published percent_unsold's 1-dp rounding step, used to build
# the conservative interval [p - INTERVAL_HALF_STEP, p + INTERVAL_HALF_STEP].
INTERVAL_HALF_STEP = 0.05

# Reason copy bank (planner-authored, BINDING — exact strings; do not reword).
REASONS = {
    "dead": (
        "Top prize already claimed — the biggest advertised win can no "
        "longer be won."
    ),
    "sold_out": (
        "Reported 0% unsold — effectively sold out; there is nothing left "
        "to buy."
    ),
    "no_print_run": (
        "Print run unknown — expected value can't be computed; ranked by "
        "the relative unclaimed-money signal only."
    ),
    "no_data": "Not enough data to compute an expected value for this game.",
    "claim_lag": (
        "Looks better than it is: most unclaimed prize money is likely on "
        "tickets already sold but not yet claimed (claim lag)."
    ),
    "high": (
        "Based on solid inventory data; the expected-value estimate is "
        "comparatively reliable."
    ),
    "medium": (
        "Inventory is thinning; the expected-value estimate carries "
        "moderate uncertainty."
    ),
    "low": (
        "Very little inventory data behind this estimate — treat this "
        "score with caution."
    ),
}


# --------------------------------------------------------------------------
# Small helpers (never raise — a bad/missing top-prize shape just yields None)
# --------------------------------------------------------------------------

def _dead_game(top_prize_value: int | None, top_prizes: list[dict]) -> bool:
    """§4 rule: dead iff ``top_prize_value`` is known and no live tier >= it.

    Null ``top_prize_value`` is "unknown", never "dead" (conservative).
    """
    if top_prize_value is None:
        return False
    for tp in top_prizes:
        if tp["level"] >= top_prize_value and tp["remaining"] >= 1:
            return False
    return True


def _r_top(top_prizes: list[dict]) -> int | None:
    """The ``remaining`` count of the highest ``level`` tier with remaining >= 1.

    ``None`` if no tier has any remaining (all top prizes claimed out).
    """
    live = [tp for tp in top_prizes if tp["remaining"] >= 1]
    if not live:
        return None
    return max(live, key=lambda tp: tp["level"])["remaining"]


def _grade_for_score(score: int) -> str:
    """Pure function: rounded int score -> letter grade via GRADE_BANDS."""
    for floor, letter in GRADE_BANDS:
        if score >= floor:
            return letter
    return GRADE_DEFAULT


def _is_rateable(game: dict) -> bool:
    """Rateable iff not dead, not sold out, print_run known, ev_ratio known."""
    return (
        game["dead_game"] is False
        and "sold_out" not in game["flags"]
        and game["print_run"] is not None
        and game["ev_ratio"] is not None
    )


def _non_rateable_reason(game: dict) -> str:
    """First-match bucket precedence: dead -> sold_out -> no_print_run -> no_data."""
    if game["dead_game"] is True:
        return REASONS["dead"]
    if "sold_out" in game["flags"]:
        return REASONS["sold_out"]
    if game["print_run"] is None:
        return REASONS["no_print_run"]
    return REASONS["no_data"]


def _rateable_reason(game: dict) -> str:
    """Rated reason: claim-lag (ev_out_of_range) beats the confidence bucket."""
    if "ev_out_of_range" in game["flags"]:
        return REASONS["claim_lag"]
    return REASONS[game["confidence"]]


def _value_index(game: dict) -> float:
    """Rateable-only index: clamped ev_ratio (published, 6-dp) * confidence weight.

    The clamp exists ONLY inside this index — it never touches the published
    ``ev_ratio`` field (M3's never-clamp rule is unchanged).
    """
    lo, hi = SCORE_EV_RATIO_CLAMP
    clamped = min(max(game["ev_ratio"], lo), hi)
    return clamped * SCORE_WEIGHT[game["confidence"]]


def _apply_scoring(games: list[dict]) -> None:
    """Mutates each game dict in place, appending value_score/grade/rated/reason.

    Daily-relative over the rateable subset. Degenerate curve (idx_max ==
    idx_min, including the single-rateable-game case) gives every rateable
    game DEGENERATE_SCORE regardless of its position in the (empty) spread.
    """
    rateable_game_nos = {g["game_no"] for g in games if _is_rateable(g)}
    indices = {
        g["game_no"]: _value_index(g)
        for g in games
        if g["game_no"] in rateable_game_nos
    }

    if indices:
        idx_min = min(indices.values())
        idx_max = max(indices.values())
        degenerate = idx_max == idx_min

    for game in games:
        if game["game_no"] not in rateable_game_nos:
            game["value_score"] = None
            game["grade"] = None
            game["rated"] = False
            game["reason"] = _non_rateable_reason(game)
            continue

        if degenerate:
            score = DEGENERATE_SCORE
        else:
            idx = indices[game["game_no"]]
            raw_score = SCORE_CURVE_FLOOR + SCORE_CURVE_SPAN * (
                (idx - idx_min) / (idx_max - idx_min)
            )
            score = round(raw_score)

        game["value_score"] = score
        game["grade"] = _grade_for_score(score)
        game["rated"] = True
        game["reason"] = _rateable_reason(game)


# --------------------------------------------------------------------------
# W2 v1.5 honesty helpers (never raise; pure functions on already-published
# fields so results are hand-reproducible from latest.json alone)
# --------------------------------------------------------------------------

def _interval_fields(
    ev_ratio: float | None,
    percent_unsold: float,
    print_run: int | None,
    total_unclaimed: float,
    price: float,
) -> tuple[int | None, int | None, float | None, float | None]:
    """Interval propagation (Resolution 2): publish BOTH pairs.

    Null iff ``ev_ratio`` is null. ``ev_ratio_max`` is additionally null iff
    ``remaining_tickets_min == 0`` (unbounded above; never a fake cap).
    Deviation from M3's raw-intermediate rule (documented, scoped to these
    four fields): the EV ends are computed FROM the published int ticket
    ends, not from a raw unrounded intermediate, so a human can reproduce
    both ends from latest.json alone.
    """
    if ev_ratio is None:
        return None, None, None, None

    p_lo = max(percent_unsold - INTERVAL_HALF_STEP, 0.0)
    p_hi = min(percent_unsold + INTERVAL_HALF_STEP, 100.0)

    remaining_tickets_min = round(p_lo * print_run / 100)
    remaining_tickets_max = round(p_hi * print_run / 100)

    if remaining_tickets_min == 0:
        ev_ratio_max = None
    else:
        ev_ratio_max = round(total_unclaimed / remaining_tickets_min / price, 6)
    ev_ratio_min = round(total_unclaimed / remaining_tickets_max / price, 6)

    return remaining_tickets_min, remaining_tickets_max, ev_ratio_min, ev_ratio_max


def _ev_scenarios(ev_ratio: float | None) -> list[dict] | None:
    """Sensitivity scenarios (Resolutions 4 + 9): exact integer-decimal math.

    ``null`` (never ``[]``) when ``ev_ratio`` is null. ``n`` is the exact int
    of the published (6-dp) ``ev_ratio`` value; each scenario's ``ev_ratio``
    is half-up rounded to 6 dp via integer arithmetic so s=0.5's exact
    decimal midpoints (whenever the 6th dp of ev_ratio is odd) are
    deterministic and hand-reproducible — never float-naive.
    """
    if ev_ratio is None:
        return None

    n = round(ev_ratio * 10**6)
    scenarios = []
    for share in SCENARIO_CLAIMED_SHARES:
        share_pct = round(share * 100)
        v_int = ((n * (100 - share_pct)) + 50) // 100
        scenarios.append(
            {"assumed_claimed_share": share, "ev_ratio": v_int / 1_000_000}
        )
    return scenarios


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def compute_latest(snapshot: dict, games_meta: dict, as_of: str) -> dict:
    """Build the real ``latest.json`` doc: join snapshot + games_meta, compute EV.

    ``snapshot`` is :func:`scraper.scrape.parse` output. ``games_meta`` is the
    loaded ``data/games.json`` dict (``{"games": {"<game_no>": {...}, ...}}``);
    only ``print_run`` and ``top_prize_value`` are consumed. A game_no absent
    from ``games_meta`` entirely is treated identically to
    ``print_run: null`` / ``top_prize_value: null`` — never a crash.

    Runs :func:`scraper.scrape.parser_gate` on the snapshot first (§6.1 still
    guards). All published floats are ``round(x, 6)`` of full-precision
    intermediates; each field rounds independently (never computed from an
    already-rounded value). ``games`` is sorted by ``game_no`` ascending.
    """
    parser_gate(snapshot)

    meta_games = games_meta.get("games") or {}

    games = []
    for game in snapshot["games"]:
        game_no = game["game_no"]
        meta = meta_games.get(str(game_no)) or {}
        print_run = meta.get("print_run")
        top_prize_value = meta.get("top_prize_value")

        percent_unsold = game["percent_unsold"]
        total_unclaimed = game["total_unclaimed"]
        price = game["price"]
        top_prizes = [dict(tp) for tp in game["top_prizes"]]

        # remaining_tickets: null when print_run is null; else the integer
        # ticket count (percent is 1-dp, so int rounding loses nothing).
        if print_run is None:
            remaining_tickets = None
        else:
            remaining_tickets = round(percent_unsold * print_run / 100)

        # ev_per_ticket / ev_ratio: null when remaining_tickets is null or 0
        # (0% unsold = sold out; EV for a buyer is undefined — the 617 guard).
        # Never clamped, never dropped, never repurposed.
        if remaining_tickets is None or remaining_tickets == 0:
            ev_per_ticket = None
            ev_ratio = None
        else:
            raw_ev_per_ticket = total_unclaimed / remaining_tickets
            ev_per_ticket = round(raw_ev_per_ticket, 6)
            raw_ev_ratio = raw_ev_per_ticket / price
            ev_ratio = round(raw_ev_ratio, 6)

        # relative_score (new, additive): computed for every game with
        # percent_unsold > 0; null at 0. Not comparable to ev_ratio.
        relative_score = (
            round(total_unclaimed / percent_unsold, 6)
            if percent_unsold > 0
            else None
        )

        dead = _dead_game(top_prize_value, top_prizes)

        # top_prize_odds_now (new, additive): null if remaining_tickets is
        # null/0, no live top tier exists, or the game is dead.
        if remaining_tickets is None or remaining_tickets == 0 or dead:
            top_prize_odds_now = None
        else:
            r_top = _r_top(top_prizes)
            top_prize_odds_now = (
                round(remaining_tickets / r_top, 6) if r_top is not None else None
            )

        in_range = ev_ratio is not None and (
            EV_RATIO_RANGE[0] < ev_ratio < EV_RATIO_RANGE[1]
        )

        flags = []
        if 0 < percent_unsold < PCT_LOW_INVENTORY:
            flags.append("low_inventory")
        if percent_unsold == 0.0:
            flags.append("sold_out")
        if ev_ratio is not None and ev_ratio > EV_RATIO_ANOMALY:
            flags.append("anomaly_candidate")
        if ev_ratio is not None and not in_range:
            flags.append("ev_out_of_range")
        if print_run is None:
            flags.append("no_print_run")
        flags.sort()

        if print_run is not None and percent_unsold >= PCT_HIGH_CONFIDENCE and in_range:
            confidence = "high"
        elif (
            print_run is not None
            and PCT_LOW_INVENTORY <= percent_unsold < PCT_HIGH_CONFIDENCE
            and in_range
        ):
            confidence = "medium"
        else:
            confidence = "low"

        games.append(
            {
                "game_no": game_no,
                "name": game["name"],
                "price": price,
                "percent_unsold": percent_unsold,
                "total_unclaimed": total_unclaimed,
                "top_prizes": top_prizes,
                "print_run": print_run,
                "remaining_tickets": remaining_tickets,
                "ev_per_ticket": ev_per_ticket,
                "ev_ratio": ev_ratio,
                "ev_ratio_adjusted": None,
                "relative_score": relative_score,
                "top_prize_odds_now": top_prize_odds_now,
                "dead_game": dead,
                "flags": flags,
                "confidence": confidence,
            }
        )

    games.sort(key=lambda g: g["game_no"])

    # value_score/grade/rated/reason (M4a) are inserted in place, in this
    # order, immediately after "confidence" (byte-stable diffs, per spec) —
    # dict insertion order already puts them there since "confidence" is the
    # last key set above and these are the first keys _apply_scoring adds.
    _apply_scoring(games)

    # W2 v1.5 honesty fields: appended after "reason", in this pinned order
    # (byte-stable diffs, M4a precedent) — dict insertion order already
    # puts them there since "reason" is the last key _apply_scoring sets.
    for game in games:
        meta = meta_games.get(str(game["game_no"])) or {}
        (
            remaining_tickets_min,
            remaining_tickets_max,
            ev_ratio_min,
            ev_ratio_max,
        ) = _interval_fields(
            game["ev_ratio"],
            game["percent_unsold"],
            game["print_run"],
            game["total_unclaimed"],
            game["price"],
        )
        game["remaining_tickets_min"] = remaining_tickets_min
        game["remaining_tickets_max"] = remaining_tickets_max
        game["ev_ratio_min"] = ev_ratio_min
        game["ev_ratio_max"] = ev_ratio_max
        game["ev_scenarios"] = _ev_scenarios(game["ev_ratio"])
        game["overall_odds_launch"] = meta.get("overall_odds")

    return {
        "as_of": as_of,
        "source_timestamp": snapshot["source_timestamp"],
        "games": games,
    }


def diff_gate(new_doc: dict, prior_doc: dict) -> None:
    """§6.4: hold the commit if a probable parse breakage is detected.

    Pairs games by ``game_no``; a pair counts only if ``ev_ratio`` is
    non-null in BOTH documents. Raises :class:`scraper.scrape.GateError` if
    pairs > 0 and the share of pairs with ``|Δev_ratio| > 0.2`` exceeds 0.30.
    Zero pairs (e.g. the inert first run) passes silently.
    """
    prior_by_no = {g["game_no"]: g for g in prior_doc.get("games", [])}

    total_pairs = 0
    moved = 0
    for new_game in new_doc.get("games", []):
        prior_game = prior_by_no.get(new_game["game_no"])
        if prior_game is None:
            continue
        new_ratio = new_game.get("ev_ratio")
        prior_ratio = prior_game.get("ev_ratio")
        if new_ratio is None or prior_ratio is None:
            continue
        total_pairs += 1
        if abs(new_ratio - prior_ratio) > DIFF_MOVE:
            moved += 1

    if total_pairs == 0:
        return

    share = moved / total_pairs
    if share > DIFF_SHARE:
        raise GateError(
            f"diff gate: {moved}/{total_pairs} paired games ({share:.1%}) moved "
            f"ev_ratio by more than {DIFF_MOVE} (share exceeds the "
            f"{DIFF_SHARE:.0%} threshold) — probable parse breakage, holding "
            "the commit"
        )


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scraper.compute",
        description=(
            "Compute v1 naive EV into latest.json from the unclaimed-prizes "
            "snapshot + data/games.json. Never fetches."
        ),
    )
    parser.add_argument(
        "--unclaimed",
        type=Path,
        required=True,
        help="path to the unclaimed-prizes HTML (frozen fixture)",
    )
    parser.add_argument(
        "--games", type=Path, required=True, help="path to data/games.json"
    )
    parser.add_argument(
        "--as-of",
        required=True,
        help="ISO date to stamp as_of with (run truth; never generated)",
    )
    parser.add_argument(
        "--prior",
        type=Path,
        default=None,
        help=(
            "path to a prior latest.json for the §6.4 diff gate; missing or "
            "omitted means an inert first run (no gate check)"
        ),
    )
    parser.add_argument(
        "--out", type=Path, default=None, help="write output here (default: stdout)"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    try:
        html = args.unclaimed.read_text(encoding="utf-8")
        snapshot = parse(html)
        games_meta = json.loads(args.games.read_text(encoding="utf-8"))
        new_doc = compute_latest(snapshot, games_meta, args.as_of)

        if args.prior is not None and args.prior.exists():
            prior_doc = json.loads(args.prior.read_text(encoding="utf-8"))
            diff_gate(new_doc, prior_doc)
        else:
            print(
                "note: no prior latest.json given/found; diff gate skipped "
                "(inert first run)",
                file=sys.stderr,
            )
    except (ParseError, GateError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    output = json.dumps(new_doc, indent=2)
    if args.out is not None:
        args.out.write_text(output, encoding="utf-8", newline="\n")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
