# M6b Phase-1 detectability report — pooled sales→claims lag

**Produced by:** lead (per program spec Phase 1 rule 5) · 2026-07-13
**Governed by:** `docs/specs/m6_v2_program_spec.md` Phase 1;
`docs/specs/m6b_estimator_redesign_addendum.md` as amended by
`docs/specs/m6b_panel_amendment2.md` (panel-arbitrated).
**Reproduce every number:** `python -m analysis.phase1_detectability --panel
data/panel/panel.jsonl` (deterministic: fixed seeds, 1999 permutation reps,
committed panel `data/panel/panel.jsonl`).
**This report ends in a HARD OWNER STOP** (program spec rule 6 /
Resolution 5): the owner rules GO / NO-GO per component and confirms or
overrides the Phase-2 evidence trigger N (Resolution 6) before any Phase-2
sub-spec drafting begins.

## 1. Data inventory

- 13,652 records; 482 game lifecycles; obs dates 2015-01-01 → 2026-07-13.
- By source: 13,587 wayback / 65 daily. By era: 4,280 (2015-17), 5,371
  (2018-20), 2,245 (2021-23), 1,756 (2024-26).
- Lifecycle status: 13,232 active / 22 exited_observed / 398
  exited_unobserved. Noncash-prize lifecycles: 4 (excluded from the
  lower-tier kernel per the semantics note; see §5).
- Detrending exclusions (amendment2 rule 3, reported never silent): 24
  lifecycles below the 6-usable-window floor (both components); 0 for
  distinct-midpoint or singular-fit reasons. 454–458 lifecycles contribute
  per eligible bin.
- Pairs entering the estimator: 236,560 (lower) / 238,947 (top).

## 2. Pooled top-tier decrement event count (to date)

**6,367 window-level decrement events** comprising **169,593 decrement
units**, by price band: high_20plus 78,817 / mid_5 42,960 / midhigh_10
38,543 / low_1_3 9,273. (The program spec's risk section assumed sparse
events from the daily panel alone; the M6a wayback backfill delivered
scale it did not anticipate.)

## 3. Method status — what these numbers are and are not

The estimator is the amendment2 design: per-lifecycle quadratic detrending,
all-ordered-disjoint pairing, tie-corrected Spearman per lag bin,
studentized max-|z| family-wise permutation p-values (plus-one, 1999 reps),
dollar-weighted slope as effect size only.

**Confirmatory inference is RETIRED** (`CONFIRMATORY_INFERENCE_RETIRED =
True`), per amendment2's own exhaustion clause, on this evidence
(`docs/reports/m6b_shared_curvature_null_validation.md`, deterministic,
regenerable via `scripts/m6b_null_validation.py`):

| randomization | lower tier | top tier |
|---|---|---|
| attempt 1: circular shift + reprojection | FAILED (1/3 seeds false-positive) | FAILED (3/3 seeds) |
| attempt 2: stratified sequence swap (production) | **CALIBRATED (0 false positives, 3/3 seeds)** | FAILED (2/3 seeds) |

Every p-value below is therefore **descriptive**. For the LOWER tier the
production randomization is calibrated on the mechanism-specific
shared-curvature null (at 300 synthetic lifecycles vs 454 contributing
real ones — a stated extrapolation, not a proof). For the TOP tier the
randomization never calibrated: its descriptive flags **cannot be
trusted** and are shown only for completeness.

Synthetic-recovery evidence (the phase's machine gate): the estimator
recovers an injected 110-day echo in bin (90,150) with positive rank
statistic at p < 0.01 across 3 seeds, both components
(`tests/analysis/test_phase1_synthetic.py`, green in the full gate).

## 4. Estimated kernels

Lower tier (pooled, dollar-weighted, noncash excluded; rho = Spearman on
detrended residuals; slope = dollar-weighted effect size; p descriptive):

| lag bin (days) | n_pairs | lifecycles | rho | slope | p |
|---|---|---|---|---|---|
| 0–45 | 27,122 | 454 | **+0.544** | +8.7e-4 (CI90 [+2.4e-4, +1.6e-3]) | 0.0005 |
| 45–90 | 28,849 | 454 | **+0.288** | −2.5e-4 | 0.0005 |
| 90–150 | 33,320 | 452 | −0.044 | −1.0e-3 | 0.005 |
| 150–250 | 47,888 | 442 | −0.212 | −6.4e-4 | 0.0005 |
| 250–400 | 51,086 | 417 | −0.033 | −1.7e-4 | 0.16 |
| 400–800 | 48,295 | 365 | +0.024 | +8.6e-5 | 0.14 |

Top tier (pooled, count-based — descriptive flags NOT trustworthy, §3):
rho +0.289 (0–45), +0.177 (45–90), −0.035 (90–150), −0.174 (150–250),
−0.043 (250–400), +0.017 (400–800) — the same qualitative shape.

**Reading:** above-trend selling predicts above-trend claiming within
0–45 days, decaying through 45–90, gone by 90–150, then a **negative**
association at 150–250 days. The negative rebound is mechanistically
expected from a genuine localized response: within a lifecycle, prizes
claimed promptly are prizes NOT available to be claimed later (pool
depletion), so a real short-lag kernel must borrow from later bins. The
shape is evidence FOR a short-lag response, not an anomaly — but the
mid-lag bins' descriptive "significant" flags should not be read as
confirmed structure.

## 5. Robustness and diagnostics

- **Price band (lower tier):** the 0–45d positive association reproduces
  in every band — low_1_3 +0.558, mid_5 +0.552, midhigh_10 +0.505,
  high_20plus +0.441 — with the same decay-then-rebound shape.
- **Lifecycle phase:** positive 0–45d in all three phases (early +0.238,
  mid +0.522, late +0.696). Stronger late-life response is consistent
  with end-of-game claim urgency.
- **Concentration (0–45d bin):** 454 contributing lifecycles; largest
  single lifecycle's pair share 1.1%; Herfindahl 0.0042; leave-one-
  lifecycle-out max |Δrho| = 0.0031. No single game drives the result.
- **Semantics assumptions relied on** (`docs/m6_semantics.md`): (a)
  noncash-prize valuation in `total_unclaimed` could not be established —
  the 4 noncash lifecycles are excluded from the lower-tier kernel; (b)
  tier-coverage ambiguity of the aggregate unclaimed figure is a stated
  Phase-1 assumption (M6a semantics note); (c) `obs_date` is page truth,
  not capture time.

## 6. Verdict recommendations (owner rules at the HARD STOP)

- **LOWER TIER: GO (recommended).** Numeric justification: pooled 0–45d
  rho +0.544 with CI90 dollar-slope excluding zero, reproduced in 4/4
  price bands and 3/3 lifecycle phases, negligible concentration, and a
  mechanistically coherent depletion rebound — produced by an estimator
  whose randomization shows ZERO false positives on the synthetic
  shared-curvature null for this component. A pooled sales→claims signal
  concentrated inside ~90 days is detectable. Caveat carried to Phase 2:
  confirmatory significance machinery is retired; Phase-2 modeling must
  stand on the state-space likelihood, not on these p-values.
- **TOP TIER: NO-GO on detectability; carry decrements forward as
  observations (recommended).** Numeric justification: no calibrated
  randomization exists for this component (false positives on null data,
  2–3 of 3 seeds, both methods), so its descriptive flags cannot support
  a detection claim. Per program spec, this partial verdict RE-SCOPES
  Phase 2 rather than killing it: top-tier decrement events remain
  observations in the Phase-2 state-space model (the model class already
  ingests them), and the sub-spec inherits the open numpy/scipy
  likelihood question (Resolution 2 path).

## 7. Phase-2 evidence trigger (Resolution 6)

**N = 1,000 pooled top-tier decrement events, with ≥ 100 in each of the
four price bands.** Justification from observed event rates: the Phase-2
model pools the top tier heavily (no per-game hazards); a regularized 2–3
parameter hazard family per price band needs order tens of events per
parameter — 100/band provides ≥ 3× that margin, and 1,000 pooled bounds
the whole-kernel uncertainty well below the effect sizes in §4.

**Current count: 6,367 events (≥ 9,273 units in the sparsest band) —
the trigger is ALREADY MET**, as of the M6a backfill (2026-07-13).
Projected date of reaching N: in the past. Anti-gaming note: N is set
from event-rate arithmetic above, not back-derived to pass; the owner may
override N in either direction at this stop.

## 8. What happens next (spec mechanics)

Owner GO on lower tier + trigger met ⇒ the PLANNER may author
`docs/specs/m6_phase2_model_spec.md` (M6c sub-spec), which the owner must
approve before ANY implementation. NO-GO on both components ⇒ the program
stops at W2's labeled sensitivity scenarios, with the panel, semantics
note, and this estimator retained as durable assets.
