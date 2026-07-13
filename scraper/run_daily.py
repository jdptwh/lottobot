"""Daily orchestrator (M5): scrape -> compute -> gate -> commit-ready write.

A thin orchestrator (docs/specs/m5_daily_action_spec.md, Resolution 1): it
imports the existing M1/M3 functions and re-implements zero parsing/EV/
scoring/gate logic. It is the runtime entry point invoked by
``.github/workflows/daily.yml`` (``--live``) and by the offline test suite
(``--fixture``).

Pipeline order (exact, per the spec's "Design rules of record"):

1. Read prior bytes from ``--prior`` into memory (missing file -> inert
   first run; a stderr note is printed, no gate check happens later).
2. Obtain HTML: ``--fixture`` reads a frozen file, or ``--live`` makes
   exactly one :func:`scraper.scrape.fetch` call.
3. :func:`scraper.scrape.parse`.
4. :func:`scraper.compute.compute_latest` (runs the §6.1 parser gate
   internally).
5. Schema gate (§6.3, first runtime enforcement): ``jsonschema.validate``.
6. Diff gate (§6.4): :func:`scraper.compute.diff_gate`, only if a prior
   document was loaded.
7. Write ``--out``, then write ``--history-dir/{as_of}.json`` (byte-identical
   copy of the same run's output).

Failure semantics: any of ``ParseError``, ``GateError``,
``RobotsDisallowed``, ``requests.RequestException``,
``jsonschema.ValidationError``, ``json.JSONDecodeError``, ``OSError`` is
caught, printed as ``error: {exc}`` to stderr, and returns exit code 1.
**No write of any kind happens before the final write step** — a failure at
any gate leaves the filesystem untouched.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import jsonschema
import requests

from scraper.compute import compute_latest, diff_gate
from scraper.scrape import GateError, ParseError, RobotsDisallowed, fetch, parse

# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scraper.run_daily",
        description=(
            "Daily orchestrator: scrape -> compute -> gate -> write "
            "data/latest.json + data/history/{as_of}.json. Reimplements no "
            "parsing/EV/scoring/gate logic (thin wrapper only)."
        ),
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--fixture", type=Path, help="path to a frozen HTML fixture")
    source.add_argument(
        "--live", action="store_true", help="fetch the live unclaimed-prizes page"
    )
    parser.add_argument(
        "--games", type=Path, default=Path("data/games.json"),
        help="path to data/games.json (default: %(default)s)",
    )
    parser.add_argument(
        "--schema", type=Path, default=Path("data/schema/latest.schema.json"),
        help="path to the latest.json JSON Schema (default: %(default)s)",
    )
    parser.add_argument(
        "--out", type=Path, default=Path("data/latest.json"),
        help="write the day's latest.json here (default: %(default)s)",
    )
    parser.add_argument(
        "--prior", type=Path, default=None,
        help=(
            "path to a prior latest.json for the §6.4 diff gate; default is "
            "the resolved value of --out; missing means an inert first run"
        ),
    )
    parser.add_argument(
        "--history-dir", type=Path, default=Path("data/history"),
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


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    prior_path = args.prior if args.prior is not None else args.out
    as_of = args.as_of or datetime.now(timezone.utc).date().isoformat()

    try:
        prior_doc = None
        if prior_path.exists():
            prior_doc = json.loads(prior_path.read_text(encoding="utf-8"))
        else:
            print(
                "note: no prior latest.json given/found; diff gate skipped "
                "(inert first run)",
                file=sys.stderr,
            )

        html = args.fixture.read_text(encoding="utf-8") if args.fixture else fetch()

        snapshot = parse(html)
        games_meta = json.loads(args.games.read_text(encoding="utf-8"))
        new_doc = compute_latest(snapshot, games_meta, as_of)

        schema = json.loads(args.schema.read_text(encoding="utf-8"))
        jsonschema.validate(instance=new_doc, schema=schema)

        if prior_doc is not None:
            diff_gate(new_doc, prior_doc)

        output = json.dumps(new_doc, indent=2)

        args.out.write_text(output, encoding="utf-8")
        args.history_dir.mkdir(parents=True, exist_ok=True)
        (args.history_dir / f"{as_of}.json").write_text(output, encoding="utf-8")
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
