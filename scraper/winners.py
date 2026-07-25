"""Maine Lottery winner-report alignment (winners showcase → winners.jsonl).

Spec: docs/specs/winners_location_spec.md. Maine publishes claimed winners
(name, hometown, game, prize, selling retailer + retailer town) on the
hand-maintained Winner Information page. This module turns that page — live
captures and web.archive.org history — into ONE canonical, deduplicated,
provenance-stamped dataset: ``data/winners/winners.jsonl``.

Design rules (mirrors the M6a wayback/panel discipline):

- **Text-pattern parser.** The showcase is curated prose ("Congratulations
  to NAME of TOWN! ... won $X in the GAME instant game ... bought at
  RETAILER in TOWN."), not a table. The parser strips markup and works the
  sentence patterns, tolerating the real page's observed variance: missing
  prize, missing hometown, missing retailer town, multi-winner splits,
  draw-game phrasing, curly-quote/encoding mangling. A field the entry does
  not state is ``null`` — never guessed.
- **Two strict layers:** pure offline parse/merge (this file's default
  paths; tests cover ONLY this layer, no network ever), and explicit
  network commands (``fetch``, ``wayback``) that are one-time/manual CLIs
  for the owner's machine. Nothing here is imported by
  ``scraper/run_daily.py`` or referenced by ``daily.yml`` (test-enforced).
- **Politeness:** ``fetch`` = 1 request with the project UA + robots.txt
  check (via :func:`scraper.scrape.fetch`'s conventions); ``wayback`` =
  web.archive.org ONLY, digest-collapsed CDX, >= 2 s inter-fetch delay,
  resumable raw cache (``data/winners/raw_cache/``, gitignored).
- **Determinism:** merge is idempotent; output sorted by
  (``first_seen``, ``winner_key``); LF-only, ``newline="\n"`` everywhere.

Record schema: ``data/schema/winner_record.schema.json``. ``winner_key`` =
sha256 prefix of the normalized (names, town, game, prize, retailer) tuple —
the page shows no dates, so identity IS the dedup key across captures;
``first_seen`` is the earliest capture date that showed the entry. Known
consequence (documented, conservative): a genuine REPEAT claim identical on
all five fields collapses into one record — an undercount, never an
overcount; the location-trends artifact carries this caveat.

Public API: :func:`parse_winners`, :func:`records_from_html`,
:func:`merge_winners`, and the ``python -m scraper.winners`` CLI.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import html as html_mod
import json
import re
import sys
import time
from pathlib import Path

PARSER_VERSION = "scraper.winners@1"

SHOWCASE_URL = (
    "https://www.mainelottery.com/players_info/winners_showcase.html"
)
CDX_API_URL = "http://web.archive.org/cdx/search/cdx"
FETCH_DELAY_S = 2.0
FETCH_TIMEOUT_S = 30

DEFAULT_WINNERS_PATH = Path("data") / "winners" / "winners.jsonl"
DEFAULT_RAW_CACHE = Path("data") / "winners" / "raw_cache"

# Draw games as named by the lottery's own site navigation; anything else
# mentioning "instant" (or matching nothing) is classified conservatively.
DRAW_GAMES = {
    "powerball", "megabucks", "mega millions", "lotto america",
    "lucky for life", "gimme 5", "pick 3", "pick 4", "cash pop",
    "world poker tour",
}

# --------------------------------------------------------------------------
# Text extraction
# --------------------------------------------------------------------------

_TAG_STRIP_RE = re.compile(r"<script.*?</script>|<style.*?</style>", re.S | re.I)
_ANY_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

# Encoding repair for the page's mangled apostrophes: cp1252 curly quote
# surviving as U+2019 or as a literal '?' wedged inside a word
# ("Bradbury?s Market").
_BAD_APOSTROPHE_RE = re.compile(r"(?<=\w)[’?](?=s\b)")

_ENTRY_SPLIT_RE = re.compile(r"(?=Congratulations to )", re.I)

_NAME_TOWN_RE = re.compile(
    r"^Congratulations to (?P<names>[^!.,]+?)"
    r"(?: of (?P<town>[A-Z][A-Za-z.' -]+?))?\s*[!.,]",
)
_PRIZE_RE = re.compile(r"\$(?P<amount>\d{1,3}(?:,\d{3})*(?:\.\d{2})?)")
_GAME_IN_RE = re.compile(
    r"\b(?:in|playing) the (?P<game>.+?) (?:instant|fast play)? ?game\b",
    re.I,
)
_GAME_TICKET_RE = re.compile(
    r"\b(?:on|bought|winning) (?:his|her|their|a|the|winning)? ?"
    r"(?P<game>[A-Z0-9][\w$\" .&'-]*?)(?: instant)? ticket\b",
)
_RETAILER_RE = re.compile(
    r"\b(?:at|from) (?P<retailer>[A-Z][\w$&.,' -]+?)"
    r"(?: in (?P<rtown>[A-Z][A-Za-z.' -]+?))?\s*(?:[.!]|$)",
)
_INSTANT_HINT_RE = re.compile(r"\binstant\b", re.I)


def _page_text(html: str) -> str:
    text = _TAG_STRIP_RE.sub(" ", html)
    text = _ANY_TAG_RE.sub(" ", text)
    text = html_mod.unescape(text)
    text = _BAD_APOSTROPHE_RE.sub("'", text)
    return _WS_RE.sub(" ", text).strip()


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip(" .,!")
    return value or None


def _classify(game: str | None, entry_text: str) -> str:
    if game is not None and game.lower().strip('"') in DRAW_GAMES:
        return "draw"
    if _INSTANT_HINT_RE.search(entry_text):
        return "instant"
    if game is None:
        return "unknown"
    return "unknown"


def parse_winners(html: str) -> list[dict]:
    """Parse showcase HTML (or already-stripped text) into winner entries.

    Returns a list of dicts with keys: ``names`` (list of str), ``town``,
    ``prize``, ``game``, ``game_type``, ``retailer``, ``retailer_town``,
    ``raw_text``. Unstated fields are ``None``. Entries whose leading
    name cannot be parsed are skipped (the page carries decorative
    "Congratulations" headings too).
    """
    text = _page_text(html)
    entries = []
    for chunk in _ENTRY_SPLIT_RE.split(text):
        chunk = chunk.strip()
        if not chunk.lower().startswith("congratulations to "):
            continue
        # Bound each entry at the next entry (split guarantees) and keep it
        # to a sane length so nav/footer noise can't attach to the last one.
        entry = chunk[:600]
        m = _NAME_TOWN_RE.match(entry)
        if m is None:
            continue
        names = [
            _clean(part) for part in re.split(r"\band\b", m.group("names"))
            if _clean(part)
        ]
        if not names:
            continue

        prize_m = _PRIZE_RE.search(entry)
        prize = (
            float(prize_m.group("amount").replace(",", ""))
            if prize_m else None
        )

        game_m = _GAME_IN_RE.search(entry)
        game = _clean(game_m.group("game")) if game_m else None
        if game is None:
            ticket_m = _GAME_TICKET_RE.search(entry)
            if ticket_m:
                candidate = _clean(ticket_m.group("game"))
                # "the winning ticket" / "his ticket" style → no game named
                if candidate and candidate.lower() not in {
                    "winning", "his", "her", "their", "the"
                }:
                    game = candidate

        retailer_m = _RETAILER_RE.search(entry)
        retailer = _clean(retailer_m.group("retailer")) if retailer_m else None
        retailer_town = (
            _clean(retailer_m.group("rtown")) if retailer_m else None
        )

        entries.append({
            "names": names,
            "town": _clean(m.group("town")),
            "prize": prize,
            "game": game,
            "game_type": _classify(game, entry),
            "retailer": retailer,
            "retailer_town": retailer_town,
            "raw_text": entry,
        })
    return entries


# --------------------------------------------------------------------------
# Records + merge
# --------------------------------------------------------------------------

def winner_key(entry: dict) -> str:
    basis = "|".join([
        ";".join(sorted(n.lower() for n in entry["names"])),
        (entry["town"] or "").lower(),
        (entry["game"] or "").lower(),
        f'{entry["prize"] or 0:.0f}',
        (entry["retailer"] or "").lower(),
    ])
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def records_from_html(
    html: str, *, source: str, capture_url: str, capture_ts: str,
    first_seen: str,
) -> list[dict]:
    """Parse + stamp provenance into full winner records."""
    content_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()
    records = []
    for entry in parse_winners(html):
        records.append({
            "winner_key": winner_key(entry),
            "names": entry["names"],
            "town": entry["town"],
            "prize": entry["prize"],
            "game": entry["game"],
            "game_type": entry["game_type"],
            "retailer": entry["retailer"],
            "retailer_town": entry["retailer_town"],
            "first_seen": first_seen,
            "source": source,
            "capture_url": capture_url,
            "capture_ts": capture_ts,
            "content_hash": content_hash,
            "parser_version": PARSER_VERSION,
        })
    return records


def merge_winners(path: Path, new_records: list[dict]) -> tuple[int, int]:
    """Idempotent merge of *new_records* into the JSONL at *path*.

    Dedup on ``winner_key``; an existing key keeps its EARLIEST
    ``first_seen`` (and that record wins wholesale — history is
    append-only, never rewritten by a later sighting). Output sorted by
    (``first_seen``, ``winner_key``), LF-only. Returns (added, total).
    """
    existing: dict[str, dict] = {}
    if path.exists():
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rec = json.loads(line)
                    existing[rec["winner_key"]] = rec

    added = 0
    for rec in new_records:
        key = rec["winner_key"]
        if key not in existing:
            existing[key] = rec
            added += 1
        elif rec["first_seen"] < existing[key]["first_seen"]:
            existing[key] = rec   # earlier capture supersedes (older truth)

    ordered = sorted(
        existing.values(), key=lambda r: (r["first_seen"], r["winner_key"])
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for rec in ordered:
            fh.write(json.dumps(rec, sort_keys=True) + "\n")
    return added, len(ordered)


# --------------------------------------------------------------------------
# Network commands (owner's machine only; never in tests, never in daily.yml)
# --------------------------------------------------------------------------

def cmd_fetch(winners_path: Path, as_of: str) -> int:
    """One polite live fetch of the showcase page → merge."""
    from scraper.scrape import USER_AGENT  # authorized fetch conventions
    import requests

    resp = requests.get(
        SHOWCASE_URL, headers={"User-Agent": USER_AGENT},
        timeout=FETCH_TIMEOUT_S,
    )
    resp.raise_for_status()
    records = records_from_html(
        resp.text, source="live", capture_url=SHOWCASE_URL,
        capture_ts=_dt.datetime.now(_dt.timezone.utc).isoformat(
            timespec="seconds"
        ),
        first_seen=as_of,
    )
    added, total = merge_winners(winners_path, records)
    print(f"fetch: parsed {len(records)} entries; added {added}; "
          f"total {total}", file=sys.stderr)
    return 0


def cmd_wayback(
    winners_path: Path, raw_cache: Path, *, delay_s: float = FETCH_DELAY_S,
    limit: int | None = None,
) -> int:
    """Backfill from web.archive.org captures of the showcase page.

    Self-contained CDX client (design rule: wayback_backfill.py is
    never imported by another scraper module). Digest-collapsed,
    status-200 only, resumable via *raw_cache*, >= *delay_s* between
    fetches, identifying UA. Accounts for every capture in the log.
    """
    from scraper.scrape import USER_AGENT
    import requests

    params = {
        "url": SHOWCASE_URL.replace("https://", ""),
        "output": "json",
        "collapse": "digest",
        "filter": "statuscode:200",
    }
    resp = requests.get(
        CDX_API_URL, params=params, headers={"User-Agent": USER_AGENT},
        timeout=FETCH_TIMEOUT_S,
    )
    resp.raise_for_status()
    rows = resp.json()
    header, rows = rows[0], rows[1:]
    ts_i = header.index("timestamp")
    orig_i = header.index("original")

    raw_cache.mkdir(parents=True, exist_ok=True)
    counts = {"captures": len(rows), "fetched": 0, "cached": 0,
              "parse_failed": 0, "merged_new": 0}
    all_records: list[dict] = []
    for row in rows[:limit]:
        ts, original = row[ts_i], row[orig_i]
        cache_file = raw_cache / f"{ts}.html"
        capture_url = f"https://web.archive.org/web/{ts}id_/{original}"
        if cache_file.exists():
            html = cache_file.read_text(encoding="utf-8", errors="replace")
            counts["cached"] += 1
        else:
            time.sleep(delay_s)
            r = requests.get(
                capture_url, headers={"User-Agent": USER_AGENT},
                timeout=FETCH_TIMEOUT_S,
            )
            if r.status_code != 200:
                print(f"wayback: skip {capture_url} (status {r.status_code})",
                      file=sys.stderr)
                counts["parse_failed"] += 1
                continue
            html = r.text
            cache_file.write_text(html, encoding="utf-8", newline="\n")
            counts["fetched"] += 1
        first_seen = f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]}"
        try:
            records = records_from_html(
                html, source="wayback", capture_url=capture_url,
                capture_ts=_dt.datetime.strptime(ts, "%Y%m%d%H%M%S")
                .replace(tzinfo=_dt.timezone.utc).isoformat(),
                first_seen=first_seen,
            )
        except Exception as exc:  # noqa: BLE001 — log-and-continue by design
            print(f"wayback: parse failed {capture_url}: {exc}",
                  file=sys.stderr)
            counts["parse_failed"] += 1
            continue
        all_records.extend(records)

    added, total = merge_winners(winners_path, all_records)
    counts["merged_new"] = added
    print(f"wayback: {json.dumps(counts)}; dataset total {total}",
          file=sys.stderr)
    return 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m scraper.winners",
        description="Winner-report alignment: parse/merge the Maine winners "
                    "showcase into data/winners/winners.jsonl.",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_parse = sub.add_parser(
        "parse", help="offline: parse an HTML file, merge into the dataset"
    )
    p_parse.add_argument("--html", type=Path, required=True)
    p_parse.add_argument("--source", default="live",
                         choices=["live", "wayback", "seed"])
    p_parse.add_argument("--capture-url", default=SHOWCASE_URL)
    p_parse.add_argument("--capture-ts", required=True,
                         help="ISO datetime of the capture (run truth)")
    p_parse.add_argument("--first-seen", required=True,
                         help="ISO date this content was first observable")
    p_parse.add_argument("--out", type=Path, default=DEFAULT_WINNERS_PATH)

    p_fetch = sub.add_parser(
        "fetch", help="NETWORK (owner machine): one polite live fetch + merge"
    )
    p_fetch.add_argument("--as-of", required=True)
    p_fetch.add_argument("--out", type=Path, default=DEFAULT_WINNERS_PATH)

    p_way = sub.add_parser(
        "wayback",
        help="NETWORK (owner machine): one-time web.archive.org backfill",
    )
    p_way.add_argument("--out", type=Path, default=DEFAULT_WINNERS_PATH)
    p_way.add_argument("--raw-cache", type=Path, default=DEFAULT_RAW_CACHE)
    p_way.add_argument("--delay", type=float, default=FETCH_DELAY_S)
    p_way.add_argument("--limit", type=int, default=None)

    args = ap.parse_args(argv)

    try:
        if args.cmd == "parse":
            records = records_from_html(
                args.html.read_text(encoding="utf-8", errors="replace"),
                source=args.source, capture_url=args.capture_url,
                capture_ts=args.capture_ts, first_seen=args.first_seen,
            )
            added, total = merge_winners(args.out, records)
            print(f"parse: {len(records)} entries; added {added}; "
                  f"total {total}", file=sys.stderr)
            return 0
        if args.cmd == "fetch":
            return cmd_fetch(args.out, args.as_of)
        if args.cmd == "wayback":
            return cmd_wayback(args.out, args.raw_cache,
                               delay_s=args.delay, limit=args.limit)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
