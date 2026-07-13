"""Offline, deterministic merge into the canonical research panel (M6a rule 3b).

Merges ``data/panel/wayback_observations.jsonl`` (produced by the one-time
manual ``scraper/wayback_backfill.py`` CLI) with every ``data/history/*.json``
(the M5 bot-owned daily snapshots) into ``data/panel/panel.jsonl`` — one JSON
object per line, per ``data/schema/panel_record.schema.json``.

No network. Never modifies ``data/history/`` — that stays exactly what M5
made it (a *source* for the panel, never a target). LF-only bytes, UTF-8,
``newline="\\n"`` on every write site (M5a rule 5 precedent). Re-running the
merge from the same inputs is idempotent: a full rebuild, byte-stable output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

# Kept in lockstep with scraper.wayback_backfill.PARSER_VERSION — both name
# the same production parser (scraper.scrape.parse) this pipeline reuses.
PARSER_VERSION = "scraper.scrape@1"

REPO_ROOT = Path(__file__).resolve().parents[1]
WAYBACK_OBS_PATH = REPO_ROOT / "data" / "panel" / "wayback_observations.jsonl"
HISTORY_DIR = REPO_ROOT / "data" / "history"
PANEL_PATH = REPO_ROOT / "data" / "panel" / "panel.jsonl"


# --------------------------------------------------------------------------
# Shared field helpers (mirror scraper.wayback_backfill; no circular import)
# --------------------------------------------------------------------------

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
# Load sources
# --------------------------------------------------------------------------

def load_wayback_observations(path: Path = WAYBACK_OBS_PATH) -> list[dict]:
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _daily_capture_ts(obs_date: str) -> str:
    """Run timestamp for daily records (design rule 2's timezone-ambiguity slot).

    data/history/*.json today only records the run date (``as_of``), not a
    finer-grained clock reading, so the run timestamp is that date at
    midnight UTC — a stated, documented assumption, not silent guessing.
    """
    return f"{obs_date}T00:00:00+00:00"


def load_daily_observations(history_dir: Path = HISTORY_DIR) -> list[dict]:
    """One record per game per data/history/YYYY-MM-DD.json file. Read-only."""
    records: list[dict] = []
    if not history_dir.exists():
        return records
    for path in sorted(history_dir.glob("*.json")):
        raw = path.read_bytes()
        content_hash = hashlib.sha256(raw).hexdigest()
        data = json.loads(raw.decode("utf-8"))
        obs_date = data["as_of"]
        capture_ts = _daily_capture_ts(obs_date)
        try:
            capture_url = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
        except ValueError:
            capture_url = str(path).replace("\\", "/")

        for game in data["games"]:
            records.append(
                {
                    "game_no": game["game_no"],
                    "game_key": game_key(game["game_no"], game["name"]),
                    "obs_date": obs_date,
                    "capture_ts": capture_ts,
                    "source": "daily",
                    "capture_url": capture_url,
                    "retrieved_at": capture_ts,
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


# --------------------------------------------------------------------------
# Merge: dedup/supersession + lifecycle labeling
# --------------------------------------------------------------------------

def merge_panel(wayback_records: list[dict], daily_records: list[dict]) -> tuple[list[dict], list[dict]]:
    """Return ``(merged_records, superseded_log)``, both deterministic given
    deterministic inputs."""
    all_records = list(wayback_records) + list(daily_records)

    # --- dedup: same (game_key, obs_date) observed by >1 distinct-digest
    # capture -> keep the later capture_ts, log the supersession.
    groups: dict[tuple[str, str], list[dict]] = {}
    for rec in all_records:
        key = (rec["game_key"], rec["obs_date"])
        groups.setdefault(key, []).append(rec)

    deduped: list[dict] = []
    superseded_log: list[dict] = []
    for (gkey, obs_date), recs in groups.items():
        if len(recs) == 1:
            deduped.append(recs[0])
            continue
        recs_sorted = sorted(recs, key=lambda r: r["capture_ts"])
        kept = recs_sorted[-1]
        deduped.append(kept)
        for dropped in recs_sorted[:-1]:
            superseded_log.append(
                {
                    "game_key": gkey,
                    "obs_date": obs_date,
                    "superseded_capture_ts": dropped["capture_ts"],
                    "superseded_capture_url": dropped["capture_url"],
                    "kept_capture_ts": kept["capture_ts"],
                    "kept_capture_url": kept["capture_url"],
                }
            )

    # --- lifecycle labeling, per game_key, over its own sorted observations.
    by_game: dict[str, list[dict]] = {}
    for rec in deduped:
        by_game.setdefault(rec["game_key"], []).append(rec)

    all_obs_dates = sorted({rec["obs_date"] for rec in deduped})

    for recs in by_game.values():
        recs.sort(key=lambda r: r["obs_date"])
        for rec in recs[:-1]:
            rec["lifecycle_status"] = "active"
        last = recs[-1]
        if last["percent_unsold"] == 0.0:
            last["lifecycle_status"] = "exited_observed"
        else:
            later_coverage_exists = any(d > last["obs_date"] for d in all_obs_dates)
            last["lifecycle_status"] = (
                "exited_unobserved" if later_coverage_exists else "active"
            )

    deduped.sort(key=lambda r: (r["obs_date"], r["game_no"]))
    return deduped, superseded_log


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

def build_panel(
    wayback_path: Path = WAYBACK_OBS_PATH,
    history_dir: Path = HISTORY_DIR,
    out_path: Path = PANEL_PATH,
) -> dict:
    wayback_records = load_wayback_observations(wayback_path)
    daily_records = load_daily_observations(history_dir)
    merged, superseded = merge_panel(wayback_records, daily_records)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="\n") as f:
        for rec in merged:
            f.write(json.dumps(rec, sort_keys=True) + "\n")

    return {
        "record_count": len(merged),
        "superseded_count": len(superseded),
        "superseded": superseded,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser_ = argparse.ArgumentParser(
        prog="python -m scraper.build_panel",
        description="Offline merge of wayback + daily observations into data/panel/panel.jsonl.",
    )
    parser_.add_argument("--wayback-path", type=Path, default=WAYBACK_OBS_PATH)
    parser_.add_argument("--history-dir", type=Path, default=HISTORY_DIR)
    parser_.add_argument("--out", type=Path, default=PANEL_PATH)
    return parser_


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    summary = build_panel(wayback_path=args.wayback_path, history_dir=args.history_dir, out_path=args.out)
    print(
        json.dumps(
            {"record_count": summary["record_count"], "superseded_count": summary["superseded_count"]},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
