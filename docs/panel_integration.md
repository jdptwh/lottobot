# Panel invocation — end-to-end flow (ROUTING.md Rule 12)

How the routed agent system actually **invokes** the panel satellite at the PLAN and
REVIEW gates. The satellite is a tool the lead/PLANNER/REVIEWER call *between* the two
human touchpoints; it advises, it never becomes the verdict of record, and it does
nothing at all while `PANEL_ENABLED=0` (the default).

> `panel_plan` / `panel_review` in the docs are shorthand for the CLI subcommands
> `python -m panel.cli plan` / `python -m panel.cli review` — **CLI today, MCP later.**

## When it runs (the trigger, evaluated PANEL_ENABLED first)
| `PANEL_ENABLED` | `PANEL_TRIGGER` | Panel runs when… |
|---|---|---|
| `0` | any | **Never** — pure v4 no-op. Nothing auto-runs. |
| `1` | `always` | every PLAN gate (PLANNER) and every REVIEW gate (REVIEWER) — still opt-in per invocation |
| `1` | `novelty` | PLAN: the **PLANNER judges the task novel** (novel architecture / high blast radius — pure judgment). REVIEW: budget-exhaustion. *(shipped default)* |
| `1` | `escalation` | **budget-exhaustion only**: a loop hit `MAX_IMPL_ATTEMPTS` or the review loop hit `MAX_REVIEW_CYCLES` |

The trigger **authorizes** an invocation; the role still decides per call (protects the
top-tier budget, Rule 8). Novelty is PLANNER judgment; `escalation` is mechanical (the two
budget counters in `.claude/agent.config`).

## PLAN gate — how the PLANNER invokes `panel_plan`
1. The PLANNER writes the draft spec + task context to a **gitignored** prompt file
   (`.claude/state/*.json` is already ignored):
   ```bash
   #  (planner has Bash) — write the prompt, then call the panel
   PID="wave7-newthing"
   printf '%s' "$DRAFT_SPEC_AND_CONTEXT" > .claude/state/panel_prompt_${PID}.json
   python -m panel.cli plan --task-id "$PID" --prompt-file .claude/state/panel_prompt_${PID}.json
   #  binary artifacts (approved mockups, design PDFs, screenshots) go via --attach
   #  (repeatable; experts only): --attach docs/mockups/dashboard_mockup.png --attach spec.pdf
   ```
2. The CLI (if `PANEL_ENABLED=1`) fans the task out to the PLAN lineup, synthesizes, meters
   cost against `PANEL_MAX_COST_USD`, and writes `PANEL_VERDICT_PATH`
   (`.claude/state/panel_verdict.json`). Exit code: `0`=PASS, `1`=FAIL, `2`=REVISE **or**
   `cost_cap_breached`, `3`=malformed. If `PANEL_ENABLED=0` it prints "disabled" and exits 0
   without doing anything.
3. The PLANNER reads `panel_verdict.json` — `synthesis.artifact` (the merged plan),
   `disagreement_summary` (consensus / contradictions / blind spots), `synthesis.findings`.
   It **edits the good parts into the final spec** and discards the rest. The PLANNER remains
   author of record; the panel advised.
4. The human still approves the final spec (touchpoint 1). Unchanged.

## REVIEW gate — how the REVIEWER invokes `panel_review`
1. Triggered on budget-exhaustion (`review_cycle` reached `MAX_REVIEW_CYCLES`) or a
   PLANNER-flagged high-blast-radius change. The REVIEWER (has Bash) captures the diff:
   ```bash
   PID="wave7-newthing-review"
   git diff > .claude/state/panel_prompt_${PID}.json    # or pipe via -  (stdin)
   python -m panel.cli review --task-id "$PID" --prompt-file .claude/state/panel_prompt_${PID}.json
   #  UI changes review better with evidence: --attach the before/after screenshots
   ```
2. The panel produces a union of independent findings + arbiter rulings in
   `panel_verdict.json`. The REVIEWER **folds those findings into its own** `verdict.json`
   `findings[]` (the schema is unchanged — no new fields). The panel is a second opinion; the
   reviewer's single machine-validated `verdict.json` is still the verdict of record.
3. `gate.sh` GATE 4 independently lints `panel_verdict.json` if present; any non-zero blocks
   the stop, so a FAIL/REVISE/cost-capped panel verdict cannot be silently passed.

## Exit 2 (REVISE / cost_cap_breached) → hard stop to the human (Rule 5)
A panel exit of `2` — REVISE, or the run hit `PANEL_MAX_COST_USD` — is treated exactly like a
budget-exhaustion escalation under **Rule 5**: the lead surfaces it to the human and does
**not** auto-accept, auto-retry, or proceed as if the panel passed. `gate.sh` GATE 4 already
enforces this at the machine floor (non-zero blocks the stop).

## Cost & safety
- Every invocation is cost-capped by `PANEL_MAX_COST_USD`; a breach forces the human path.
- The panel calls **OpenRouter only** (reads `OPENROUTER_API_KEY` from `.env`/env). The lead
  stays interactive/subscription-authenticated — **never export `ANTHROPIC_API_KEY`** in the
  lead's environment (the `claude -p` metering footgun, V5_PLAN Key Finding 5).
- Two human touchpoints are unchanged: approve the spec (PLAN), accept the result (REVIEW).

## Enabling it
Set `PANEL_ENABLED=1` (dashboard Config tab or `.claude/agent.config`) and configure
`OPENROUTER_API_KEY` (`python scripts/setup.py`). Prove the wire path with
`python -m pytest -q -m live` (~1¢) first. See `docs/RUNBOOK.md` for the full checklist.
