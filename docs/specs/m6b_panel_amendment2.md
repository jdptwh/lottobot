## AMENDMENT 2: M6b estimator — panel-arbitrated redesign of rules 3/4/5
**Provenance:** PLAN-gate panel consult (Rule 12, novelty). task_id=m6b-estimator-detrend gate=plan cost=$1.54 lineup=fable-5+gpt-5.6-sol-pro synth=sol-pro date=2026-07-13.
Verdict: **ADOPT WITH CHANGES** — the proposed linear-detrending amendment was
REJECTED as insufficient (exit 1); the panel synthesized the replacement below.
Supersedes rules 3, 5 (permutation), and 6 (generator) of
`m6b_estimator_redesign_addendum.md`. Rules 1, 2, 4 (rank statistic) stand,
with the studentization change below. Archived verdict:
`.claude/state/panel_verdict_m6b-estimator-detrend.json` (gitignored).
Transcribed VERBATIM by the lead; implementer transcribes, does not iterate
(owner directive 2026-07-13). Implementation budget: MAX_IMPL_ATTEMPTS=2 per
addendum §4 — the exhaustion path (NO-GO-methodological) is unchanged, except
per the panel: if the reprojected circular shift fails the shared-curvature
null, attempt 2 switches to the stratified between-lifecycle sequence swap
rather than escalating polynomial degree.

### Panel synthesis (verbatim artifact)

VERDICT: ADOPT WITH CHANGES. Do not ship linear detrending alone. Use quadratic age residualization, strengthen the residual randomization, and replace the four-window synthetic validation design.

Replacement Rule 3 — DETRENDING: “For each lifecycle with at least 6 usable windows and at least 3 distinct midpoint times, normalize midpoint time as x=(t-midrange)/(half-range). Separately for s and d, fit y=a+b*x+c*x^2 by closed-form OLS and retain residuals e=y−ŷ. Reject singular or numerically ill-conditioned fits. Build all pairs, Spearman statistics, and weighted OLS effect sizes from these residuals. Exclude shorter lifecycles from confirmatory inference and report their exclusion; do not vary polynomial degree by lifecycle.” Quadratic detrending is preferred to linear because exponential decay leaves shared curvature after a linear fit. Do not first-difference: s and d are already stock-change rates, so another difference changes the estimand to an innovation/second-difference relationship and distorts the stated lag-kernel semantics.

Replacement Rule 4 — RANDOMIZATION AND FAMILY-WISE TEST: “For each replicate and lifecycle, draw a circular offset uniformly from all offsets {0,…,m−1}, including identity, shift the ordered d-residual vector, and reproject it through the same quadratic residual-maker, e*=M(Pe). Use one offset per lifecycle across every lag bin. Rebuild pairs and statistics. Studentize each eligible bin using its permutation mean and standard deviation, and use the replicate maximum |z| across bins for family-wise adjusted p-values. Compute p=(1+# exceedances)/(R+1), with at least 1,999 replicates for a p<0.01 recovery claim and a fixed seed.” This is still an approximate randomization on short, irregular grids; acceptance is conditional on synthetic calibration. If it fails the shared-curvature null, the second and final attempt should compare a stratified between-lifecycle whole-sequence swap, matched by lifecycle length and time-order rank, rather than escalating polynomial degree.

Eligibility and diagnostics: retain n_pairs≥30 only as a computational floor, but additionally require broad lifecycle support (pre-register a minimum, provisionally 15 contributing lifecycles per bin). Report contributor counts, effective lifecycle concentration, largest lifecycle pair share, and leave-one-lifecycle-out sensitivity. If a few lifecycles dominate, replace pooled-pair inference with a lifecycle-balanced cluster statistic before making confirmatory claims. Use tie-corrected Spearman.

Generator changes: use at least 10–12 irregularly spaced windows per synthetic lifecycle. Embed the four designated probes among ordinary windows, preserving disjoint bump/echo windows and an exact 110-day midpoint lag; use the same grid logic for null and recovery. Add a mechanism-specific null with common exponential age decay or matched decay constants but no sales-to-claims echo, plus independent claim bumps/noise. Vary curvature, lifecycle length, spacing, and zero/noisy flows. Assert injection integrity and record how much of the echo survives residualization. Run the required recovery test and the specified ≥3 deterministic null seeds, but also estimate family-wise error over substantially more seeds (preferably ≥10, ideally about 50) rather than treating three zero-rejection seeds as calibration.

Execution: (1) unit-test quadratic projection, singular handling, identity offsets, reprojection, studentization, and plus-one p-values; (2) run the shared-curvature null first; (3) run broader independent-null simulations; (4) run recovery requiring the 90–150-day bin at adjusted p<0.01; (5) inspect lifecycle concentration and leave-one-out results. Convergence within two attempts is plausible only if detrending, permutation, and generator changes are made together. If both calibrated randomization approaches fail, stop confirmatory inference and deliver a null-calibrated descriptive analysis without significant-bin claims; top-tier-only is not an automatic remedy because the same confounding applies there.

### Panel findings (severity-tagged, binding on the implementation)

- **critical**: Linear detrending alone cannot guarantee removal of common nonlinear age paths, so the proposed amendment may merely attenuate the existing all-bin false positives.
- **critical**: The deterministic four-window generator cannot validly test quadratic detrending or short-sequence randomization because it leaves only one residual degree of freedom.
- **major**: The current nonzero-only circular shifts omit identity and are not the intended complete cyclic randomization set.
- **major**: Circular index shifts are only approximately exchangeable on irregular, short observation grids; synthetic calibration must reflect production lengths and spacing.
- **major**: Pooled all-pairs Spearman and n_pairs≥30 can give a few long lifecycles disproportionate influence while overstating independent information.
- **major**: The current null suite does not directly and robustly estimate family-wise error under the diagnosed shared-curvature mechanism, and ≥3 seeds is inadequate for calibration.
- **minor**: Raw max-|T| testing across bins with heterogeneous null variances can have uneven power; permutation studentization is preferable.
- **minor**: A recovery injection with roughly 100:1 per-pair SNR validates plumbing but provides little evidence of realistic power.
- **minor**: Midpoint lag assignment and quantized sales proxies can create bin leakage and rank ties that require explicit diagnostics and tie-corrected Spearman.

### Blind spots flagged by the panel (must be measured/tested, not assumed)

- Neither expert established how many real lifecycles would survive a six-window inferential threshold after the production window construction; this must be measured before adopting the exclusion rule.
- Neither expert demonstrated that residual sequences are exchangeable under circular shifts or that lifecycles are exchangeable under between-lifecycle swaps; both proposed randomizations remain assumptions requiring stress-test evidence.
- Neither expert fully specified a lifecycle-balanced replacement statistic if pooled Spearman is found to be dominated by long lifecycles.
- The impact of missing snapshots, negative/zero decrements, data corrections, or monotonicity violations in prize stocks was not addressed.
- No expert specified numerical conditioning tolerances for the standard-library 3×3 quadratic solve; these must be defined and unit-tested rather than left implementation-dependent.
