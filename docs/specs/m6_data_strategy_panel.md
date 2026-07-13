# M6 data-strategy panel verdict (Rule 12 PLAN-gate advisory, 2026-07-13)

**Invocation:** first live panel run of this project. `python -m panel.cli plan
--task-id m6-data-strategy` · experts `anthropic/claude-fable-5` +
`openai/gpt-5.6-sol-pro` · synthesis `openai/gpt-5.6-sol-pro` (owner-requested
lineup) · cost $1.24 of the $2.00 cap · archived verdict:
`.claude/state/panel_verdict.m6-data-strategy.json` (gitignored).
**Question posed:** full prompt preserved at
`.claude/state/panel_prompt_m6-data-strategy.json` — data-acquisition ranking,
strongest defensible claim-lag model class, precise predictive ceiling, and
pre-M6 quick wins.

**Verdict: FAIL** — a technical judgment against the *plan as posed*, i.e. the
project spec's own §3-v2 sketch. The panel advises; the PLANNER owns; the owner
approves. This document is the input of record for the M6 PLAN loop.

## The headline finding (critical)

> "The proposed per-tier M6 claim-lag model is not identifiable for lower tiers
> from aggregate unclaimed dollars; static initial prize tables do not repair
> the missing dynamic observations."

The state publishes dynamic counts only for TOP tiers; lower-tier unclaimed
value is one aggregate dollar number. No volume of history separates per-tier
lag curves out of an aggregate — the spec's per-tier lag-window model must be
replaced, not calibrated. M6's spec must be rewritten around this constraint.

## All findings

- **critical** — per-tier model unidentifiable for lower tiers (above).
- **major** — naive EV is not an unbiased estimate; it is an UPPER BOUND on
  unclaimed value per estimated unsold ticket and should be labeled as such.
- **major** — the spec's lag-window formula conflates redemption delay with
  sales velocity; must not be presented as fitted or as a deterministic bound.
- **major** — "~30 snapshots" is not a valid readiness criterion; information
  content depends on sales movement, quantization, event counts, archive
  coverage, lifecycle diversity.
- **major** — Wayback cadence/coverage is UNVERIFIED; audit before scheduling
  anything on it.
- **major** — percent_unsold's 0.1-point rounding must be modeled as interval
  censoring, never as exact daily ticket sales.
- **minor** — official field semantics + Maine's claim deadline unverified;
  print-run coverage lacks an imputation/exclusion policy; no empirical basis
  exists yet for any specific error range.

## Expert dissent (preserved, per instruction)

1. **Is a simple lag-window discount a shippable lower bound?** Expert A: ship
   a conservative global lag-window as a pessimistic bound and grade on it.
   Expert B: the assumption-free lower bound is effectively ZERO; lag-window
   outputs are sensitivity scenarios, not bounds. *(Synthesis sided with B.)*
2. **What do full static prize tables buy?** Expert A: decomposition of
   unclaimed value into a dynamic tier-value vector. Expert B: initial
   structure and priors only — they cannot decompose subsequent aggregate
   dollars. *(Synthesis sided with B; tables become generative priors.)*

## Blind spots the synthesis flagged in both experts

Noncash/annuity/free-ticket prize treatment in source totals; Bayesian-refit
compute budget vs GitHub Actions limits (likely: periodic offline refit +
lightweight daily inference); user-facing policy for rank ties when credible
intervals overlap; model governance (rollback thresholds, posterior
reproducibility, calibration-drift monitoring).

## The synthesized plan (verbatim artifact, 9 points)

1. Establish semantics and provenance first. Verify official meanings of "percent unsold" and "unclaimed," the claim deadline, and treatment of low-tier/noncash prizes. Continue immutable daily captures with raw HTML, retrieval/as-of timestamps, hashes, parser versions, and anomaly alerts.

2. Make Wayback reconnaissance the first acquisition task. Query CDX and produce a cadence/coverage report before committing M6 dates. If useful, backfill each unique capture into an era-versioned parser and canonical history schema. Preserve irregular observation intervals, duplicate/corrected captures, page-format or semantic drift, timezone ambiguity, left truncation, game disappearance, game-number reuse, and completed games; never treat the archive as a clean daily panel.

3. In parallel, recover authoritative print runs and complete initial prize tables from approved article pages or archives, recording provenance and coverage. These data provide launch/book EV and generative priors but do not reveal dynamic lower-tier remaining counts. Ingest scratchdates weekly for lifecycle labels and verified claim deadlines. Request richer data from the Lottery through a non-scraping channel: exact inventory, dynamic full-tier counts, effective timestamps, or aggregate sale-to-redemption summaries. Defer Fast Play to a separate model and use other-state data only for sensitivity priors after transport checks.

4. Ship v1.5 before fitting M6. Rename naive EV to "unclaimed-value upper bound per estimated unsold ticket," propagate 0.1-point inventory rounding into an interval, and explain its assumptions. The assumption-free lower bound is effectively zero, so do not label a heuristic discount as a bound. Make highly depleted or unstable games ineligible for "best pick"; show them as unrankable with widening uncertainty. Display launch/book EV where available, audit current confidence bands against archived trajectories, and offer transparent sensitivity scenarios for several lag assumptions rather than a fitted-looking point correction.

5. Build a canonical irregular-interval panel. Represent rounded percent-unsold values as inventory intervals and infer a monotone latent inventory/sales path, with explicit correction/outlier handling. Treat page disappearance as interval-censored lifecycle exit, not zero remaining value. Preserve dead games without claiming their final hidden unsold-stock value is observed.

6. Use a staged model. First test whether pooled sales-to-claim lag is detectable using robust distributed-lag summaries over variable intervals. Then fit a parsimonious Bayesian hierarchical state-space model with latent ticket sales, unsold prize value, sold-but-unredeemed value, a regularized geometric/Weibull/lognormal redemption hazard, reporting/batching effects, and observations consisting of rounded inventory, aggregate unclaimed dollars, and top-tier count decrements. Pool broadly by price/prize band and lifecycle phase. Estimate only a pooled dollar-weighted lag kernel for unobserved lower tiers; static prize tables cannot identify tier-specific dynamic hazards. Model top-tier behavior separately but heavily pool it because events are sparse. Do not use ordinary per-game Kaplan–Meier or the spec's uniform-window formula as the principal model.

7. Gate release on evidence, not 30 calendar days. Use rolling-origin, held-out-game, and held-out-lifecycle tests against the current quotient, launch EV, and simple pooled-lag baselines. Evaluate future aggregate claim-flow prediction, top-tier decrement calibration, interval coverage, rank stability, and sensitivity to priors. Release adjusted EV only if it materially improves held-out results and its 80%/95% intervals calibrate; otherwise retain sensitivity scenarios. Daily production should use a versioned prefit model or otherwise be designed to fit GitHub Actions limits.

8. Publish posterior expected unsold-stock EV per dollar, credible intervals, probability of being top-ranked, archive/data-quality status, and both naive-upper-bound and adjusted views. Never collapse uncertainty into a confidence multiplier or advertise precise late-game rankings.

9. State the ceiling explicitly. With adequate lifecycle history, the system may estimate population-level redemption lag, rounded sales velocity, expected aggregate claim flow, broad prize-band effects, and probabilistic EV rankings. It cannot identify exact prizes in unsold stock, individual sale-to-claim pairs, detailed lower-tier hazards from aggregate dollars, winning tickets, retailers, packs, or buyers. Near sellout, latent sold-versus-unredeemed value and inventory quantization make rankings structurally weak. More aggregate history has diminishing returns once pooled hazards stabilize; exact inventory and dynamic tier counts would raise the EV-estimation ceiling, but no dataset can turn random tickets into win predictions. "Optimal price point" requires a stated utility/risk objective; under monetary EV and the product's premise, the optimum is not to play.

## Implications for the roadmap (planner note, pending owner direction)

- The project spec's §3-v2 model sketch is superseded in principle; M6's PLAN
  loop should spec the staged model of point 6 with the release gate of point 7.
- Two new pre-M6 work packages emerge: **W1 Wayback reconnaissance** (CDX
  cadence/coverage audit → go/no-go on backfill) and **W2 v1.5 honesty pass**
  (upper-bound labeling, interval-ized inventory, launch/book EV display,
  sensitivity scenarios). Both are spec-able immediately; W1 gates M6's
  schedule, W2 improves the live product now.
- A non-scraping data request to the Lottery (point 3) is an owner action —
  drafting the email is cheap and the upside (exact inventory / dynamic tier
  counts) raises the ceiling more than any scraping ever will.
