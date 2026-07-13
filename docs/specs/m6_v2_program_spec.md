# SPEC (program): M6 v2 — claim-lag model, staged and evidence-gated (M6a–M6d)

**Author of record:** PLANNER (`claude-fable-5`) · 2026-07-13
**Status:** program spec of record for the M6 rebuild. Phase 0 (M6a) is implementable directly from this document; Phases 1–3 (M6b–M6d) are governed by it, and Phase 2 additionally requires its own sub-spec (`docs/specs/m6_phase2_model_spec.md`) approved before any implementation.
**Governing authorities:** `docs/specs/m6_data_strategy_panel.md` (panel verdict — the design authority; its 9-point synthesized plan is binding unless this spec explicitly narrows it); `docs/specs/w1_wayback_coverage.md` (GO on backfill, bounded expectations); maine-scratch-ev-spec.md §4 (additive-only `latest.json` contract, `required` list frozen), §6 (gates), §8 (responsible use, polite scraping); `docs/specs/m4a_scoring_spec.md` (scoring semantics — the `claim_lag` reason copy and F-grade rule are live UI contract); `docs/specs/m5_daily_action_spec.md` + `m5a_test_rebaseline_spec.md` (discipline precedents: thin runtime, frozen regression artifacts, LF determinism, bot-owned `data/latest.json`).

## Supersession record

1. **Project spec §3-v2 is superseded in full.** The panel's critical finding stands: a per-tier lag-window model is not identifiable for lower tiers from one aggregate unclaimed-dollar number, and static prize tables cannot repair the missing dynamic observations. No work item in this program may implement, calibrate, or present the §3-v2 `lag_window_pct` formula as a fitted model or a bound. (Its scenarios survive only as W2's explicitly labeled sensitivity views.)
2. **Project spec §7 M6's "~30 snapshots" readiness criterion is superseded** by the evidence gates below (panel major finding: snapshot count is not information content).
3. `ev_ratio_adjusted` remains reserved: M3's rule that it stays `null` is amended to "stays `null` in production until the M6d SHIP decision" (Phase 2 populates it in tests/backtests only).

## Program overview and milestone map

Pipeline: **build the panel → prove the signal exists → fit only what is identifiable → ship only what beats the baselines.** Each phase gates the next; a NO-GO at any gate is a valid, cheap outcome, not a failure of execution.

| Milestone | Phase | Deliverable | Gate to proceed |
|---|---|---|---|
| **M6a** | 0 | Wayback backfill + canonical irregular-interval panel (`data/panel/`) + semantics note | Panel builds green; owner accepts the panel + semantics note (touchpoint) |
| **M6b** | 1 | Pooled distributed-lag detectability study → `docs/reports/m6_phase1_detectability_report.md` | **HARD OWNER STOP** on the report (GO / NO-GO per component) |
| **M6c** | 2 | Offline Bayesian hierarchical state-space fit → versioned `data/models/claimlag_vN.json` + runtime `scraper/apply_claimlag.py` | Own sub-spec approved first (touchpoint); evidence trigger met (Resolution 6) |
| **M6d** | 3 | Backtest + calibration harness → binary SHIP / WITHHOLD report; if SHIP, UI via Rule 11 mockup | Owner ship/withhold decision, including the score-keying ruling (Resolution 7); mockup approval if SHIP |

Lettered milestones per house precedent (M4a/M4b, M5a). Each milestone closes with its own reviewer PASS and owner touchpoint; a failed loop resumes from git state (Rule 9). Novel-architecture judgment calls inside M6c may re-invoke the panel per Rule 12 (`PANEL_ENABLED=1`); the panel advises, this spec and its sub-spec decide.

---

## Phase 0 (M6a) — Wayback backfill and the canonical panel

### Objective

Turn W1's ~200 usable web.archive.org captures (2015–2026 era) plus the accumulating `data/history/` dailies into ONE canonical, irregular-interval observation panel under `data/panel/`, honestly modeling interval censoring, lifecycle exits, and provenance — never pretending the archive is a clean daily series (panel points 2 and 5). Also: establish the field-semantics facts the panel demanded first (point 1).

### Design rules of record

1. **New `data/panel/` layout (Resolution 1).** The panel is a research contract, distinct from the frozen §4 site contract; `data/history/` stays exactly what M5 made it (bot-owned byte-copies of `latest.json`) and is a *source* for the panel, never modified by it.
2. **Record schema** — new `data/schema/panel_record.schema.json`; one JSON object per line (JSONL), fields:
   - `game_no` (int), `game_key` (string, `"{game_no}:{name-slug}"` — guards game-number reuse across the 2015–2026 span: same `game_no` + different name ⇒ distinct lifecycle),
   - `obs_date` (ISO date, **page truth**: parsed from the page's own "as of" line, ET; never the capture timestamp),
   - `capture_ts` (ISO datetime UTC: CDX timestamp for wayback records, run timestamp for daily records; the timezone-ambiguity record),
   - `source` (`"wayback"` | `"daily"`), `capture_url` (wayback URL, or the repo-relative `data/history/YYYY-MM-DD.json` path), `retrieved_at` (ISO datetime UTC), `content_hash` (sha256 of raw source bytes), `parser_version` (string),
   - `percent_unsold` (number, as published) **plus** `pu_interval` (`[lo, hi)` pair: the 0.1-point rounding modeled as interval censoring — `[x−0.05, x+0.05)`, floored at 0 — never treated as exact),
   - `total_unclaimed` (number), `top_prizes` (same shape as §4), `price` (number), `name` (string),
   - `lifecycle_status` (`"active"` | `"exited_observed"` | `"exited_unobserved"`), assigned at merge time: `exited_observed` = last record shows 0% unsold or a scratchdates-confirmed end; `exited_unobserved` = the game vanishes between captures — an interval-censored exit whose final hidden unsold value is NOT observed (panel point 5; W1 finding 4).
3. **Two modules, strict separation:**
   - `scraper/wayback_backfill.py` — CDX query (digest-collapsed, status 200), fetch each unique in-era capture into a **gitignored** raw cache (`data/panel/raw_cache/`), parse with the production `scraper.scrape.parse`, emit `data/panel/wayback_observations.jsonl`. **Era guard: captures dated < 2015-01-01 are skipped and counted, never parsed** (W1: pre-2015 formats fail the parser; era-versioned parsers are out of scope). Parse failures inside the era are logged with `capture_url` and skipped — never fatal. §6.1's `parser_gate` is NOT applied per-capture (historical pages legitimately differ); instead the coverage AC below is the gate.
   - `scraper/build_panel.py` — offline, deterministic, no network: merges `wayback_observations.jsonl` + every `data/history/*.json` into canonical `data/panel/panel.jsonl`, sorted by (`obs_date`, `game_no`), LF-only, UTF-8, `newline="\n"` on every write site (M5a rule 5 precedent — Windows CRLF is a known bug class here). Dedup: CDX digest-collapse handles identical pages; if two distinct-digest wayback captures share an `obs_date` for a game, keep the later `capture_ts` and log the supersession. Re-running the merge is idempotent (full rebuild, byte-stable).
4. **Politeness (non-negotiable):** `wayback_backfill.py` requests **web.archive.org only** (zero requests to mainelottery.com or maine.gov), ≥ 2 s delay between fetches, identifying UA string, resumable via the raw cache (a re-run fetches only cache misses). It is a **one-time manual CLI**: it must never be imported by `scraper/run_daily.py`, never referenced by `daily.yml`, and a test enforces both.
5. **Runtime purity:** nothing under `scraper/` gains a new runtime dependency; both new modules are stdlib + already-authorized `requests` (fetch path only). Tests never hit the network (existing socket-guard conftest pattern; fixtures are frozen W1-era capture samples).
6. **Semantics subtask (panel point 1 / blind spot 1):** produce `docs/m6_semantics.md` documenting, with source URLs/quotes: the official meaning of "percent unsold" and "unclaimed" as published; Maine's prize-claim deadline (scratchdates page / official rules); and the treatment of noncash / annuity / free-ticket prizes in the published unclaimed totals. Where a fact cannot be established from public pages, say so explicitly — unresolved items become stated model assumptions in Phase 1/2, not silent guesses. (The non-scraping data request to the Lottery remains an owner action outside this program.)

### File plan (touch nothing else)

- `scraper/wayback_backfill.py` — NEW (rule 3a).
- `scraper/build_panel.py` — NEW (rule 3b).
- `data/schema/panel_record.schema.json` — NEW.
- `data/panel/wayback_observations.jsonl`, `data/panel/panel.jsonl` — NEW committed artifacts (JSONL; raw cache gitignored via `.gitignore` entry `data/panel/raw_cache/`).
- `tests/scraper/test_wayback_backfill.py`, `tests/scraper/test_build_panel.py` — NEW; offline, frozen fixtures under `tests/scraper/fixtures/wayback/` (≥ 3 era samples: ~2015/2017-era, ~2019-era, current-era; plus one pre-2015 sample asserting the era guard skips it).
- `docs/m6_semantics.md` — NEW (rule 6).
- `.gitignore` — one additive line.
- `CLAUDE.md` — "Current state" at close.
- Do NOT touch: `scraper/scrape.py`, `scraper/compute.py`, `scraper/games.py`, `scraper/run_daily.py`, `.github/workflows/daily.yml`, `data/latest.json`, `data/history/` contents, `data/games.json`, `data/schema/latest.schema.json`, `site/`, any existing test or fixture, `requirements.txt`.

### Acceptance criteria

1. Offline: fixture captures for each era parse into records that validate against `panel_record.schema.json` via `jsonschema`; the pre-2015 fixture is skipped by the era guard with a counted log line, not an error.
2. `pu_interval` is present and correct on every record (`[x−0.05, x+0.05)`, floor 0); a synthetic test asserts a 0.0% record gets `[0, 0.05)`.
3. `build_panel.py` merge is deterministic: two runs byte-identical; output sorted (`obs_date`, `game_no`); LF-only bytes asserted; daily records carry `source: "daily"` with the history-file path as `capture_url` and its sha256 as `content_hash`.
4. Lifecycle labeling: synthetic tests cover all three statuses, including a game that disappears between two wayback `obs_date`s ⇒ `exited_unobserved` (never `exited_observed`, never dropped).
5. `game_key` collision test: same `game_no`, different name across eras ⇒ two distinct `game_key` lifecycles.
6. Purity tests: no module under `scraper/` other than `wayback_backfill.py` imports it; `daily.yml` byte-unchanged (git diff clean); no runtime `requirements.txt` change; full `python -m pytest -q` green offline.
7. **Live backfill run (CP2, human-observed, like M5's CP3):** the one-time run completes; **≥ 150 of the in-era unique captures parse into records** (W1 estimates ~200 in-era; below 150, stop and report to the planner — do not lower the bar); the log accounts for every capture (parsed / duplicate / era-skipped / parse-failed with URL).
8. Committed `panel.jsonl` spot-check worksheet for the owner touchpoint: 3 named games traced across ≥ 5 observations each, including at least one completed lifecycle (launch → sellout/exit) and one `exited_unobserved` game.
9. `docs/m6_semantics.md` exists with sourced findings or explicit "could not establish" entries for all three semantics questions in rule 6.

### Tier, budget, checkpoints

- **IMPLEMENTER** throughout (parsing judgment, lifecycle semantics, live-run care). No BULK slice — the panel tests ARE the machine check being built.
- Loop budget: defaults (MAX_IMPL_ATTEMPTS=3, MAX_REVIEW_CYCLES=2); the live backfill run is diagnosed from logs, not blindly retried — a second failed live run escalates to the planner.
- **CP1** — both modules + tests green offline; commit. **CP2** — live backfill (AC-7), `wayback_observations.jsonl` committed. **CP3** — canonical `panel.jsonl` + semantics note committed; reviewer PASS; owner accepts (touchpoint) with the AC-8 worksheet.

---

## Phase 1 (M6b) — pooled distributed-lag detectability study

### Objective

Answer, with numbers, the question the panel made the gate (point 6, first stage): **is a pooled sales-to-claim lag detectable at all** from {coarse wayback panel + growing daily panel}, before any model is fit? Two components, reported separately: (a) **top-tier**, from observed top-prize count decrements (sparse events, heavily pooled); (b) **lower-tier**, only as a single pooled dollar-weighted lag kernel from aggregate unclaimed deltas vs. interval-censored sales movement — per-tier lower-tier claims are forbidden (unidentifiable, panel critical finding).

### Design rules of record

1. Analysis code lives in a NEW top-level `analysis/` directory (`analysis/phase1_detectability.py` + helpers), **never imported by anything under `scraper/`** (test-enforced). It reads `data/panel/panel.jsonl` only.
2. **Stack: stdlib first.** If stdlib is genuinely insufficient, `numpy` is hereby authorized as a **dev-only** dependency (append to `requirements-dev.txt`; `requirements.txt` byte-unchanged; no `numpy` import under `scraper/`). Nothing heavier in this phase (Resolution 2).
3. Methods must respect the panel's constraints: irregular intervals natively (no daily interpolation), `pu_interval` censoring (no exact-sales arithmetic), robust distributed-lag summaries (not per-game Kaplan–Meier, not the §3-v2 formula), pooling by price/prize band and lifecycle phase where event counts allow.
4. **New verification surface first** (routing rule for new artifact types): before analyzing real data, a synthetic-recovery test must exist — inject a known lag kernel into simulated irregular-interval, interval-censored data and assert the estimator recovers it within stated tolerance. This test is the phase's machine gate; the report is the human gate.
5. **Report** (`docs/reports/m6_phase1_detectability_report.md`, produced by the implementer/lead, reviewed like code) must contain: data inventory (record counts by source/era/lifecycle); pooled top-tier decrement event count to date; the estimated kernels with uncertainty; the synthetic-recovery evidence; the semantics-note assumptions it relies on; separate **GO / NO-GO verdicts for the top-tier and lower-tier components** with numeric justification; prior/robustness sensitivity notes; and the **Phase-2 evidence trigger** it is required to set (Resolution 6 below).
6. **This phase ends in a HARD OWNER STOP** (Resolution 5). No Phase-2 sub-spec drafting begins before the owner rules on the report. A partial GO (e.g. top-tier GO, lower-tier NO-GO) re-scopes Phase 2 accordingly rather than killing it.

### File plan

`analysis/phase1_detectability.py` (+ minimal helpers in `analysis/`), `tests/analysis/test_phase1_synthetic.py` (NEW dir; offline, seeded, deterministic), optionally `requirements-dev.txt` (+`numpy` line only), `docs/reports/m6_phase1_detectability_report.md`, `CLAUDE.md`. Nothing under `scraper/`, `data/` (read-only), `site/`, `.github/` may change.

### Acceptance criteria

1. Synthetic-recovery test green (rule 4), seeded and deterministic; full `python -m pytest -q` green offline.
2. Purity: no `analysis` import under `scraper/`; `requirements.txt` byte-unchanged.
3. Report contains every element of rule 5; every numeric claim in it is reproducible by re-running the committed analysis script against the committed panel (command line stated in the report).
4. Owner stop executed; verdict and trigger recorded in CLAUDE.md.

**Tier:** IMPLEMENTER (statistical judgment). **Budget:** defaults. **Checkpoints:** CP1 synthetic surface green; CP2 report + owner stop.

---

## Phase 2 (M6c) — offline fit + versioned artifact + thin runtime (governed here, specced in its own sub-spec)

**Precondition (two-key gate):** Phase-1 owner GO **and** the evidence trigger of Resolution 6 met. Then the PLANNER authors `docs/specs/m6_phase2_model_spec.md`; the owner approves it before implementation (touchpoint).

Binding constraints the sub-spec inherits (it may tighten, never loosen):

1. **Model class:** parsimonious Bayesian hierarchical state-space per panel point 6 — latent interval-censored inventory/sales path, regularized redemption hazard (geometric/Weibull/lognormal family), reporting/batching effects; observations = rounded inventory intervals + aggregate unclaimed dollars + top-tier decrements; broad pooling by price/prize band and lifecycle phase; **one pooled dollar-weighted kernel for lower tiers, separately-but-heavily-pooled top tier.** Forbidden: per-tier lower-tier dynamic hazards, per-game Kaplan–Meier, the §3-v2 formula, any confidence-multiplier collapse (panel point 8).
2. **Fit is offline, dev-deps only, never in `daily.yml`** (panel blind spot 2: Actions compute budget). Fit stack (Resolution 2): the sub-spec must first argue whether a custom EM / Laplace / grid approximation suffices at this scale (~65 active + ~dozens historical lifecycles) before reaching for a PPL; `scipy` is pre-authorized dev-only alongside `numpy`; **`pymc` (or any PPL) requires explicit owner sign-off at sub-spec approval** (owner-visible line item).
3. **Artifact (Resolution 3):** committed `data/models/claimlag_v1.json` — target ≤ 100 KB, hard cap 512 KB (breach = design smell, escalate; do not move to a release asset — the runtime needs it at checkout and `daily.yml` stays fetch-free). Content: pooled kernel parameters + posterior summaries needed at runtime, plus fit metadata (panel snapshot `content_hash`, fit-script git SHA, seed, date, priors). Old versions are retained; the active version is a single constant in `scraper/apply_claimlag.py`, so **rollback = one-line revert** (governance, panel blind spot 4).
4. **Runtime:** `scraper/apply_claimlag.py` — stdlib-only, pure, deterministic; imported by `compute.py`; populates only additive fields: `ev_ratio_adjusted` (first permitted population), `ev_ratio_adjusted_ci80`, `ev_ratio_adjusted_ci95`, `probability_top_ranked`, `data_quality_status`, `claimlag_model_version`. Schema edit additive-only; the `required` list stays frozen; M1's verbatim §4-example test stays green. **Production `latest.json` keeps these fields null until the M6d SHIP decision** — Phase 2 exercises them in tests and backtests only.
5. **Reproducibility:** committed fit script + committed input panel snapshot reference + fixed seed ⇒ the artifact is regenerable bit-for-bit (or within a documented numerical tolerance, stated in the artifact metadata).
6. **Calibration-drift monitoring** (manual re-run procedure, documented in the sub-spec): empirical coverage on the rolling backtest window must satisfy **80% interval coverage ∈ [70, 90] and 95% interval coverage ∈ [90, 100]**; a breach ⇒ WITHHOLD/rollback, owner notified.

**Tier:** IMPLEMENTER, reviewer end-to-end read of `apply_claimlag.py` mandatory (it enters the daily pipeline's import graph). **Budget:** set in the sub-spec, bounded above by defaults.

## Phase 3 (M6d) — evidence-gated release

1. **Backtest harness** (`analysis/backtest.py`, dev-only): rolling-origin, held-out-game, and held-out-lifecycle evaluation (the wayback panel's completed lifecycles exist for exactly this — W1 point 1) against three baselines: current naive quotient, launch/book EV, simple pooled-lag heuristic. Metrics fixed by panel point 7: future aggregate claim-flow prediction, top-tier decrement calibration, interval coverage (thresholds of Phase-2 rule 6), rank stability, prior sensitivity.
2. **Binary SHIP / WITHHOLD report** to the owner. SHIP requires: material held-out improvement over ALL three baselines AND calibrated intervals. The report must also carry the two owner decisions pinned by Resolutions 7 and 8: what `value_score`/`grade` key on once adjusted EV exists (with a planner-drafted recommendation grounded in the calibration data — including whether the M4a claim-lag F-grade rule and `claim_lag` reason copy survive, change, or gate on `data_quality_status`), and the rank-tie/interval-overlap presentation policy. Pinned principle for the latter: **games whose 80% credible intervals overlap are presented as a statistical tie group, never as a strict ranking**; exact rendering is decided at the mockup.
3. **If SHIP:** UI work under Rule 11 — `docs/mockups/adjusted_ev_mockup.html` approved by the owner BEFORE any `site/` change; polish audit against the approved mockup before presentation; both naive-upper-bound and adjusted views published, never a single collapsed number (panel point 8); §8 framing stays prominent.
4. **If WITHHOLD:** W2's labeled sensitivity scenarios remain the surfaced treatment; adjusted fields stay unsurfaced (null in production, or surfaced only under a `data_quality_status` gate if the owner so rules). WITHHOLD is a recorded, respectable end state — the program does not loop until it ships.

**Tier:** harness IMPLEMENTER; the backtest metric assertions vs. this spec's pinned list are a possible BULK slice only if the sub-spec names the 1:1 machine check. **Budget:** defaults; a budget-exhausted loop here escalates to the planner for re-scoping, never for more attempts.

---

## Cross-phase out of scope

Fast Play (separate model, per panel); other-state data (deferred entirely — even as priors — until an owner-approved transport check exists); pre-2015 era-versioned parsers; the non-scraping Lottery data request (owner action, outside this program); W2 itself (separate spec; it neither blocks nor is blocked by M6a/M6b); any change to daily scraping cadence, `daily.yml` triggers, or `scraper/run_daily.py` before M6d SHIP; any per-tier lower-tier dynamic-hazard claim anywhere, in any phase; modifying `data/history/`, the frozen fixtures, or the §4 `required` list; monetization/accounts; every file not in a phase's file plan.

## Verification

- `python -m pytest -q` (primary gate, every phase; fully offline — the socket guard extends to `tests/analysis/`).
- Live surfaces: Phase-0 CP2 backfill run (human-observed); Phase-2/3 have none until the M6d SHIP wiring, which rides the existing M5 pipeline and its gates unchanged.
- Human gates: Phase-0 panel acceptance; Phase-1 HARD STOP; Phase-2 sub-spec approval; M6d ship/withhold + score ruling (+ mockup approval if SHIP).

## Loop budgets

Defaults (`.claude/agent.config`: MAX_IMPL_ATTEMPTS=3, MAX_REVIEW_CYCLES=2) for M6a/M6b; M6c/M6d budgets set in the Phase-2 sub-spec, never above defaults; live-run failures are diagnosed-then-retried once, second failure escalates. Budget exhaustion anywhere ⇒ planner re-scopes (this program is deliberately split so any single phase is droppable or repeatable without replaying the others).

## Risks

- **Phase 1 returns NO-GO on the lower-tier kernel.** Likely enough to plan for: the program then ships top-tier-only adjustment or stops at W2's sensitivity scenarios. That outcome still leaves the panel, the semantics note, and the backtest harness as durable assets.
- **The evidence trigger binds on calendar time.** The daily panel is 1 day old (2026-07-13); top-tier decrements are sparse. Phase 2 may sit gated for months — by design. Nothing in this spec authorizes shortcutting the trigger to fill the wait.
- **Semantics surprises** (noncash/annuity prizes inflating or deflating "unclaimed" dollars) could bias the pooled kernel; that is why `docs/m6_semantics.md` precedes any fitting, and unresolved items must appear as stated assumptions in the Phase-1 report.
- **Archive fragility:** CDX throttling, capture rot, or intra-era format drift below W1's sample resolution. Contained by the resumable cache, the ≥150 coverage AC with a stop-and-report rule, and per-capture failure logging.
- **Game-number reuse / timezone ambiguity** silently splicing two games' lifecycles — the `game_key` and dual-timestamp rules exist for this; the AC-8 human worksheet is the last line.
- **Repo bloat:** raw HTML cache is gitignored; committed JSONL is text and diff-friendly; the model artifact has a hard cap.
- **Overfit-and-ship temptation at M6d:** the release gate is three baselines + calibration, binary, owner-decided. A model that only ties the naive quotient does not ship.
- **M4a copy/grade contract collision:** the live `claim_lag` reason string and F-grade rule assume no adjusted EV exists. Resolution 7 pins that reconciliation to the M6d gate so it is decided once, with data, not drifted into.
- **Windows newline regression** in new writers — prevented by the explicit `newline="\n"` rule (M5a precedent) and LF byte assertions.

---

## Resolution record (drafter's 8 open questions, planner-ruled)

1. **Panel location:** NEW `data/panel/` (JSONL + own schema). `data/history/` is a bot-owned M5 artifact under the site contract's discipline; the panel is a research contract with different keys, censoring fields, and provenance.
2. **Dependencies (owner-visible):** `numpy` authorized dev-only for Phase 1 fallback (stdlib first); `scipy` pre-authorized dev-only for Phase 2; **any PPL (pymc etc.) requires explicit owner sign-off at Phase-2 sub-spec approval**, and the sub-spec must first argue a simpler estimator (EM/Laplace/grid) is insufficient at this data scale. Runtime `requirements.txt` never changes for M6; nothing new ever runs in `daily.yml`.
3. **Model artifact:** committed `data/models/claimlag_vN.json`, ≤ 100 KB target / 512 KB hard cap, versions retained, active version = one constant in `apply_claimlag.py` (rollback = one-line revert). Not a release asset: the runtime must be whole at checkout and the daily workflow stays fetch-free.
4. **Milestones:** lettered **M6a–M6d**, one per phase — house precedent (M4a/M4b, M5a); each phase has its own owner touchpoint and DoD.
5. **Phase-1 stop (owner-visible):** YES — hard owner stop. The panel already killed one model design at this exact kind of gate; the detectability report is precisely the evidence-review touchpoint the harness exists for.
6. **Phase-2 evidence trigger (owner-visible):** mechanism pinned, number delegated to evidence: *Phase-2 sub-spec drafting may begin only when (a) the Phase-1 report is GO for the relevant component, AND (b) the pooled top-tier decrement event count in the combined panel reaches the threshold **N that the Phase-1 report itself must set and justify from observed event rates** (the report must also state the current count and the projected calendar date of reaching N).* Anti-gaming rails: the report shows both numbers to the owner at the hard stop, and the owner may override N in either direction there — that override is the escape hatch, not a silent re-derivation later.
7. **Score/grade interaction (owner-visible):** deliberately NOT decided now. It is a mandatory, named line item inside the M6d ship/withhold decision, where calibration data exists to ground it; the planner drafts a recommendation in that report (options: score keys on adjusted; parallel adjusted score; naive score retained with `data_quality_status` gating; F-grade/claim-lag-copy fate). The M4a contract stays untouched until then.
8. **Rank-tie / interval-overlap policy:** owned by **Phase 3 (M6d)**, not W2 — W2 ships before any credible interval exists, so it has nothing to overlap. The 80%-CI tie-group principle is pinned above; rendering is a Rule 11 mockup decision.
