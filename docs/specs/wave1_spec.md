# SPEC: Wave 1 — panel verdict schema + verdict_lint panel branch + gate.sh branch

> Status: **AWAITING JOE'S APPROVAL** (touchpoint 1 of 2). Drafted by spec-drafter
> (Sonnet), finalized and owned by planner (Opus 4.8). Do not implement until approved.
> Model IDs/prices in fixtures come from `docs/openrouter_models_verified_2026-07-07.md`
> (verified live), not V5_PLAN.md's baseline.

## Objective
Extend the v4 verdict contract to recognize a panel-emitted verdict (`panel_verdict.json`,
`"source":"panel"`) without disturbing the existing reviewer verdict path. Three
deliverables: (1) a JSON Schema file documenting the panel verdict shape; (2) a
`"source"`-dispatched branch in `verdict_lint.py` that validates panel verdicts using
stdlib only and maps their `verdict`/`cost_cap_breached` fields to a defined exit-code
contract; (3) a `gate.sh` branch that discovers and lints `panel_verdict.json` when
present. No API calls, no new runtime deps, no `PANEL_*` config keys (those are Wave 4).
The v4 reviewer path must remain byte-for-byte behaviorally identical.

## File plan
- **NEW** `panel/schema/panel_verdict.schema.json` — JSON Schema (draft 2020-12).
  Documentation + single source of truth for required keys/enums the validator mirrors.
  `"source":"panel"` const, `gate` enum, `verdict` enum (`PASS|FAIL|REVISE`),
  `synthesis.artifact` nullable, both aggregate and review shapes.
- **NEW** `tests/panel/__init__.py` — empty package marker (clean pytest collection).
- **NEW** `tests/panel/test_panel_verdict_lint.py` — fixture-driven tests for the panel branch.
- **NEW** `tests/panel/fixtures/plan_pass.json` — plan-gate: `gate:"plan"`, `verdict:"PASS"`,
  non-null `synthesis.artifact`, `expert_opinions` with OpenRouter dotted slugs.
- **NEW** `tests/panel/fixtures/review_pass.json` — review-gate: `gate:"review"`,
  `synthesis.artifact:null`, `synthesis.findings` with `arbiter_ruling` values.
- **NEW** `tests/panel/fixtures/plan_revise.json` — `verdict:"REVISE"` → exit 2.
- **NEW** `tests/panel/fixtures/plan_fail.json` — `verdict:"FAIL"` → exit 1 (verifies criterion 5's FAIL mapping; added per reviewer nit).
- **NEW** `tests/panel/fixtures/cost_cap_breached.json` — `verdict:"PASS"` + `cost_cap_breached:true` → exit 2.
- **NEW** `tests/panel/fixtures/malformed_panel.json` — `"source":"panel"` with a required key wrong/missing → exit 3.
- **MODIFY** `.claude/hooks/verdict_lint.py` — add top-level `"source"` dispatch: absent or
  `!= "panel"` → existing v4 path unchanged; `== "panel"` → new `validate_panel()`. Update
  docstring exit-code table. No change to any v4 code path's behavior or exit values.
- **MODIFY** `.claude/hooks/gate.sh` — after the existing gates, if
  `.claude/state/panel_verdict.json` exists, run `verdict_lint.py` against it; treat
  non-zero as a block (exit 2).

**Do NOT touch:** `.claude/agent.config` (no `PANEL_*` keys — Wave 4), `ROUTING.md`,
`V5_PLAN.md`, any `panel/*.py` module (Waves 2–3), the PLANNER subagent frontmatter
(Wave 4), `tests/test_harness_smoke.py` (regression floor — must pass unchanged).
`CLAUDE.md` "Current state" update is the one allowed edit (Definition of Done), not a
file-plan item.

## Acceptance criteria
1. `python -m pytest -q` passes with zero failures from repo root, including the
   pre-existing `tests/test_harness_smoke.py` unchanged (its 4 v4 tests still green). *(machine)*
2. A v4 reviewer verdict with **no `"source"` key** (the exact dict in
   `test_harness_smoke.py::test_valid_pass_verdict_exits_0`) still exits **0**; a v4 verdict
   with `verdict:"MAYBE"` still exits **2**; a missing v4 file still exits **1**. The v4
   dispatch is selected whenever `"source"` is absent OR `!= "panel"`. *(machine — pinned by a test)*
3. `panel/schema/panel_verdict.schema.json` is valid JSON, a JSON-Schema object with
   `"$schema"` = draft 2020-12, declaring `source` const `"panel"`, `gate` enum
   `["plan","review"]`, `verdict` enum `["PASS","FAIL","REVISE"]`, and `synthesis.artifact`
   as `type:["string","null"]`. *(machine)*
4. For `"source":"panel"` verdicts the linter validates (stdlib only, no `jsonschema`):
   top-level object; `source=="panel"`; `schema_version` str; `gate in {plan,review}`;
   `task_id` str; `verdict in {PASS,FAIL,REVISE}`; `cost_cap_breached` bool; `cost_usd_total`
   number; `expert_opinions` a non-empty list of objects each with `model` (str), `summary`
   (str), `confidence` (number); `synthesis` an object with `synthesizer` (str) and `artifact`
   (str or null); if `synthesis.findings` present, a list of objects each with
   `severity in {critical,major,minor}` and `arbiter_ruling in {upheld,rejected,null}`.
   Missing/mistyped required field → `[verdict_lint] FAIL:` on stderr, exit **3**. *(machine)*
5. Panel **verdict-state → exit-code**: `PASS` & `cost_cap_breached:false` → **0**;
   `FAIL` → **1**; `REVISE` → **2**; `cost_cap_breached:true` (any verdict) → **2**. *(machine)*
6. **Structural errors on the panel path use exit 3; file-missing stays 1.** Malformed
   panel verdict → **3**; missing panel file → **1** (`FileNotFoundError` is source-agnostic —
   the file can't be read to inspect `"source"`). Panel-path exit **2** means *only*
   REVISE/cost-cap, never malformed. Resolves the V5_PLAN.md line-141 collision. *(machine)*
7. `synthesis.artifact` accepts a non-null string (plan mode) and `null` (review mode);
   both fixtures validate to exit 0. `synthesis.findings` + `arbiter_ruling` exercised by
   `review_pass.json`. *(machine)*
8. All fixture `model`/`synthesizer` values use OpenRouter dotted slugs from the verified
   doc (`anthropic/claude-fable-5`, `anthropic/claude-opus-4.8`, `openai/gpt-5.5`,
   `deepseek/deepseek-v4-pro`), never Anthropic-native hyphenated strings. *(machine — `grep 'claude-opus-4-8' tests/panel/fixtures/` returns nothing)*
9. `gate.sh`: with `.claude/state/panel_verdict.json` present, gate.sh runs `verdict_lint.py`
   against it and on non-zero exits 2 (blocking) with a `[gate:panel]` stderr line; with the
   file absent, behavior is byte-for-byte unchanged from v4. Panel lint runs *after* the three
   verification gates and only if `CLAUDE.md` is present (existing opt-in guard). *(human — shell dry-run)*
10. Linter and schema import nothing outside stdlib (`json`, `sys` only in the linter);
    `grep` for `jsonschema`/`requests`/etc. returns nothing; `panel/schema/` holds only the
    `.schema.json`. *(machine)*
11. `verdict_lint.py` docstring documents all four panel codes (0/1/2/3), noting 3=malformed-panel
    is distinct from v4's 2=malformed-v4. *(human)*

## Verification commands
```bash
python -m pytest -q                       # primary gate (agent.config VERIFY_CMD)
python -m pytest -q tests/panel           # targeted panel suite

python .claude/hooks/verdict_lint.py tests/panel/fixtures/plan_pass.json         # expect 0
python .claude/hooks/verdict_lint.py tests/panel/fixtures/review_pass.json       # expect 0
python .claude/hooks/verdict_lint.py tests/panel/fixtures/plan_revise.json       # expect 2
python .claude/hooks/verdict_lint.py tests/panel/fixtures/cost_cap_breached.json # expect 2
python .claude/hooks/verdict_lint.py tests/panel/fixtures/malformed_panel.json   # expect 3
python .claude/hooks/verdict_lint.py /nonexistent/panel_verdict.json             # expect 1

python -c "import json; json.load(open('panel/schema/panel_verdict.schema.json'))"
grep -RnE 'import (jsonschema|requests|yaml|pydantic)' .claude/hooks/verdict_lint.py panel/   # no output
grep -Rn 'claude-opus-4-8' tests/panel/fixtures/                                              # no output
bash .claude/hooks/gate.sh; echo "exit=$?"   # no-panel-file path unchanged
```

## Out of scope
Any `PANEL_*` config keys / `agent.config` edits (Wave 4); the orchestrator, provider
adapters, cost meter, safe_retry, synthesis prompts, CLI/MCP server (Waves 2–4); live or
mocked provider API calls (Waves 2+); repointing/editing the PLANNER subagent (Wave 4);
wiring the lead to *consume* panel_verdict.json; findings dedup/severity-scoring logic
(schema describes shape only).

## Tier assignment
Schema authoring + validator branch + exit-code design + gate.sh branch: **IMPLEMENTER**
(Sonnet). Judgment work — the exit-code collision resolution and the "v4 must not regress"
invariant are hard-to-verify-if-wrong integration concerns (Rule 1). **No BULK slice:** the
fixtures are small and semantically load-bearing (they encode the exit-code contract), so
they stay with the implementer.

## Loop budget
Standard: `MAX_IMPL_ATTEMPTS=3`, `MAX_REVIEW_CYCLES=2` (agent.config unchanged). Exhaustion
escalates to PLANNER as a spec-sizing problem.

## Checkpoints (Rule 9 resume-not-replay)
1. Schema + all fixtures written and parseable → commit "wave1: panel verdict schema + fixtures".
2. `verdict_lint.py` panel branch + panel tests passing → commit "wave1: verdict_lint panel branch".
3. `gate.sh` branch + no-panel-file regression confirmed, full `pytest` green → commit "wave1: gate.sh panel lint branch".

## Risks
- **R1 — Silent v4 regression (highest).** `"source"` dispatch could alter keyless v4 verdicts.
  *Mitigation:* dispatch `v.get("source") == "panel"` → panel; **else fall through to untouched
  v4 code**. Criterion 2 pins it with a test on the exact harness_smoke dict. Do not restructure the v4 block.
- **R2 — Exit-code collision.** v4 owns 1=missing, 2=malformed; plan wanted FAIL→1, REVISE→2.
  *Mitigation:* add **exit 3 = malformed panel**, keep 1 shared for missing-file, reserve panel-2 for REVISE/cost-cap.
- **R3 — Schema/validator drift.** Hand-rolled validator vs. schema file can diverge.
  *Mitigation:* a test reads the schema's `enum`/`const` and asserts equality with the validator's
  hard-coded tuples — a drift tripwire without vendoring `jsonschema`.
- **R4 — gate.sh path discovery vs. Rule 10.** *Mitigation:* hardcode `.claude/state/panel_verdict.json`
  with a `# Wave 4: replace with PANEL_VERDICT_PATH` TODO. Rule 10 governs gate commands/budgets/lineup,
  not internal hook artifact paths (reviewer `VERDICT_PATH` is likewise informational, not read by gate.sh).
- **R5 — Coexistence ambiguity.** *Mitigation:* verdict.json and panel_verdict.json are independent
  channels; gate.sh lints only the panel file (it never linted verdict.json). No precedence contest.
- **R6 — Windows/bash split.** *Mitigation:* gate.sh invokes the linter via `python "$path"` (not the
  `python3` shebang) per the CLAUDE.md landmine; tests use `sys.executable` (interpreter-agnostic).
- **R7 — Fixture slug rot.** *Mitigation:* criterion 8 + the `grep 'claude-opus-4-8'` command.
- **R8 — Empty `expert_opinions`.** A zero-expert panel is degenerate, not a valid PASS.
  *Mitigation:* validator requires `expert_opinions` be non-empty (see ratification #2).

## Resolved design decisions
- **(a) Path + coexistence.** Panel writes `.claude/state/panel_verdict.json`. gate.sh lints it
  only if present, after the three gates. verdict.json and panel_verdict.json are independent;
  gate.sh never touched verdict.json and won't start.
- **(b) Full exit-code mapping:**

  | source × state | exit |
  |---|---|
  | v4 valid | 0 |
  | v4 file missing | 1 |
  | v4 malformed | 2 |
  | panel PASS & !cost_cap | 0 |
  | panel FAIL | 1 |
  | panel REVISE | 2 |
  | panel cost_cap_breached (any verdict) | 2 |
  | panel malformed | **3** |
  | panel file missing | 1 |

  0/1/2 stay identical to V5_PLAN.md line 141 on the panel path; malformed gets its own code (3).
  gate.sh blocks on any non-zero, so 3 costs the gate nothing; the lead distinguishes "re-emit" (3)
  from "needs human/revise" (2). Missing-file stays 1 (source unreadable from an absent file).
- **(c) Validation: hand-rolled stdlib + drift tripwire.** No `jsonschema`. Validator mirrors the v4
  explicit-dict pattern; a test links schema enums to validator tuples (R3).
- **(d) Gate discovery vs. Rule 10.** Hardcode the path now with a Wave-4 TODO. Rule 10 governs gate
  commands/budgets/lineup, not hook artifact paths; adding a `PANEL_*` key is forbidden until Wave 4.
- **(other) `synthesis.artifact` nullable — yes** (review gate produces findings, not an artifact).
- **(other) Both plan- and review-gate fixtures ship** so the schema is exercised on both modes.
- **(other) `"source"` dispatch must not break keyless v4 verdicts — pinned by criterion 2.**

## Decisions needing Joe's ratification
1. **Exit code 3 for malformed-panel** (vs. cramming malformed into 2 and losing the REVISE/malformed
   distinction). *Recommended: adopt exit 3.* Deviates from V5_PLAN.md line 141's literal 0/1/2, but
   line 141 never accounted for structural errors on the panel path — an omission, not a committed design.
2. **Require `expert_opinions` non-empty (≥1).** *Recommended: yes.* A zero-expert panel is a failed run,
   not a valid verdict. The plan's schema left `[]` allowable.
3. **`cost_cap_breached:true` overrides even a PASS to exit 2.** *Recommended: yes.* Matches line 141's
   "REVISE or cost_cap_breached→2"; means a panel can report `verdict:"PASS"` yet still not exit 0.
