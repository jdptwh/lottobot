"""Phase-1 (M6b) unit tests for amendment2 primitives (Execution step 1):
`docs/specs/m6b_panel_amendment2.md` Execution: "(1) unit-test quadratic
projection, singular handling, identity offsets, reprojection,
studentization, and plus-one p-values." These are the low-level building
blocks of the amendment2-redesigned estimator in
`analysis/phase1_detectability.py`, tested directly and independently of
the synthetic-recovery integration tests in `test_phase1_synthetic.py`.

Offline, deterministic; no network.
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# See test_phase1_synthetic.py for the rationale of this guarded skip
# (harness-packaging self-test copies `tests/` without `analysis/`).
if not (REPO_ROOT / "analysis" / "phase1_detectability.py").exists():
    pytest.skip(
        "analysis/ is this project's own code, not part of the installable harness",
        allow_module_level=True,
    )

from analysis.phase1_detectability import (
    circular_offset,
    circular_shift,
    fit_quadratic_residuals,
    plus_one_pvalue,
    reproject_through_quadratic,
    studentize,
)

# ---------------------------------------------------------------------------
# Quadratic projection
# ---------------------------------------------------------------------------

def test_quadratic_projection_residuals_orthogonal_to_design():
    xs = [-1.0, -0.6, -0.2, 0.1, 0.5, 0.9, 1.0]
    ys = [2.0, 1.5, 1.1, 1.3, 1.8, 2.6, 3.0]
    residuals = fit_quadratic_residuals(xs, ys)
    assert residuals is not None
    assert abs(sum(residuals)) < 1e-6
    assert abs(sum(r * x for r, x in zip(residuals, xs))) < 1e-6
    assert abs(sum(r * x * x for r, x in zip(residuals, xs))) < 1e-6


def test_quadratic_projection_recovers_zero_residual_on_exact_quadratic():
    xs = [-1.0, -0.5, 0.0, 0.4, 0.8, 1.0]
    a, b, c = 0.3, -1.2, 2.5
    ys = [a + b * x + c * x * x for x in xs]
    residuals = fit_quadratic_residuals(xs, ys)
    assert residuals is not None
    assert all(abs(r) < 1e-8 for r in residuals)


# ---------------------------------------------------------------------------
# Singular / ill-conditioned handling
# ---------------------------------------------------------------------------

def test_singular_handling_too_few_points():
    assert fit_quadratic_residuals([0.0, 1.0], [1.0, 2.0]) is None


def test_singular_handling_duplicate_x_values():
    # Only 2 distinct x values among >= 3 points -- a singular quadratic
    # design (amendment2: "reject singular or numerically ill-conditioned
    # fits").
    assert fit_quadratic_residuals([0.0, 0.0, 1.0, 1.0], [1.0, 1.1, 2.0, 2.2]) is None


def test_singular_handling_all_same_x():
    assert fit_quadratic_residuals([1.0, 1.0, 1.0, 1.0], [1.0, 2.0, 3.0, 4.0]) is None


def test_singular_handling_nearly_duplicate_x_ill_conditioned():
    # Three points, two of which are numerically indistinguishable at
    # float precision -- exercises the conditioning tolerance, not just
    # exact duplicates.
    xs = [0.0, 1e-13, 1.0]
    assert fit_quadratic_residuals(xs, [1.0, 1.0, 2.0]) is None


# ---------------------------------------------------------------------------
# Circular offsets -- amendment2 replacement rule 4: uniform over
# {0, ..., m-1} INCLUDING IDENTITY
# ---------------------------------------------------------------------------

def test_circular_offset_includes_identity():
    import random

    rng = random.Random(0)
    offsets = {circular_offset(4, rng) for _ in range(500)}
    assert offsets == {0, 1, 2, 3}, "must draw uniformly from ALL offsets {0,...,m-1}, including 0"


def test_circular_offset_single_window_only_identity():
    import random

    rng = random.Random(0)
    assert all(circular_offset(1, rng) == 0 for _ in range(20))


def test_circular_offset_rejects_nonpositive_m():
    import random

    rng = random.Random(0)
    with pytest.raises(ValueError):
        circular_offset(0, rng)


def test_circular_shift_identity_is_noop():
    values = [10.0, 20.0, 30.0, 40.0]
    assert circular_shift(values, 0) == values


def test_circular_shift_preserves_multiset():
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    for k in range(len(values)):
        shifted = circular_shift(values, k)
        assert sorted(shifted) == sorted(values)


def test_circular_shift_empty():
    assert circular_shift([], 0) == []


# ---------------------------------------------------------------------------
# Reprojection: e* = M(Pe)
# ---------------------------------------------------------------------------

def test_reprojection_orthogonal_after_shift():
    xs = [-1.0, -0.6, -0.2, 0.1, 0.5, 0.9, 1.0]
    ys = [2.0, 1.5, 1.1, 1.3, 1.8, 2.6, 3.0]
    residuals = fit_quadratic_residuals(xs, ys)
    assert residuals is not None
    shifted = circular_shift(residuals, 2)
    reprojected = reproject_through_quadratic(xs, shifted)
    assert reprojected is not None
    assert abs(sum(reprojected)) < 1e-6
    assert abs(sum(r * x for r, x in zip(reprojected, xs))) < 1e-6
    assert abs(sum(r * x * x for r, x in zip(reprojected, xs))) < 1e-6


def test_reprojection_identity_offset_reproduces_original_residuals():
    xs = [-1.0, -0.6, -0.2, 0.1, 0.5, 0.9, 1.0]
    ys = [2.0, 1.5, 1.1, 1.3, 1.8, 2.6, 3.0]
    residuals = fit_quadratic_residuals(xs, ys)
    assert residuals is not None
    shifted = circular_shift(residuals, 0)
    reprojected = reproject_through_quadratic(xs, shifted)
    assert reprojected is not None
    for a, b in zip(reprojected, residuals):
        assert abs(a - b) < 1e-9


# ---------------------------------------------------------------------------
# Studentization
# ---------------------------------------------------------------------------

def test_studentize_basic():
    assert studentize(1.0, 0.0, 2.0) == pytest.approx(0.5)
    assert studentize(-1.0, 0.0, 2.0) == pytest.approx(-0.5)


def test_studentize_degenerate_sd_returns_none():
    assert studentize(1.0, 0.0, 0.0) is None
    assert studentize(1.0, 0.0, -1.0) is None


# ---------------------------------------------------------------------------
# Plus-one p-values: p = (1 + #exceedances) / (R + 1)
# ---------------------------------------------------------------------------

def test_plus_one_pvalue_zero_exceedances_floor():
    assert plus_one_pvalue(0, 1999) == pytest.approx(1 / 2000)


def test_plus_one_pvalue_all_exceed():
    assert plus_one_pvalue(1999, 1999) == pytest.approx(1.0)


def test_plus_one_pvalue_never_zero():
    assert plus_one_pvalue(0, 50) > 0.0
