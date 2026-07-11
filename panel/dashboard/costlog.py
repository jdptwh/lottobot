"""Dashboard-owned append-only cost log (JSONL). Read-only w.r.t. the CLI and the
verdict file: the dashboard records each newly-observed verdict so the cost meter can
accumulate honestly without touching Wave 4. Idempotent by (task_id, cost_usd_total)."""
from __future__ import annotations

import json
import os


def _read(path):
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    except FileNotFoundError:
        pass
    return out


def _fingerprint(v):
    return (v.get("task_id"), v.get("cost_usd_total"))


def observe(cost_log_path, verdict):
    """Append one entry iff this (task_id, cost_usd_total) is new. Returns True if
    appended, False if it was already recorded. Never raises on a missing dir."""
    if not isinstance(verdict, dict) or "cost_usd_total" not in verdict:
        return False
    fp = _fingerprint(verdict)
    for e in _read(cost_log_path):
        if _fingerprint(e) == fp:
            return False
    entry = {
        "task_id": verdict.get("task_id"),
        "gate": verdict.get("gate"),
        "verdict": verdict.get("verdict"),
        "cost_usd_total": verdict.get("cost_usd_total"),
        "cost_cap_breached": verdict.get("cost_cap_breached"),
    }
    d = os.path.dirname(os.path.abspath(cost_log_path)) or "."
    os.makedirs(d, exist_ok=True)
    with open(cost_log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return True


def tally(cost_log_path):
    """Return {total_usd, count, latest, entries} over the distinct observed verdicts."""
    entries = _read(cost_log_path)
    total = 0.0
    for e in entries:
        try:
            total += float(e.get("cost_usd_total") or 0)
        except (TypeError, ValueError):
            pass
    return {"total_usd": round(total, 6), "count": len(entries),
            "latest": entries[-1] if entries else None, "entries": entries}
