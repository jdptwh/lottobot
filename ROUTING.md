# ROUTING.md — Model Routing Doctrine

Drop this in the repo root. CLAUDE.md references it; the lead agent follows it.
It is model-agnostic: it defines ROLES and a routing discipline. The specific
models filling each role are set per install (see Tier Lineup) based on what your
plan supports.

## Tier Lineup (set at install; substitute per your plan)

| Role         | Purpose                                  | Full lineup      | If no top tier | If Sonnet-only |
|--------------|------------------------------------------|------------------|----------------|----------------|
| PLANNER      | Spec authority + escalation arbiter      | Fable / top Opus | Opus           | Sonnet         |
| SPEC-DRAFTER | Cheap first-draft of the spec            | Sonnet           | Sonnet         | (skip)         |
| IMPLEMENTER  | Judgment work — code, docs, artifacts    | Sonnet           | Sonnet         | Sonnet         |
| REVIEWER     | Senior review over the implementer       | Opus             | Opus / Sonnet  | Sonnet         |
| BULK         | Machine-verifiable grunt work            | Haiku            | Haiku          | Haiku          |

The ROLES never change. Only the model strings in the agent files change. If your
plan lacks a premium tier, substitute down — the method still holds, it just runs
with less headroom. On a Sonnet-only plan the drafter collapses into the planner
(no point drafting cheaply for a same-tier reviewer) and review becomes peer-level;
the machine gates and the human arbiter carry correctness in that case.

## The Four Loops

1. **PLAN** — SPEC-DRAFTER drafts the spec from the template → PLANNER reviews,
   corrects, and OWNS the final spec (or authors directly if no drafter). Human
   approves the spec. *Draft-then-review exists to spend the expensive planner on
   correction, not verbose authoring — its cost is dominated by output tokens.*
   *When the panel is enabled and triggered (Rule 12), the PLANNER invokes `panel_plan`
   here and edits the returned synthesis into the spec — the panel advises, planner owns.*
2. **IMPLEMENT** — IMPLEMENTER does judgment work; BULK takes machine-verifiable
   slices per the spec's tier assignments.
3. **VERIFY** — the hooks run the verification surface (build/tests/lint/UI/
   validator) on every completion. This is DETERMINISTIC, not a model. It runs
   underneath every tier, every loop. Failures bounce back automatically.
4. **REVIEW** — REVIEWER (senior, over the implementer) returns PASS/FAIL →
   escalates hard calls to PLANNER (the appeals court: architecture, second
   failures, unreadable correctness) → then the HUMAN is the true final arbiter
   (hands-on testing / judgment), non-negotiable for any interactive work.
   *When enabled and triggered (Rule 12), the REVIEWER invokes `panel_review` and folds
   its union+arbiter findings into the verdict; `gate.sh` GATE 4 lints the panel verdict.*

The human has exactly two mandatory touchpoints: approve the SPEC (loop 1), accept
the final result (loop 4). Everything between runs hands-off.

## Rule 1 — Route by VERIFIABILITY, not difficulty

Before assigning a task ask: **"If this is wrong, what catches it?"**
- A machine catches it instantly (compiler, tests, linter, schema, validator,
  template diff) → BULK is allowed.
- A model/human must read carefully to catch it (logic, integration, architecture,
  structure — any judgment) → IMPLEMENTER minimum.
- Nothing downstream catches it and blast radius is large → escalate to PLANNER.

Cheap tiers on hard-to-verify work is the failure mode. Never do it.

## Rule 2 — The verification surface is the precondition for everything

Verifiability-based routing only works if a real machine gate EXISTS for this
project. That gate takes the form appropriate to the artifact:
- Code → unit/integration tests
- Documents (bibles, SOPs, screenplays) → structure/reference validator
- Data → schema/shape validation
- Frontend/UI → build + lint + UI smoke
- No machine-checkable surface possible → reviewer-only path, explicitly flagged;
  an inadequate verification surface is a DEFECT, not a steady state.

The surface is established at install and grown per task. Any task producing a new
artifact type must confirm its surface exists or spec its creation first.

## Rule 3 — PLANNER touches a task in exactly these cases

Plan finalization (loop 1), and escalation arbitration (loop 4). Never routine
review, never implementation, never boilerplate. The PLANNER is the scarcest,
most capable tier — protect it. Draft-then-review and event-driven escalation are
both here to keep PLANNER usage minimal without losing its judgment.

## Rule 4 — Spec quality is the first-pass lever

Every final spec is executable, not a vibe: file-level plan, concrete acceptance
criteria, out-of-scope, and the exact verification commands. The implementer
executes; it does not reinterpret. Ambiguous spec → implementer stops and asks.

## Rule 5 — Escalation, de-escalation, and loop budgets

- BULK fails once → retry with the error attached (MAX_BULK_RETRIES). Fails
  again → IMPLEMENTER.
- IMPLEMENTER fails twice on the same task → PLANNER (with full failure context).
- Never re-run the same tier, same prompt, expecting a different result.
- After a PLANNER fix, write the corrected pattern into CLAUDE.md's landmines so
  the failure class can't recur.
- **Loop budgets are hard stop conditions** (`.claude/agent.config`):
  MAX_IMPL_ATTEMPTS caps implementer attempts per task; MAX_REVIEW_CYCLES caps
  implement→review cycles before a mandatory hard stop to the human. Budgets
  bound the autonomy contract — an autonomous loop that can thrash indefinitely
  is not autonomous, it is unsupervised. Budget exhaustion escalates to the
  PLANNER as a spec-sizing problem, never as a request for more attempts.

## Rule 6 — Context hygiene (the silent budget killer)

- `/clear` between unrelated tasks — the whole conversation is resent every turn.
- Keep CLAUDE.md and ROUTING.md LEAN — they are fixed overhead on every message.
- One task per dispatch. No "and also" riders.

## Rule 7 — UI work gets the third gate

Any task with UI acceptance criteria passes build/tests → lint → UI smoke (real
click-through, element presence, zero console errors) before PASS. Missing smoke
coverage on a UI task is a spec defect — the planner adds the test. UI tasks are ALSO
governed by Rule 11 (an approved mockup precedes buildout; a polish audit precedes
presentation).

## Rule 8 — Model economics (why the structure is shaped this way)

On subscription plans the top tier is capped (often a hard fraction of weekly
usage) and everything shares one pool. Two consequences drive this doctrine:
- The top tier (PLANNER) is your genuinely scarce resource; tiers below it are
  comparatively abundant. Spend the scarce one only where its judgment is
  irreplaceable — planning and appeals.
- Frontier cost is dominated by OUTPUT tokens. Draft-then-review cuts the
  planner's output (it edits instead of authoring), which is the single highest-
  leverage way to stretch a capped top tier.
REVIEWER on a strong non-top tier (e.g. Opus, drawn from the abundant pool) buys
senior review quality without touching the scarce PLANNER budget. Verify your own
plan's buckets with `/usage`; substitute the lineup accordingly.

## Rule 9 — Resume, never replay (side-effect safety)

Agent work has side effects: file edits, commits, generated artifacts. A failed
or interrupted loop is therefore NEVER retried by re-running the original prompt
— replay double-executes side effects and corrupts state. Instead:

- Every spec declares CHECKPOINTS — commit boundaries that are safe resume points.
- On any interruption or failure, recovery starts with STATE INSPECTION
  (`git status` / `git diff` / `git log`), then continues from what exists on
  disk toward the remaining acceptance criteria.
- If state is ambiguous (uncommitted partial work of unclear intent), roll back
  to the last checkpoint commit and resume from there. Git is the undo — this is
  why `git init` is the mandatory first task of any repo running this system.
- Pure read-only work (drafting, review, analysis) has no side effects and may
  be freely re-run.

## Rule 10 — One source of truth for configuration

All gate commands, loop budgets, and the model lineup live in
`.claude/agent.config`. gate.sh sources it; CLAUDE.md and specs reference it;
nothing duplicates it. Layering, highest precedence first:

1. **Environment variable** — per-session override (`CLAUDE_VERIFY_CMD=… claude`)
2. **`.claude/agent.config`** — the repo's committed configuration
3. **Built-in default** — empty gate slots are skipped; budgets default 3/2/1

If two places ever disagree about a gate command, agent.config wins and the
other place is a bug to fix.

## Rule 11 — UI tasks require an approved mockup before buildout

Any task that produces or changes a user interface MUST ship a static HTML **mockup**,
approved by the human, BEFORE implementation starts — and must pass a **polish audit**
against that mockup BEFORE it is presented for acceptance. This inserts a UI loop and a
third human touchpoint (approve the mockup) between spec approval and buildout:

`spec approved → MOCKUP built (docs/mockups/<screen>_mockup.html) → HUMAN approves the
mockup → implement to match → POLISH AUDIT vs. the mockup → review → human accepts.`

The approved mockup is the acceptance target: the built UI is not "done" until the polish
audit confirms parity (layout, states, hierarchy, affordances, copy, constraint compliance).
Deviations from an approved mockup need the human's ok. The mockup must be designed against
high-end, DOMAIN-RELEVANT references and must NOT ship the generic AI-dashboard look (a flat
grid of same-size dark cards, one indigo accent, no real data viz, no identity) — it carries
cited design notes so the audit can check reference fidelity and distinctiveness. It must also
adopt the reference's LAYOUT/INTERACTION paradigm (compact single-view, tabs/segments, visual
controls) — reskinning the prior layout with new colours is an explicit fail. Full rubric
and the mockup quality bar: `docs/ui_mockup_protocol.md`. Non-UI tasks are unaffected.

## Rule 12 — Panel invocation at the gates

The panel satellite is a tool the routed system CALLS at the PLAN and REVIEW gates (it does
not replace them). Invocation is the literal Bash CLI:
`python -m panel.cli plan|review --task-id <ID> --prompt-file <FILE>` — shorthand `panel_plan`
/ `panel_review`.[^cli] It is gated on `PANEL_ENABLED` FIRST, then `PANEL_TRIGGER`:

| `PANEL_ENABLED` | `PANEL_TRIGGER` | Panel runs when… |
|---|---|---|
| `0` | any | **Never** — pure v4 no-op (default; nothing auto-runs) |
| `1` | `always` | every PLAN gate + every REVIEW gate (still opt-in per invocation) |
| `1` | `novelty` | PLAN: PLANNER judges the task **novel** (novel architecture / high blast radius — pure judgment). REVIEW: budget-exhaustion. *(shipped default)* |
| `1` | `escalation` | budget-exhaustion only (`MAX_IMPL_ATTEMPTS` / `MAX_REVIEW_CYCLES` hit) |

- **PLAN:** the PLANNER writes the draft spec/context to a gitignored `.claude/state/panel_prompt_<id>.json`,
  runs `panel_plan`, reads `panel_verdict.json` (synthesis artifact + disagreement + findings),
  and EDITS it into the final spec. The panel advises; the PLANNER is author of record; the
  human still approves the spec.
- **REVIEW:** on budget-exhaustion or a PLANNER-flagged high-blast-radius change, the REVIEWER
  runs `panel_review` over the `git diff` and folds the union+arbiter findings into its own
  `verdict.json` (schema unchanged). The panel is a second opinion, never the verdict of record.
- **Exit codes:** `0`=PASS, `1`=FAIL, `2`=REVISE **or** `cost_cap_breached`, `3`=malformed. A
  `2` is a **hard stop to the human via Rule 5** — never auto-accepted, never silently retried.
  `gate.sh` GATE 4 blocks the stop on a **fresh** non-PASS panel verdict. Because the panel
  *advises* (it is never the verdict of record), that block is released once the REVIEWER records
  its verdict of record (`VERDICT_PATH`, written after folding in the panel's findings): a panel
  verdict older than the reviewer verdict is *consumed* and only warns. This keeps the hard-stop
  teeth while ensuring a single stale verdict cannot wedge every future stop. Ad-hoc/audit panel
  runs should archive their verdict after reading (or use a non-default `PANEL_VERDICT_PATH`).
- **Guarantees:** the two human touchpoints are unchanged (approve spec, accept result); every
  call is cost-capped by `PANEL_MAX_COST_USD`; the panel calls OpenRouter only — never export
  `ANTHROPIC_API_KEY` in the lead's environment (Rule 8 economics / the metering footgun).

Full flow, prompt-file convention, and a worked example: `docs/panel_integration.md`.

[^cli]: `panel_plan`/`panel_review` = the `panel.cli plan`/`review` subcommands — CLI today, MCP later.

## Rule 13 — Visual assets go through asset-forge

When an approved spec calls for a visual asset (UI graphic, icon, illustration,
placeholder art), the IMPLEMENTER creates it with the **asset-forge** skill
(`.claude/skills/asset-forge/` — Atlas Cloud MCP generation + cross-family QA judge
+ bounded loop), never by hand-prompting an image model ad hoc. Gated on
`ASSET_ENABLED` (default `0` — dormant, like the panel). Non-negotiables
(docs/specs/asset_pipeline_spec.md, approved 2026-07-09):

- **Explicit acceptance criteria before generating** — the judge scores only what
  the contract states; an asset without criteria cannot be QA'd and doesn't ship.
- **Cross-family judging** — enforced by `panel.asset_qa`; never worked around.
- **Bounded loop** — `ASSET_MAX_ATTEMPTS` / `ASSET_MAX_COST_USD`; an EXHAUSTED loop
  escalates to `panel_review` (best candidate `--attach`ed) then the human (Rule 5
  hard stop). Never auto-accept, never wire an unapproved asset into UI.
- **Provenance** — every shipped asset has its `<asset>.forge.json` sidecar.
- **Video** — same loop with the `ASSET_VIDEO_*` knobs (model / cost cap / QA
  frames); QA is frame-sampled and VISUAL-TRACK ONLY — audio criteria fail closed
  and are flagged for the human's ears.
- Rule 11 is unchanged: assets inside a UI still ship under an approved mockup.

## Gate Checklist (REVIEWER verifies before PASS)

1. Verification commands run green (re-run, don't trust the report).
2. Every acceptance criterion explicitly satisfied.
3. No changes outside the spec's file list.
4. No unauthorized dependencies.
5. Diff is readable — if the reviewer can't follow it, it fails on that alone.
6. Panel (Rule 12): if a `panel_verdict.json` is present it lints clean via `gate.sh` GATE 4;
   a REVISE/cost-capped panel verdict is a hard stop to the human, not an auto-pass.
7. UI tasks only (Rule 11): the polish audit passed — the built UI matches the approved
   `docs/mockups/*` mockup on layout, states, hierarchy, affordances, copy, and constraints.

Verdict (v4): structured JSON written to `.claude/state/verdict.json` and
validated by `python3 .claude/hooks/verdict_lint.py` (exit 0 = well-formed,
1 = missing, 2 = malformed). The lead branches on validated fields —
`verdict`, `escalate`, `review_cycle` — never on prose. A verdict that fails
validation is not a verdict; the reviewer re-emits it. The reviewer never
fixes anything; the lead decides what to apply.
