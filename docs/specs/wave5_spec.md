# SPEC: Wave 5 — local project-aware dashboard

> Status: **AWAITING JOE'S APPROVAL** (touchpoint 1 of 2). Drafted by spec-drafter
> (Sonnet), finalized and owned by planner (Opus 4.8). Do not implement until approved.
> Observe/config ONLY — no prompt input, no task initiation (V5_PLAN.md scope note).
> UI work → the third gate (ROUTING.md Rule 7): GATE 1 pytest → GATE 3 UI smoke + human pass.

## Objective
Ship a read-only, localhost-only, stdlib-only web dashboard that (1) renders the latest
`panel_verdict.json`, (2) shows a running cost meter accumulated across observed verdicts,
and (3) provides a safe, line-preserving editor for a **fixed allowlist** of
`.claude/agent.config` keys. Launched via `python -m panel.dashboard`, fully separate from
`panel/cli.py`, never invoked by `gate.sh`/`cli.py`. **No task initiation, no prompt input.**

## File plan (nothing outside this list changes except the single `UI_VERIFY_CMD` edit)
- `panel/dashboard/__init__.py` — empty package marker (subpackage of real `panel/`; the
  `tests/panel` shadowing landmine does NOT apply here).
- `panel/dashboard/__main__.py` — `python -m panel.dashboard` entrypoint (`--host` default
  `127.0.0.1`, `--port` default `8787`, `--config`, `--verdict-path`, `--cost-log`); bind
  guard; starts the server. Imports neither `panel.orchestrator` nor `panel.cli`.
- `panel/dashboard/server.py` — `ThreadingHTTPServer` + handler. Routes: `GET /`,
  `GET /api/verdict`, `GET /api/cost`, `GET /api/config`, `POST /api/config`. All else → 404;
  bad method → 405. `make_server(host, port, *, config_path, verdict_path, cost_log_path)`.
  **Write via bash heredoc; verify `ast.parse` + line count before the gate** (truncation landmine).
- `panel/dashboard/config_writer.py` — `EDITABLE_KEYS` allowlist, per-key validators,
  `read_editable(path)->dict`, `write_editable(path, updates)` (line-preserving atomic rewrite).
- `panel/dashboard/render.py` — pure `render_index(verdict, cost, editable)->str`; **all
  model-derived text through `html.escape`**; f-strings only, no template engine.
- `panel/dashboard/costlog.py` — append-only JSONL: `observe(path, verdict)->bool` (append iff
  `(task_id, cost_usd_total)` unseen), `tally(path)->dict`. Read-only w.r.t. CLI/verdict file.
- `panel/dashboard/templates/index.html` — static shell/CSS (or folded into render.py); if
  separate, heredoc + line-count check.
- `tests/panel_dashboard/{test_config_writer,test_render,test_costlog,test_server_smoke,conftest}.py`
  — **no `__init__.py`** (keeps the dir out of the `panel`-shadow set); collected by `testpaths=["tests"]`.
- **MODIFY** `.claude/agent.config` — **single line**: `UI_VERIFY_CMD="python -m pytest -q tests/panel_dashboard/test_server_smoke.py"`.

## Acceptance criteria
1. `python -m pytest -q` (GATE 1) passes: prior 114 + all new dashboard tests; no regressions. *(machine)*
2. `ast.parse` of all `panel/dashboard/*.py` exits 0 (truncation guard). *(machine)*
3. **No task initiation, by import graph:** importing any dashboard module loads **neither**
   `panel.orchestrator` **nor** `panel.cli` into `sys.modules`, and no dashboard module
   references `subprocess`/`os.system`/`os.popen` (source grep). *(machine)*
4. **Route deny-list:** GET/POST to `/api/run`, `/api/plan`, `/api/review`, `/api/execute`,
   `/api/task` returns 404/405 (never 2xx); exactly the five allowed routes exist. *(machine)*
5. **HTTP smoke (GATE 3):** `make_server` on `127.0.0.1:0` in a background thread; `urllib`
   GET `/`,`/api/verdict`,`/api/cost`,`/api/config` all 200 (HTML / parseable JSON); no 5xx;
   clean shutdown+join in teardown. *(machine)*
6. **Bind guard:** refuse any non-loopback host (`0.0.0.0`, `::`, non-`127.0.0.1`/`localhost`/`::1`)
   before binding; test asserts refusal. *(machine)*
7. **Config round-trip fidelity:** `write_editable(tmp, {"PANEL_MAX_COST_USD":"3.50"})` changes
   only that key's line; every other line (comments, blanks, order, other keys) byte-identical;
   re-parses via `load_config` to the new value. *(machine)*
8. **Rejected write leaves file byte-identical:** invalid update (`PANEL_MAX_COST_USD="abc"`,
   `MAX_IMPL_ATTEMPTS="0"`, non-allowlisted key, or a value with `"`/newline/`$`/backtick)
   raises `ValueError` before any rename; file bytes unchanged. *(machine)*
9. **Atomic write:** temp file in same dir then `os.replace`; no lingering temp on success. *(machine)*
10. **Allowlist enforced:** `EDITABLE_KEYS` is exactly the ratified set; `read_editable` returns
    only those; `POST /api/config` with any other key → 400, writes nothing. *(machine)*
11. **XSS/escaping:** a verdict with `<script>alert(1)</script>` in `synthesis.artifact` /
    an expert summary renders escaped (`&lt;script&gt;`); literal `<script>` absent from output. *(machine)*
12. **Secret hygiene:** no dashboard module reads/echoes/writes `OPENROUTER_API_KEY` or any
    `*_API_KEY`/`*_TOKEN`; `GET /api/config` returns only `EDITABLE_KEYS`; source grep asserts absence. *(machine)*
13. **Cost meter accumulates honestly:** dashboard-owned append-only log; `observe` appends one
    entry per new `(task_id, cost_usd_total)` fingerprint (idempotent — no double-count on refresh);
    `/api/cost` `total_usd` = sum of distinct entries. CLI/verdict file never written. *(machine)*
14. **Latest-verdict view:** `GET /api/verdict` returns the parsed current verdict, or
    `{"present": false}` when absent (no crash); `GET /` renders gate/task_id/verdict/expert
    summaries/artifact/cost/cap-breached from the fixture. *(machine)*
15. **Read-only w.r.t. artifacts:** verdict path opened read-only; no write to `PANEL_VERDICT_PATH`;
    no CLI invocation. *(machine)*
16. `UI_VERIFY_CMD` set to the smoke command; `gate.sh` GATE 3 picks it up (env override still works). *(machine/human)*
17. **Human hands-on pass (Rule 7):** launch `python -m panel.dashboard`, load `127.0.0.1:8787`,
    confirm verdict renders, cost meter shows, and editing an allowlisted key persists while
    comments/other keys stay untouched. *(human — the accept touchpoint)*

## Verification commands
```bash
python -m pytest -q                                             # GATE 1 (full suite)
python -m pytest -q tests/panel_dashboard/test_server_smoke.py  # GATE 3 (UI_VERIFY_CMD surface)
python -c "import ast,pathlib; [ast.parse(pathlib.Path(p).read_text()) for p in __import__('glob').glob('panel/dashboard/*.py')]"
```

## Out of scope
Any prompt input / task initiation / run-plan-review trigger (hard constraint, AC-3/4); editing
`agent.config` keys outside `EDITABLE_KEYS` (secrets, `*_PATH`, `VERIFY_CMD`/`LINT_CMD`/`UI_VERIFY_CMD`,
`PANEL_PROVIDER`/`PANEL_ROUTING`, arbitrary keys); any Wave 1–4 code change except the one
`UI_VERIFY_CMD` line; new runtime deps, auth, TLS, multi-user, remote bind, Playwright/Selenium,
a DB; Wave 4 CLI cost-log changes.

## Tier assignment
IMPLEMENTER (Sonnet) — HTTP handler design, line-preserving config rewrite, escaping, and the
security-property tests are judgment work. **No BULK** (security/escaping/round-trip carry real
correctness risk). REVIEWER (Opus 4.8) final review; escalate allowlist/secret-boundary ambiguity.

## Loop budget
`MAX_IMPL_ATTEMPTS=3`, `MAX_REVIEW_CYCLES=2`, plus the mandatory human hands-on pass (Rule 7).

## Checkpoints
1. `config_writer.py` + `costlog.py` + tests green (security/fidelity core first).
2. `render.py` + `test_render.py` green (escaping proven).
3. `server.py` + `__main__.py` + `test_server_smoke.py` green; deny-list + bind-guard + import-graph tests green.
4. `UI_VERIFY_CMD` set; GATE 1 + GATE 3 green; human hands-on pass; commit; CLAUDE.md → Wave 5 SHIPPED.

## Risks
- **Mount truncation** of `server.py`/`index.html` → heredoc + `ast.parse`/line-count (AC-2).
- **tests/panel_dashboard shadowing** → no `__init__.py`; importlib mode; distinct dir name.
- **Socket/thread flakiness** → `port=0` ephemeral, daemon thread, deterministic shutdown+join, short urllib timeouts, assert no 5xx.
- **Config corruption on write** → validate-then-atomic-`os.replace`; AC-7/8/9 prove byte-identity on success and failure.
- **Injection into config values** → reject `"`,`'`,newline,`$`,backtick (shell-sourceable file safety).
- **XSS via model output** → `html.escape` all verdict text (AC-11).
- **Secret leakage** → allowlist-gated `/api/config` + source grep (AC-12).
- **Non-loopback exposure** → bind guard (AC-6), default `127.0.0.1`.
- **Cost double-count** → fingerprint idempotency (AC-13).

## Resolved design decisions
- **(a) Cost source = dashboard-owned append-only JSONL (`costlog.py`), NOT a Wave 4 CLI change.**
  Appends one entry per new `(task_id, cost_usd_total)` fingerprint; read-only w.r.t. CLI/verdict.
  Honest accumulation, stdlib, idempotent; `/api/cost` also returns `latest`.
- **(b) UI smoke = stdlib HTTP-level** (ephemeral 127.0.0.1 port, urllib GET/POST, status/JSON/no-5xx/deny-list).
  No browser dependency (Playwright would break the no-new-dep rule). Wired to `UI_VERIFY_CMD`.
- **(c) Config write = read lines; replace only editable+valid keys' assignment (preserve trailing
  inline comment); emit all other lines byte-for-byte; validate ALL updates first; temp + `os.replace`.**
  Rejected write leaves file byte-identical.
- **(d) Layout = `panel/dashboard/` package + `tests/panel_dashboard/` (no `__init__.py`).**
- **(e) Entrypoint = `python -m panel.dashboard`, fully separate from cli.py; never on the gate/task path.**
- **(f) Editable allowlist (the crux) = roles + lineups + budgets + cost cap + safe panel toggles,**
  matching the brief literally, with strong validation:
  - Roles (`*_MODEL`, non-empty, no shell metachars): `PLANNER_MODEL`, `DRAFTER_MODEL`,
    `IMPLEMENTER_MODEL`, `REVIEWER_MODEL`, `BULK_MODEL`.
  - Lineups/synth/arbiter (non-empty slug/list): `PANEL_PLAN_LINEUP`, `PANEL_PLAN_SYNTH`,
    `PANEL_REVIEW_LINEUP`, `PANEL_REVIEW_ARBITER`.
  - Budgets (positive int ≥1): `MAX_IMPL_ATTEMPTS`, `MAX_REVIEW_CYCLES`, `MAX_BULK_RETRIES`.
  - Cost cap (float >0): `PANEL_MAX_COST_USD`.
  - Panel toggles: `PANEL_ENABLED` (bool), `PANEL_TRIGGER` (enum), `PANEL_MODE_PLAN`/`PANEL_MODE_REVIEW` (enum).
  - **NOT editable (→400):** `PANEL_PROVIDER`, `PANEL_ROUTING`, `PANEL_VERDICT_PATH`, `VERDICT_PATH`,
    `VERIFY_CMD`, `LINT_CMD`, `UI_VERIFY_CMD`, any unlisted key. Never secrets.
- **Smoke double-run:** the smoke lives in `tests/` so it runs in BOTH GATE 1 and GATE 3 — fast,
  deterministic; cheaper than a marker-excluded test GATE 1 wouldn't cover.
- **Wave 1–4 regression:** the ONLY existing-file edit is `UI_VERIFY_CMD`; test config writes target
  a temp copy, never the repo's real `agent.config`.

## Decisions needing Joe's ratification
1. **Editable-key breadth (crux).** *Recommended: the full allowlist in (f)* — roles + lineups +
   budgets + cost cap + safe toggles, matching the brief, all validated. Fallback: PANEL_* only.
2. **Cost-log location** `.claude/state/panel_cost_log.jsonl` (overridable via `--cost-log`). *Recommended: accept.*
3. **Default port `8787`** (overridable `--port`). *Recommended: accept.*
4. **May the dashboard edit `PANEL_ENABLED`?** *Recommended: yes* (bool-validated no-op toggle) — but
   flipping it to `1` arms real paid API calls on the next gate, so the UI shows a "this arms paid
   calls" note. Drop it from the allowlist if you'd rather it only be flippable by hand.
