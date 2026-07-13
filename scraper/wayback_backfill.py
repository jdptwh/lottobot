"""Wayback Machine backfill for the historical unclaimed-prizes panel (M6a).

One-time manual CLI (docs/specs/m6_v2_program_spec.md Phase 0, design rule 3a):
queries the CDX API for web.archive.org captures of the Maine Lottery
unclaimed-prizes page, fetches each unique in-era capture into a gitignored
raw cache (``data/panel/raw_cache/``), parses with the production
``scraper.scrape.parse``, and emits per-game observation records to
``data/panel/wayback_observations.jsonl``.

Era guard: captures dated before 2015-01-01 are skipped and counted, never
parsed (W1: pre-2015 formats fail the parser; era-versioned parsers are out
of scope). Parse failures inside the era are logged with ``capture_url`` and
skipped — never fatal.

Politeness (non-negotiable, design rule 4): requests go to web.archive.org
ONLY, at least 2s between live fetches, the same identifying UA string as the
daily scraper, resumable via the raw cache (a re-run fetches only cache
misses).

This module is NEVER imported by ``scraper/run_daily.py`` and is never
referenced by ``.github/workflows/daily.yml`` — enforced by
``tests/scraper/test_wayback_backfill.py``.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import requests

from scraper.scrape import USER_AGENT, ParseError, parse

CDX_API_URL = "http://web.archive.org/cdx/search/cdx"
TARGET_URL = "https://www.mainelottery.com/players_info/unclaimed_prizes.html"
ERA_START = _dt.date(2015, 1, 1)
FETCH_DELAY_S = 2.0
FETCH_TIMEOUT_S = 30
# Tied to the production parser this module reuses (scraper.scrape.parse);
# bump if that parser's output shape changes in a way that matters to the panel.
PARSER_VERSION = "scraper.scrape@1"

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_CACHE_DIR = REPO_ROOT / "data" / "panel" / "raw_cache"
OBSERVATIONS_PATH = REPO_ROOT / "data" / "panel" / "wayback_observations.jsonl"


# --------------------------------------------------------------------------
# Timestamp / era-guard helpers
# --------------------------------------------------------------------------

def cdx_timestamp_to_datetime(ts: str) -> _dt.datetime:
    """Parse a 14-digit CDX timestamp (UTC) into a timezone-aware datetime."""
    return _dt.datetime.strptime(ts, "%Y%m%d%H%M%S").replace(tzinfo=_dt.timezone.utc)


def is_pre_era(ts: str) -> bool:
    """True if a CDX timestamp predates the 2015-01-01 era guard."""
    return cdx_timestamp_to_datetime(ts).date() < ERA_START


def wayback_capture_url(ts: str, original: str) -> str:
    """The raw ('id_') wayback URL for one CDX capture."""
    return f"https://web.archive.org/web/{ts}id_/{original}"


_OBS_DATE_FORMATS = ("%B %d, %Y %I:%M %p",)


def parse_obs_date(source_timestamp: str) -> str:
    """Convert the page's own 'as of ...' string to an ISO date (page truth, ET).

    Never the capture timestamp (design rule 2) — the page's "as of" line can
    lag the capture by days.
    """
    text = source_timestamp.strip()
    for fmt in _OBS_DATE_FORMATS:
        try:
            return _dt.datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    raise ParseError(f"could not parse obs_date from source_timestamp: {source_timestamp!r}")


def pu_interval(percent_unsold: float) -> list[float]:
    """[x-0.05, x+0.05) interval-censoring the published 0.1-point rounding, floored at 0."""
    lo = max(percent_unsold - 0.05, 0.0)
    hi = percent_unsold + 0.05
    return [round(lo, 10), round(hi, 10)]


def game_key(game_no: int, name: str) -> str:
    """'{game_no}:{name-slug}' — distinguishes reused game numbers across eras."""
    slug = "-".join(name.strip().lower().split())
    return f"{game_no}:{slug}"


# --------------------------------------------------------------------------
# Fetch (network; cache-first and resumable)
# --------------------------------------------------------------------------

def fetch_capture_html(
    ts: str,
    original: str,
    *,
    cache_dir: Path = RAW_CACHE_DIR,
    session: Any = None,
    delay_s: float = FETCH_DELAY_S,
) -> str:
    """Return raw HTML for one capture. Cache-first: a cache hit never touches
    the network (resumability, design rule 4)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{ts}.html"
    if path.exists():
        return path.read_text(encoding="utf-8")

    url = wayback_capture_url(ts, original)
    client = session or requests
    resp = client.get(url, headers={"User-Agent": USER_AGENT}, timeout=FETCH_TIMEOUT_S)
    resp.raise_for_status()
    html = resp.text
    path.write_text(html, encoding="utf-8", newline="\n")
    time.sleep(delay_s)
    return html


class CDXError(Exception):
    """The CDX API did not return the JSON this module expects (throttle/503/HTML)."""


def query_cdx(target_url: str = TARGET_URL, *, session: Any = None) -> list[dict]:
    """Query the CDX API, digest-collapsed, status-200-only. Network call.

    Raises :class:`CDXError` with a clear, human-diagnosable message (status
    code + a body snippet) on a non-JSON response — e.g. archive.org
    throttling with a 503 or an HTML error page — instead of letting an
    opaque ``resp.json()`` traceback surface. No retry/backoff: this is a
    one-time, human-observed CLI; the operator diagnoses and re-runs.
    """
    client = session or requests
    params = {
        "url": target_url,
        "output": "json",
        "filter": "statuscode:200",
        "collapse": "digest",
        "fl": "timestamp,original,digest,statuscode",
    }
    resp = client.get(
        CDX_API_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=FETCH_TIMEOUT_S
    )
    resp.raise_for_status()
    try:
        rows = resp.json()
    except ValueError as exc:
        snippet = (resp.text or "")[:100]
        raise CDXError(
            f"CDX API returned a non-JSON response (status {resp.status_code}): "
            f"{snippet!r}"
        ) from exc
    if not rows:
        return []
    header, *data_rows = rows
    return [dict(zip(header, row)) for row in data_rows]


# --------------------------------------------------------------------------
# Parse one capture into per-game observation records
# --------------------------------------------------------------------------

def build_records_from_html(
    html: str,
    *,
    capture_ts: str,
    capture_url: str,
    retrieved_at: str,
    content_hash: str,
) -> list[dict]:
    """Parse one capture's HTML into per-game wayback observation records.

    ``lifecycle_status`` is left ``null`` here — it is assigned only at
    ``build_panel.py`` merge time (design rule 2), which needs the full
    cross-capture sequence to tell ``active`` from ``exited_unobserved``.
    """
    snapshot = parse(html)
    obs_date = parse_obs_date(snapshot["source_timestamp"])
    records = []
    for game in snapshot["games"]:
        records.append(
            {
                "game_no": game["game_no"],
                "game_key": game_key(game["game_no"], game["name"]),
                "obs_date": obs_date,
                "capture_ts": capture_ts,
                "source": "wayback",
                "capture_url": capture_url,
                "retrieved_at": retrieved_at,
                "content_hash": content_hash,
                "parser_version": PARSER_VERSION,
                "percent_unsold": game["percent_unsold"],
                "pu_interval": pu_interval(game["percent_unsold"]),
                "total_unclaimed": game["total_unclaimed"],
                "top_prizes": [dict(tp) for tp in game["top_prizes"]],
                "price": game["price"],
                "name": game["name"],
                "lifecycle_status": None,
            }
        )
    return records


def process_capture(
    cdx_row: dict,
    *,
    cache_dir: Path = RAW_CACHE_DIR,
    session: Any = None,
    delay_s: float = FETCH_DELAY_S,
    now: _dt.datetime | None = None,
) -> tuple[str, list[dict], str | None]:
    """Process one CDX row end-to-end.

    Returns ``(status, records, detail)`` where ``status`` is one of
    ``"era_skipped"``, ``"parse_failed"``, ``"ok"``. Never raises for
    in-era parse/fetch failures — those are reported via the return value
    so the caller can log them and keep going (design rule 3a).
    """
    ts = cdx_row["timestamp"]
    original = cdx_row["original"]

    if is_pre_era(ts):
        return "era_skipped", [], None

    capture_url = wayback_capture_url(ts, original)
    try:
        html = fetch_capture_html(ts, original, cache_dir=cache_dir, session=session, delay_s=delay_s)
    except Exception as exc:  # network/cache failure — logged, never fatal
        return "parse_failed", [], f"{capture_url}: fetch error: {exc}"

    content_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()
    capture_ts = cdx_timestamp_to_datetime(ts).isoformat()
    retrieved_at = (now or _dt.datetime.now(_dt.timezone.utc)).isoformat()

    try:
        records = build_records_from_html(
            html,
            capture_ts=capture_ts,
            capture_url=capture_url,
            retrieved_at=retrieved_at,
            content_hash=content_hash,
        )
    except ParseError as exc:
        return "parse_failed", [], f"{capture_url}: {exc}"

    return "ok", records, None


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

def run_backfill(
    cdx_rows: list[dict],
    *,
    cache_dir: Path = RAW_CACHE_DIR,
    out_path: Path = OBSERVATIONS_PATH,
    session: Any = None,
    delay_s: float = FETCH_DELAY_S,
    now: _dt.datetime | None = None,
) -> dict:
    """Process every CDX row, write the observations JSONL, return a log summary."""
    all_records: list[dict] = []
    summary = {
        "captures_total": len(cdx_rows),
        "parsed": 0,
        "era_skipped": 0,
        "parse_failed": 0,
        "failures": [],
    }

    for row in cdx_rows:
        try:
            status, records, detail = process_capture(
                row, cache_dir=cache_dir, session=session, delay_s=delay_s, now=now
            )
        except Exception as exc:
            # A malformed CDX row (e.g. a non-14-digit timestamp raising
            # ValueError) must never abort the run — the resumable cache
            # would otherwise re-hit the same bad row forever with no
            # progress. Log it with the row content and count it as a
            # failure, then keep going.
            status = "parse_failed"
            records, detail = [], f"malformed CDX row {row!r}: {exc}"

        if status == "era_skipped":
            summary["era_skipped"] += 1
        elif status == "parse_failed":
            summary["parse_failed"] += 1
            summary["failures"].append(detail)
        else:
            summary["parsed"] += 1
            all_records.extend(records)

    all_records.sort(key=lambda r: (r["obs_date"], r["game_no"], r["capture_ts"]))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="\n") as f:
        for rec in all_records:
            f.write(json.dumps(rec, sort_keys=True) + "\n")

    summary["records_written"] = len(all_records)
    return summary


def _build_arg_parser() -> argparse.ArgumentParser:
    parser_ = argparse.ArgumentParser(
        prog="python -m scraper.wayback_backfill",
        description=(
            "One-time manual CLI: backfill data/panel/wayback_observations.jsonl "
            "from web.archive.org captures of the unclaimed-prizes page."
        ),
    )
    parser_.add_argument(
        "--out", type=Path, default=OBSERVATIONS_PATH, help="output JSONL path"
    )
    parser_.add_argument(
        "--cache-dir", type=Path, default=RAW_CACHE_DIR, help="raw HTML cache directory"
    )
    return parser_


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    try:
        cdx_rows = query_cdx()
    except CDXError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    summary = run_backfill(cdx_rows, cache_dir=args.cache_dir, out_path=args.out)
    print(json.dumps(summary, indent=2), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
