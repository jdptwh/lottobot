"""Maine Fast Play (terminal-generated instant games) EV extension — v1.

Parses the state's daily Fast Play "unclaimed/unsold" disclosure
(https://www.mainelottery.com/fastplay/unclaimed_fastplay.html), enforces a
parser gate by analogy to the scratch pipeline's §6.1, and computes a
schema-conformant ``fastplay.json`` doc using the scratch scoring
methodology BY ANALOGY (docs/specs/m4a_scoring_spec.md + scraper/compute.py)
— never by shared code. This module is a self-contained, independently
regenerable pipeline: per docs/specs/fastplay_extension_spec.md D8, it may
import ONLY ``USER_AGENT``, ``FETCH_TIMEOUT_S``, ``ParseError``,
``GateError``, ``RobotsDisallowed`` from :mod:`scraper.scrape`, and it MUST
NOT import ``scraper.compute`` at all — the scratch curve stays untouchable.

**v1 EV posture (D1, binding):** no print-run source exists yet for Fast
Play, so ``data/fastplay_games.json`` ships as an empty metadata seam
(``{"games": {}}``). Every game therefore takes the ``no_print_run`` path:
``ev_ratio: null``, ``rated: false``, ``value_score: null``, ``grade: null``.
A follow-on task can light up real EV/grades with ZERO code change here by
populating that file with real ``print_run``/``top_prize_value``/
``overall_odds`` data.

**Progressive-jackpot guard (D2, binding):** the page never publishes a
live jackpot dollar value, and it is unverified whether the published
dollar column includes any jackpot amount for a progressive row. Any game
flagged ``progressive_jackpot`` (D9: any ``top_prizes`` item with
``level: null``) has ``ev_per_ticket``/``ev_ratio`` forced ``null`` in code
— an unconditional guard, not just an artifact of missing metadata — so a
silently wrong EV number can never be published for these games, even after
the D1 follow-on lands real print-run data.

**D10 column-semantics finding (recorded here + in the CP3 spike report):**
the live Fast Play page's dollar column is literally headed "Total Unsold"
(not "Total Unclaimed" as on the scratch page), which is exactly the
ambiguity docs/reports/edge_research_2026-07-26.md flagged ("total unsold
dollars") and D10 condition 1 exists to catch. Fixture-review finding: the
SAME scratch page already mixes this vocabulary internally — its own intro
sentence reads "the list of top unclaimed prizes", its percent column is
literally headed "Percent Unsold", and its prize-count column is headed
"Top Prize(s) Unclaimed", all on one page describing one underlying
quantity. Given the publisher already treats "unsold" and "unclaimed" as
loose synonyms on the page whose semantics are already relied on
(``total_unclaimed``), the Fast Play page's parallel "Total Unsold" /
"Top Prize(s) Unsold" headers read as the same house style, not evidence of
a genuinely different measure. D10 condition 1 is therefore judged CLEARED
(not triggered): the field keeps the name ``total_unclaimed`` and the
scratch upper-bound honesty framing applies verbatim, per D10's default.
D10 condition 2 (table structure) is also cleared: the page uses the
identical 7-``<td>``-cell layout, cell order, and blank-leading-cells
continuation-row pattern as the scratch page.

**D9 fixture cross-check:** every fixture game whose name contains
"PROGRESSIVE" (or the truncated "MAINE CA$H MULTIPLIER PROGRESS") does
carry a ``JACKPOT`` top-prize-level cell and therefore does receive the
``progressive_jackpot`` flag structurally (never by name-matching) — no
mismatch found.

Public API: :func:`parse`, :func:`parser_gate`, :func:`compute_fastplay`,
:func:`fetch`, and the ``python -m scraper.fastplay`` CLI.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
import urllib.robotparser
from pathlib import Path
from urllib.parse import urlparse

import jsonschema
import requests
from bs4 import BeautifulSoup

from scraper.scrape import FETCH_TIMEOUT_S, USER_AGENT, GateError, ParseError, RobotsDisallowed

PAGE_URL = "https://www.mainelottery.com/fastplay/unclaimed_fastplay.html"

REQUIRED_GAME_FIELDS_FASTPLAY = (
    "game_no", "name", "price", "percent_unsold", "total_unclaimed",
)

# D3: sanity floors. MIN_GAMES_FASTPLAY=20 is fixed by the spec (the memo
# verified 28-30 active games on 2026-07-25; 20 is a 71%-of-low-end
# cushion, the same philosophy as scratch's 40-of-65).
MIN_GAMES_FASTPLAY = 20

# MIN_TOTAL_UNCLAIMED_FASTPLAY (D3 pinned formula):
#   0.25 x sum(total_unclaimed across the frozen fixture), rounded DOWN to
#   one significant figure.
# Source: tests/scraper/fixtures/unclaimed_fastplay_2026-07-27.html (28
# games), sum(total_unclaimed) = $107,852,508.00.
#   0.25 x 107,852,508.00 = 26,963,127.00
#   rounded down to 1 sig fig (leading digit 2, at the ten-millions place)
#   -> $20,000,000
# Asserted against this exact derivation by a CP1 test
# (tests/scraper/test_fastplay.py).
MIN_TOTAL_UNCLAIMED_FASTPLAY = 20_000_000

# --------------------------------------------------------------------------
# M4a scoring constants (D8): OWN copies, intentionally identical in value to
# scraper.compute's — a test asserts equality; intentional divergence
# requires a spec amendment that updates that test.
# --------------------------------------------------------------------------

SCORE_WEIGHT = {"high": 1.0, "medium": 0.85, "low": 0.45}
SCORE_EV_RATIO_CLAMP = (0.0, 1.5)
SCORE_CURVE_FLOOR = 40
SCORE_CURVE_SPAN = 55
DEGENERATE_SCORE = 68
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
# M3-analog EV/confidence constants — Fast Play's own copies (scoring
# conventions extended by analogy per the spec's governing authorities;
# not covered by the D8 parity test, which is scoped to the M4a list above).
# --------------------------------------------------------------------------

PCT_LOW_INVENTORY = 5.0
PCT_HIGH_CONFIDENCE = 15.0
EV_RATIO_ANOMALY = 0.85
EV_RATIO_RANGE = (0.0, 1.5)

# --------------------------------------------------------------------------
# Binding copy bank (planner-authored — exact strings; do not reword).
# Bucket precedence (first match wins):
#   progressive_jackpot -> dead -> sold_out -> no_print_run -> no_data.
# --------------------------------------------------------------------------

FASTPLAY_REASONS = {
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

# NOT part of the binding FASTPLAY_REASONS copy bank above (which the spec
# pins exactly, 5 keys). This is a locally-scoped, currently-DORMANT
# extension for the "rated" path (D1: every real v1 game is non-rateable,
# since data/fastplay_games.json ships empty, so this dict is exercised only
# by the AC-4 synthetic scoring test, never by production data). Reproduced
# verbatim from scraper.compute's REASONS strings ("scoring conventions
# extended by analogy, not shared code") as a placeholder; a follow-on task
# that populates real print-run metadata should have its own copy-bank
# review before this path ever ships live copy.
_RATED_REASON_COPY = {
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
# Cell parsing helpers (own copies — no import from scraper.scrape's parser
# internals per D8; only the four names listed at module top are shared).
# --------------------------------------------------------------------------

def _is_blank(cell_text: str) -> bool:
    return cell_text.replace("\xa0", " ").strip() == ""


def _parse_money(cell_text: str) -> float:
    text = cell_text.replace("\xa0", " ").strip().replace("$", "").replace(",", "")
    try:
        return float(text)
    except ValueError as exc:
        raise ParseError(f"malformed money cell: {cell_text!r}") from exc


def _parse_percent(cell_text: str) -> float:
    text = cell_text.replace("\xa0", " ").strip()
    try:
        return float(text)
    except ValueError as exc:
        raise ParseError(f"malformed percent cell: {cell_text!r}") from exc


def _parse_int(cell_text: str) -> int:
    text = cell_text.replace("\xa0", " ").strip()
    try:
        return int(text)
    except ValueError as exc:
        raise ParseError(f"malformed integer cell: {cell_text!r}") from exc


def _parse_prize_level(cell_text: str):
    """Tolerant BY DEFAULT (D9 — unlike scratch, where tolerance is opt-in).

    Returns ``int`` for a numeric cell. On a non-numeric cell (observed live
    as "JACKPOT"), returns ``(None, label)`` where ``label`` is the cell text
    verbatim with internal whitespace normalized — never raises.
    """
    text = cell_text.replace("\xa0", " ").strip().replace("$", "").replace(",", "")
    try:
        return int(text)
    except ValueError:
        label = " ".join(cell_text.replace("\xa0", " ").split())
        return None, label


def _prize_item(raw_level, remaining: int) -> dict:
    if isinstance(raw_level, tuple):
        level, level_label = raw_level
        return {"level": level, "level_label": level_label, "remaining": remaining}
    return {"level": raw_level, "remaining": remaining}


def _extract_timestamp(soup: BeautifulSoup) -> str:
    for p in soup.find_all("p"):
        text = p.get_text()
        idx = text.find("as of ")
        if idx != -1:
            return text[idx + len("as of ") :].strip()
    raise ParseError("could not find an 'as of <timestamp>' paragraph")


# --------------------------------------------------------------------------
# Public API: parse / gate
# --------------------------------------------------------------------------

def parse(html: str) -> dict:
    """Parse the Fast Play unclaimed/unsold HTML into
    ``{"source_timestamp", "games"}``.

    ``games`` is a list of dicts (page order):
    ``{"game_no": int, "name": str, "price": float, "percent_unsold": float,
    "total_unclaimed": float, "top_prizes": [...]}``. Progressive rows yield
    ``{"level": None, "level_label": "<verbatim>", "remaining": int}``
    top_prizes items without raising (D9, tolerant by default).

    Raises :class:`~scraper.scrape.ParseError` on a missing table, an orphan
    continuation row, a row with other than 7 ``<td>`` cells, or a malformed
    non-prize-level cell value.
    """
    soup = BeautifulSoup(html, "html.parser")
    source_timestamp = _extract_timestamp(soup)

    table = soup.find("table", class_="tbstriped")
    if table is None:
        raise ParseError("missing data table (table.tbstriped)")

    games: list[dict] = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if not tds:
            continue  # header row (all <th>)
        if len(tds) != 7:
            raise ParseError(f"expected 7 <td> cells in data row, got {len(tds)}")

        cells = [td.get_text() for td in tds]

        if all(_is_blank(c) for c in cells[:5]):
            # Continuation row: (level, count) appends to the previous game.
            if not games:
                raise ParseError(
                    "orphan continuation row: no preceding game row to attach to"
                )
            raw_level = _parse_prize_level(cells[5])
            remaining = _parse_int(cells[6])
            games[-1]["top_prizes"].append(_prize_item(raw_level, remaining))
            continue

        price = _parse_money(cells[0])
        game_no = _parse_int(cells[1])
        name = cells[2].replace("\xa0", " ").strip()
        percent_unsold = _parse_percent(cells[3])
        total_unclaimed = _parse_money(cells[4])
        raw_level = _parse_prize_level(cells[5])
        remaining = _parse_int(cells[6])

        games.append(
            {
                "game_no": game_no,
                "name": name,
                "price": price,
                "percent_unsold": percent_unsold,
                "total_unclaimed": total_unclaimed,
                "top_prizes": [_prize_item(raw_level, remaining)],
            }
        )

    return {"source_timestamp": source_timestamp, "games": games}


def parser_gate(snapshot: dict) -> None:
    """D3 floors: raise :class:`~scraper.scrape.GateError` naming the failed check."""
    games = snapshot.get("games") or []

    if len(games) < MIN_GAMES_FASTPLAY:
        raise GateError(
            f"parser gate: only {len(games)} games parsed "
            f"(< {MIN_GAMES_FASTPLAY} floor)"
        )

    for idx, game in enumerate(games):
        for field in REQUIRED_GAME_FIELDS_FASTPLAY:
            if game.get(field) is None:
                raise GateError(
                    f"parser gate: game at index {idx} "
                    f"(game_no={game.get('game_no')!r}) missing required field "
                    f"'{field}'"
                )

    total_unclaimed = sum(game["total_unclaimed"] for game in games)
    if total_unclaimed <= MIN_TOTAL_UNCLAIMED_FASTPLAY:
        raise GateError(
            f"parser gate: sum(total_unclaimed)={total_unclaimed} does not "
            f"exceed the ${MIN_TOTAL_UNCLAIMED_FASTPLAY:,} sanity floor"
        )


# --------------------------------------------------------------------------
# Scoring helpers (by analogy to scraper.compute; NOT imported from it — D8)
# --------------------------------------------------------------------------

def _dead_game(top_prize_value: int | None, top_prizes: list[dict]) -> bool:
    """§4-style rule, extended for D9 progressive tiers: dead iff
    ``top_prize_value`` is known and no live tier >= it.

    Null ``top_prize_value`` is "unknown", never "dead" (conservative). A
    progressive (``level: None``) tier is structurally the game's top tier
    by definition — its ``level`` can't be numerically compared to
    ``top_prize_value``, so a live (``remaining >= 1``) progressive tier
    unconditionally counts as "top prize still live" rather than raising or
    silently mis-comparing ``None``.
    """
    if top_prize_value is None:
        return False
    for tp in top_prizes:
        if tp["level"] is None:
            if tp["remaining"] >= 1:
                return False
            continue
        if tp["level"] >= top_prize_value and tp["remaining"] >= 1:
            return False
    return True


def _grade_for_score(score: int) -> str:
    for floor, letter in GRADE_BANDS:
        if score >= floor:
            return letter
    return GRADE_DEFAULT


def _is_rateable(game: dict) -> bool:
    """Rateable iff not progressive, not dead, not sold out, print_run known,
    ev_ratio known (D2's progressive exclusion comes first in precedence)."""
    return (
        "progressive_jackpot" not in game["flags"]
        and game["dead_game"] is False
        and "sold_out" not in game["flags"]
        and game["print_run"] is not None
        and game["ev_ratio"] is not None
    )


def _non_rateable_reason(game: dict) -> str:
    """Bucket precedence: progressive_jackpot -> dead -> sold_out ->
    no_print_run -> no_data."""
    if "progressive_jackpot" in game["flags"]:
        return FASTPLAY_REASONS["progressive_jackpot"]
    if game["dead_game"] is True:
        return FASTPLAY_REASONS["dead"]
    if "sold_out" in game["flags"]:
        return FASTPLAY_REASONS["sold_out"]
    if game["print_run"] is None:
        return FASTPLAY_REASONS["no_print_run"]
    return FASTPLAY_REASONS["no_data"]


def _rateable_reason(game: dict) -> str:
    if "ev_out_of_range" in game["flags"]:
        return _RATED_REASON_COPY["claim_lag"]
    return _RATED_REASON_COPY[game["confidence"]]


def _value_index(game: dict) -> float:
    lo, hi = SCORE_EV_RATIO_CLAMP
    clamped = min(max(game["ev_ratio"], lo), hi)
    return clamped * SCORE_WEIGHT[game["confidence"]]


def _apply_scoring(games: list[dict]) -> None:
    """Mutates each game dict in place, appending value_score/grade/rated/reason.

    Daily-relative over the rateable subset; identical mechanics to
    scraper.compute's ``_apply_scoring`` (degenerate curve included), by
    analogy, not by shared code (D8).
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
# Public API: compute
# --------------------------------------------------------------------------

def compute_fastplay(snapshot: dict, games_meta: dict, as_of: str) -> dict:
    """Build the ``fastplay.json`` doc: join snapshot + games_meta, compute EV.

    ``snapshot`` is :func:`parse` output. ``games_meta`` is the loaded
    ``data/fastplay_games.json`` dict (``{"games": {"<game_no>": {...}}}``,
    D1); only ``print_run`` and ``top_prize_value`` are consumed here. A
    game_no absent from ``games_meta`` (the v1 default: EVERY game_no, since
    the committed seam is ``{"games": {}}``) is treated identically to
    ``print_run: null`` / ``top_prize_value: null`` — never a crash.

    D2 progressive guard: a ``progressive_jackpot``-flagged game has
    ``ev_per_ticket``/``ev_ratio`` forced ``null`` unconditionally in code,
    regardless of what ``games_meta`` supplies (even after a future
    print-run-populating task lands).

    Runs :func:`parser_gate` on the snapshot first. All published floats
    are ``round(x, 6)``. ``games`` is sorted by ``game_no`` ascending.
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

        progressive = any(tp["level"] is None for tp in top_prizes)

        if print_run is None:
            remaining_tickets = None
        else:
            remaining_tickets = round(percent_unsold * print_run / 100)

        if remaining_tickets is None or remaining_tickets == 0:
            ev_per_ticket = None
            ev_ratio = None
        else:
            raw_ev_per_ticket = total_unclaimed / remaining_tickets
            ev_per_ticket = round(raw_ev_per_ticket, 6)
            raw_ev_ratio = raw_ev_per_ticket / price
            ev_ratio = round(raw_ev_ratio, 6)

        if progressive:
            # D2 guard: unconditional, code-level. The page's jackpot
            # treatment in the dollar column is unverified, so no EV number
            # (numerator or ratio) is ever published for a progressive game.
            ev_per_ticket = None
            ev_ratio = None

        relative_score = (
            round(total_unclaimed / percent_unsold, 6)
            if percent_unsold > 0
            else None
        )

        dead = _dead_game(top_prize_value, top_prizes)

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
        if progressive:
            flags.append("progressive_jackpot")
        flags.sort()

        if (
            print_run is not None
            and percent_unsold >= PCT_HIGH_CONFIDENCE
            and in_range
        ):
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
                "dead_game": dead,
                "flags": flags,
                "confidence": confidence,
            }
        )

    games.sort(key=lambda g: g["game_no"])

    # value_score/grade/rated/reason (M4a-by-analogy) inserted in place,
    # immediately after "confidence" (byte-stable diffs, per M4a precedent).
    _apply_scoring(games)

    return {
        "as_of": as_of,
        "source_timestamp": snapshot["source_timestamp"],
        "games": games,
    }


def fetch(url: str = PAGE_URL) -> str:
    """Politely fetch ``url``: robots.txt check, shared UA, 30s timeout, no retries."""
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(robots_url)
    rp.read()  # 404 -> RobotFileParser treats the site as unrestricted
    if not rp.can_fetch(USER_AGENT, url):
        raise RobotsDisallowed(f"robots.txt disallows fetching {url}")

    response = requests.get(
        url, headers={"User-Agent": USER_AGENT}, timeout=FETCH_TIMEOUT_S
    )
    response.raise_for_status()
    return response.text


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scraper.fastplay",
        description=(
            "Fast Play orchestrator: parse -> parser gate -> compute -> "
            "schema-validate -> write data/fastplay.json + "
            "data/fastplay_history/{as_of}.json. No write of any kind "
            "before the final write step."
        ),
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--fixture", type=Path, help="path to a frozen HTML fixture")
    source.add_argument(
        "--live", action="store_true", help="fetch the live Fast Play unclaimed page"
    )
    parser.add_argument(
        "--games", type=Path, default=Path("data/fastplay_games.json"),
        help="path to data/fastplay_games.json (default: %(default)s)",
    )
    parser.add_argument(
        "--schema", type=Path, default=Path("data/schema/fastplay.schema.json"),
        help="path to the fastplay.json JSON Schema (default: %(default)s)",
    )
    parser.add_argument(
        "--out", type=Path, default=Path("data/fastplay.json"),
        help="write the day's fastplay.json here (default: %(default)s)",
    )
    parser.add_argument(
        "--history-dir", type=Path, default=Path("data/fastplay_history"),
        help="directory to write {as_of}.json into (default: %(default)s)",
    )
    parser.add_argument(
        "--as-of", default=None,
        help=(
            "ISO date to stamp as_of with (default: today's UTC date; the "
            "Action passes nothing, tests always pass this explicitly)"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    as_of = args.as_of or _dt.datetime.now(_dt.timezone.utc).date().isoformat()

    try:
        html = args.fixture.read_text(encoding="utf-8") if args.fixture else fetch()

        snapshot = parse(html)
        games_meta = json.loads(args.games.read_text(encoding="utf-8"))
        new_doc = compute_fastplay(snapshot, games_meta, as_of)

        schema = json.loads(args.schema.read_text(encoding="utf-8"))
        jsonschema.validate(instance=new_doc, schema=schema)

        output = json.dumps(new_doc, indent=2)

        args.out.write_text(output, encoding="utf-8", newline="\n")
        args.history_dir.mkdir(parents=True, exist_ok=True)
        (args.history_dir / f"{as_of}.json").write_text(
            output, encoding="utf-8", newline="\n"
        )
    except (
        ParseError,
        GateError,
        RobotsDisallowed,
        requests.RequestException,
        jsonschema.ValidationError,
        json.JSONDecodeError,
        OSError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
