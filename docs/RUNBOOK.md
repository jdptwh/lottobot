# panel-satellite — operator runbook

The v5 satellite is **built and complete**: five waves shipped, dashboard polished and
accepted, 161 unit tests + 14 UI-smoke tests green. It is **dormant by default**
(`PANEL_ENABLED=0`) — installed as a no-op that reproduces v4 behaviour exactly until you
switch it on. This runbook is how to operate it.

## What it is (one line)
A stateless, read-only tool the v4 routed agent system calls at the plan/spec and QA gates:
it fans a task out to a mixed-provider expert panel via OpenRouter, aggregates (PLAN =
synthesis, REVIEW = union + arbiter), meters cost against a cap, and writes a
`panel_verdict.json` that flows through the existing `verdict_lint.py` / `gate.sh`.

## The pieces
- `panel/adapters.py` · `cost_meter.py` · `prices.py` · `safe_retry.py` — OpenRouter call path.
- `panel/orchestrator.py` — parallel fan-out + synthesis/arbiter, emits a schema-valid verdict.
- `panel/cli.py` — `python -m panel.cli plan|review` (writes the verdict, exits 0/1/2/3).
- `panel/config.py` + `.claude/agent.config` `PANEL_*` keys — configuration.
- `panel/dashboard/` — local observe/config dashboard (`python -m panel.dashboard`).
- `.claude/hooks/verdict_lint.py` (+`gate.sh` GATE 4) — validates the verdict, maps exit codes.

## Daily verification (the gate)
```
python -m pytest -q            # GATE 1: full suite, mocked, zero network, zero cost
```
`gate.sh` runs this as GATE 1, and the dashboard UI-smoke as GATE 3 (`UI_VERIFY_CMD`).

## The dashboard (observe / configure)
```
python -m panel.dashboard      # → http://127.0.0.1:8207/   (127.0.0.1 only)
```
Tabs: Overview / Verdict / Cost / Config. The Config tab edits an allowlist of
`agent.config` keys (roles / lineups / budgets / cost cap / toggles) with a byte-preserving
atomic write. It cannot start a panel or submit a prompt — observe/config only.

## Enabling it for real (your call — costs money)
Follow V5_PLAN.md §D migration checklist. In short:
1. **Confirm the lead is interactive and `ANTHROPIC_API_KEY` is NOT exported.** This is the
   $1,800-in-two-days footgun (V5_PLAN Key Finding 5). The panel uses OpenRouter only.
2. `export OPENROUTER_API_KEY=...` (fund credits; set a spend cap on OpenRouter).
3. Prove the wire path cheaply: `python -m pytest -q -m live` (one call, cheapest model,
   asserts `cost_usd < 0.01`).
4. Set `PANEL_ENABLED=1` and `PANEL_TRIGGER=novelty` (Config tab or edit `agent.config`).
   Recommended Week-1 lineup: mid (`deepseek/deepseek-v4-pro` + `openai/gpt-5.5`, synth
   `anthropic/claude-opus-4.8`); promote to the premium Fable lineup for novel/high-blast tasks.
5. Dry-run: `python -m panel.cli plan --task-id t --prompt-file some_spec.md`; confirm
   `.claude/state/panel_verdict.json` validates (`gate.sh` lints it) and the cost is sane.
6. Only then consider enabling REVIEW panels for large diffs.

## Exit-code contract (CLI and verdict_lint agree)
PASS→0 · FAIL→1 · REVISE or cost_cap_breached→2 · malformed→3 · missing file→1.

## Standing rules (baked into ROUTING.md / CLAUDE.md)
- Re-verify OpenRouter model IDs/prices at spec time (they drift); cost truth is `usage.cost`.
- API-touching waves gate on MOCKED tests; live calls are a separate budget-capped target.
- UI tasks (Rule 11): approved mockup before build, polish audit before presentation.

## Environment caveats (this repo was built through a mounted folder)
- **git:** native git on Windows is fine. The Linux sandbox mount corrupts git's index on
  in-place writes; commits from there were done with the index redirected to local tmpfs.
- **Large writes:** the mount can silently truncate big file writes — write big files via a
  reliable method and verify (`ast.parse` + line count) before gating.
- **python vs python3:** the gate uses `python -m pytest`; under WSL/Git Bash where only
  `python3` exists, override `CLAUDE_VERIFY_CMD` / `CLAUDE_UI_VERIFY_CMD`.

## Status
Build complete. Remaining work is operator enablement (fund a key, flip `PANEL_ENABLED=1`),
which is intentionally a human decision. Nothing is blocked.
