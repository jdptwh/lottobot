"""Synthetic panel-record generator for the Phase-1 recovery test
(`tests/analysis/test_phase1_synthetic.py`).

Simulates irregular-interval, interval-censored (0.1-point `pu_interval`)
game lifecycles with a KNOWN, injected sales->claim lag, so the
distributed-lag estimator in `analysis/phase1_detectability.py` can be
checked for recovery before it is trusted on real data (Phase 1 design
rule 4 -- the machine gate for this phase).

This module implements `docs/specs/m6b_estimator_redesign_addendum.md`
section 2.6 AS AMENDED by `docs/specs/m6b_panel_amendment2.md` ("Generator
changes"), which supersedes addendum rule 6. The prior generator was
diagnosed (addendum D3) as silently dropping the injected echo in a
fraction of lifecycles via the `min(1.0, ...)` clamp; amendment2
additionally requires (a) at least 10-12 irregularly spaced windows per
lifecycle (up from 8-14, floor raised), (b) the same grid logic for null
and recovery (already true here -- the four deterministic probes are
computed and merged into the grid identically regardless of scenario), (c)
a MECHANISM-SPECIFIC null with a common/matched exponential age-decay
constant across sales and claims but NO sales-to-claims echo -- this is the
diagnosed shared-curvature defect (shared lifecycle decay trends surviving
detrending produced all-bin false positives) that this synthetic scenario
exists to stress-test (amendment2 Execution step 2, "run the shared-
curvature null first"), and (d) varied per-lifecycle noise scale ("noisy
flows").

Model per synthetic lifecycle (seeded, deterministic):

  - Two smooth secular trends, always present in BOTH scenarios: a
    sales-fraction decline (`1/decay_s`) and a claim-fraction decline
    (`1/decay_c`). In the two INDEPENDENT-null and recovery scenarios,
    `decay_s`/`decay_c` are drawn independently per lifecycle, so pooling
    many lifecycles' secular trends alone must not produce a detectable
    pooled slope. In the SHARED-CURVATURE null scenario (amendment2,
    `null_mode="shared_curvature"`), `decay_c` is set EQUAL to `decay_s`
    (a common/matched exponential age-decay constant) -- the mechanism the
    panel diagnosed as capable of surviving a linear detrend and producing
    an all-bins false positive; quadratic detrending is stress-tested
    against exactly this case.
  - A single localized "bump" (a smooth Gaussian-CDF ramp) added to the
    SALES curve at a random time `t0` per lifecycle, in EVERY scenario --
    sales genuinely fluctuate locally for reasons besides a claim-lag
    mechanism, and every null must still contain that fluctuation so the
    test is honest about what "no signal" means.
  - **Known-kernel scenario** (`inject_kernel=True`): the SAME bump
    shape/amplitude is ALSO added to the CLAIM curve, shifted by
    `lag_days` -- claims respond to that one sales event, `lag_days` later.
    `decay_c` is chosen (subject to a bounded retry search) so that the
    echo's peak-plus-tail (`t0 + lag_days + 3*BUMP_SIGMA`) never approaches
    the claim curve's `min(1.0, ...)` ceiling -- "injection integrity" --
    asserted explicitly below, never left to chance.
  - **Independent-null scenario** (`inject_kernel=False`,
    `null_mode="independent"`): the claim curve is a fully INDEPENDENT
    process -- its own secular decay AND its own localized bump at an
    INDEPENDENTLY drawn time, with zero functional dependence on the sales
    curve's bump time.
  - **Shared-curvature null scenario** (`inject_kernel=False`,
    `null_mode="shared_curvature"`, amendment2 "Generator changes"): the
    claim curve shares the SAME exponential age-decay constant as the sales
    curve (`decay_c = decay_s`) but still has its OWN independently timed
    bump and zero functional dependence on the sales bump time -- i.e. the
    only shared structure is the common secular decay curvature, never an
    echo of the sales event.
  - The irregular observation grid is randomly generated per lifecycle
    (30-180 day gaps, at least 10-12 windows), PLUS four DETERMINISTIC
    probe timestamps per lifecycle in EVERY scenario: `t0-2*sigma`,
    `t0+2*sigma`, `t0+lag_days-2*sigma`, `t0+lag_days+2*sigma`. These probes
    are embedded among the ordinary irregular windows (merged and sorted
    together, not appended as a separate segment), guaranteeing at least
    one window whose span brackets the sales bump and a second, DISJOINT
    window whose span brackets `t0+lag_days`, with window-midpoint lag
    exactly `lag_days` -- reachable under the estimator's all-ordered-
    disjoint pairing rule (addendum rule 1, unchanged).
  - The top-tier remaining-count series is generated the same way (as an
    integer count derived from the claim-fraction curve), so the top-tier
    component can be recovery-tested too.
  - Percent-unsold values are quantized to the nearest 0.1 point before
    being converted to `pu_interval` (never treated as exact), and small
    Gaussian measurement noise is added to both series, with a per-
    lifecycle noise-SCALE multiplier ("noisy flows", amendment2 "vary
    curvature, lifecycle length, spacing, and zero/noisy flows") drawn
    independently per lifecycle.

**Documented SNR / minimum-detectable-amplitude (MDE) note**: the echo
moves the claim curve by `BUMP_AMPLITUDE * u_init` = 0.30 * u_init dollars
at its peak, against a per-observation Gaussian measurement-noise sd of
`noise_scale * 0.002 * u_init` -- roughly a 100:1 (at noise_scale=1)
per-observation amplitude-to-noise ratio wherever the echo is not clamped,
i.e. detectability in this synthetic design is overwhelmingly an ALIGNMENT-
GEOMETRY question (does some pair's window bracket the bump and a disjoint
later window bracket the echo?), not an amplitude question. Because the
per-pair signal is this strong, the approximate minimum detectable
amplitude at the panel scale used here (N ~= 150-260 lifecycles, ~10-16
windows/lifecycle, family-wise alpha 0.05) for a rank-based test to clear
p < 0.01 in the true-lag bin is roughly one to two orders of magnitude
below 0.30 (order 0.01-0.03 fractional pool movement) -- the constraint
binding real-panel detectability (Phase 1 report) is expected to be pair
COUNT and grid ALIGNMENT (how often a real lifecycle's irregular capture
gaps happen to bracket bump and echo), not amplitude headroom.
"""
from __future__ import annotations

import math
import random
from datetime import date, timedelta

PRICES = (1.0, 2.0, 3.0, 5.0, 10.0, 20.0, 25.0, 30.0)

BUMP_AMPLITUDE = 0.30   # fraction of the prize pool moved by the bump (both scenarios' sales)
BUMP_SIGMA = 8.0        # days; how sharp the localized event is

# Clamp-integrity margin: the injected echo's secular level plus the bump
# amplitude must never reach the min(1.0, ...) ceiling with margin to spare,
# so the clamp never truncates it.
CLAMP_INTEGRITY_CEILING = 0.95
_CLAMP_TARGET_SECULAR_CAP = CLAMP_INTEGRITY_CEILING - BUMP_AMPLITUDE

_DECAY_LO, _DECAY_HI = 150.0, 400.0
_MAX_DECAY_C_RETRIES = 50

# Amendment2 "Generator changes": at least 10-12 irregularly spaced windows
# per synthetic lifecycle (raised from the addendum's 8-14 floor of 8).
_N_OBS_LO, _N_OBS_HI = 10, 16

# Amendment2 "vary ... zero/noisy flows": per-lifecycle noise-scale
# multiplier applied to both measurement-noise standard deviations.
_NOISE_SCALE_LO, _NOISE_SCALE_HI = 0.5, 2.0

NULL_MODES = ("independent", "shared_curvature")


def _bump_cdf(t: float, t0: float, sigma: float) -> float:
    return 0.5 * (1.0 + math.erf((t - t0) / (sigma * math.sqrt(2.0))))


def simulate_panel_records(
    n_lifecycles: int,
    lag_days: float,
    inject_kernel: bool,
    seed: int,
    null_mode: str = "independent",
) -> list[dict]:
    """Returns a flat list of panel-record dicts (schema-shaped, minimal
    fields) across `n_lifecycles` synthetic games.

    `null_mode` is only consulted when `inject_kernel` is False:
      - "independent" (default): claims are a fully independent process
        (independent decay constant AND independent bump time).
      - "shared_curvature" (amendment2 "Generator changes"): claims share
        the SAME exponential age-decay constant as sales (the diagnosed
        shared-curvature defect) but still have their own independently
        timed bump -- no echo either way.
    """
    if null_mode not in NULL_MODES:
        raise ValueError(f"null_mode must be one of {NULL_MODES}, got {null_mode!r}")
    rng = random.Random(seed)
    base_date = date(2018, 1, 1)
    records: list[dict] = []

    for i in range(n_lifecycles):
        price = rng.choice(PRICES)
        u0 = price * rng.uniform(3000.0, 20000.0)
        r0 = rng.randint(8, 40)
        lifespan = rng.uniform(500, 1100)
        decay_s = rng.uniform(_DECAY_LO, _DECAY_HI)   # secular sales-decline time constant
        noise_scale = rng.uniform(_NOISE_SCALE_LO, _NOISE_SCALE_HI)  # amendment2: "noisy flows"

        # Sales bump time: independent event, kept well inside the lifespan and
        # far enough from the end that its lagged echo (if injected) plus the
        # deterministic probes around t0+lag_days still fit inside [0, lifespan].
        bump_t0_hi = lifespan - lag_days - 100.0
        if bump_t0_hi <= 80.0:
            continue  # lifespan too short for this lag to fit with margin; skip draw
        bump_t0 = rng.uniform(80.0, bump_t0_hi)

        if inject_kernel:
            # Injection integrity: search for a decay_c such that the echo's
            # tail (t0 + lag_days + 3*sigma) never reaches the claim curve's
            # [0, 1] clamp with amplitude added on top.
            decay_c = None
            t_echo_tail = bump_t0 + lag_days + 3.0 * BUMP_SIGMA
            for _ in range(_MAX_DECAY_C_RETRIES):
                candidate = rng.uniform(_DECAY_LO, _DECAY_HI)
                # secular_c(t_echo_tail) = 1 - exp(-t_echo_tail/candidate) must be
                # <= _CLAMP_TARGET_SECULAR_CAP, i.e. t_echo_tail <= -candidate*ln(1-cap)
                t_max = -candidate * math.log(1.0 - _CLAMP_TARGET_SECULAR_CAP)
                if t_echo_tail <= t_max:
                    decay_c = candidate
                    break
            if decay_c is None:
                continue  # could not satisfy clamp integrity for this draw; skip lifecycle
            assert (
                (1.0 - math.exp(-t_echo_tail / decay_c)) + BUMP_AMPLITUDE
                <= CLAMP_INTEGRITY_CEILING + 1e-9
            ), "clamp-integrity violated: injected echo would be truncated by the [0,1] cap"
            claim_bump_t0 = bump_t0 + lag_days
        elif null_mode == "shared_curvature":
            # Amendment2 shared-curvature null: common/matched exponential
            # age-decay constant across sales and claims, but the claim
            # bump is still independently timed and there is NO echo.
            decay_c = decay_s
            null_bump_hi = lifespan - 100.0
            claim_bump_t0 = rng.uniform(80.0, max(81.0, null_bump_hi))
        else:
            # Independent null: claims are an independent process with
            # their OWN secular decay AND their OWN bump at an
            # INDEPENDENTLY drawn time -- zero functional dependence on the
            # sales bump time.
            decay_c = rng.uniform(_DECAY_LO, _DECAY_HI)
            null_bump_hi = lifespan - 100.0
            claim_bump_t0 = rng.uniform(80.0, max(81.0, null_bump_hi))

        def sales_frac(t: float, decay_s=decay_s, bump_t0=bump_t0) -> float:
            if t <= 0:
                return 0.0
            secular = 1.0 - math.exp(-t / decay_s)
            bump = BUMP_AMPLITUDE * _bump_cdf(t, bump_t0, BUMP_SIGMA)
            return min(1.0, secular + bump)

        def claim_frac(t: float, decay_c=decay_c, claim_bump_t0=claim_bump_t0) -> float:
            if t <= 0:
                return 0.0
            secular = 1.0 - math.exp(-t / decay_c)
            bump = BUMP_AMPLITUDE * _bump_cdf(t, claim_bump_t0, BUMP_SIGMA)
            return min(1.0, secular + bump)

        # Irregular observation grid, PLUS four deterministic probe times so a
        # window brackets the sales bump and a disjoint later window brackets
        # t0+lag_days -- embedded among ordinary windows (same grid logic for
        # every scenario, amendment2 "Generator changes").
        n_obs = rng.randint(_N_OBS_LO, _N_OBS_HI)
        t = 0.0
        obs_times = [0.0]
        for _ in range(n_obs - 1):
            t += rng.uniform(30, 180)
            if t > lifespan:
                break
            obs_times.append(t)

        probes = [
            bump_t0 - 2.0 * BUMP_SIGMA,
            bump_t0 + 2.0 * BUMP_SIGMA,
            bump_t0 + lag_days - 2.0 * BUMP_SIGMA,
            bump_t0 + lag_days + 2.0 * BUMP_SIGMA,
        ]
        obs_times.extend(probes)
        obs_times = sorted(set(round(x, 3) for x in obs_times if 0 <= x <= lifespan))
        if len(obs_times) < 5:
            continue

        game_key = f"synthetic-{i}:game-{i}"
        for t in obs_times:
            pu_noise = rng.gauss(0, 0.3 * noise_scale)
            pu = max(0.0, min(100.0, 100.0 * (1.0 - sales_frac(t)) + pu_noise))
            pu_rounded = round(pu, 1)
            pu_interval = [max(0.0, round(pu_rounded - 0.05, 10)), round(pu_rounded + 0.05, 10)]

            u_noise = rng.gauss(0, u0 * 0.002 * noise_scale)
            total_unclaimed = round(max(0.0, u0 * (1.0 - claim_frac(t)) + u_noise), 2)

            remaining = max(0, round(r0 * (1.0 - claim_frac(t))))

            obs_date = base_date + timedelta(days=round(t))
            records.append(
                {
                    "game_no": 900 + i,
                    "game_key": game_key,
                    "obs_date": obs_date.isoformat(),
                    "capture_ts": obs_date.isoformat() + "T00:00:00+00:00",
                    "source": "wayback",
                    "capture_url": "synthetic://test",
                    "retrieved_at": obs_date.isoformat() + "T00:00:00+00:00",
                    "content_hash": "0" * 64,
                    "parser_version": "synthetic@1",
                    "percent_unsold": pu_rounded,
                    "pu_interval": pu_interval,
                    "total_unclaimed": total_unclaimed,
                    "top_prizes": [{"level": 10000, "remaining": remaining}],
                    "price": price,
                    "name": f"SYNTHETIC GAME {i}",
                    "lifecycle_status": "active",
                    "has_noncash_prize": False,
                }
            )
    return records
