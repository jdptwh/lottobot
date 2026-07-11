# SPEC: Wave 4 — CLI entrypoint + PANEL_* config keys

> Status: **AWAITING JOE'S APPROVAL** (touchpoint 1 of 2). Drafted by spec-drafter
> (Sonnet), finalized and owned by planner (Opus 4.8). Do not implement until approved.
> Config default slugs use the verified dotted OpenRouter IDs
> (docs/openrouter_models_verified_2026-07-07.md), not V5_PLAN's short names.

## Objective
Add a stdlib-only config loader (`panel/config.py`) and a stdlib-only CLI (`panel/cli.py`)
with two subcommands (`plan`, `review`) that read `.claude/agent.config`, are gated by
`PANEL_ENABLED` (default `"0"`), and either (disabled) no-op cleanly or (enabled) call the
Wave 3 orchestrator, write a schema-valid `panel_verdict.json` to a configurable
`PANEL_VERDICT_PATH`, and exit with a code **identical to `verdict_lint.py` run on that
same file**. Add the `PANEL_*` keys to `agent.config` and rewire `gate.sh` GATE 4 to read
`PANEL_VERDICT_PATH` via the existing env>config>default layering, removing the Wave 4 TODO.
`PANEL_ENABLED=0` with no `panel_verdict.json` present reproduces v4 behavior byte-for-byte.
No new runtime dependencies. No MCP server this wave.

## File plan
- **NEW `panel/config.py`** — parses `.claude/agent.config` (`KEY="VALUE"`) into a typed
  frozen `PanelConfig`; env>config>built-in-default precedence per key; coerces bool/float/
  list; `load_config(config_path=".claude/agent.config", environ=os.environ) -> PanelConfig`.
  Injectable `environ`/`config_path` for tests.
- **NEW `panel/cli.py`** — `argparse` subcommands `plan`/`review`; `main(argv=None) -> int`;
  disabled path returns 0 without importing/calling the orchestrator or writing a file;
  enabled path builds lineup from config, calls `run_plan`/`run_review`, writes verdict JSON
  to `PANEL_VERDICT_PATH` (creating parent dirs), then exits with the **same mapping
  `verdict_lint.py` uses**. `__main__` guard.
- **NEW `panel/README.md`** — usage, `PANEL_*` key table, the `PANEL_ENABLED=0` no-op
  contract, secret handling (`OPENROUTER_API_KEY` only), exit-code table.
- **MODIFY `.claude/agent.config`** — append a `# ---- Panel satellite (v5) ----` block
  (keys in decision (c)), `PANEL_ENABLED="0"`.
- **MODIFY `.claude/hooks/gate.sh`** — resolve `PANEL_VERDICT_FILE` from
  `${_env_panel_path:-${PANEL_VERDICT_PATH:-.claude/state/panel_verdict.json}}` (capture
  `_env_panel_path` **before** sourcing agent.config, mirroring `_env_verify`); remove the
  Wave 4 TODO. GATE 4 does **not** gate on `PANEL_ENABLED` (decision d).
- **MODIFY `.claude/hooks/verdict_lint.py`** — extract the panel verdict→exit-code mapping
  into a pure module-level `panel_exit_code(verdict_dict) -> int` (no behavior change; the
  CLI imports it so the mapping has one source of truth). *(Protected Wave 1 file — this is
  the one authorized edit; the existing branch behavior/tests are preserved.)*
- **NEW `tests/panel/test_config.py`**, **`test_cli.py`**, **`test_gate_panel_path.py`**.

**Do NOT touch:** orchestrator/adapters/cost_meter/prices/errors/safe_retry, the JSON
schema, prompts, existing tests. No new runtime dependency.

## Acceptance criteria
1. `config.py` parses `KEY="VALUE"`, `KEY=VALUE`, `KEY='VALUE'` → unquoted string; blank
   lines + full-line `#` comments ignored; trailing inline ` # comment` after an **unquoted**
   value stripped; a `#` **inside** a quoted value preserved. *(test)*
2. Key present-but-empty (`PANEL_LINEUP=""`) → empty-typed default (empty list, not `[""]`);
   key absent → built-in default; missing config file → all-defaults `PanelConfig`, no raise. *(test)*
3. Env > file > default for every key. Coercion: bools accept `{1,true,yes,on}`→True /
   `{0,false,no,off,""}`→False (case-insensitive); `PANEL_MAX_COST_USD`→float (malformed →
   default, no crash); lineup keys → `list[str]` split on commas, whitespace stripped, empties dropped. *(test)*
4. **`PANEL_ENABLED=0` no-op:** `main(["plan",...])` (unset/falsey) returns 0, does **not**
   call `run_plan`/`run_review` (monkeypatched sentinel fails the test if invoked), writes
   **no file**. Same for `review`. *(test)*
5. **Enabled happy path (mocked):** `PANEL_ENABLED=1` + injected fake `call_model` →
   `main(["plan",...])` writes a file at `PANEL_VERDICT_PATH` that parses, passes
   `assert_valid_panel_verdict`, and passes `verdict_lint.py` (subprocess) for a PASS fixture.
   No real network (no-network guard). *(test)*
6. Written file contains **no secret**: `OPENROUTER_API_KEY` value never appears in the
   verdict JSON or CLI stdout/stderr; key read only from env / explicit arg; never reads/sets
   `ANTHROPIC_API_KEY`. *(test + grep)*
7. **CLI exit == verdict_lint exit, in lockstep:** the CLI derives its code from the extracted
   `panel_exit_code()` in `verdict_lint.py` (imported, single source) — no reimplemented copy.
   Parametrized test: for each Wave-1 fixture (plan_pass, review_pass, plan_revise, plan_fail,
   cost_cap_breached) `cli exit == subprocess verdict_lint exit` on the identical file. *(test)*
8. **Malformed/edge parity:** a defensively schema-failing dict still yields CLI exit ==
   `verdict_lint`'s (3 if shelling out; if importing, validated via the same path). Document which. *(test)*
9. `gate.sh` honors `PANEL_VERDICT_PATH`: PASS file → GATE 4 lints, gate exit 0; FAIL/REVISE/
   cost_cap file → gate exit 2. Test drives `bash .claude/hooks/gate.sh` in a temp repo with a
   `CLAUDE.md` sentinel. *(test)*
10. **Absent-file byte-identical:** `PANEL_VERDICT_PATH` set but target absent (and unset +
    default absent) → GATE 4 silent no-op, gate exit 0, no `[gate:panel]` line. *(test)*
11. **v4 reproduction:** `PANEL_ENABLED` unset + no `panel_verdict.json` → entire existing
    suite passes unchanged, and `gate.sh` PASS/exit-0 behavior unchanged (only a comment/var
    line differs, asserted not to alter output). *(test + full suite)*
12. `ast.parse` succeeds for `config.py`/`cli.py` and line counts > 0 match intended content
    (truncation guard). *(checkpoint)*
13. `grep -R "ANTHROPIC_API_KEY" panel/ .claude/agent.config` → nothing; `OPENROUTER_API_KEY`
    read only from env in cli.py/config.py. *(grep)*
14. `.claude/state/*.json` stays gitignored (`.gitignore`); default `PANEL_VERDICT_PATH` stays
    inside `.claude/state/` so the verdict is never committed. *(human + default value)*

## Verification commands
```bash
python -m pytest -q                                   # full suite incl. new tests; live deselected
python -c "import ast; ast.parse(open('panel/config.py').read()); ast.parse(open('panel/cli.py').read()); print('ok')"
bash .claude/hooks/gate.sh; echo "exit=$?"            # clean tree -> unchanged v4 behavior
PANEL_ENABLED=0 python -m panel.cli plan --task-id t --prompt-file X; echo $?   # -> 0, writes nothing
```

## Out of scope
MCP server / MCP SDK dependency (deferred); any change to orchestrator/prompts/adapters/
cost_meter/prices/schema internals; `PANEL_TRIGGER` enforcement/novelty detection (store +
surface only); live end-to-end run (separate budget-capped human step, migration checklist #7);
Wave 5 dashboard; auto-invocation of the CLI via Claude Code hooks/settings.json.

## Tier assignment
**IMPLEMENTER (Sonnet):** `config.py`, `cli.py`, the `verdict_lint.py` mapping extraction,
`gate.sh` edit, and all three test files (precedence semantics, exit-code lockstep, bash
layering — judgment). **BULK (Haiku):** the `agent.config` append and `README.md` (mechanical
transcription; `test_config.py` reads the config back, README grep-checked against the key table).

## Loop budget
`MAX_IMPL_ATTEMPTS=3`, `MAX_REVIEW_CYCLES=2` (repo defaults; no override).

## Checkpoints
1. `config.py` + `test_config.py` green (parse/precedence/coercion/edge); ast+line-count verified.
2. `verdict_lint.py` `panel_exit_code` extraction (drift tripwire still green) + `cli.py` +
   `test_cli.py` green (no-op, enabled write, exit lockstep, secret hygiene, no-network); ast+line-count verified.
3. `agent.config` PANEL_* block + `gate.sh` rewire + `test_gate_panel_path.py` green; full
   suite green; v4-reproduction assertions pass.
4. `README.md` written; reviewer pass; CLAUDE.md "Current state" → "Wave 4 SHIPPED"; commit.

## Risks
- **Mount truncation on large writes** (`cli.py` is biggest) → write via bash heredoc, then
  `ast.parse` + line-count verify before the gate (AC-12).
- **Exit-code drift** → single source: extract `panel_exit_code()` in verdict_lint, CLI
  imports it; AC-7 pins parity across fixtures.
- **`tests/panel` must never be a package** → no `__init__.py`; `test_gate_panel_path.py`
  shells out to bash, doesn't import gate logic.
- **GATE 4 gating on PANEL_ENABLED could suppress a legit verdict** → GATE 4 stays
  file-presence-driven only (decision d); staleness prevented at the source.
- **gate.sh env-capture ordering** → capture `_env_panel_path` **before** sourcing agent.config
  (like `_env_verify`); AC-9/10 test both env-set and config-only.
- **Bash test portability on Windows** → `test_gate_panel_path.py` uses
  `skipif(shutil.which("bash") is None)` so the Windows gate stays green; bash path runs in WSL/CI.
- **No pre-existing gate.sh panel test** → "Wave 1 gate floor" is vacuous here; AC-9/10 *add*
  that coverage; no existing test modified.
- **Coercion crash on bad config** → malformed float → default, never raise (AC-3); parsing is total.

## Resolved design decisions
- **(a) CLI-only; no MCP, no stdio shim.** MCP SDK is a runtime dep vs the stdlib-only posture;
  the lead invokes the CLI as a subprocess fine. Revisit MCP in a later wave. Testable: no dep
  added; `grep import mcp panel/` empty.
- **(b) Mapped exit codes 0/1/2/3, single shared mapping.** CLI must not always-0 (gate + lead
  branch on it); lockstep via extracted `panel_exit_code()` (AC-7).
- **(c) Full dotted slugs; soft-warn validation.** Defaults use verified slugs; `config_loader`
  warns (stderr) on a lineup slug absent from `VERIFIED_PRICES` but does **not** hard-fail
  (unknown-but-valid new slug must still run; `usage.cost` is cost truth). Defaults:
  `PANEL_ENABLED="0"`, `PANEL_TRIGGER="novelty"`, `PANEL_PROVIDER="openrouter"`,
  `PANEL_MAX_COST_USD="2.00"`, `PANEL_VERDICT_PATH=".claude/state/panel_verdict.json"`,
  `PANEL_PLAN_LINEUP="anthropic/claude-fable-5,openai/gpt-5.5"`,
  `PANEL_PLAN_SYNTH="anthropic/claude-opus-4.8"`,
  `PANEL_REVIEW_LINEUP="anthropic/claude-opus-4.8,openai/gpt-5.5"`,
  `PANEL_REVIEW_ARBITER="anthropic/claude-fable-5"`, plus `PANEL_MODE_PLAN="aggregate"`,
  `PANEL_MODE_REVIEW="union"`, `PANEL_ROUTING="exacto"`.
- **(d) Disabled = write nothing, exit 0; GATE 4 does NOT check PANEL_ENABLED.** No-op means no
  file is written, so there's no stale artifact to suppress — and gating GATE 4 on
  PANEL_ENABLED could ignore a legit verdict whose env the hook can't see. AC-4 + AC-10 give
  "PANEL_ENABLED=0 reproduces v4 exactly."
- **(e) PANEL_TRIGGER store-only.** Parsed/exposed; no CLI gating this wave.
- **(f) gate.sh reads PANEL_VERDICT_PATH via env>config>default; absent-file byte-identical.**
  Capture `_env_panel_path="${PANEL_VERDICT_PATH-}"` before sourcing; existing `[ -f ]` guard
  unchanged. AC-9/10.
- **(g) Prompt via positional arg OR `--prompt-file` OR stdin (`-`); `--task-id` required.**
  Exactly one non-empty prompt source or the CLI errors (exit 2, no orchestrator call).
- **Scrutiny:** exit mapping owned by verdict_lint; backward-compat proven by AC-11;
  `.claude/state/*.json` already gitignored (verdict never committed).

## Decisions needing Joe's ratification
1. **Exit-mapping mechanism: import `panel_exit_code()` from verdict_lint vs. shell out.**
   *Recommended: import the extracted function* (no subprocess; low-risk refactor improves
   testability). Fallback to shelling out only if importing a `.claude/hooks/` module from
   `panel/` is objectionable.
2. **`--prompt-file`/stdin scope.** *Recommended: all three input modes* (arg, `--prompt-file`,
   stdin) — real spec prompts are large. Drop stdin for a minimal surface if preferred.
3. **Slug validation strictness.** *Recommended: soft-warn* — hard-fail risks blocking
   legitimately-new slugs.
4. **CLI subcommand names `plan`/`review`** (`python -m panel.cli plan|review`). *Recommended:
   as listed.* Standalone `panel_plan`/`panel_review` console scripts would need a
   `[project.scripts]` block — deferred unless you want it.
