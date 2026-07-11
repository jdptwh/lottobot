"""Maine Lottery print-run scraper (M2, satellite S1).

Parses the frozen per-game "what's new" article fixtures
(``tests/scraper/fixtures/games/article_<id>.html``) plus the frozen
scratchdates fixture into ``data/games.json``: per-game static metadata
(print run, overall odds, on-sale date, top prize value) keyed by
``game_no``, plus independently-sourced game end dates. All parsing is
offline against frozen fixtures — this module never fetches (see
maine-scratch-ev-spec.md §8's documented, owner-approved one-time-pull
exception; docs/specs/m2_printrun_spec.md is the binding spec for this file).

Design notes worth calling out explicitly (both are spec-directed choices,
not accidents):

* **Price.** Per the spec's games.json shape, the price-point tile page an
  article was tiled on is the PRIMARY price source ("price from the
  price-point page the article was tiled on when known"); the M1
  unclaimed-prizes snapshot, joined by ``game_no``, is the fallback for
  wayback-recovered/untiled articles and article-less active games.
  :func:`build_games` takes an ``article_id -> price`` mapping built from
  the frozen ``pricepages/scratch{N}dollar_*.html`` fixtures (the price is
  the ``N`` in the filename; :func:`parse_pricepage_article_ids` extracts
  the tiled article ids) and prefers it. If a game's tile price ever
  disagrees with its unclaimed price, that's a data-integrity signal: the
  tile wins and the conflict is recorded in the coverage block's
  ``price_conflicts`` (empty on the frozen fixtures — all 33 games present
  in both sources agree).

* **Missing-article active games (acceptance criterion 6).** For an active
  game_no with no article fixture, the *article-derived* fields go null:
  ``print_run``, ``overall_odds``, ``top_prize_value``, ``on_sale``,
  ``source``, ``article_id``. ``name``, ``price``, ``end_date`` and
  ``last_cash_date`` are populated from their own independent frozen
  sources (unclaimed page / scratchdates) whenever available — those are
  separate joins by game_no (criterion 5 is explicit that the scratchdates
  join doesn't depend on article coverage), and nulling data we do have
  would just throw it away for no spec-stated reason. Name precedence
  when more than one source has a spelling: article ``<h1>`` (most
  authoritative — the game's own page) > unclaimed page > scratchdates
  (spec's own example: unclaimed's "SILVER 7S" vs. scratchdates' "SILVER
  7's" for game 704 — never join on name, only on game_no).

Public API: :func:`parse_article`, :func:`parse_scratchdates`,
:func:`parse_pricepage_article_ids`, :func:`build_games`, and the
``python -m scraper.games`` CLI.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

from scraper.scrape import parse as parse_unclaimed

# --------------------------------------------------------------------------
# Article field regexes (spec §"Source structure", tolerant: nulls not crashes)
# --------------------------------------------------------------------------

GAME_NO_RE = re.compile(r"Game #(\d+)")

# Three eras of print-run label coexist in the fixtures: "Tickets Printed
# 960,000" (no separator), "Ticket printed: 5,400,000" (colon, singular
# "Ticket"), "Tickets Printed - 840,000" (dash). Case-insensitive.
PRINT_RUN_RE = re.compile(r"Tickets?\s+printed\s*[-:]?\s*([\d,]+)", re.IGNORECASE)

# Anchored on "OVERALL ODDS OF WINNING" specifically so it never matches the
# unrelated "HIGHEST INSTANT PRIZE ODDS 1:180,000" label that precedes it on
# the same page. Comma-bearing figures (rare but possible) parse fine too.
OVERALL_ODDS_RE = re.compile(
    r"OVERALL ODDS OF WINNING\s+1:\s*([\d,]+(?:\.\d+)?)", re.IGNORECASE
)

# "On Sale - July 2, 2026" / "On Sale: August 1, 2024" / "On Sale -
# December 5, 2024" — dash or colon, tolerate both.
ON_SALE_RE = re.compile(
    r"On Sale\s*[-:]?\s*([A-Za-z]+\s+\d{1,2},\s*\d{4})", re.IGNORECASE
)

MAX_AWARD_RE = re.compile(r"Maximum Award:\s*\$?([\d,]+)", re.IGNORECASE)

# Price-point tile pages: the price is the N in the fixture filename
# (scratch5dollar_2026-07-11.html -> $5); the tiles themselves are
# whatsnew index.php article links wrapping the game-name <h2>.
PRICEPAGE_FILENAME_RE = re.compile(r"scratch(\d+)dollar")
ARTICLE_HREF_ID_RE = re.compile(r"[?&]id=(\d+)")

DATE_FORMAT = "%B %d, %Y"

MIN_COVERAGE_PCT = 80.0


class BuildError(Exception):
    """Raised when the games.json build fails the M2 DoD coverage gate."""


# --------------------------------------------------------------------------
# Small parsing helpers (never raise — a bad/missing match is just None)
# --------------------------------------------------------------------------

def _int_or_none(match: re.Match | None) -> int | None:
    if match is None:
        return None
    try:
        return int(match.group(1).replace(",", ""))
    except ValueError:
        return None


def _float_or_none(match: re.Match | None) -> float | None:
    if match is None:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def _parse_date_text(text: str) -> str | None:
    """Parse a ``"Month D, YYYY"`` date string to ISO 8601, or ``None``."""
    text = text.strip()
    if not text:
        return None
    try:
        return _dt.datetime.strptime(text, DATE_FORMAT).date().isoformat()
    except ValueError:
        return None


def _on_sale_date(text: str) -> str | None:
    match = ON_SALE_RE.search(text)
    if match is None:
        return None
    return _parse_date_text(match.group(1))


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def parse_article(
    html: str, *, article_id: str, source: str | None
) -> dict:
    """Parse one frozen per-game article fixture into a metadata dict.

    Returns ``{"game_no", "name", "print_run", "overall_odds",
    "top_prize_value", "on_sale", "source", "article_id"}``. Any field whose
    tolerant regex doesn't match is ``None`` (fragility rule, spec §2) —
    only ``game_no`` being unparseable is treated as "this article can't be
    keyed" by the caller (:func:`build_games` drops such entries; the spec
    calls ``Game #NNN`` an "anchor field; always present" and it is, in all
    58 frozen fixtures).
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n")

    game_no_match = GAME_NO_RE.search(text)
    game_no = int(game_no_match.group(1)) if game_no_match else None

    h1 = soup.find("h1")
    name = h1.get_text(strip=True) if h1 is not None else None

    return {
        "game_no": game_no,
        "name": name,
        "print_run": _int_or_none(PRINT_RUN_RE.search(text)),
        "overall_odds": _float_or_none(OVERALL_ODDS_RE.search(text)),
        "top_prize_value": _int_or_none(MAX_AWARD_RE.search(text)),
        "on_sale": _on_sale_date(text),
        "source": source,
        "article_id": article_id,
    }


def parse_scratchdates(html: str) -> dict[int, dict]:
    """Parse the scratchdates fixture's ``table.tbstriped`` rows.

    Returns ``{game_no: {"name": str, "end_date": str|None,
    "last_cash_date": str|None}}``. Rows that aren't exactly 4 ``<td>``
    cells, or whose first cell isn't an integer, are skipped rather than
    raised (fragility rule §2) — the header row (all ``<th>``) is the
    expected instance of this, not a parse failure.
    """
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="tbstriped")
    if table is None:
        return {}

    result: dict[int, dict] = {}
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) != 4:
            continue
        try:
            game_no = int(tds[0].get_text(strip=True))
        except ValueError:
            continue
        result[game_no] = {
            "name": tds[1].get_text(strip=True),
            "end_date": _parse_date_text(tds[2].get_text(strip=True)),
            "last_cash_date": _parse_date_text(tds[3].get_text(strip=True)),
        }
    return result


def parse_pricepage_article_ids(html: str) -> set[str]:
    """Extract the tiled article ids from one price-point page fixture.

    A tile is an ``<a>`` whose href points at the whatsnew CMS article view
    (``.../tools/whatsnew/index.php?topic=Lottery_Scratch&id=NNN&v=article``),
    wrapping the game-name ``<h2>``. Returns the set of ``id`` values as
    strings (they key into the article fixtures / PROVENANCE.json). Pages
    with no tiles (or no such links) return an empty set, never raise.
    """
    soup = BeautifulSoup(html, "html.parser")
    ids: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "whatsnew/index.php" not in href or "v=article" not in href:
            continue
        match = ARTICLE_HREF_ID_RE.search(href)
        if match is not None:
            ids.add(match.group(1))
    return ids


def build_games(
    articles: list[dict],
    scratchdates: dict[int, dict],
    unclaimed_snapshot: dict,
    as_of: str,
    tile_prices: dict[str, float] | None = None,
) -> dict:
    """Assemble the ``data/games.json`` shape (spec's ``games.json`` §).

    ``articles`` is a list of :func:`parse_article` outputs — one per frozen
    article fixture, including the two articles for not-yet-active games
    714/721 (spec risk note: "include them; they'll matter within weeks").
    ``unclaimed_snapshot`` is M1's :func:`scraper.scrape.parse` output over
    the frozen unclaimed-prizes fixture: it defines the active game_no
    universe (the M2 DoD gate denominator) and the fallback ``price``.
    ``tile_prices`` maps ``article_id -> price`` from the price-point tile
    pages — the primary price source per the spec's games.json shape; when
    a game's article is tiled, the tile price wins, and any disagreement
    with the unclaimed price is recorded in ``coverage.price_conflicts``.

    Raises :class:`BuildError` if fewer than ``MIN_COVERAGE_PCT`` percent of
    active games have a non-null ``print_run`` (M2 DoD gate, spec acceptance
    criterion 2) — the caller (CLI) must not write output in that case.
    """
    if tile_prices is None:
        tile_prices = {}

    unclaimed_by_no = {g["game_no"]: g for g in unclaimed_snapshot["games"]}
    active_game_nos = set(unclaimed_by_no)

    articles_by_no = {
        a["game_no"]: a for a in articles if a["game_no"] is not None
    }

    all_game_nos = sorted(active_game_nos | set(articles_by_no))

    games: dict[str, dict] = {}
    price_conflicts: list[dict] = []
    for game_no in all_game_nos:
        article = articles_by_no.get(game_no)
        unclaimed = unclaimed_by_no.get(game_no)
        dates = scratchdates.get(game_no)

        name = None
        if article is not None and article.get("name"):
            name = article["name"]
        elif unclaimed is not None:
            name = unclaimed["name"]
        elif dates is not None:
            name = dates.get("name")

        # Price: tile page (primary, when this game's article was tiled) ->
        # unclaimed page by game_no (fallback) -> null.
        tile_price = (
            tile_prices.get(article["article_id"]) if article is not None else None
        )
        unclaimed_price = unclaimed["price"] if unclaimed is not None else None
        if (
            tile_price is not None
            and unclaimed_price is not None
            and tile_price != unclaimed_price
        ):
            price_conflicts.append(
                {
                    "game_no": game_no,
                    "tile_price": tile_price,
                    "unclaimed_price": unclaimed_price,
                }
            )
        price = tile_price if tile_price is not None else unclaimed_price

        games[str(game_no)] = {
            "game_no": game_no,
            "name": name,
            "price": price,
            "print_run": article["print_run"] if article is not None else None,
            "overall_odds": (
                article["overall_odds"] if article is not None else None
            ),
            "top_prize_value": (
                article["top_prize_value"] if article is not None else None
            ),
            "on_sale": article["on_sale"] if article is not None else None,
            "end_date": dates["end_date"] if dates is not None else None,
            "last_cash_date": (
                dates["last_cash_date"] if dates is not None else None
            ),
            "source": article["source"] if article is not None else None,
            "article_id": (
                article["article_id"] if article is not None else None
            ),
        }

    with_print_run = sum(
        1 for no in active_game_nos if games[str(no)]["print_run"] is not None
    )
    total_active = len(active_game_nos)
    coverage_pct = (with_print_run / total_active * 100) if total_active else 0.0
    missing = sorted(
        no for no in active_game_nos if games[str(no)]["print_run"] is None
    )
    non_active_articles = sorted(set(articles_by_no) - active_game_nos)

    if coverage_pct < MIN_COVERAGE_PCT:
        raise BuildError(
            f"print_run coverage {coverage_pct:.1f}% ({with_print_run}/"
            f"{total_active} active games) is below the M2 DoD gate of "
            f"{MIN_COVERAGE_PCT:.0f}%"
        )

    return {
        "as_of": as_of,
        "games": games,
        "coverage": {
            "active_games": total_active,
            "with_print_run": with_print_run,
            "coverage_pct": round(coverage_pct, 1),
            "gate_threshold_pct": MIN_COVERAGE_PCT,
            "missing": missing,
            "non_active_articles": non_active_articles,
            "price_conflicts": price_conflicts,
        },
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scraper.games",
        description=(
            "Build data/games.json from frozen per-game article fixtures "
            "plus the scratchdates fixture (M2). Never fetches; --as-of is "
            "passed in so the build stays deterministic."
        ),
    )
    parser.add_argument(
        "--fixtures-dir",
        type=Path,
        required=True,
        help=(
            "root fixtures dir containing games/ (article_*.html + "
            "PROVENANCE.json), pricepages/ (scratch{N}dollar_*.html), "
            "scratchdates_*.html, and unclaimed_prizes_*.html"
        ),
    )
    parser.add_argument(
        "--as-of",
        required=True,
        help="ISO date to stamp as_of with (run truth; never generated)",
    )
    parser.add_argument(
        "--out", type=Path, default=None, help="write output here (default: stdout)"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    fixtures_dir: Path = args.fixtures_dir
    games_dir = fixtures_dir / "games"

    try:
        provenance_path = games_dir / "PROVENANCE.json"
        provenance = (
            json.loads(provenance_path.read_text(encoding="utf-8"))
            if provenance_path.exists()
            else {}
        )

        article_paths = sorted(games_dir.glob("article_*.html"))
        scratchdates_paths = sorted(fixtures_dir.glob("scratchdates_*.html"))
        unclaimed_paths = sorted(fixtures_dir.glob("unclaimed_prizes_*.html"))

        if not article_paths:
            raise FileNotFoundError(f"no article_*.html fixtures under {games_dir}")
        if not scratchdates_paths:
            raise FileNotFoundError(
                f"no scratchdates_*.html fixture under {fixtures_dir}"
            )
        if not unclaimed_paths:
            raise FileNotFoundError(
                f"no unclaimed_prizes_*.html fixture under {fixtures_dir}"
            )

        articles = []
        for path in article_paths:
            article_id = path.stem.removeprefix("article_")
            source = provenance.get(article_id, {}).get("source")
            html = path.read_text(encoding="utf-8")
            articles.append(
                parse_article(html, article_id=article_id, source=source)
            )

        # Tile prices (primary price source): each pricepages fixture's
        # filename carries the price point; its tiles name the article ids.
        # The primary source vanishing must fail as loudly as the fallbacks do.
        pricepage_paths = sorted(
            (fixtures_dir / "pricepages").glob("scratch*dollar_*.html")
        )
        if not pricepage_paths:
            raise FileNotFoundError(
                f"no pricepages/scratch*dollar_*.html fixtures under {fixtures_dir}"
            )
        tile_prices: dict[str, float] = {}
        for path in pricepage_paths:
            filename_match = PRICEPAGE_FILENAME_RE.match(path.name)
            if filename_match is None:
                continue
            price = float(filename_match.group(1))
            for article_id in parse_pricepage_article_ids(
                path.read_text(encoding="utf-8")
            ):
                tile_prices[article_id] = price

        scratchdates = parse_scratchdates(
            scratchdates_paths[0].read_text(encoding="utf-8")
        )
        unclaimed_snapshot = parse_unclaimed(
            unclaimed_paths[0].read_text(encoding="utf-8")
        )

        games_doc = build_games(
            articles,
            scratchdates,
            unclaimed_snapshot,
            as_of=args.as_of,
            tile_prices=tile_prices,
        )
    except (BuildError, FileNotFoundError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    output = json.dumps(games_doc, indent=2, sort_keys=True)
    if args.out is not None:
        args.out.write_text(output, encoding="utf-8")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
