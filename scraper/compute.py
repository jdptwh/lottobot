"""Maine Lottery naive EV computation (M3, satellite S2).

Joins the M1 unclaimed-prizes snapshot (``scraper.scrape.parse`` output) with
the M2 per-game metadata (``data/games.json``: ``print_run`` and
``top_prize_value`` only) and computes v1 naive EV per
maine-scratch-ev-spec.md §3, producing the first REAL ``data/latest.json``
(M1 defined the shape with the EV fields left null). All computation is
offline and deterministic; this module never fetches.
``ev_ratio_adjusted`` stays ``null`` until M6 (the claim-lag model).

Public API: :func:`compute_latest`, :func:`diff_gate`, and the
``python -m scraper.compute`` CLI. docs/specs/m3_ev_spec.md is the binding
spec for this file; its "field semantics" and "hand-check worksheet"
sections are the rules of record reproduced in the docstrings/comments below.
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
        args.out.write_text(output, encoding="utf-8")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
