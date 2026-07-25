"""Ticket-complexity scoring + lifecycle burn-rate study (descriptive).

Spec: docs/specs/complexity_burnrate_spec.md. DEV-ONLY analysis — never
imported by anything under ``scraper/`` (test-enforced, same purity rule as
``analysis/phase1_detectability.py``). Reads the committed research panel
(``data/panel/panel.jsonl``), ``data/games.json``, and the frozen maine.gov
article fixtures (play-mechanic text) — fully offline, deterministic, seeded.

Two constructs, kept separate and honest:

1. **Ticket complexity** — per lifecycle:
   - *structural* components, computable for every panel lifecycle from its
     own first observation (+ games.json when the game_no is covered):
     price, count of published top-prize tiers, log10 top-prize level,
     top-prize-to-price ratio, overall odds (where known).
   - *mechanic* components, parsed from the frozen maine.gov article fixtures
     for the ~56 current-era games those cover: match rules, reveal/bonus
     symbols, multiplier magnitude, two-sided play, instruction length.
   The published ``complexity_index`` (0–100) is the mean of the z-scored
   components that EXIST for the game; ``mechanics`` is null (never guessed)
   when no article fixture maps to the lifecycle.

2. **Burn rate** — per usable arc (>= MIN_OBS observations, first observation
   >= MIN_FIRST_PU percent unsold), all relative to the arc's own first
   observation, never interpolated:
   - ``s`` = share of the first-observation inventory sold since the arc
     began = (pu0 - pu) / pu0;  ``u`` = unclaimed dollars as a fraction of
     the first observation's unclaimed dollars.
   - ``burn_gap`` = trapezoid-average of (u - (1 - s)) over the observed
     path: the average unclaimed-money EXCESS above the instant-claim
     diagonal. Positive = prize money lingers unclaimed while inventory
     sells (claim lag / slow burn); negative = prize money exits faster
     than sales (front-loaded wins claimed early / fast burn).
   - ``u_last`` / ``top_value_survival`` / ``tier_attrition`` = how much
     money / value-weighted top-prize mass is still outstanding at the arc's
     LAST sighting, and how many published top tiers vanished (claimed out).

**Censoring honesty (binding, per the M6b discipline):** presence on the
unclaimed page itself implies outstanding prizes — no record in the panel
ever shows zero top prizes remaining, because claimed-out games/tiers are
de-listed. "Ends with outstanding winners" is therefore quantified (how MUCH
is outstanding at the last sighting), never treated as a binary that could
be compared against a games-without-outstanding-winners group, which the
source page cannot produce. ``exited_unobserved`` arcs are last-SIGHTING
censored; the ``near_complete`` cohort (exited, last pu <= NEAR_COMPLETE_PU)
is the honest terminal-state proxy. All correlations are Spearman with
seeded bootstrap CIs and are DESCRIPTIVE — no significance claims, no
confirmatory inference (CONFIRMATORY_INFERENCE_RETIRED, M6b).

CLI:
    python -m analysis.complexity \
        --panel data/panel/panel.jsonl --games data/games.json \
        --articles tests/scraper/fixtures/games \
        --as-of 2026-07-22 --out data/insights/complexity_burn.json

All writes pin ``newline="\n"`` (M5a rule). Public API: :func:`run_study`.
"""
from __future__ import annotations

import argparse
import hashlib
import html as html_mod
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

# --------------------------------------------------------------------------
# Tunable constants (analysis parameters, not schema)
# --------------------------------------------------------------------------

MIN_OBS = 5              # arc usability: minimum observations
MIN_FIRST_PU = 50.0      # arc usability: first obs must be this early in life
NEAR_COMPLETE_PU = 5.0   # terminal-proxy cohort: last obs at/below this
BOOTSTRAP_REPS = 2000    # seeded bootstrap for correlation CIs
DEFAULT_SEED = 20260722
ROUND_DP = 4

# Structural component keys, in publication order.
STRUCTURAL_KEYS = (
    "price",
    "n_top_tiers",
    "log10_top_prize",
    "top_prize_to_price",
    "overall_odds",
)

# Mechanic component keys, in publication order.
MECHANIC_KEYS = (
    "match_rules",
    "reveal_rules",
    "max_multiplier",
    "two_sided",
    "instruction_words",
)


# --------------------------------------------------------------------------
# Article (play-mechanic) parsing — frozen maine.gov fixtures only
# --------------------------------------------------------------------------

_TAG_RE = re.compile(r"<script.*?</script>|<style.*?</style>", re.S | re.I)
_ANY_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_GAME_NO_RE = re.compile(r"Game\s*#\s*(\d+)")
_INSTR_START_RE = re.compile(
    r"Instructions for (?:the )?ticket front|\bTO PLAY\b", re.I
)
_INSTR_END_RE = re.compile(
    r"(HIGHEST INSTANT PRIZE ODDS|OVERALL ODDS OF WINNING|On Sale\b)", re.I
)
_MATCH_RE = re.compile(r"\bmatch(?:es|ing)?\b", re.I)
_REVEAL_RE = re.compile(r"\b(?:reveal|get)\b", re.I)
_MULT_RE = re.compile(r"\b(\d+)\s*(?:X\b|\s*TIMES\b)", re.I)
_BACK_RE = re.compile(r"Instructions for (?:the )?ticket back", re.I)


def _article_text(raw_html: str) -> str:
    text = _TAG_RE.sub(" ", raw_html)
    text = _ANY_TAG_RE.sub(" ", text)
    return _WS_RE.sub(" ", html_mod.unescape(text)).strip()


def parse_article_mechanics(raw_html: str) -> dict | None:
    """Extract play-mechanic complexity signals from one maine.gov article.

    Returns ``None`` when the page carries no recognizable instruction block
    (never guesses). ``game_no`` is parsed from the page's own "Game #N".
    """
    text = _article_text(raw_html)
    m_no = _GAME_NO_RE.search(text)
    if m_no is None:
        return None
    # Instruction block: an explicit header where one exists; otherwise the
    # text immediately following "Game #N" (the dominant maine.gov layout).
    m_start = _INSTR_START_RE.search(text)
    start = m_start.start() if m_start is not None else m_no.end()
    tail = text[start:]
    m_end = _INSTR_END_RE.search(tail)
    instructions = tail[: m_end.start()] if m_end else tail
    mults = [int(x) for x in _MULT_RE.findall(instructions)]
    return {
        "game_no": int(m_no.group(1)),
        "match_rules": len(_MATCH_RE.findall(instructions)),
        "reveal_rules": len(_REVEAL_RE.findall(instructions)),
        "max_multiplier": max(mults) if mults else 1,
        "two_sided": bool(_BACK_RE.search(instructions)),
        "instruction_words": len(instructions.split()),
    }


def load_mechanics(articles_dir: Path) -> dict[int, dict]:
    """Parse every ``article_*.html`` under *articles_dir* → {game_no: mechanics}.

    Deterministic: files are processed in sorted order; on a duplicate
    game_no the lexically-last article wins (stable, logged by caller).
    """
    out: dict[int, dict] = {}
    for path in sorted(articles_dir.glob("article_*.html")):
        parsed = parse_article_mechanics(
            path.read_text(encoding="utf-8", errors="replace")
        )
        if parsed is not None:
            out[parsed["game_no"]] = parsed
    return out


# --------------------------------------------------------------------------
# Panel → lifecycle arcs
# --------------------------------------------------------------------------

def load_lifecycles(panel_path: Path) -> dict[str, list[dict]]:
    by_key: dict[str, list[dict]] = defaultdict(list)
    with panel_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rec = json.loads(line)
                by_key[rec["game_key"]].append(rec)
    for arc in by_key.values():
        arc.sort(key=lambda r: (r["obs_date"], r["capture_ts"]))
    return dict(by_key)


def _top_value(rec: dict) -> float:
    """Value-weighted outstanding top-prize mass; noncash tiers (level null,
    M6a tolerant mode) contribute nothing rather than crashing or guessing."""
    return float(sum(
        tp["level"] * tp["remaining"]
        for tp in rec["top_prizes"]
        if tp.get("level") is not None and tp.get("remaining") is not None
    ))


def arc_burn_metrics(arc: list[dict]) -> dict | None:
    """Burn metrics for one lifecycle arc; ``None`` if the arc is unusable."""
    if len(arc) < MIN_OBS:
        return None
    first, last = arc[0], arc[-1]
    pu0 = first["percent_unsold"]
    u0 = first["total_unclaimed"]
    if pu0 < MIN_FIRST_PU or u0 <= 0:
        return None

    s_path, u_path = [], []
    for rec in arc:
        pu = min(rec["percent_unsold"], pu0)   # guard page corrections upward
        s_path.append((pu0 - pu) / pu0)
        u_path.append(rec["total_unclaimed"] / u0)

    # Monotone-s prefix: sales can only move forward; drop out-of-order noise
    # (page corrections) by keeping the running max of s with its u.
    s_clean, u_clean = [], []
    s_max = -1.0
    for s, u in zip(s_path, u_path):
        if s > s_max:
            s_clean.append(s)
            u_clean.append(u)
            s_max = s
    if len(s_clean) < 2 or s_clean[-1] <= 0:
        return None

    # Trapezoid average of (u - (1 - s)) over observed s-span.
    excess = 0.0
    for i in range(1, len(s_clean)):
        ds = s_clean[i] - s_clean[i - 1]
        e0 = u_clean[i - 1] - (1.0 - s_clean[i - 1])
        e1 = u_clean[i] - (1.0 - s_clean[i])
        excess += 0.5 * (e0 + e1) * ds
    burn_gap = excess / s_clean[-1]

    v0 = _top_value(first)
    v_last = _top_value(last)
    tiers0 = len(first["top_prizes"])
    tiers_last = len(last["top_prizes"])
    exited = last["lifecycle_status"] != "active"

    return {
        "n_obs": len(arc),
        "pu_first": pu0,
        "pu_last": last["percent_unsold"],
        "s_span": round(s_clean[-1], ROUND_DP),
        "burn_gap": round(burn_gap, ROUND_DP),
        "u_last": round(u_clean[-1], ROUND_DP),
        "top_value_survival": (
            round(min(v_last / v0, 1.0), ROUND_DP) if v0 > 0 else None
        ),
        "tier_attrition": (
            round(max(tiers0 - tiers_last, 0) / tiers0, ROUND_DP)
            if tiers0 > 0 else None
        ),
        "lifecycle_status": last["lifecycle_status"],
        "exited": exited,
        "near_complete": exited and last["percent_unsold"] <= NEAR_COMPLETE_PU,
    }


# --------------------------------------------------------------------------
# Complexity components
# --------------------------------------------------------------------------

def structural_components(arc: list[dict], games_meta: dict) -> dict:
    first = arc[0]
    levels = [
        tp["level"] for tp in first["top_prizes"]
        if tp.get("level") is not None          # noncash tiers: level is null
    ]
    top_level = max(levels) if levels else None
    meta = games_meta.get(str(first["game_no"])) or {}
    return {
        "price": first["price"],
        "n_top_tiers": len(first["top_prizes"]),   # counts noncash tiers too
        "log10_top_prize": (
            round(math.log10(top_level), ROUND_DP) if top_level else None
        ),
        "top_prize_to_price": (
            round(top_level / first["price"], ROUND_DP)
            if top_level and first["price"] > 0 else None
        ),
        "overall_odds": meta.get("overall_odds"),
    }


def _zscore_matrix(rows: list[dict], keys: tuple[str, ...]) -> dict[str, tuple]:
    """Per-key (mean, std) over non-null values; std 0 → component skipped."""
    stats = {}
    for key in keys:
        vals = [float(r[key]) for r in rows if r.get(key) is not None]
        if len(vals) >= 2:
            mean = float(np.mean(vals))
            std = float(np.std(vals))
            if std > 0:
                stats[key] = (mean, std)
    return stats


def complexity_index(
    structural: dict, mechanics: dict | None,
    s_stats: dict, m_stats: dict,
) -> float | None:
    """Mean of available z-scored components → rescaled to ~0–100.

    The 0–100 rescale maps z=-2.5 → 0 and z=+2.5 → 100 (clamped): a fixed,
    documented transform — NOT a daily-relative curve (this is a research
    index, not the M4a score).
    """
    zs = []
    for key, (mean, std) in s_stats.items():
        val = structural.get(key)
        if val is not None:
            zs.append((float(val) - mean) / std)
    if mechanics is not None:
        for key, (mean, std) in m_stats.items():
            val = mechanics.get(key)
            if val is not None:
                zs.append((float(val) - mean) / std)   # callers pre-cast bools
    if not zs:
        return None
    z = float(np.mean(zs))
    return round(max(0.0, min(100.0, (z + 2.5) * 20.0)), 2)


# --------------------------------------------------------------------------
# Descriptive association: Spearman + seeded bootstrap CI
# --------------------------------------------------------------------------

def _rank(a: np.ndarray) -> np.ndarray:
    """Ranks with ties averaged (the Spearman convention)."""
    vals, inv, counts = np.unique(a, return_inverse=True, return_counts=True)
    cum = np.cumsum(counts) - counts
    avg = cum + (counts - 1) / 2.0
    return avg[inv]


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    rx, ry = _rank(x), _rank(y)
    rx = rx - rx.mean()
    ry = ry - ry.mean()
    denom = math.sqrt(float((rx ** 2).sum()) * float((ry ** 2).sum()))
    if denom == 0:
        return float("nan")
    return float((rx * ry).sum() / denom)


def spearman_with_ci(
    x: list[float], y: list[float], rng: np.random.Generator,
    reps: int = BOOTSTRAP_REPS,
) -> dict:
    ax, ay = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    n = len(ax)
    rho = spearman(ax, ay)
    boots = np.empty(reps)
    for i in range(reps):
        idx = rng.integers(0, n, n)
        boots[i] = spearman(ax[idx], ay[idx])
    boots = boots[~np.isnan(boots)]
    # Degenerate inputs (a constant variable) have no defined rank
    # correlation: publish null, never NaN (NaN is not valid JSON and
    # breaks equality/determinism checks).
    if math.isnan(rho) or len(boots) == 0:
        return {"n": n, "spearman": None, "ci95": None}
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return {
        "n": n,
        "spearman": round(rho, ROUND_DP),
        "ci95": [round(float(lo), ROUND_DP), round(float(hi), ROUND_DP)],
    }


# --------------------------------------------------------------------------
# Study driver
# --------------------------------------------------------------------------

def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_study(
    panel_path: Path, games_path: Path, articles_dir: Path | None,
    as_of: str, seed: int = DEFAULT_SEED,
) -> dict:
    lifecycles = load_lifecycles(panel_path)
    games_meta = json.loads(games_path.read_text(encoding="utf-8")).get(
        "games", {}
    )
    mechanics_by_no = load_mechanics(articles_dir) if articles_dir else {}

    rows = []
    for game_key in sorted(lifecycles):
        arc = lifecycles[game_key]
        burn = arc_burn_metrics(arc)
        structural = structural_components(arc, games_meta)
        # Mechanics only attach when the article's game_no matches AND the
        # lifecycle is current-era (its game_no appears in games.json) —
        # guards the 2015–2026 game-number-reuse landmine.
        game_no = arc[0]["game_no"]
        mech = (
            {k: mechanics_by_no[game_no][k] for k in MECHANIC_KEYS}
            if game_no in mechanics_by_no and str(game_no) in games_meta
            else None
        )
        rows.append({
            "game_key": game_key,
            "game_no": game_no,
            "name": arc[0]["name"],
            "price": arc[0]["price"],
            "first_obs": arc[0]["obs_date"],
            "last_obs": arc[-1]["obs_date"],
            "structural": structural,
            "mechanics": mech,
            "burn": burn,
        })

    # z-stats over the population, then the per-game index
    s_stats = _zscore_matrix([r["structural"] for r in rows], STRUCTURAL_KEYS)
    mech_rows = [
        {**r["mechanics"], "two_sided": float(r["mechanics"]["two_sided"])}
        for r in rows if r["mechanics"] is not None
    ]
    m_stats = _zscore_matrix(mech_rows, MECHANIC_KEYS)
    for r in rows:
        mech = r["mechanics"]
        mech_num = (
            {**mech, "two_sided": float(mech["two_sided"])} if mech else None
        )
        r["complexity_index"] = complexity_index(
            r["structural"], mech_num, s_stats, m_stats
        )

    # ---- cohorts -----------------------------------------------------------
    usable = [r for r in rows if r["burn"] is not None]
    near_complete = [r for r in usable if r["burn"]["near_complete"]]
    exited_observed = [
        r for r in usable if r["burn"]["lifecycle_status"] == "exited_observed"
    ]

    # ---- correlations (descriptive only) -----------------------------------
    rng = np.random.default_rng(seed)
    correlations = []

    def corr(name, cohort, xkey, ykey, xget, yget, note):
        pairs = [
            (xget(r), yget(r)) for r in cohort
            if xget(r) is not None and yget(r) is not None
        ]
        if len(pairs) < 10:
            correlations.append({
                "id": name, "x": xkey, "y": ykey, "n": len(pairs),
                "spearman": None, "ci95": None,
                "note": f"SKIPPED — n={len(pairs)} < 10. {note}",
            })
            return
        xs, ys = zip(*pairs)
        result = spearman_with_ci(list(xs), list(ys), rng)
        correlations.append(
            {"id": name, "x": xkey, "y": ykey, **result, "note": note}
        )

    cx = lambda r: r["complexity_index"]
    correlations_spec = [
        ("complexity_vs_burn_gap", usable, "complexity_index", "burn_gap",
         cx, lambda r: r["burn"]["burn_gap"],
         "All usable arcs. Positive burn_gap = unclaimed money lingers "
         "above the instant-claim diagonal."),
        ("complexity_vs_terminal_unclaimed", near_complete,
         "complexity_index", "u_last",
         cx, lambda r: r["burn"]["u_last"],
         "Near-complete cohort (exited, last pu <= "
         f"{NEAR_COMPLETE_PU}%): terminal-state proxy."),
        ("complexity_vs_top_survival", near_complete,
         "complexity_index", "top_value_survival",
         cx, lambda r: r["burn"]["top_value_survival"],
         "Value-weighted top-prize mass still outstanding at last sighting."),
        ("burn_gap_vs_top_survival", usable, "burn_gap", "top_value_survival",
         lambda r: r["burn"]["burn_gap"],
         lambda r: r["burn"]["top_value_survival"],
         "Available winners vs money on sold-but-unclaimed tickets: do "
         "slow-burn games also keep top prizes alive?"),
        ("price_vs_burn_gap", usable, "price", "burn_gap",
         lambda r: r["price"], lambda r: r["burn"]["burn_gap"],
         "Confounder check: price alone vs burn_gap."),
        ("complexity_vs_tier_attrition", near_complete,
         "complexity_index", "tier_attrition",
         cx, lambda r: r["burn"]["tier_attrition"],
         "Share of published top tiers that vanished (claimed out) by the "
         "last sighting."),
    ]
    for spec in correlations_spec:
        corr(*spec)

    # Within-price-band strata: the price confounder check that matters —
    # does complexity still track burn once price is held (nearly) fixed?
    bands = [(1.0, 1.0), (2.0, 2.0), (3.0, 3.0), (5.0, 5.0), (10.0, 30.0)]
    for lo, hi in bands:
        stratum = [r for r in near_complete if lo <= r["price"] <= hi]
        label = f"${int(lo)}" if lo == hi else f"${int(lo)}-{int(hi)}"
        corr(
            f"complexity_vs_terminal_unclaimed_{label}", stratum,
            "complexity_index", "u_last",
            cx, lambda r: r["burn"]["u_last"],
            f"Near-complete cohort, {label} price band only "
            "(price-confounder control).",
        )

    return {
        "as_of": as_of,
        "params": {
            "min_obs": MIN_OBS,
            "min_first_pu": MIN_FIRST_PU,
            "near_complete_pu": NEAR_COMPLETE_PU,
            "bootstrap_reps": BOOTSTRAP_REPS,
            "seed": seed,
            "index_transform": "mean-z, z=-2.5→0 / z=+2.5→100, clamped",
        },
        "inputs": {
            "panel_path": str(panel_path).replace("\\", "/"),
            "panel_sha256": _sha256(panel_path),
            "games_sha256": _sha256(games_path),
            "n_records": sum(len(a) for a in lifecycles.values()),
            "n_lifecycles": len(lifecycles),
            "n_articles_parsed": len(mechanics_by_no),
        },
        "cohorts": {
            "usable_arcs": len(usable),
            "near_complete": len(near_complete),
            "exited_observed": len(exited_observed),
            "with_mechanics": sum(
                1 for r in rows if r["mechanics"] is not None
            ),
        },
        "caveats": [
            "DESCRIPTIVE ONLY — no significance claims; confirmatory lag "
            "inference is retired for this panel (M6b).",
            "Presence on the unclaimed page implies outstanding prizes: "
            "claimed-out games/tiers are de-listed, so 'ended with "
            "outstanding winners' is quantified (how much remained at last "
            "sighting), never a binary vs. a nonexistent comparison group.",
            "exited_unobserved arcs are last-sighting censored; only the "
            "near_complete cohort approximates terminal state.",
            "Mechanics cover only current-era games with frozen article "
            "fixtures; historical complexity is structural-only.",
            "Wayback-era arcs are irregular-interval; burn_gap uses the "
            "trapezoid over observed points, never daily interpolation.",
        ],
        "correlations": correlations,
        "games": rows,
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m analysis.complexity",
        description="Ticket-complexity + burn-rate descriptive study "
                    "(offline, deterministic).",
    )
    ap.add_argument("--panel", type=Path, required=True)
    ap.add_argument("--games", type=Path, required=True)
    ap.add_argument("--articles", type=Path, default=None,
                    help="dir of frozen article_*.html fixtures (optional)")
    ap.add_argument("--as-of", required=True,
                    help="ISO date stamped into the output (run truth)")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--out", type=Path, default=None,
                    help="write JSON here (default: stdout)")
    args = ap.parse_args(argv)

    try:
        doc = run_study(args.panel, args.games, args.articles,
                        args.as_of, args.seed)
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    payload = json.dumps(doc, indent=1)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(payload + "\n")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
