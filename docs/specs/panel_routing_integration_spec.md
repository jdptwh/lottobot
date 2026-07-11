# SPEC: Wire panel invocation into the routing (the missing keystone)

> Status: **AWAITING JOE'S APPROVAL**. Drafted by spec-drafter, finalized/owned by planner
> (Opus 4.8). Docs + one config-default flip only — no `panel/` code changes; `PANEL_ENABLED`
> stays `0` (this ADDS capability + doctrine, it ENABLES nothing).

## Objective
Encode *when and how* the routed agent system invokes the panel satellite at the PLAN and
REVIEW gates. The satellite is fully built (Waves 1–5) but no doctrine file ever calls it —
this supplies the missing keystone: a trigger rule gated on `PANEL_ENABLED`, the literal
Bash invocation, the prompt-delivery convention, and PLANNER/REVIEWER role-prompt teaching.

## File plan (exhaustive — these seven files, nothing else)
1. `ROUTING.md` — add **Rule 12 — Panel invocation at the gates** (trigger table + literal
   call + two-touchpoint/cost-cap guarantees; full flow linked out). One-line pointer in The
   Four Loops at loop 1 (PLAN) and loop 4 (REVIEW). Do not rewrite the loops.
2. `.claude/agents/planner.md` — "Panel delegation (PLAN gate)" paragraph in Job 1: when the
   planner judges a task **novel** and `PANEL_ENABLED=1`, it MAY invoke `panel_plan`, read the
   verdict, and OWN the merge (panel advises; planner is author of record; human still approves).
3. `.claude/agents/reviewer.md` — "Panel delegation (REVIEW gate)" paragraph: on budget
   exhaustion (`review_cycle` == `MAX_REVIEW_CYCLES`) or planner-flagged high-blast-radius, and
   `PANEL_ENABLED=1`, the reviewer MAY invoke `panel_review`, fold findings into its own JSON
   verdict, and still emit the single machine-validated `verdict.json` (panel never the verdict of record).
4. `.claude/agent.config` — set `PANEL_ENABLED="1"` → `PANEL_ENABLED="0"` (restore the dormant
   default; the working copy is currently armed). No other config line changes.
5. `docs/panel_integration.md` — NEW: full flow (prompt-file convention, exact Bash commands,
   exit-code handling, one worked novel-task example), so ROUTING.md stays lean (Rule 6).
6. `CLAUDE.md` — one Routing-section line pointing to Rule 12 + `docs/panel_integration.md`;
   update Current state.
7. `tests/test_panel_routing_docs.py` — NEW: minimal token-presence guard (AC-8).

## Acceptance criteria
1. `ROUTING.md` has `## Rule 12 — Panel invocation at the gates` containing the literal
   `python -m panel.cli` at least once. *(machine)*
2. Rule 12 has the trigger table with all four states — `PANEL_ENABLED=0`, `always`,
   `novelty`, `escalation` — and gates on `PANEL_ENABLED=0 ⇒ never` **before** `PANEL_TRIGGER`. *(human+machine)*
3. Rule 12 states the exit map `0=PASS,1=FAIL,2=REVISE or cost_cap_breached (→ hard stop to
   human, Rule 5),3=malformed`, says the panel **never auto-accepts**, and cross-refs Rule 5. *(human+machine)*
4. Rule 12 defines "novel" as **pure PLANNER judgment** (no numeric heuristic) and `escalation`
   as **budget-exhaustion only** (`MAX_IMPL_ATTEMPTS`/`MAX_REVIEW_CYCLES`); names the PLANNER as judge. *(human)*
5. `.claude/agent.config` has `PANEL_ENABLED="0"`; `python -m pytest` baseline **165 passed, 1
   deselected** unchanged (panel path stays dormant). *(machine)*
6. `planner.md`/`reviewer.md` each gain a panel-delegation paragraph that references Rule 12,
   states the panel is advisory / never the verdict of record, and preserves the two touchpoints. *(human+machine)*
7. `docs/panel_integration.md` documents the prompt-file convention using a **gitignored
   `.json` path** under `.claude/state/`, `--prompt-file`, `git diff` as review input, and one
   worked example with the full Bash command. *(human+machine)*
8. `tests/test_panel_routing_docs.py` asserts **token presence only** (never prose): ROUTING.md
   has `Rule 12` + `python -m panel.cli` + the four trigger tokens; `agent.config` has
   `PANEL_ENABLED="0"`; `planner.md` has `panel_plan`; `reviewer.md` has `panel_review`. *(machine)*
9. `git diff --stat` shows only the seven file-plan files; no `panel/` file appears. *(machine)*
10. CLAUDE.md Current state reflects this integration + `PANEL_ENABLED=0` default restored. *(human)*

## Verification commands
```bash
python -m pytest -q                              # -> 166 passed, 1 deselected (165 baseline + 1 doc test)
python -m pytest -q tests/test_panel_routing_docs.py
git diff --stat                                  # seven-file scope
```

## Out of scope
Any `panel/` code change (the CLI contract is frozen); enabling the panel / funding a key /
any live call; the MCP entrypoint (Bash-CLI now, MCP later — footnoted); a numeric novelty
heuristic; auto-merge of panel output; editing `.gitignore` (the `.json` convention avoids it);
the real novel-task dry-run (human-driven enablement, "Next up").

## Tier assignment
IMPLEMENTER (Sonnet) — prose + one config flip + a token-presence test (judgment: doctrine
wording must be precise; not architectural). No BULK slice. PLANNER owns this spec.

## Loop budget
`MAX_IMPL_ATTEMPTS=3`, `MAX_REVIEW_CYCLES=2` (defaults; reversible via git, low blast radius).

## Checkpoints
1. `docs/panel_integration.md` + ROUTING.md Rule 12 + Four-Loops pointers.
2. `planner.md` + `reviewer.md` delegation paragraphs.
3. `agent.config` → `PANEL_ENABLED="0"`; CLAUDE.md updated.
4. Doc test added + green; full gate 166; `git diff --stat` scope check.

## Risks
- **R1 leftover `PANEL_ENABLED="1"`** (the working copy is armed now) → AC-5/AC-8 assert `"0"`.
- **R2 brittle doc test** → token-presence only, ≥1 occurrence, no prose/ordering.
- **R3 prompt-file leak** → use a `.json` path under `.claude/state/` (already gitignored); no `.gitignore` edit.
- **R4 ROUTING.md bloat** → Rule 12 = table + call + guarantees; full flow in the docs file.
- **R5 role prompts implying auto-accept** → each paragraph states the panel is advisory / not the verdict of record.

## Resolved design decisions
**(a) Trigger rule (evaluated `PANEL_ENABLED` first):**

| `PANEL_ENABLED` | `PANEL_TRIGGER` | Panel runs when… |
|---|---|---|
| `0` | any | **Never** — pure v4 no-op |
| `1` | `always` | every PLAN gate (planner) and every REVIEW gate (reviewer) |
| `1` | `novelty` | PLAN: **planner judges the task novel** (novel architecture / high blast radius — pure judgment). REVIEW: budget-exhaustion. *(shipped default)* |
| `1` | `escalation` | **budget-exhaustion only** (`MAX_IMPL_ATTEMPTS`/`MAX_REVIEW_CYCLES` hit) |

Novelty = PLANNER judgment (Rule 3 already makes the planner the finalization authority);
`escalation` is mechanical (the two budget counters). The trigger **authorizes, never forces** —
the role still decides per invocation (protects Rule 8 top-tier budget).

**(b) Mechanism:** Bash CLI now, MCP deferred. ROUTING.md spells the literal call once —
`python -m panel.cli plan|review --task-id <ID> --prompt-file <FILE>` — then uses `panel_plan`/
`panel_review` as shorthand, footnoted "CLI today, MCP later".

**(c) Prompt/diff delivery:** planner writes the draft spec+context to a **gitignored**
`.claude/state/panel_prompt_<task-id>.json` (covered by the existing `.claude/state/*.json`
ignore — verified) and passes `--prompt-file`; review diff comes from `git diff` into the same
path or via `-` stdin. **No `.gitignore` edit.**

**(d) Doc-grep test:** KEEP, minimal — the one regression that matters (leftover
`PANEL_ENABLED="1"`) is machine-catchable; assertions are token-presence only so the docs stay editable.

**(e) Exit 2 (REVISE/cost_cap):** maps onto **existing Rule 5** (hard stop to human) — no new
doctrine. `gate.sh` GATE 4 already blocks the stop on any non-zero panel verdict, so
"never auto-accept a REVISE/cost-capped verdict" is already machine-enforced.

**No-op guarantee (explicit):** with `PANEL_ENABLED=0` nothing runs — the CLI early-exits 0
without importing the orchestrator, GATE 4 finds no verdict, the pytest baseline is unchanged
(165→166 solely from the new doc test). Two touchpoints and the ANTHROPIC_API_KEY footgun preserved.

## Decisions needing Joe's ratification
1. **Default `PANEL_TRIGGER` stays `novelty`.** *Recommended: yes* (matches V5_PLAN §D; exercises
   the PLAN aggregator on genuinely novel work — the satellite's highest-value use).
2. **Drop the drafter's `≥200-line diff` REVIEW trigger; use budget-exhaustion + planner-flagged
   high-blast-radius only.** *Recommended: yes* — raw line count is a poor risk proxy and would be
   the one numeric heuristic we otherwise avoid. Add it later if you want a cheap second opinion on big diffs.
3. **Panel stays opt-in per invocation even when `TRIGGER=always`** (trigger authorizes, the role
   decides). *Recommended: yes* (preserves top-tier budget discipline). Override only if you want
   `always` to mean literally every gate, unconditionally.
