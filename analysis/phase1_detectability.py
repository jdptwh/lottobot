"""Pooled distributed-lag detectability study (M6b / Phase 1).

Governed by `docs/specs/m6_v2_program_spec.md` Phase 1 and
`docs/specs/m6_data_strategy_panel.md` points 5/6/9, AND (this revision)
`docs/specs/m6b_estimator_redesign_addendum.md` section 2 (the redesign of
record after the first arbitration) AS AMENDED by
`docs/specs/m6b_panel_amendment2.md` (second, panel-arbitrated arbitration).
Amendment2 supersedes addendum rules 3 (demeaning), 5 (permutation), and 6
(synthetic generator); addendum rules 1 (pairing) and 2 (normalization)
stand unchanged, and rule 4 (rank statistic decides significance; OLS is
effect-size only) stands WITH a studentization change (below). This module
transcribes amendment2's replacement rules verbatim; irregular intervals are
respected natively (no daily interpolation), `pu_interval` censoring is used
instead of exact-sales arithmetic, and the estimator produces ROBUST POOLED
distributed-lag summaries only -- never a per-game Kaplan-Meier curve and
never a per-tier lower-tier claim (unidentifiable per the panel's critical
finding). Two components are estimated and reported SEPARATELY:

  - "top" (top-tier): sparse observed count-decrement events on the game's
    published top-prize tier(s), pooled heavily (no price/phase split).
  - "lower" (lower tiers): ONE pooled dollar-weighted lag kernel from
    aggregate `total_unclaimed` deltas vs. interval-censored sales movement,
    never split into per-tier claims.

Redesign of record, addendum rules 1/2 (UNCHANGED, transcribed):

  1. Pairing: ALL ordered disjoint window pairs within a lifecycle (every
     (A, B) with B.start >= A.end), not adjacent-only. Lag L = B.mid -
     A.mid, positive by construction; s is always the EARLIER window's
     sales rate, d is always the LATER window's claim/decrement rate.
  2. Normalization: per-lifecycle SCALE constant, not per-window. Lower
     tier: d_B = (U_start - U_end) / (dt_B * U_max_g), U_max_g = that
     lifecycle's maximum observed total_unclaimed. Top tier:
     decrement / (dt_B * r_max_g), r_max_g = max observed remaining count.
     s_A unchanged (already scale-free). No dollar floor -- the guard is
     only "skip windows with U_start <= 0".

Amendment2 Replacement Rule 3 -- DETRENDING (supersedes addendum rule 3,
demeaning): for each lifecycle with >= 6 usable windows and >= 3 distinct
window-midpoint times, normalize midpoint time x = (t - midrange) /
(half-range) and, separately for s and d, fit y = a + b*x + c*x^2 by
closed-form OLS; retain residuals e = y - yhat. Reject singular or
numerically ill-conditioned fits. Build all pairs, Spearman statistics, and
weighted OLS effect sizes from these residuals. Shorter lifecycles (or a
lifecycle whose fit is singular/ill-conditioned) are EXCLUDED from
confirmatory inference and the exclusion is reported, never silently
dropped. Quadratic (not linear) detrending is required because exponential
decay leaves shared curvature after a linear fit -- this is the diagnosed
defect this amendment fixes (shared lifecycle decay trends survived
demeaning/linear detrending and produced all-bins false positives on null
data). No first-differencing (s and d are already stock-change rates) and
no per-lifecycle polynomial-degree variation.

Statistic (addendum rule 4, STANDS): the Spearman rank correlation (tie-
corrected via average ranks) of the pooled per-bin (s, d) residual pairs
(unweighted ranks) decides detection/significance. The dollar-weighted OLS
slope (weight = the per-lifecycle scale constant, capped at the bin's own
90th-percentile weight) is reported alongside as the kernel MAGNITUDE only.

Amendment2 Replacement Rule 4 -- RANDOMIZATION AND FAMILY-WISE TEST
(supersedes addendum rule 5, permutation): for each replicate and lifecycle,
draw a circular offset uniformly from ALL offsets {0, ..., m-1} INCLUDING
IDENTITY, circularly shift the lifecycle's ordered d-residual vector, and
REPROJECT it through the same quadratic residual-maker (refit the closed-
form quadratic OLS on the shifted vector against the SAME (fixed) x
positions, take the new residuals: e* = M(Pe)). Rebuild all pairs and
statistics from these reprojected residuals. Studentize each eligible bin
using ITS OWN permutation mean and standard deviation (two-pass: first pass
builds the per-bin null distribution and its mean/sd; second pass converts
every replicate's per-bin statistic to a z-score with that same mean/sd and
takes the replicate's maximum |z| across bins), and use the empirical
distribution of those replicate maxima for family-wise-adjusted p-values:
p = (1 + #exceedances) / (R + 1), with >= 1999 replicates for a p < 0.01
recovery claim, fixed seed.

Eligibility and diagnostics (amendment2): n_pairs >= 30 is retained only as
a computational floor; a bin additionally requires broad lifecycle support
(pre-registered minimum, provisionally 15 contributing lifecycles). Every
bin fit reports contributor lifecycle count, the largest single lifecycle's
pair-share, an effective-concentration (Herfindahl) index, and leave-one-
lifecycle-out sensitivity (max |rank-stat delta| from dropping any single
contributing lifecycle) -- for a human/report to INSPECT before making a
confirmatory claim (amendment2 Execution step 5). No automatic swap to a
lifecycle-balanced cluster statistic is implemented -- amendment2 does not
specify the trigger threshold for that swap, so it is left as a reported
diagnostic, not an automated decision.

EXHAUSTION OUTCOME (amendment2's own fallback/exhaustion clause, reached
during Phase-1 build validation, see `CONFIRMATORY_INFERENCE_RETIRED`
below): the primary randomization (circular-shift reprojection) failed the
shared-curvature null; the amendment's own pre-authorized fallback
(stratified between-lifecycle whole-sequence swap, `_stratified_swap_rep`)
cleared it for the lower-tier component but NOT for the top-tier
(count-based) component at the production pooling scale. Per amendment2:
"If both calibrated randomization approaches fail, stop confirmatory
inference and deliver a null-calibrated descriptive analysis without
significant-bin claims; top-tier-only is not an automatic remedy because
the same confounding applies there." This module therefore reports
`rank_stat` / `dollar_slope` / `p_value` / `diagnostics` as DESCRIPTIVE
outputs only; `BinResult.significant()` remains available as a raw
p<alpha diagnostic but is never a validated confirmatory claim while
`CONFIRMATORY_INFERENCE_RETIRED` is True.

Stdlib only (the redesign's SNR check found detectability is an alignment-
geometry question, not a numerical-library question, so numpy is not needed
here; the closed-form 3x3 quadratic solve is small enough for a pure-Python
Gaussian elimination with an explicit conditioning check).

Reproducible entry point:
    python -m analysis.phase1_detectability --panel data/panel/panel.jsonl
prints a JSON summary (data inventory, kernels, bootstrap CIs, GO/NO-GO
inputs) used verbatim by docs/reports/m6_phase1_detectability_report.md.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants (pooling scheme)
# ---------------------------------------------------------------------------

# Lag bins in whole calendar days between the midpoint of the earlier
# ("sales") window and the midpoint of the later ("claim"/"decrement")
# window. Chosen to match the panel's actual cadence (wayback gaps run
# ~1-9 months; see the data-inventory section of the report) rather than an
# arbitrary fine grid the panel cannot resolve.
LAG_BINS: list[tuple[int, int]] = [
    (0, 45),
    (45, 90),
    (90, 150),
    (150, 250),
    (250, 400),
    (400, 800),
]

# Price bands (Maine's instant price points are a small discrete set:
# 1, 2, 3, 5, 10, 20, 25, 30 -- see the report's data inventory).
PRICE_BANDS: list[tuple[str, tuple[float, ...]]] = [
    ("low_1_3", (1.0, 2.0, 3.0)),
    ("mid_5", (5.0,)),
    ("midhigh_10", (10.0,)),
    ("high_20plus", (20.0, 25.0, 30.0)),
]

# Lifecycle phase, by percent-unsold MIDPOINT at the start of a window.
PHASE_EARLY_MIN = 50.0
PHASE_LATE_MAX = 15.0

MIN_PAIRS_FOR_FIT = 30  # computational floor only (amendment2 eligibility note)
MIN_LIFECYCLES_FOR_FIT = 15  # amendment2: pre-registered minimum contributing lifecycles per bin

MIN_WINDOWS_FOR_DETREND = 6           # amendment2 replacement rule 3
MIN_DISTINCT_MIDPOINTS_FOR_DETREND = 3  # amendment2 replacement rule 3
QUAD_COND_REL_TOL = 1e-9              # numerical conditioning tolerance for the 3x3 solve

BOOTSTRAP_REPS = 1000
BOOTSTRAP_SEED = 20260713
CI_LOW, CI_HIGH = 0.05, 0.95  # 90% percentile bootstrap CI

# Amendment2 replacement rule 4: >= 1999 replicates required for a p < 0.01
# recovery claim.
PERMUTATION_REPS = 1999
PERMUTATION_SEED = 20260714
PERMUTATION_ALPHA = 0.05

WEIGHT_CAP_PERCENTILE = 0.90


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_panel_records(path: str | Path) -> list[dict]:
    records = []
    with open(path, "r", encoding="utf-8", newline="") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def parse_iso_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def price_band(price: float) -> str:
    for label, prices in PRICE_BANDS:
        if price in prices:
            return label
    return "other"


def phase_of(pu_mid_value: float) -> str:
    if pu_mid_value >= PHASE_EARLY_MIN:
        return "early"
    if pu_mid_value <= PHASE_LATE_MAX:
        return "late"
    return "mid"


def lag_bin_for(days: float) -> tuple[int, int] | None:
    for lo, hi in LAG_BINS:
        if lo <= days < hi:
            return (lo, hi)
    return None


def pu_mid(record: dict) -> float:
    """Midpoint of pu_interval [lo, hi) -- never the rounded point value."""
    lo, hi = record["pu_interval"]
    return (lo + hi) / 2.0


def top_prize_remaining_by_level(record: dict) -> dict[int, int]:
    """Numeric (cash) top-prize levels only -- noncash cells (level: null)
    are excluded from top-tier decrement counting per docs/m6_semantics.md
    ruling 3 (their count units are not comparable to cash tiers); this is a
    stated Phase-1 assumption, not a silent guess."""
    out = {}
    for tp in record.get("top_prizes", []):
        if tp.get("level") is not None:
            out[tp["level"]] = tp["remaining"]
    return out


def _top_decrement(a: dict, b: dict) -> int:
    top0, top1 = top_prize_remaining_by_level(a), top_prize_remaining_by_level(b)
    return sum(max(0, top0[lvl] - top1[lvl]) for lvl in top0 if lvl in top1)


# ---------------------------------------------------------------------------
# Windows (raw, per-lifecycle-adjacent-observation) and lifecycle scaling
# ---------------------------------------------------------------------------

@dataclass
class Window:
    game_key: str
    start: date
    end: date
    dt_days: float
    price: float
    pu_mid_start: float
    sales_rate: float          # (pu_mid_start - pu_mid_end) / dt_days, points/day; scale-free
    top_start: dict
    top_end: dict
    lower_d: float | None      # (U_start - U_end) / (dt_days * U_max_g); None if U_start <= 0
    top_d: float | None        # decrement / (dt_days * r_max_g); None if r_max_g <= 0

    @property
    def mid(self) -> date:
        return self.start + (self.end - self.start) / 2


def lifecycle_scale_constants(records: list[dict]) -> tuple[float, int]:
    """U_max_g (max observed total_unclaimed) and r_max_g (max observed
    total top-tier remaining count) for one lifecycle -- addendum rule 2:
    normalization is a PER-LIFECYCLE scale constant, not a per-window one."""
    u_max = max((r["total_unclaimed"] for r in records), default=0.0)
    r_max = max(
        (sum(top_prize_remaining_by_level(r).values()) for r in records), default=0
    )
    return float(u_max), int(r_max)


def build_windows(records: list[dict], u_max_g: float, r_max_g: float) -> list[Window]:
    """Adjacent-observation windows within one lifecycle, sorted by
    obs_date. Irregular gaps are used exactly as observed -- never
    interpolated. Guard: a window with `total_unclaimed_start <= 0` gets
    `lower_d = None` (skip, not clamp -- addendum rule 2)."""
    windows: list[Window] = []
    for a, b in zip(records, records[1:]):
        d0, d1 = parse_iso_date(a["obs_date"]), parse_iso_date(b["obs_date"])
        dt_days = (d1 - d0).days
        if dt_days <= 0:
            continue  # duplicate/out-of-order obs_date; skip rather than divide by zero
        pu0, pu1 = pu_mid(a), pu_mid(b)
        u0, u1 = a["total_unclaimed"], b["total_unclaimed"]
        decrement = _top_decrement(a, b)

        lower_d = None
        if u0 > 0 and u_max_g > 0:
            lower_d = (u0 - u1) / (dt_days * u_max_g)

        top_d = None
        if r_max_g > 0:
            top_d = decrement / (dt_days * r_max_g)

        windows.append(
            Window(
                game_key=a["game_key"],
                start=d0,
                end=d1,
                dt_days=float(dt_days),
                price=a["price"],
                pu_mid_start=pu0,
                sales_rate=(pu0 - pu1) / dt_days,
                top_start=top_prize_remaining_by_level(a),
                top_end=top_prize_remaining_by_level(b),
                lower_d=lower_d,
                top_d=top_d,
            )
        )
    return windows


# ---------------------------------------------------------------------------
# Closed-form quadratic OLS (3x3 normal equations, pure stdlib)
# ---------------------------------------------------------------------------

def _quadratic_design_row(x: float) -> list[float]:
    return [1.0, x, x * x]


def _normal_equations(xs: list[float], ys: list[float]) -> tuple[list[list[float]], list[float]]:
    XtX = [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]
    Xty = [0.0, 0.0, 0.0]
    for x, y in zip(xs, ys):
        row = _quadratic_design_row(x)
        for a in range(3):
            Xty[a] += row[a] * y
            for b in range(3):
                XtX[a][b] += row[a] * row[b]
    return XtX, Xty


def _solve_3x3(XtX: list[list[float]], Xty: list[float], tol: float = QUAD_COND_REL_TOL) -> list[float] | None:
    """Gaussian elimination with partial pivoting on the augmented 3x4
    matrix. Returns None if the system is singular or numerically
    ill-conditioned (pivot magnitude below `tol` relative to the matrix's
    own scale) -- amendment2's explicit numerical-conditioning requirement
    (a panel-flagged blind spot: no expert specified this tolerance)."""
    n = 3
    A = [XtX[i][:] + [Xty[i]] for i in range(n)]
    scale = max((abs(A[r][c]) for r in range(n) for c in range(n)), default=0.0)
    if scale <= 0.0:
        return None
    for col in range(n):
        pivot_row = max(range(col, n), key=lambda r: abs(A[r][col]))
        pivot_val = A[pivot_row][col]
        if abs(pivot_val) < tol * max(scale, 1.0):
            return None  # singular or ill-conditioned
        if pivot_row != col:
            A[col], A[pivot_row] = A[pivot_row], A[col]
        pivot_val = A[col][col]
        for r in range(n):
            if r == col:
                continue
            factor = A[r][col] / pivot_val
            if factor == 0.0:
                continue
            for c in range(col, n + 1):
                A[r][c] -= factor * A[col][c]
    beta = []
    for i in range(n):
        if A[i][i] == 0.0:
            return None
        beta.append(A[i][n] / A[i][i])
    return beta


def fit_quadratic_residuals(xs: list[float], ys: list[float]) -> list[float] | None:
    """Amendment2 replacement rule 3/4: closed-form OLS fit y = a + b*x +
    c*x^2, returning residuals e = y - yhat, or None if the fit is singular
    or ill-conditioned (fewer than 3 points, or fewer than 3 distinct x
    values, or a numerically degenerate normal-equations matrix)."""
    n = len(xs)
    if n < 3 or n != len(ys):
        return None
    if len(set(round(x, 12) for x in xs)) < 3:
        return None
    XtX, Xty = _normal_equations(xs, ys)
    beta = _solve_3x3(XtX, Xty)
    if beta is None:
        return None
    a, b, c = beta
    return [y - (a + b * x + c * x * x) for x, y in zip(xs, ys)]


def _normalize_midpoint_x(mids: list[date]) -> list[float] | None:
    """x = (t - midrange) / (half-range), amendment2 replacement rule 3."""
    ordinals = [m.toordinal() for m in mids]
    lo, hi = min(ordinals), max(ordinals)
    half_range = (hi - lo) / 2.0
    if half_range <= 0:
        return None
    midrange = (lo + hi) / 2.0
    return [(o - midrange) / half_range for o in ordinals]


# ---------------------------------------------------------------------------
# Detrending (amendment2 replacement rule 3, supersedes addendum rule 3) and
# all-ordered-disjoint pairing (addendum rule 1, unchanged)
# ---------------------------------------------------------------------------

@dataclass
class DetrendedWindow:
    game_key: str
    start: date
    end: date
    price: float
    pu_mid_start: float
    x: float        # normalized midpoint time used for this lifecycle's quadratic fit
    s: float        # quadratic-detrended sales-rate residual
    d: float        # quadratic-detrended response-rate residual
    weight: float   # U_max_g for "lower"; 1.0 for "top"

    @property
    def mid(self) -> date:
        return self.start + (self.end - self.start) / 2


EXCLUSION_KEYS = (
    "insufficient_windows",
    "insufficient_distinct_midpoints",
    "singular_or_ill_conditioned_fit",
)


def build_lifecycle_detrended_windows(
    lifecycles: dict[str, list[dict]], component: str
) -> tuple[dict[str, list[DetrendedWindow]], dict[str, int]]:
    """Amendment2 replacement rule 3: for each lifecycle with >=
    MIN_WINDOWS_FOR_DETREND usable windows and >=
    MIN_DISTINCT_MIDPOINTS_FOR_DETREND distinct window-midpoint times,
    normalize midpoint time and fit a quadratic (separately for s and d),
    retaining residuals. Lifecycles that don't meet the window/midpoint
    floor, or whose fit is singular/ill-conditioned, are EXCLUDED from
    confirmatory inference; the exclusion counts are returned (never
    silently dropped) for the caller to report."""
    d_attr = "lower_d" if component == "lower" else "top_d"
    windows_map: dict[str, list[DetrendedWindow]] = {}
    exclusions = {k: 0 for k in EXCLUSION_KEYS}
    for game_key, records in lifecycles.items():
        u_max_g, r_max_g = lifecycle_scale_constants(records)
        raw_windows = build_windows(records, u_max_g, r_max_g)
        valid = [w for w in raw_windows if getattr(w, d_attr) is not None]
        if len(valid) < MIN_WINDOWS_FOR_DETREND:
            exclusions["insufficient_windows"] += 1
            continue
        mids = [w.mid for w in valid]
        if len(set(mids)) < MIN_DISTINCT_MIDPOINTS_FOR_DETREND:
            exclusions["insufficient_distinct_midpoints"] += 1
            continue
        xs = _normalize_midpoint_x(mids)
        if xs is None:
            exclusions["insufficient_distinct_midpoints"] += 1
            continue
        s_vals = [w.sales_rate for w in valid]
        d_vals = [getattr(w, d_attr) for w in valid]
        s_resid = fit_quadratic_residuals(xs, s_vals)
        d_resid = fit_quadratic_residuals(xs, d_vals)
        if s_resid is None or d_resid is None:
            exclusions["singular_or_ill_conditioned_fit"] += 1
            continue
        weight_value = u_max_g if component == "lower" else 1.0
        detrended = [
            DetrendedWindow(
                game_key=w.game_key,
                start=w.start,
                end=w.end,
                price=w.price,
                pu_mid_start=w.pu_mid_start,
                x=x,
                s=s,
                d=d,
                weight=weight_value,
            )
            for w, x, s, d in zip(valid, xs, s_resid, d_resid)
        ]
        windows_map[game_key] = detrended  # already time-sorted (valid derives from sorted records)
    return windows_map, exclusions


@dataclass
class Pair:
    game_key: str
    price_band: str
    phase: str
    lag_bin: tuple[int, int]
    lag_days: float
    s: float       # EARLIER window's detrended sales residual
    d: float       # LATER window's detrended response residual
    weight: float  # dollar-weighted for "lower"; 1.0 for "top"


@dataclass
class LocalPair:
    """A within-lifecycle pair's fixed structure (index positions, bin, and
    `s`, none of which change under the amendment2 rule-4 permutation --
    only the `d` value at index `j` is re-drawn each replicate)."""
    i: int
    j: int
    price_band: str
    phase: str
    lag_bin: tuple[int, int]
    lag_days: float
    s: float


def _local_pairs_for_lifecycle(windows: list[DetrendedWindow]) -> list[LocalPair]:
    """Addendum rule 1 (unchanged): EVERY ordered disjoint (A, B) pair
    within a lifecycle (B.start >= A.end), never adjacent-only."""
    n = len(windows)
    out: list[LocalPair] = []
    for i in range(n):
        a = windows[i]
        for j in range(i + 1, n):
            b = windows[j]
            if b.start < a.end:
                continue  # not disjoint; should not occur for time-sorted non-overlapping windows
            lag_days = (b.mid - a.mid).days
            bin_ = lag_bin_for(lag_days)
            if bin_ is None:
                continue
            out.append(
                LocalPair(
                    i=i,
                    j=j,
                    price_band=price_band(a.price),
                    phase=phase_of(a.pu_mid_start),
                    lag_bin=bin_,
                    lag_days=float(lag_days),
                    s=a.s,
                )
            )
    return out


@dataclass
class LifecycleFit:
    """Precomputed, per-lifecycle fixed structure reused across every
    permutation replicate: window list (with fixed x positions and the
    observed detrended s/d), and the local pair skeleton (fixed i/j/bin/s;
    only `d` at index j is re-drawn per replicate)."""
    game_key: str
    windows: list[DetrendedWindow]
    xs: list[float]
    local_pairs: list[LocalPair]


def _lifecycle_fits_from_windows_map(
    windows_map: dict[str, list[DetrendedWindow]]
) -> dict[str, LifecycleFit]:
    out: dict[str, LifecycleFit] = {}
    for game_key, windows in windows_map.items():
        out[game_key] = LifecycleFit(
            game_key=game_key,
            windows=windows,
            xs=[w.x for w in windows],
            local_pairs=_local_pairs_for_lifecycle(windows),
        )
    return out


def _pairs_from_fits(lifecycle_fits: dict[str, LifecycleFit]) -> list[Pair]:
    pairs: list[Pair] = []
    for fit in lifecycle_fits.values():
        for lp in fit.local_pairs:
            b = fit.windows[lp.j]
            pairs.append(
                Pair(
                    game_key=fit.game_key,
                    price_band=lp.price_band,
                    phase=lp.phase,
                    lag_bin=lp.lag_bin,
                    lag_days=lp.lag_days,
                    s=lp.s,
                    d=b.d,
                    weight=b.weight,
                )
            )
    return pairs


# ---------------------------------------------------------------------------
# Rank statistic (tie-corrected Spearman) -- decides detection/significance
# (addendum rule 4, stands)
# ---------------------------------------------------------------------------

def _ranks(values: list[float]) -> list[float]:
    """Average ranks (1-indexed), ties get the mean of their tied ranks --
    this is the tie-correction amendment2 requires."""
    n = len(values)
    order = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1
    return ranks


def spearman_rho(xs: list[float], ys: list[float]) -> float | None:
    """Tie-corrected Spearman rank correlation of pooled (s, d) pairs,
    UNWEIGHTED ranks. This decides detection; it is never weighted."""
    n = len(xs)
    if n < 2 or n != len(ys):
        return None
    rx, ry = _ranks(xs), _ranks(ys)
    mean_rx, mean_ry = sum(rx) / n, sum(ry) / n
    num = sum((a - mean_rx) * (b - mean_ry) for a, b in zip(rx, ry))
    den_x = sum((a - mean_rx) ** 2 for a in rx)
    den_y = sum((b - mean_ry) ** 2 for b in ry)
    if den_x <= 0 or den_y <= 0:
        return None
    return num / math.sqrt(den_x * den_y)


# ---------------------------------------------------------------------------
# Dollar-weighted slope -- magnitude only, never decides significance
# ---------------------------------------------------------------------------

def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
    return s[idx]


def _slope_from_svdw(s_vals: list[float], d_vals: list[float], w_vals: list[float]) -> float | None:
    if len(s_vals) < 2:
        return None
    w_sum = sum(w_vals)
    if w_sum <= 0:
        return None
    s_bar = sum(w * s for w, s in zip(w_vals, s_vals)) / w_sum
    d_bar = sum(w * d for w, d in zip(w_vals, d_vals)) / w_sum
    num = sum(w * (s - s_bar) * (d - d_bar) for w, s, d in zip(w_vals, s_vals, d_vals))
    den = sum(w * (s - s_bar) ** 2 for w, s in zip(w_vals, s_vals))
    if den <= 0:
        return None
    return num / den


def dollar_weighted_slope(bin_pairs: list[Pair]) -> float | None:
    """Weighted OLS slope of d on s, weight = the per-lifecycle scale
    constant capped at THIS BIN's own 90th-percentile weight -- reported as
    the kernel MAGNITUDE only; it never decides significance (Spearman
    does, see `spearman_rho`)."""
    if len(bin_pairs) < 2:
        return None
    weights = [p.weight for p in bin_pairs]
    cap = _percentile(weights, WEIGHT_CAP_PERCENTILE)
    capped = [min(w, cap) if cap > 0 else w for w in weights]
    return _slope_from_svdw([p.s for p in bin_pairs], [p.d for p in bin_pairs], capped)


def bootstrap_ci(
    pairs: list[Pair],
    reps: int = BOOTSTRAP_REPS,
    seed: int = BOOTSTRAP_SEED,
) -> tuple[float, float] | None:
    """Lifecycle-block bootstrap (resample game_keys with replacement, not
    individual pairs -- pairs within one lifecycle are correlated) of the
    dollar-weighted slope, for uncertainty reporting only."""
    if not pairs:
        return None
    by_lifecycle: dict[str, list[Pair]] = defaultdict(list)
    for p in pairs:
        by_lifecycle[p.game_key].append(p)
    lifecycle_keys = list(by_lifecycle.keys())
    if len(lifecycle_keys) < 3:
        return None
    rng = random.Random(seed)
    slopes = []
    for _ in range(reps):
        sample_keys = [rng.choice(lifecycle_keys) for _ in lifecycle_keys]
        sample_pairs = [p for k in sample_keys for p in by_lifecycle[k]]
        slope = dollar_weighted_slope(sample_pairs)
        if slope is not None:
            slopes.append(slope)
    if len(slopes) < reps // 2:
        return None
    slopes.sort()
    lo_idx = int(CI_LOW * len(slopes))
    hi_idx = min(len(slopes) - 1, int(CI_HIGH * len(slopes)))
    return (slopes[lo_idx], slopes[hi_idx])


# ---------------------------------------------------------------------------
# Amendment2 replacement rule 4: circular offset (INCLUDING identity),
# reprojection through the same quadratic residual-maker, studentization,
# and the plus-one family-wise p-value
# ---------------------------------------------------------------------------

def circular_offset(m: int, rng: random.Random) -> int:
    """Draw a circular offset uniformly from ALL offsets {0, ..., m-1},
    INCLUDING IDENTITY (offset 0) -- the superseded addendum rule 5 excluded
    zero; the panel's major finding is that nonzero-only shifts are not the
    intended complete cyclic randomization set."""
    if m < 1:
        raise ValueError("m must be >= 1")
    return rng.randrange(0, m)


def circular_shift(values: list[float], k: int) -> list[float]:
    """Pe: circularly shift `values` by offset k. Output index `idx` holds
    values[(idx - k) % m]. k=0 is the identity permutation."""
    m = len(values)
    if m == 0:
        return []
    return [values[(idx - k) % m] for idx in range(m)]


def reproject_through_quadratic(xs: list[float], shifted_values: list[float]) -> list[float] | None:
    """e* = M(Pe): reproject a circularly shifted residual vector through
    the SAME quadratic residual-maker (the same fixed x positions used to
    produce the observed residuals). Returns None if the reprojected fit is
    singular/ill-conditioned (defensive; should not occur since `xs` was
    already validated non-singular when the observed residuals were built)."""
    return fit_quadratic_residuals(xs, shifted_values)


def studentize(value: float, mean: float, sd: float) -> float | None:
    """z = (value - mean) / sd; None if sd is not usable (degenerate null)."""
    if sd is None or sd <= 0:
        return None
    return (value - mean) / sd


def plus_one_pvalue(exceedance_count: int, n_reps: int) -> float:
    """p = (1 + #exceedances) / (R + 1) -- amendment2 replacement rule 4."""
    return (1 + exceedance_count) / (n_reps + 1)


def _reprojected_rep(
    lifecycle_fits: dict[str, LifecycleFit],
    rng: random.Random,
) -> dict[tuple[int, int], list[tuple[float, float]]]:
    """One replicate: for each lifecycle with >= 3 windows (the quadratic
    reprojection floor), draw its own circular offset (including identity),
    shift its own d-residual sequence, reproject through the same quadratic
    residual-maker, and rebuild every (s, d*) pair from the fixed local-pair
    skeleton. Returns, per lag bin, the pooled (s, d*) pairs for this
    replicate."""
    per_bin: dict[tuple[int, int], list[tuple[float, float]]] = defaultdict(list)
    for fit in lifecycle_fits.values():
        m = len(fit.windows)
        if m < 3 or not fit.local_pairs:
            continue
        k = circular_offset(m, rng)
        d_seq = [w.d for w in fit.windows]
        shifted = circular_shift(d_seq, k)
        e_star = reproject_through_quadratic(fit.xs, shifted)
        if e_star is None:
            continue  # defensive; xs already validated non-singular
        for lp in fit.local_pairs:
            per_bin[lp.lag_bin].append((lp.s, e_star[lp.j]))
    return per_bin


def _stratum_key(m: int) -> int:
    """Bucket window counts in pairs for the fallback stratified swap --
    "matched by lifecycle length" (amendment2's fallback clause)."""
    return m // 2


def _rank_align(donor_values: list[float], target_len: int) -> list[float]:
    """Align a donor sequence to `target_len` positions by nearest-rank
    (used only when a length-bucketed stratum contains lifecycles whose
    exact window counts differ) -- "matched by ... time-order rank"."""
    n = len(donor_values)
    if n == target_len:
        return donor_values
    if n == 1:
        return [donor_values[0]] * target_len
    return [
        donor_values[min(n - 1, round(i * (n - 1) / max(1, target_len - 1)))]
        for i in range(target_len)
    ]


def _stratified_swap_rep(
    lifecycle_fits: dict[str, LifecycleFit],
    rng: random.Random,
) -> dict[tuple[int, int], list[tuple[float, float]]]:
    """FALLBACK randomization (amendment2 replacement rule 4's own
    escalation clause): "if it fails the shared-curvature null, the second
    and final attempt should compare a stratified between-lifecycle
    whole-sequence swap, matched by lifecycle length and time-order rank,
    rather than escalating polynomial degree." Lifecycles are grouped into
    length-matched strata (bucketed window count); within each stratum, one
    uniformly random permutation of the WHOLE (ordered) d-residual sequence
    is drawn per replicate and reassigned across the stratum's lifecycles
    (identity is a valid draw). The received donor sequence is aligned by
    time-order rank to the recipient's own window count if the stratum
    bucket spans more than one exact length, then reprojected through the
    RECIPIENT's own quadratic residual-maker (its own x positions) before
    rebuilding pairs -- same downstream studentization/family-wise
    machinery as the primary method."""
    per_bin: dict[tuple[int, int], list[tuple[float, float]]] = defaultdict(list)
    strata: dict[int, list[LifecycleFit]] = defaultdict(list)
    for fit in lifecycle_fits.values():
        if len(fit.windows) < 3 or not fit.local_pairs:
            continue
        strata[_stratum_key(len(fit.windows))].append(fit)

    for group in strata.values():
        n = len(group)
        perm = list(range(n))
        if n >= 2:
            rng.shuffle(perm)
        for recipient_idx, donor_idx in enumerate(perm):
            recipient = group[recipient_idx]
            donor = group[donor_idx]
            m = len(recipient.windows)
            donor_d = [w.d for w in donor.windows]
            donor_d = _rank_align(donor_d, m)
            e_star = reproject_through_quadratic(recipient.xs, donor_d)
            if e_star is None:
                continue
            for lp in recipient.local_pairs:
                per_bin[lp.lag_bin].append((lp.s, e_star[lp.j]))
    return per_bin


# Amendment2's own escalation clause: attempt 1 (circular-shift reprojection,
# `_reprojected_rep`) was validated against the shared-curvature null and
# FAILED calibration (multiple deterministic seeds produced FW-significant
# bins on mechanism-specific null data with no injected echo -- see
# docs/reports/m6b_shared_curvature_null_validation.md). Per the amendment's
# own pre-authorized fallback ("attempt 2 switches to the stratified
# between-lifecycle sequence swap rather than escalating polynomial
# degree"), the estimator's randomization is switched to
# `_stratified_swap_rep` below. This is a transcribed, spec-provided
# fallback -- not a freelance redesign.
_REP_FN = _stratified_swap_rep


def family_wise_pvalues(
    lifecycle_fits: dict[str, LifecycleFit],
    observed_stats: dict[tuple[int, int], float],
    reps: int = PERMUTATION_REPS,
    seed: int = PERMUTATION_SEED,
) -> dict[tuple[int, int], float]:
    """Family-wise-corrected significance across ALL eligible lag bins
    together, per amendment2 replacement rule 4 (using the amendment's own
    fallback randomization, `_stratified_swap_rep` -- see the module-level
    note above `_REP_FN`): two-pass studentized max-|z| permutation. Pass 1
    builds each eligible bin's null Spearman
    distribution (and its mean/sd) from `reps` replicates of the
    fallback-randomization procedure. Pass 2 converts every replicate's own
    per-bin statistic into a z-score using that SAME bin mean/sd, and takes
    the replicate's maximum |z| across bins -- the null distribution of
    those maxima. A bin's p-value is
    (1 + #{replicate maxima >= |z_observed_bin|}) / (reps + 1)."""
    eligible_bins = list(observed_stats.keys())
    if not eligible_bins:
        return {}
    rng = random.Random(seed)

    rep_bin_stats: list[dict[tuple[int, int], float]] = []
    null_values_by_bin: dict[tuple[int, int], list[float]] = defaultdict(list)
    for _ in range(reps):
        per_bin_pairs = _REP_FN(lifecycle_fits, rng)
        rep_result: dict[tuple[int, int], float] = {}
        for b in eligible_bins:
            pairs = per_bin_pairs.get(b, [])
            if not pairs:
                continue
            rho = spearman_rho([p[0] for p in pairs], [p[1] for p in pairs])
            if rho is not None:
                rep_result[b] = rho
                null_values_by_bin[b].append(rho)
        rep_bin_stats.append(rep_result)

    bin_mean: dict[tuple[int, int], float] = {}
    bin_sd: dict[tuple[int, int], float] = {}
    for b in eligible_bins:
        vals = null_values_by_bin.get(b, [])
        if len(vals) < 2:
            continue
        mean_b = statistics.mean(vals)
        sd_b = statistics.stdev(vals)
        if sd_b > 0:
            bin_mean[b] = mean_b
            bin_sd[b] = sd_b

    if not bin_mean:
        return {}

    null_max: list[float] = []
    for rep_result in rep_bin_stats:
        zs = []
        for b, val in rep_result.items():
            if b not in bin_mean:
                continue
            z = studentize(val, bin_mean[b], bin_sd[b])
            if z is not None:
                zs.append(abs(z))
        if zs:
            null_max.append(max(zs))

    if not null_max:
        return {}

    n = len(null_max)
    p_values: dict[tuple[int, int], float] = {}
    for b in eligible_bins:
        if b not in bin_mean:
            continue
        z_obs = studentize(observed_stats[b], bin_mean[b], bin_sd[b])
        if z_obs is None:
            continue
        z_obs = abs(z_obs)
        n_exceed = sum(1 for m in null_max if m >= z_obs)
        p_values[b] = plus_one_pvalue(n_exceed, n)
    return p_values


# ---------------------------------------------------------------------------
# Diagnostics (amendment2 eligibility/diagnostics): contributor counts,
# concentration, leave-one-lifecycle-out sensitivity
# ---------------------------------------------------------------------------

def leave_one_out_diagnostics(bin_pairs: list[Pair]) -> dict:
    """Amendment2 diagnostics (Execution step 5, "inspect lifecycle
    concentration and leave-one-out results"): per-bin contributor count,
    largest single lifecycle's pair share, an effective-concentration
    (Herfindahl) index, and the maximum |rank-stat delta| from dropping any
    single contributing lifecycle."""
    by_lc: dict[str, list[Pair]] = defaultdict(list)
    for p in bin_pairs:
        by_lc[p.game_key].append(p)
    total = len(bin_pairs)
    if total == 0 or not by_lc:
        return {}
    counts = {k: len(v) for k, v in by_lc.items()}
    largest_share = max(counts.values()) / total
    herfindahl = sum((c / total) ** 2 for c in counts.values())
    full_rho = spearman_rho([p.s for p in bin_pairs], [p.d for p in bin_pairs])
    max_abs_delta = 0.0
    if full_rho is not None:
        for lc in by_lc:
            reduced = [p for p in bin_pairs if p.game_key != lc]
            rho = spearman_rho([p.s for p in reduced], [p.d for p in reduced])
            if rho is not None:
                max_abs_delta = max(max_abs_delta, abs(rho - full_rho))
    return {
        "n_contributing_lifecycles": len(counts),
        "largest_lifecycle_pair_share": largest_share,
        "effective_lifecycle_concentration_herfindahl": herfindahl,
        "leave_one_out_max_abs_rho_delta": max_abs_delta,
    }


# ---------------------------------------------------------------------------
# Amendment2's own exhaustion clause -- validated, not asserted
# ---------------------------------------------------------------------------
#
# Amendment2 replacement rule 4's fallback text: "If it fails the shared-
# curvature null, the second and final attempt should compare a stratified
# between-lifecycle whole-sequence swap ... rather than escalating
# polynomial degree." Attempt 1 (`_reprojected_rep`, within-lifecycle
# circular shift + quadratic reprojection) was checked against the
# shared-curvature null and failed calibration (multiple deterministic
# seeds produced family-wise-significant bins on mechanism-specific null
# data). Attempt 2 (`_stratified_swap_rep`, now `_REP_FN`) was checked next
# and cleared the shared-curvature null for the LOWER-tier component across
# every seed tried (validated at the production pooling scale, >= 1999
# reps). The SAME check on the TOP-tier (count-based) component still
# produced family-wise-significant bins on shared-curvature null data for 2
# of 3 canonical seeds at that same pooling scale -- i.e. attempt 2 also
# fails calibration for top-tier. Per the amendment's own final clause:
# "If both calibrated randomization approaches fail, stop confirmatory
# inference and deliver a null-calibrated descriptive analysis without
# significant-bin claims; top-tier-only is not an automatic remedy because
# the same confounding applies there." CONFIRMATORY_INFERENCE_RETIRED
# records that this exhaustion condition was reached: `BinResult.p_value`
# and `.significant()` remain available as DESCRIPTIVE diagnostics (they
# are informative and cheap to keep), but callers/reports MUST NOT surface
# a bin as a validated "significant" claim while this flag is True -- no
# significant-bin claims are authorized by amendment2's own text.
CONFIRMATORY_INFERENCE_RETIRED = True


# ---------------------------------------------------------------------------
# Per-bin results and the pooled/stratified kernel fit
# ---------------------------------------------------------------------------

@dataclass
class BinResult:
    lag_bin: tuple[int, int]
    n_pairs: int
    n_lifecycles: int
    rank_stat: float | None       # Spearman rho (unweighted); effect direction (descriptive)
    dollar_slope: float | None    # weighted OLS slope; kernel MAGNITUDE only
    ci90: tuple[float, float] | None
    p_value: float | None = None
    diagnostics: dict = field(default_factory=dict)

    def significant(self) -> bool:
        """DESCRIPTIVE p<alpha flag only -- see CONFIRMATORY_INFERENCE_RETIRED
        above. While that flag is True, this method's return value is NOT a
        validated confirmatory claim (amendment2's own exhaustion clause)."""
        if self.rank_stat is None:
            return False
        if self.n_pairs < MIN_PAIRS_FOR_FIT or self.n_lifecycles < MIN_LIFECYCLES_FOR_FIT:
            return False
        if self.p_value is None:
            return False
        return self.p_value < PERMUTATION_ALPHA


def fit_from_lifecycle_fits(
    lifecycle_fits: dict[str, LifecycleFit],
    permutation_reps: int = PERMUTATION_REPS,
    permutation_seed: int = PERMUTATION_SEED,
) -> tuple[list[BinResult], list[Pair]]:
    pairs = _pairs_from_fits(lifecycle_fits)
    by_bin: dict[tuple[int, int], list[Pair]] = defaultdict(list)
    for p in pairs:
        by_bin[p.lag_bin].append(p)

    observed_stats: dict[tuple[int, int], float] = {}
    for lo, hi in LAG_BINS:
        bin_pairs = by_bin.get((lo, hi), [])
        n_lifecycles = len({p.game_key for p in bin_pairs})
        if len(bin_pairs) >= MIN_PAIRS_FOR_FIT and n_lifecycles >= MIN_LIFECYCLES_FOR_FIT:
            rho = spearman_rho([p.s for p in bin_pairs], [p.d for p in bin_pairs])
            if rho is not None:
                observed_stats[(lo, hi)] = rho

    p_values = family_wise_pvalues(
        lifecycle_fits, observed_stats, reps=permutation_reps, seed=permutation_seed
    )

    results: list[BinResult] = []
    for lo, hi in LAG_BINS:
        bin_pairs = by_bin.get((lo, hi), [])
        n_lifecycles = len({p.game_key for p in bin_pairs})
        rank_stat = observed_stats.get((lo, hi))
        dollar_slope = dollar_weighted_slope(bin_pairs) if bin_pairs else None
        ci = bootstrap_ci(bin_pairs) if rank_stat is not None else None
        p_value = p_values.get((lo, hi))
        diagnostics = leave_one_out_diagnostics(bin_pairs) if bin_pairs else {}
        results.append(
            BinResult((lo, hi), len(bin_pairs), n_lifecycles, rank_stat, dollar_slope, ci, p_value, diagnostics)
        )
    return results, pairs


def _filter_lifecycles(lifecycles: dict[str, list[dict]], exclude_noncash: bool) -> dict[str, list[dict]]:
    if not exclude_noncash:
        return lifecycles
    return {
        k: v for k, v in lifecycles.items() if not any(r.get("has_noncash_prize") for r in v)
    }


def build_pairs(
    lifecycles: dict[str, list[dict]],
    component: str,
    exclude_noncash: bool,
) -> list[Pair]:
    """Public entry: component 'lower' (dollar-weighted, aggregate
    total_unclaimed) or 'top' (count-based, top-tier decrements). Builds
    ALL ordered disjoint within-lifecycle pairs (addendum rule 1) from
    within-lifecycle-DETRENDED windows (amendment2 replacement rule 3)."""
    if component not in ("lower", "top"):
        raise ValueError(component)
    filtered = _filter_lifecycles(lifecycles, exclude_noncash)
    windows_map, _ = build_lifecycle_detrended_windows(filtered, component)
    lifecycle_fits = _lifecycle_fits_from_windows_map(windows_map)
    return _pairs_from_fits(lifecycle_fits)


def fit_pooled_kernel(
    lifecycles: dict[str, list[dict]],
    component: str,
    exclude_noncash: bool = False,
    permutation_reps: int = PERMUTATION_REPS,
    permutation_seed: int = PERMUTATION_SEED,
) -> list[BinResult]:
    """Overall-pooled kernel (all price bands / phases combined) -- the
    PRIMARY reported kernel for a component, per lag bin."""
    filtered = _filter_lifecycles(lifecycles, exclude_noncash)
    windows_map, _ = build_lifecycle_detrended_windows(filtered, component)
    lifecycle_fits = _lifecycle_fits_from_windows_map(windows_map)
    results, _ = fit_from_lifecycle_fits(
        lifecycle_fits, permutation_reps=permutation_reps, permutation_seed=permutation_seed
    )
    return results


def fit_pooled_kernel_with_exclusions(
    lifecycles: dict[str, list[dict]],
    component: str,
    exclude_noncash: bool = False,
    permutation_reps: int = PERMUTATION_REPS,
    permutation_seed: int = PERMUTATION_SEED,
) -> tuple[list[BinResult], dict[str, int]]:
    """Same as `fit_pooled_kernel` but also returns the detrending exclusion
    counts (amendment2: shorter/singular-fit lifecycles are excluded from
    confirmatory inference and the exclusion must be reported)."""
    filtered = _filter_lifecycles(lifecycles, exclude_noncash)
    windows_map, exclusions = build_lifecycle_detrended_windows(filtered, component)
    lifecycle_fits = _lifecycle_fits_from_windows_map(windows_map)
    results, _ = fit_from_lifecycle_fits(
        lifecycle_fits, permutation_reps=permutation_reps, permutation_seed=permutation_seed
    )
    return results, exclusions


def fit_by_stratum(
    lifecycles: dict[str, list[dict]],
    component: str,
    by: str,
    exclude_noncash: bool = False,
    permutation_reps: int = PERMUTATION_REPS,
    permutation_seed: int = PERMUTATION_SEED,
) -> dict[str, list[BinResult]]:
    """Sensitivity split by price_band or phase (spec: 'where event counts
    allow' -- reported as robustness views, not the primary kernel). Each
    stratum gets its own full fit (own permutation null), consistent with
    the pooled kernel's method. NOTE: a stratum's reprojection reuses the
    normalized-x positions computed against the FULL lifecycle's quadratic
    fit (not refit on the stratum subset) -- consistent with how the
    stratum's observed residuals were produced; this is documented as a
    known simplification for these non-primary robustness views."""
    filtered = _filter_lifecycles(lifecycles, exclude_noncash)
    windows_map, _ = build_lifecycle_detrended_windows(filtered, component)

    groups: dict[str, dict[str, list[DetrendedWindow]]] = defaultdict(dict)
    if by == "price_band":
        for game_key, windows in windows_map.items():
            if not windows:
                continue
            band = price_band(windows[0].price)
            groups[band][game_key] = windows
    elif by == "phase":
        for game_key, windows in windows_map.items():
            by_phase: dict[str, list[DetrendedWindow]] = defaultdict(list)
            for w in windows:
                by_phase[phase_of(w.pu_mid_start)].append(w)
            for phase_key, ws in by_phase.items():
                if len(ws) >= 2:
                    groups[phase_key][game_key] = ws
    else:
        raise ValueError(by)

    return {
        stratum: fit_from_lifecycle_fits(
            _lifecycle_fits_from_windows_map(ws_map),
            permutation_reps=permutation_reps,
            permutation_seed=permutation_seed,
        )[0]
        for stratum, ws_map in groups.items()
    }


# ---------------------------------------------------------------------------
# Data inventory
# ---------------------------------------------------------------------------

def data_inventory(records: list[dict]) -> dict:
    by_source = Counter(r["source"] for r in records)
    by_status = Counter(r["lifecycle_status"] for r in records)
    lifecycles: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        lifecycles[r["game_key"]].append(r)
    for v in lifecycles.values():
        v.sort(key=lambda r: r["obs_date"])
    noncash_lifecycles = sum(
        1 for v in lifecycles.values() if any(r.get("has_noncash_prize") for r in v)
    )
    obs_dates = sorted(r["obs_date"] for r in records)
    era_counts: Counter = Counter()
    for d in obs_dates:
        year = int(d[:4])
        if year < 2018:
            era_counts["2015-2017"] += 1
        elif year < 2021:
            era_counts["2018-2020"] += 1
        elif year < 2024:
            era_counts["2021-2023"] += 1
        else:
            era_counts["2024-2026"] += 1
    return {
        "total_records": len(records),
        "by_source": dict(by_source),
        "by_lifecycle_status": dict(by_status),
        "n_lifecycles": len(lifecycles),
        "noncash_lifecycles": noncash_lifecycles,
        "by_era": dict(era_counts),
        "obs_date_min": obs_dates[0] if obs_dates else None,
        "obs_date_max": obs_dates[-1] if obs_dates else None,
    }


def build_lifecycles(records: list[dict]) -> dict[str, list[dict]]:
    lifecycles: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        lifecycles[r["game_key"]].append(r)
    for v in lifecycles.values():
        v.sort(key=lambda r: r["obs_date"])
    return lifecycles


def top_tier_event_inventory(lifecycles: dict[str, list[dict]]) -> dict:
    """Pooled top-tier decrement EVENT count to date (report must state
    this explicitly, independent of whether the kernel fit succeeds)."""
    total_events = 0
    total_decrement_count = 0
    by_price_band: Counter = Counter()
    for records in lifecycles.values():
        for a, b in zip(records, records[1:]):
            d0, d1 = parse_iso_date(a["obs_date"]), parse_iso_date(b["obs_date"])
            if (d1 - d0).days <= 0:
                continue
            dec = _top_decrement(a, b)
            if dec > 0:
                total_events += 1
                total_decrement_count += dec
                by_price_band[price_band(a["price"])] += dec
    return {
        "n_decrement_events": total_events,
        "n_decrement_units": total_decrement_count,
        "by_price_band": dict(by_price_band),
    }


def bin_result_to_dict(r: BinResult) -> dict:
    return {
        "lag_bin_days": list(r.lag_bin),
        "n_pairs": r.n_pairs,
        "n_lifecycles": r.n_lifecycles,
        "rank_stat": r.rank_stat,
        "dollar_slope": r.dollar_slope,
        "ci90": list(r.ci90) if r.ci90 else None,
        "p_value": r.p_value,
        "significant": r.significant(),
        "diagnostics": r.diagnostics,
    }


def run_study(panel_path: str | Path) -> dict:
    records = load_panel_records(panel_path)
    lifecycles = build_lifecycles(records)

    lower_kernel, lower_exclusions = fit_pooled_kernel_with_exclusions(
        lifecycles, component="lower", exclude_noncash=True
    )
    top_kernel, top_exclusions = fit_pooled_kernel_with_exclusions(
        lifecycles, component="top", exclude_noncash=False
    )

    lower_pairs = build_pairs(lifecycles, component="lower", exclude_noncash=True)
    top_pairs = build_pairs(lifecycles, component="top", exclude_noncash=False)

    lower_by_price = fit_by_stratum(lifecycles, component="lower", by="price_band", exclude_noncash=True)
    lower_by_phase = fit_by_stratum(lifecycles, component="lower", by="phase", exclude_noncash=True)

    return {
        "data_inventory": data_inventory(records),
        "top_tier_event_inventory": top_tier_event_inventory(lifecycles),
        "lower_tier_kernel_pooled": [bin_result_to_dict(r) for r in lower_kernel],
        "top_tier_kernel_pooled": [bin_result_to_dict(r) for r in top_kernel],
        "lower_tier_detrend_exclusions": lower_exclusions,
        "top_tier_detrend_exclusions": top_exclusions,
        "lower_tier_kernel_by_price_band": {
            k: [bin_result_to_dict(r) for r in v] for k, v in lower_by_price.items()
        },
        "lower_tier_kernel_by_phase": {
            k: [bin_result_to_dict(r) for r in v] for k, v in lower_by_phase.items()
        },
        "n_lower_pairs": len(lower_pairs),
        "n_top_pairs": len(top_pairs),
        "lag_bins": [list(b) for b in LAG_BINS],
        "min_pairs_for_fit": MIN_PAIRS_FOR_FIT,
        "min_lifecycles_for_fit": MIN_LIFECYCLES_FOR_FIT,
        "bootstrap_reps": BOOTSTRAP_REPS,
        "ci_level": [CI_LOW, CI_HIGH],
        "permutation_reps": PERMUTATION_REPS,
        "permutation_alpha": PERMUTATION_ALPHA,
        "confirmatory_inference_retired": CONFIRMATORY_INFERENCE_RETIRED,
        "confirmatory_inference_note": (
            "amendment2's exhaustion clause was reached during Phase-1 build "
            "validation: the fallback stratified-swap randomization cleared the "
            "shared-curvature null for the lower-tier component but not for the "
            "top-tier (count-based) component at the production pooling scale. "
            "Per docs/specs/m6b_panel_amendment2.md, no bin's `significant` flag "
            "in this report is a validated confirmatory claim; `rank_stat`, "
            "`dollar_slope`, `p_value`, and `diagnostics` are descriptive only."
        ),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--panel", default="data/panel/panel.jsonl")
    args = ap.parse_args()
    summary = run_study(args.panel)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
