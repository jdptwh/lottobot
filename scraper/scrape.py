"""Maine Lottery unclaimed-prizes scraper (M1, satellite S1).

Parses the state's daily "unclaimed prizes" HTML page into structured game
records, enforces the spec's parser gate (maine-scratch-ev-spec.md §6.1),
and builds a §4-schema-conformant ``latest.json`` shape with the EV fields
left null (EV math lands in M3/S2).

Public API: :func:`parse`, :func:`parser_gate`, :func:`build_latest`,
:func:`fetch`, and the ``python -m scraper.scrape`` CLI.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
import urllib.robotparser
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

PAGE_URL = "https://www.mainelottery.com/players_info/unclaimed_prizes.html"
USER_AGENT = (
    "MaineScratchEVRanker/0.1 (personal open-data project; "
    "contact: jdptwh@gmail.com)"
)
FETCH_TIMEOUT_S = 30

REQUIRED_GAME_FIELDS = ("price", "game_no", "percent_unsold", "total_unclaimed")
MIN_GAMES = 40
MIN_TOTAL_UNCLAIMED = 50_000_000


class ParseError(Exception):
    """The unclaimed-prizes HTML did not match the expected structure."""


class GateError(Exception):
    """A parsed snapshot failed the §6.1 parser sanity gate."""


class RobotsDisallowed(Exception):
    """robots.txt explicitly disallows fetching the unclaimed-prizes page."""


# --------------------------------------------------------------------------
# Cell parsing helpers
# --------------------------------------------------------------------------

def _is_blank(cell_text: str) -> bool:
    """True if a cell is whitespace-only (treat \\xa0/&nbsp; as whitespace)."""
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


def _parse_prize_level(cell_text: str, *, tolerant: bool = False):
    """Parse a top-prize-level cell.

    Default (``tolerant=False``): behavior and the raised message are
    byte-identical to the pre-existing parser — returns ``int`` or raises
    :class:`ParseError`.

    ``tolerant=True`` (opt-in, ``wayback_backfill.py`` only — see
    docs/specs/m6a_noncash_addendum.md): on a non-numeric cell (observed in
    the wild as a noncash/vehicle prize, e.g. "CHEVROLET CAMARO 2SS"),
    returns ``(None, label)`` instead of raising, where ``label`` is the
    cell text verbatim with internal whitespace normalized. Numeric cells
    are unaffected either way.
    """
    text = cell_text.replace("\xa0", " ").strip().replace("$", "").replace(",", "")
    try:
        return int(text)
    except ValueError as exc:
        if tolerant:
            label = " ".join(cell_text.replace("\xa0", " ").split())
            return None, label
        raise ParseError(f"malformed prize-level cell: {cell_text!r}") from exc


def _extract_timestamp(soup: BeautifulSoup) -> str:
    for p in soup.find_all("p"):
        text = p.get_text()
        idx = text.find("as of ")
        if idx != -1:
            return text[idx + len("as of ") :].strip()
    raise ParseError("could not find an 'as of <timestamp>' paragraph")


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def _prize_item(raw_level, remaining: int) -> dict:
    """Build one top_prizes item from a `_parse_prize_level` return value."""
    if isinstance(raw_level, tuple):
        level, level_label = raw_level
        return {"level": level, "level_label": level_label, "remaining": remaining}
    return {"level": raw_level, "remaining": remaining}


def parse(html: str, *, prize_level_tolerant: bool = False) -> dict:
    """Parse the unclaimed-prizes HTML into ``{"source_timestamp", "games"}``.

    ``games`` is a list of dicts (page order):
    ``{"game_no": int, "name": str, "price": float, "percent_unsold": float,
    "total_unclaimed": float, "top_prizes": [{"level": int, "remaining": int}, ...]}``.

    Raises :class:`ParseError` on a missing table, an orphan continuation
    row, a row with other than 7 ``<td>`` cells, or a malformed cell value.

    ``prize_level_tolerant`` (default ``False``, keyword-only): opt-in used
    only by ``scraper/wayback_backfill.py`` for historical noncash/vehicle
    prize cells (docs/specs/m6a_noncash_addendum.md). At the default, this
    parameter changes nothing — production behavior stays byte-identical.
    When ``True``, a non-numeric top-prize-level cell yields
    ``{"level": None, "level_label": "<verbatim, whitespace-normalized>",
    "remaining": int}`` instead of raising.
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
            raw_level = _parse_prize_level(cells[5], tolerant=prize_level_tolerant)
            remaining = _parse_int(cells[6])
            games[-1]["top_prizes"].append(_prize_item(raw_level, remaining))
            continue

        price = _parse_money(cells[0])
        game_no = _parse_int(cells[1])
        name = cells[2].replace("\xa0", " ").strip()
        percent_unsold = _parse_percent(cells[3])
        total_unclaimed = _parse_money(cells[4])
        raw_level = _parse_prize_level(cells[5], tolerant=prize_level_tolerant)
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
    """Enforce spec §6.1: raise :class:`GateError` naming the failed check."""
    games = snapshot.get("games") or []

    if len(games) < MIN_GAMES:
        raise GateError(
            f"parser gate: only {len(games)} games parsed (< {MIN_GAMES} floor)"
        )

    for idx, game in enumerate(games):
        for field in REQUIRED_GAME_FIELDS:
            if game.get(field) is None:
                raise GateError(
                    f"parser gate: game at index {idx} "
                    f"(game_no={game.get('game_no')!r}) missing required field "
                    f"'{field}'"
                )

    total_unclaimed = sum(game["total_unclaimed"] for game in games)
    if total_unclaimed <= MIN_TOTAL_UNCLAIMED:
        raise GateError(
            f"parser gate: sum(total_unclaimed)={total_unclaimed} does not "
            f"exceed the ${MIN_TOTAL_UNCLAIMED:,} sanity floor"
        )


def build_latest(snapshot: dict, as_of: str) -> dict:
    """Build the §4-shaped ``latest.json`` dict (EV fields null; M1 scope)."""
    games = []
    for game in snapshot["games"]:
        games.append(
            {
                "game_no": game["game_no"],
                "name": game["name"],
                "price": game["price"],
                "percent_unsold": game["percent_unsold"],
                "total_unclaimed": game["total_unclaimed"],
                "top_prizes": [dict(tp) for tp in game["top_prizes"]],
                "print_run": None,
                "remaining_tickets": None,
                "ev_per_ticket": None,
                "ev_ratio": None,
                "ev_ratio_adjusted": None,
                "dead_game": False,
                "flags": [],
                "confidence": "low",
            }
        )
    return {
        "as_of": as_of,
        "source_timestamp": snapshot["source_timestamp"],
        "games": games,
    }


def fetch(url: str = PAGE_URL) -> str:
    """Politely fetch ``url``: robots.txt check, UA string, 30s timeout, no retries."""
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
        prog="python -m scraper.scrape",
        description="Parse the Maine Lottery unclaimed-prizes page into latest.json.",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--fixture", type=Path, help="path to a frozen HTML fixture")
    source.add_argument(
        "--live", action="store_true", help="fetch the live unclaimed-prizes page"
    )
    parser.add_argument(
        "--out", type=Path, default=None, help="write output here (default: stdout)"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    try:
        html = (
            args.fixture.read_text(encoding="utf-8") if args.fixture else fetch()
        )
        snapshot = parse(html)
        parser_gate(snapshot)
    except (ParseError, GateError, RobotsDisallowed, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    as_of = _dt.date.today().isoformat()
    latest = build_latest(snapshot, as_of)
    output = json.dumps(latest, indent=2)

    if args.out is not None:
        args.out.write_text(output, encoding="utf-8")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
