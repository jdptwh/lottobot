"""Phase-1 (M6b) machine gate: synthetic-recovery test.

`docs/specs/m6_v2_program_spec.md` Phase 1 design rule 4 + the pinned
redesign in `docs/specs/m6b_estimator_redesign_addendum.md` section 3, AS
AMENDED by `docs/specs/m6b_panel_amendment2.md` (quadratic detrending,
studentized reprojected-permutation family-wise test, and a mechanism-
specific "shared-curvature" null in addition to the original independent
null): before analyzing real data, a synthetic-recovery test must exist
that injects a KNOWN lag kernel into simulated irregular-interval,
interval-censored lifecycles and checks the estimator recovers it, plus
NULL cases (no injected lag) that stress-test whether the estimator
hallucinates signal.

VALIDATION OUTCOME -- amendment2's own exhaustion clause was reached
(Execution steps 1-4, run against this implementation before finalizing
test parameters, at the full >= 1999-rep resolution required for a p<0.01
recovery claim):

  - Attempt 1 (`_reprojected_rep`, within-lifecycle circular shift +
    quadratic reprojection, amendment2's primary randomization) FAILED the
    shared-curvature null: multiple deterministic seeds produced
    family-wise-significant bins on mechanism-specific null data (no
    injected echo) at an elevated rate.
  - Attempt 2 (`_stratified_swap_rep`, now `analysis.phase1_detectability
    ._REP_FN` -- the amendment's own pre-authorized fallback, "a stratified
    between-lifecycle whole-sequence swap ... rather than escalating
    polynomial degree") CLEARED the shared-curvature null for the
    LOWER-tier component across every seed tried at this pooling scale, but
    the SAME check on the TOP-tier (count-based) component still produced
    family-wise-significant bins on shared-curvature null data for 2 of 3
    canonical seeds tried (4242, 77, 55).

Per the amendment's own final clause: "If both calibrated randomization
approaches fail, stop confirmatory inference and deliver a
null-calibrated descriptive analysis without significant-bin claims;
top-tier-only is not an automatic remedy because the same confounding
applies there." `analysis.phase1_detectability.CONFIRMATORY_INFERENCE_
RETIRED` records that this exhaustion condition was reached. Consequently:

  - The RECOVERY tests below still assert a positive rank statistic and a
    low p-value in the true-lag bin -- this remains a legitimate
    DESCRIPTIVE/plumbing check that the estimator detects real injected
    structure with the correct sign, in the correct bin.
  - The NULL tests below do NOT assert "zero significant bins" (that
    assertion is exactly the condition amendment2's own exhaustion clause
    says failed); they assert the fit completes and produces well-formed,
    bounded descriptive output, and a structural (not confirmatory) sanity
    bound that the method has not totally broken down (not every bin
    flagged simultaneously). No bin's `.significant()` flag is treated as
    validated in this project while CONFIRMATORY_INFERENCE_RETIRED is True.

This is reported for the human/report to inspect (amendment2 Execution
step 5), not silently swept aside -- see
`analysis.phase1_detectability.CONFIRMATORY_INFERENCE_RETIRED` and
`run_study()`'s `confirmatory_inference_note` field for the same statement
surfaced in the CLI/report output.

Recovery tests are parametrized over 3 seeds (4242, 77, 55) with IDENTICAL
thresholds -- no seed-specific tolerance anywhere. Offline, seeded,
deterministic; no network (the socket guard in
tests/panel/test_no_network.py already covers the whole test suite
process-wide, and this package adds no network use of its own).
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# `tests/` is copied wholesale into a fresh directory by the harness packaging
# self-test (tests/test_packaging.py); `analysis/` is this project's own code,
# not part of the reusable harness, so it does not ship there. Degrade to a
# clean skip ONLY in that nested harness-only copy -- when analysis/ exists on
# disk (this repo), an import failure must fail loudly, never silently skip
# the Phase-1 machine gate (m5a/M1 landmine precedent, tests/scraper/test_scrape.py).
if not (REPO_ROOT / "analysis" / "phase1_detectability.py").exists():
    pytest.skip(
        "analysis/ is this project's own code, not part of the installable harness",
        allow_module_level=True,
    )
from analysis.phase1_detectability import (
    CONFIRMATORY_INFERENCE_RETIRED,
    LAG_BINS,
    build_lifecycles,
    fit_pooled_kernel,
)
from analysis.synthetic import simulate_panel_records

SEEDS = [4242, 77, 55]
TRUE_LAG_DAYS = 110  # falls inside the (90, 150) lag bin

# Amendment2 replacement rule 4 requires >= 1999 replicates for a p < 0.01
# recovery claim; the null checks use the same rep count (validation showed
# lower rep counts produce noisy, anti-conservative studentized null
# estimates -- see the module docstring).
PERMUTATION_REPS = 1999
RECOVERY_P_THRESHOLD = 0.01

# Recovery: request enough lifecycles that the true-lag bin comfortably
# clears both eligibility floors (n_pairs >= 30, n_lifecycles >= 15) even
# after the recovery-branch generator's clamp-integrity retry attrition.
RECOVERY_N_LIFECYCLES = 220
# Null scenarios have ~100% generator retention (no retry attrition). This
# specific size (matching the pre-implementation calibration validation
# run) is required for the descriptive-output checks below to reflect the
# same pooling scale the validation was run at.
NULL_N_LIFECYCLES = 300


def _kernel_for(seed: int, n_lifecycles: int, inject_kernel: bool, component: str, null_mode: str = "independent"):
    records = simulate_panel_records(
        n_lifecycles=n_lifecycles,
        lag_days=TRUE_LAG_DAYS,
        inject_kernel=inject_kernel,
        seed=seed,
        null_mode=null_mode,
    )
    lifecycles = build_lifecycles(records)
    return fit_pooled_kernel(
        lifecycles,
        component=component,
        exclude_noncash=False,
        permutation_reps=PERMUTATION_REPS,
    )


def _bin_result(kernel, lo, hi):
    for r in kernel:
        if r.lag_bin == (lo, hi):
            return r
    raise AssertionError(f"lag bin ({lo}, {hi}) missing from kernel result")


def test_confirmatory_inference_is_retired():
    """Amendment2's own exhaustion clause was reached during validation
    (see the module docstring); this is recorded as a module constant, not
    silently assumed."""
    assert CONFIRMATORY_INFERENCE_RETIRED is True


# ---------------------------------------------------------------------------
# Known-kernel recovery (lower-tier / dollar-weighted component) -- a
# descriptive/plumbing check: does the estimator detect real injected
# structure, with the correct sign, in the correct bin?
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("seed", SEEDS)
def test_lower_tier_recovers_injected_lag(seed):
    kernel = _kernel_for(seed, RECOVERY_N_LIFECYCLES, inject_kernel=True, component="lower")
    target = _bin_result(kernel, 90, 150)

    assert target.n_pairs >= 30, "synthetic design should populate the true-lag bin"
    assert target.n_lifecycles >= 15, "amendment2 eligibility floor: broad lifecycle support"
    assert target.rank_stat is not None and target.rank_stat > 0, (
        "the bin containing the true injected lag must show a positive rank statistic "
        f"(got rank_stat={target.rank_stat})"
    )
    assert target.p_value is not None and target.p_value < RECOVERY_P_THRESHOLD, (
        "the bin containing the true injected lag must clear p < "
        f"{RECOVERY_P_THRESHOLD} (descriptive detection-power check, not a confirmatory "
        f"claim -- see CONFIRMATORY_INFERENCE_RETIRED) -- got rank_stat={target.rank_stat}, "
        f"p_value={target.p_value}"
    )


# ---------------------------------------------------------------------------
# Known-kernel recovery (top-tier / count-based component)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("seed", SEEDS)
def test_top_tier_recovers_injected_lag(seed):
    kernel = _kernel_for(seed, RECOVERY_N_LIFECYCLES, inject_kernel=True, component="top")
    target = _bin_result(kernel, 90, 150)

    assert target.n_pairs >= 30
    assert target.n_lifecycles >= 15
    assert target.rank_stat is not None and target.rank_stat > 0
    assert target.p_value is not None and target.p_value < RECOVERY_P_THRESHOLD, (
        f"top-tier bin containing the true lag must clear p < {RECOVERY_P_THRESHOLD} "
        f"(descriptive detection-power check) -- got rank_stat={target.rank_stat}, "
        f"p_value={target.p_value}"
    )


# ---------------------------------------------------------------------------
# Null scenarios -- DESCRIPTIVE only (amendment2's exhaustion clause: no
# significant-bin claims are authorized). These checks assert the fit
# completes and produces well-formed, bounded output, plus a structural
# (not confirmatory) sanity bound -- not that every bin is flagged
# simultaneously, which would indicate the method has broken down entirely
# rather than showing the occasional, bounded false-positive rate observed
# during validation.
# ---------------------------------------------------------------------------

def _assert_well_formed_descriptive_kernel(kernel):
    assert len(kernel) == len(LAG_BINS)
    for r in kernel:
        assert isinstance(r.n_pairs, int) and r.n_pairs >= 0
        assert isinstance(r.n_lifecycles, int) and r.n_lifecycles >= 0
        if r.p_value is not None:
            assert 0.0 <= r.p_value <= 1.0
    significant_bins = [r.lag_bin for r in kernel if r.significant()]
    assert len(significant_bins) < len(kernel), (
        "every bin flagged simultaneously on null data would indicate total "
        f"estimator breakdown, not the bounded false-positive rate observed "
        f"during validation; got {significant_bins}"
    )


@pytest.mark.parametrize("seed", SEEDS)
def test_lower_tier_independent_null_is_well_formed(seed):
    kernel = _kernel_for(seed, NULL_N_LIFECYCLES, inject_kernel=False, component="lower", null_mode="independent")
    _assert_well_formed_descriptive_kernel(kernel)


@pytest.mark.parametrize("seed", SEEDS)
def test_lower_tier_shared_curvature_null_is_well_formed(seed):
    """Amendment2 "Generator changes" + Execution step 2 ("run the shared-
    curvature null first"): a common/matched exponential age-decay
    constant across sales and claims, with independently timed bumps and NO
    echo -- the diagnosed defect (shared lifecycle decay trends surviving
    detrending) this scenario exists to stress-test. See the module
    docstring: this scenario is exactly where the exhaustion clause was
    reached for the top-tier component; the lower-tier component cleared
    it, but confirmatory claims are retired project-wide regardless."""
    kernel = _kernel_for(seed, NULL_N_LIFECYCLES, inject_kernel=False, component="lower", null_mode="shared_curvature")
    _assert_well_formed_descriptive_kernel(kernel)


@pytest.mark.parametrize("seed", SEEDS)
def test_top_tier_independent_null_is_well_formed(seed):
    kernel = _kernel_for(seed, NULL_N_LIFECYCLES, inject_kernel=False, component="top", null_mode="independent")
    _assert_well_formed_descriptive_kernel(kernel)


@pytest.mark.parametrize("seed", SEEDS)
def test_top_tier_shared_curvature_null_is_well_formed(seed):
    kernel = _kernel_for(seed, NULL_N_LIFECYCLES, inject_kernel=False, component="top", null_mode="shared_curvature")
    _assert_well_formed_descriptive_kernel(kernel)


# ---------------------------------------------------------------------------
# Amendment2 Execution step 5: "inspect lifecycle concentration and
# leave-one-out results" -- diagnostics must be present and sane on a
# recovery fit (cheap rep count; this test inspects structure, not
# calibration).
# ---------------------------------------------------------------------------

def test_diagnostics_present_and_bounded():
    records = simulate_panel_records(
        n_lifecycles=RECOVERY_N_LIFECYCLES, lag_days=TRUE_LAG_DAYS, inject_kernel=True, seed=4242
    )
    lifecycles = build_lifecycles(records)
    kernel = fit_pooled_kernel(lifecycles, component="lower", exclude_noncash=False, permutation_reps=50)
    target = _bin_result(kernel, 90, 150)
    diag = target.diagnostics
    assert diag, "a populated bin must report leave-one-out/concentration diagnostics"
    assert diag["n_contributing_lifecycles"] == target.n_lifecycles
    assert 0.0 < diag["largest_lifecycle_pair_share"] <= 1.0
    assert 0.0 < diag["effective_lifecycle_concentration_herfindahl"] <= 1.0
    assert diag["leave_one_out_max_abs_rho_delta"] >= 0.0
    # No single synthetic lifecycle should dominate the pooled recovery bin
    # (amendment2: "if a few lifecycles dominate ... replace pooled-pair
    # inference"; this synthetic design pools broadly by construction).
    assert diag["largest_lifecycle_pair_share"] < 0.5


# ---------------------------------------------------------------------------
# Purity: analysis/ must never be imported under scraper/
# ---------------------------------------------------------------------------

def test_analysis_not_imported_under_scraper():
    scraper_dir = REPO_ROOT / "scraper"
    offenders = []
    for path in scraper_dir.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("import analysis") or stripped.startswith("from analysis"):
                offenders.append(f"{path}: {stripped}")
    assert offenders == [], f"scraper/ must never import analysis/: {offenders}"


def test_requirements_txt_unchanged_no_numpy():
    text = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "numpy" not in text.lower(), (
        "Phase 1 stayed stdlib-only; requirements.txt must not gain numpy"
    )
