"""panel/config.py — PANEL_* configuration loader.

Reads the shell-sourceable `.claude/agent.config` (KEY="VALUE" lines), layered
env > config-file > built-in default per key (mirroring gate.sh), and returns a
typed, frozen PanelConfig. Stdlib only. No PANEL_* value is a secret; the
OpenRouter key is read from the environment by the adapter, never from here.
"""
from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass

from panel.cost_meter import DEFAULT_COST_CAP_USD
from panel.prices import VERIFIED_PRICES

# Built-in defaults (full dotted OpenRouter slugs, verified 2026-07-09).
DEFAULTS = {
    "PANEL_ENABLED": "0",
    "PANEL_TRIGGER": "novelty",
    "PANEL_PROVIDER": "openrouter",
    "PANEL_ROUTING": "exacto",
    "PANEL_MODE_PLAN": "aggregate",
    "PANEL_MODE_REVIEW": "union",
    "PANEL_MAX_COST_USD": str(DEFAULT_COST_CAP_USD),
    "PANEL_VERDICT_PATH": ".claude/state/panel_verdict.json",
    "PANEL_PLAN_LINEUP": "anthropic/claude-fable-5,openai/gpt-5.6-sol",
    "PANEL_PLAN_SYNTH": "anthropic/claude-opus-4.8",
    "PANEL_REVIEW_LINEUP": "anthropic/claude-opus-4.8,openai/gpt-5.6-sol,openai/gpt-5.6-terra",
    "PANEL_REVIEW_ARBITER": "anthropic/claude-fable-5",
}

_TRUE = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class PanelConfig:
    enabled: bool
    trigger: str
    provider: str
    routing: str
    mode_plan: str
    mode_review: str
    max_cost_usd: float
    verdict_path: str
    plan_lineup: tuple
    plan_synth: str
    review_lineup: tuple
    review_arbiter: str
    raw: dict


def parse_config_file(path):
    """Parse shell KEY="VALUE" lines into {KEY: value}. Tolerant of blank lines,
    full-line and trailing (unquoted) comments; preserves '#' inside quotes.
    Missing file -> {}."""
    out = {}
    try:
        text = open(path, encoding="utf-8").read()
    except (FileNotFoundError, IsADirectoryError):
        return out
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, _, val = s.partition("=")
        key, val = key.strip(), val.strip()
        if val and val[0] in "\"'":
            q = val[0]
            end = val.find(q, 1)
            val = val[1:end] if end != -1 else val[1:]  # inner value; preserve '#', drop trailing comment
        elif "#" in val:
            val = val.split("#", 1)[0].strip()           # strip trailing inline comment (unquoted)
        out[key] = val
    return out


def _resolve(key, file_vals, environ):
    env = environ.get(key)
    if env is not None and env != "":
        return env
    if key in file_vals:
        return file_vals[key]
    return DEFAULTS[key]


def _as_bool(s):
    return str(s).strip().lower() in _TRUE


def _as_float(s, default):
    # A cost cap must be finite and positive. inf/nan (from a hand-edited
    # agent.config or env var) would make `total > cap` never breach — a silent
    # cap bypass (audit fix). The dashboard editor already rejects these; the load
    # path now matches, falling back to the default.
    try:
        f = float(s)
    except (TypeError, ValueError):
        return default
    return f if math.isfinite(f) and f > 0 else default


def _as_list(s):
    return tuple(x.strip() for x in str(s).split(",") if x.strip())


def load_config(config_path=".claude/agent.config", environ=None, warn=True):
    environ = os.environ if environ is None else environ
    fv = parse_config_file(config_path)
    r = {k: _resolve(k, fv, environ) for k in DEFAULTS}

    cfg = PanelConfig(
        enabled=_as_bool(r["PANEL_ENABLED"]),
        trigger=r["PANEL_TRIGGER"],
        provider=r["PANEL_PROVIDER"],
        routing=r["PANEL_ROUTING"],
        mode_plan=r["PANEL_MODE_PLAN"],
        mode_review=r["PANEL_MODE_REVIEW"],
        max_cost_usd=_as_float(r["PANEL_MAX_COST_USD"], DEFAULT_COST_CAP_USD),
        verdict_path=r["PANEL_VERDICT_PATH"],
        plan_lineup=_as_list(r["PANEL_PLAN_LINEUP"]),
        plan_synth=r["PANEL_PLAN_SYNTH"],
        review_lineup=_as_list(r["PANEL_REVIEW_LINEUP"]),
        review_arbiter=r["PANEL_REVIEW_ARBITER"],
        raw=r,
    )
    if warn:
        _warn_unknown_slugs(cfg)
    return cfg


def _warn_unknown_slugs(cfg):
    slugs = set(cfg.plan_lineup) | set(cfg.review_lineup) | {cfg.plan_synth, cfg.review_arbiter}
    unknown = sorted(s for s in slugs if s and s not in VERIFIED_PRICES)
    if unknown:
        print(f"[panel.config] warning: {len(unknown)} configured slug(s) absent from the "
              f"verified price table (cost-cap falls back to usage.cost only): "
              f"{', '.join(unknown)}", file=sys.stderr)
