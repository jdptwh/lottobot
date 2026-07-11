# SPEC: Wave 3 — panel orchestrator + synthesis prompts

> Status: **AWAITING JOE'S APPROVAL** (touchpoint 1 of 2). Drafted by spec-drafter
> (Sonnet), finalized and owned by planner (Opus 4.8). Do not implement until approved.
> Lineup/structured-output facts re-verified 2026-07-07 (docs/openrouter_notes_wave3.md).

## Objective
Add `panel/orchestrator.py`: a stateless, read-only orchestrator that fans a task out to
a mixed-provider expert panel over the Wave 2 `call_model` (wrapped in `call_with_retry`),
meters cost with `CostMeter`, and assembles a schema-valid `panel_verdict` dict for both
gates. PLAN → aggregator synthesis (Opus merges expert plans into one artifact). REVIEW →
union of independent findings + arbiter adjudicating **only disputed** findings. The
orchestrator **derives** `verdict` deterministically from structured fields so mocked
fixtures pin exact verdicts, enforces the cost cap with a short-circuit before further
spend, and applies the V5_PLAN §B bias mitigations (seeded expert-order shuffle,
identity-stripping before synthesis, "penalize length / do not infer missing facts") as
*verifiable* behaviors. Prompt templates live in `panel/prompts/*.md`. Gate is
MOCKED-provider only; no new runtime dependency; nothing outside the file plan changes.

## File plan
- **NEW** `panel/orchestrator.py` — `run_plan(...)` and `run_review(...)` returning a
  `panel_verdict` dict; parallel dispatch, synthesis/arbiter, cost metering, verdict
  derivation, bias mitigations, template loading.
- **NEW** `panel/prompts/plan_aggregate.md` — PLAN aggregator-synthesizer template.
- **NEW** `panel/prompts/review_arbiter.md` — REVIEW arbiter template (disputed only).
- **NEW** `panel/prompts/expert_plan.md` — per-expert PLAN prompt (templated for the
  identity-strip + token-assert criteria; not inlined).
- **NEW** `panel/prompts/expert_review.md` — per-expert REVIEW prompt.
- **NEW** `tests/panel/test_orchestrator_plan.py`, `test_orchestrator_review.py`,
  `test_orchestrator_common.py` (cost/cap/partial-failure/ordering/no-network/lint round-trip).
- **NEW** `tests/panel/fixtures/` additions (canned expert JSON payloads).
- **NO edits** to: `panel/schema/panel_verdict.schema.json`, `.claude/hooks/verdict_lint.py`,
  `gate.sh`, `panel/adapters.py`, `panel/cost_meter.py`, `panel/safe_retry.py`,
  `panel/errors.py`, `panel/prices.py`, `pyproject.toml`, `conftest.py`. If any appears to
  *need* a change, STOP and escalate — out of scope for Wave 3.
- **Do NOT** add `__init__.py` under `tests/panel/` (known landmine — shadows real `panel/`).

## Acceptance criteria
1. `run_plan`/`run_review` accept an injected `call_model`-shaped callable (default
   `panel.adapters.call_model`); tests inject a fake so no test reaches the network. A
   no-network tripwire (patch `socket.socket.connect` + `urllib.request.urlopen` to raise)
   runs a full orchestration and still succeeds. *(machine)*
2. Parallel dispatch: with N experts the injected callable is invoked exactly N times for
   experts (+1 synthesizer for PLAN; +1 arbiter for REVIEW **only when** ≥1 disputed
   finding, else 0). Assert exact counts. Uses `concurrent.futures.ThreadPoolExecutor`. *(machine)*
3. Each expert call is routed through `call_with_retry` (transient-then-success fake
   retries; terminal fake propagates without retry). *(machine)*
4. The returned dict validates against the schema AND, written to a temp file and passed to
   `.claude/hooks/verdict_lint.py` via subprocess (the `run_lint` pattern), exits with the
   derived-verdict-correct code: PASS→0, FAIL→1, REVISE→2, cap-breach→2. Asserted for all
   four cases. *(machine)*
5. PLAN aggregate shape: `gate=="plan"`; `expert_opinions` one entry per surviving expert
   (`model`, `summary`, `confidence`); `disagreement_summary` populated; `synthesis.synthesizer`
   == configured synth slug; `synthesis.artifact` a non-null merged-plan string. *(machine)*
6. REVIEW union shape: `gate=="review"`; `synthesis.artifact` is `null`; `synthesis.findings`
   is the deduped union with stable ordering (crit 12), each carrying `severity`,
   `source_models`, `disputed`, `arbiter_ruling` (`upheld|rejected` for arbitrated disputes,
   else `null`). *(machine)*
7. Verdict derivation deterministic from structured fields (rule below); fixture-pinned:
   critical→FAIL, major-only→REVISE, minor/none→PASS; identical fixtures → identical verdict
   every run (no model free-text consulted). *(machine)*
8. Cost: `cost_usd_total == CostMeter.total` summed over every call (experts + synth +
   arbiter). Exact equality vs. fake results. *(machine)*
9. Cap short-circuit: cap checked **after experts, before synth/arbiter**. If experts alone
   breach, return immediately with `cost_cap_breached=true`, `synthesis.artifact=null`
   (PLAN)/empty findings (REVIEW), verdict per rule, and **no** synth/arbiter call (assert
   fake not called). Dict validates, lints to exit 2. *(machine)*
10. Seeded shuffle determinism: fixed `seed` → identical dispatch/synth-payload order across
    runs; different seeds may differ. *(machine)*
11. Identity-stripping: the payload sent to synthesizer/arbiter (captured from the fake)
    contains **no** lineup model slug (`gpt-5.5`, `fable`, `deepseek`, `opus`, `anthropic/`,
    `openai/`); experts labeled anonymously ("Expert A/B/C"). Substring-scan the serialized
    synth request. (Slugs still appear in the output dict's `expert_opinions[].model` /
    `synthesis.synthesizer` — those aren't sent back into a model.) *(machine)*
12. Deterministic REVIEW dedup/union: findings deduped by a stable key, `source_models`
    sorted, emitted sorted by `(severity_rank, key)`; identical inputs → byte-identical order. *(machine)*
13. Prompt templates loaded from `panel/prompts/*.md` (not inlined); a distinctive token per
    file (e.g. `do not infer missing facts` in the aggregator; `adjudicate only disputed` or
    equivalent in the arbiter) appears in the constructed request. *(machine)*
14. Partial failure: survivors = experts returning parseable results. Proceed **iff ≥2
    survive**, recording each dropped expert as a `blind_spots` note. If <2 survive, return a
    structured-failure verdict (`verdict="REVISE"`, schema-valid, ≥1 opinion, `artifact=null`,
    rationale, no synth/arbiter call). Assert both branches. *(machine)*
15. Wave 1 + Wave 2 regression: full `python -m pytest` stays green; no existing test
    modified; the schema↔validator drift tripwire still passes. *(machine + human)*

## Verification commands
```bash
python -m pytest                       # loop-3 gate (addopts: -q -m 'not live' --import-mode=importlib); zero network
python -m pytest -q tests/panel/test_orchestrator_plan.py tests/panel/test_orchestrator_review.py
grep -ri "ANTHROPIC_API_KEY" panel/ tests/    # expect no matches
```

## Out of scope
Writing `panel_verdict.json` to a hardcoded state path (Wave 4); reading any `PANEL_*` key /
`agent.config` (Wave 4 — lineup/synth/arbiter/cap/seed are function args with defaults);
CLI/MCP (Wave 4); triggering policy + review-size gating + caching/provider-pin tuning; any
new live/paid call; edits to schema, `verdict_lint.py`, `gate.sh`, or Wave 2 modules; dashboard (Wave 5).

## Tier assignment
IMPLEMENTER (Sonnet) — whole wave is judgment work (aggregation/union semantics, verdict
derivation, bias-mitigation seams, prompt authoring). **No BULK slice** (prompt templates
require judgment to match V5_PLAN §B language). REVIEWER (Opus 4.8) verifies all criteria,
special scrutiny on 6/9/10/11/14; escalates aggregation-semantics or path-ownership ambiguity
to PLANNER.

## Loop budget
`MAX_IMPL_ATTEMPTS=3`, `MAX_REVIEW_CYCLES=2` (unchanged). If the two-mode orchestrator shows
it needs splitting, escalate a spec-sizing concern rather than request more attempts.

## Checkpoints
1. Prompt templates + loader helper; token-presence tests (13).
2. Expert fan-out (ThreadPoolExecutor + call_with_retry), seeded shuffle, submission-order
   collection; tests 2, 3, 10.
3. PLAN aggregator synthesis + identity-strip + expert_opinions/disagreement_summary; tests 5, 11.
4. REVIEW union+dedup+arbiter-on-disputed; tests 6, 12.
5. Verdict derivation + cost metering + cap short-circuit + partial-failure; tests 7, 8, 9, 14.
6. Schema + verdict_lint round-trip (4) + full regression (15); final commit.

## Risks
- **R1 non-deterministic verdict** from trusting model free-text → verdict *derived* from
  structured fields; fixtures pin it (7).
- **R2 model identity leaks into synthesis** (family-bias) → anonymized labels + substring
  scan on the actual synth payload (11).
- **R3 non-reproducible ordering** under parallel completion → fixed ordering pipeline (dec f);
  seeded determinism test (10).
- **R4 cost undercount / overspend** → `cost_usd_total==CostMeter.total` (8); cap checked
  after experts, before synth, short-circuits (9); CostMeter raises on no-cost-no-price.
- **R5 schema/lint drift** → round-trip through the real `verdict_lint.py` for all classes (4).
- **R6 1-opinion "panel"** slips `minItems=1` → ≥2-survivor threshold or structured failure (14).
- **R7 arbiter budget blowout** → arbiter called at most once, only when ≥1 disputed (dec d, crit 2).
- **R8 hidden network** → injected fake `call_model` + no-network tripwire over a full run (1).
- **R9 import-mode fragility** → no `__init__.py` under `tests/panel/`; rely on importlib mode.
- **R10 executor swallows an exception** → collect via `future.result()` in try/except per
  future; explicit survivor/failed branch (14).

## Resolved design decisions
- **(a) Concurrency = stdlib `ThreadPoolExecutor` over sync `call_model`.** I/O-bound fan-out,
  real parallelism, ZERO new dep; keeps the satellite stdlib-only through Wave 3. I decline
  asyncio+httpx. Testable: orchestrator imports no third-party module.
- **(b) Verdict DERIVED deterministically per gate.**
  - **PLAN:** `FAIL` if any `synthesis.findings[].severity=="critical"`; else `REVISE` if any
    `major` **or** `disagreement_summary.contradictions` non-empty; else `PASS`.
  - **REVIEW:** consider findings not `disputed`, or disputed with `arbiter_ruling=="upheld"`
    (rejected disputes drop). `FAIL` if any is critical; else `REVISE` if any major; else `PASS`.
  - Cap-breach overrides only exit-code routing (lints to 2 via `cost_cap_breached`).
- **(c) Orchestrator RETURNS the dict; writes no file.** No `output_path` kwarg in Wave 3
  (hardcoded state path is Wave 4). Keeps it stateless so safe_retry's "always safe" holds.
- **(d) Dispute = conflicting reviewer positions** on the same normalized issue key (different
  severities, or one raises / another contradicts). Identical-severity agreement is NOT
  disputed. Arbiter receives only the disputed subset, returns `upheld|rejected`.
- **(e) Request `response_format` json_schema from experts + synth, but VALIDATE returned JSON
  locally** (unparseable → treated as a failed expert, feeding partial-failure). No
  `provider.require_parameters` in Wave 3.
- **(f) Ordering pipeline:** stable lineup → seeded `random.Random(seed).shuffle` (the
  mitigation shuffle) → submit in shuffled order retaining index → **collect by submission
  index, not completion order**. Reproducible regardless of which call finishes first.
- **(g) Partial failure:** proceed iff ≥2 experts survive (note dropped ones in `blind_spots`);
  else structured-failure `REVISE` (schema-valid, ≥1 opinion, artifact null, rationale, no
  synth/arbiter). A 1-opinion panel isn't a panel; REVISE routes to a human (lint exit 2).
- **Mocked seam:** `call_model` is an injectable parameter (mirrors Wave 2's injectable
  transport); fakes return canned `ModelResult`s / raise canned `PanelError`s and record requests.
- **Cost equality & cap timing:** every result → one `CostMeter`; cap checked once, after
  experts, before synth/arbiter.
- **Dedup determinism:** dedup by `(normalized_issue_text, file, line)`, `source_models`
  sorted, emit sorted by `(severity_rank, key)` with critical<major<minor.

## Decisions needing Joe's ratification
- **J1 — PLAN: unresolved contradictions force REVISE.** *Recommended: yes* (a plan the
  experts still contradict isn't trustworthy-final). Flip to severity-only if you'd rather
  contradictions be advisory.
- **J2 — Partial-failure survivor threshold = 2.** *Recommended: require ≥2* (a 1-opinion
  panel isn't a panel), vs. honoring the schema's literal `minItems=1`.
- **J3 — Default test lineup:** PLAN experts `deepseek-v4-pro` + `gpt-5.5`, synth `opus-4.8`;
  REVIEW reviewers `opus-4.8` + `gpt-5.5`, arbiter `fable-5` (V5_PLAN §B cheap/mid; all in
  `prices.py`). Test-facing args only. *Recommended: as listed.*
- **J4 — Synth also uses `response_format`** (artifact carried as a JSON string field). vs.
  free-form prose artifact. *Recommended: structured for both.*
