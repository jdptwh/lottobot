# SPEC: Wave 2 — provider adapters + cost meter + safe_retry

> Status: **AWAITING JOE'S APPROVAL** (touchpoint 1 of 2). Drafted by spec-drafter
> (Sonnet), finalized and owned by planner (Opus 4.8). Do not implement until approved.
> API facts from `docs/openrouter_api_notes_wave2.md`; model IDs/prices from
> `docs/openrouter_models_verified_2026-07-07.md` (both verified live 2026-07-07).
> Standing rule: re-verify the smoke slug/price is still live at implementation time.

## Objective
Give the panel satellite a **stdlib-only**, deterministically mock-tested OpenRouter
call path — a single-expert adapter that normalizes the OpenAI-compatible chat
response, a USD cost accumulator whose ground truth is `usage.cost`, and a
transient-only retry wrapper — so Wave 3's orchestrator inherits a safe, metered,
side-effect-free building block. The default gate (`python -m pytest -q`, unchanged)
must make **zero** network calls and cost **zero** dollars; a single `live`-marked
smoke test proves the real wire path under a hard USD ceiling only when opted in with
a key present.

## File plan
- **NEW** `panel/__init__.py` — package marker (empty; `panel/` currently has only
  `panel/schema/`). Confirms `import panel.adapters` resolves.
- **NEW** `panel/errors.py` — exception hierarchy. `PanelError(Exception)` base;
  `MissingAPIKeyError`; `TransientProviderError` / `TerminalProviderError`, each
  carrying `code`, `message`, `raw`. Module-level `classify(status, body) -> type`
  maps verified sets (transient: 408/429/502/503 + "no content"/cold-start;
  terminal: 400/401/402/403). Unknown codes → terminal (fail-closed: never loop on
  an unclassified error).
- **NEW** `panel/adapters.py` — `call_model(model, messages, *, response_format=None,
  provider=None, max_tokens=None, api_key=None, transport=None, extra_headers=None)
  -> ModelResult`. Builds `POST /chat/completions` (always injects
  `"usage":{"include":true}`; `response_format`/`provider`/`max_tokens` included
  only when supplied). Key from `api_key` arg else `OPENROUTER_API_KEY` env, else
  `MissingAPIKeyError`. Sends via an **injectable `transport` callable** (default =
  thin `urllib.request` transport). **Classifies errors from the parsed body
  regardless of HTTP status** (the 200-with-error trap). Returns frozen
  `ModelResult(model, content, tokens_in, tokens_out, cost_usd, raw)`;
  `cost_usd = usage.cost` or `None` if omitted.
- **NEW** `panel/cost_meter.py` — `CostMeter(cap_usd=DEFAULT_COST_CAP_USD)`.
  `.add(result_or_usage)`, `.total`, `.breached` (`total > cap_usd`). Ground truth
  is `usage.cost`; falls back to `tokens_in*in + tokens_out*out` via an injected
  price table **only** when cost is absent. `DEFAULT_COST_CAP_USD = 2.00`. No
  `PANEL_*` read (Wave 4 owns config keys).
- **NEW** `panel/prices.py` — `VERIFIED_PRICES`: slug → `(in_usd_per_1m,
  out_usd_per_1m)`, transcribed from `docs/openrouter_models_verified_2026-07-07.md`
  with a docstring citing that file **and date**, marked *fallback-only —
  `usage.cost` is ground truth*.
- **NEW** `panel/safe_retry.py` — `call_with_retry(fn, *, max_attempts=4,
  base_delay_s=0.5, max_delay_s=8.0, max_total_wait_s=20.0, sleep=time.sleep,
  rng=random.random)`. On `TransientProviderError` → jittered exponential backoff +
  retry; on `TerminalProviderError` (or any non-`PanelError`) → re-raise immediately;
  stops after `max_attempts` or once cumulative wait would exceed `max_total_wait_s`.
  `sleep`/`rng` injectable for instant deterministic tests.
- **NEW** `tests/panel/test_adapters.py`, `test_cost_meter.py`, `test_safe_retry.py`,
  `test_no_network.py` — mocked-transport unit tests (no network).
- **NEW** `tests/panel/live/__init__.py`, `tests/panel/live/test_smoke_live.py` —
  `@pytest.mark.live`, `skipif` no `OPENROUTER_API_KEY`, one real call.
- **MODIFY** `pyproject.toml` — register the `live` marker; change `addopts` from
  `"-q"` to `"-q -m 'not live'"`. **No** `[project.dependencies]` change (stdlib-only).

**Do NOT touch:** `verdict_lint.py`, `panel/schema/`, `gate.sh` (Wave 1); `.claude/agent.config`
(no `PANEL_*` — Wave 4); Wave 1 tests/fixtures (regression floor); orchestrator/prompts (Wave 3).

## Acceptance criteria
1. `python -m pytest -q` (unchanged gate) passes with all new + all Wave 1 tests green; the `live` suite is deselected ("N deselected"). *(machine)*
2. `adapters.py` request body always has `usage.include==true`; includes `response_format`/`provider`/`max_tokens` iff passed; sets `Authorization: Bearer <key>` + `Content-Type`. Asserted on the captured request via injected transport. *(machine)*
3. `call_model` raises `MissingAPIKeyError` with no key **without** invoking the transport. *(machine)*
4. **200-with-error trap:** transport `status=200` + body `{"error":{"code":429}}` → `TransientProviderError`; `{"error":{"code":400}}` at 200 → `TerminalProviderError`. Classification from the body's `error.code`, not the status. *(machine)*
5. Classification table exhaustively tested: 408/429/502/503 + no-content → transient; 400/401/402/403 → terminal; unknown code (e.g. 418) → terminal (fail-closed). *(machine)*
6. Success body → `ModelResult` with `content`, `tokens_in`/`tokens_out` from `usage`, `cost_usd = usage.cost`. *(machine)*
7. `CostMeter`: N `usage.cost` values sum (float-tolerant); `.breached` False at `total==cap`, True at `total>cap` (boundary pinned). *(machine)*
8. Fallback: `cost_usd is None` + token counts → metered via injected price table (`=tokens_in*in+tokens_out*out`); a result **with** `usage.cost` **ignores** the table (ground-truth precedence). *(machine)*
9. `safe_retry`: transient twice then success within `max_attempts=4`; injected `sleep` called exactly twice with non-negative, capped delays. *(machine)*
10. `safe_retry` re-raises `TerminalProviderError` on first occurrence with **zero** sleeps; re-raises non-`PanelError` unchanged. *(machine)*
11. `safe_retry` exhausts after `max_attempts` or once projected wait exceeds `max_total_wait_s`, re-raising the last transient; total sleep never exceeds `max_total_wait_s`. *(machine)*
12. **No-network guard:** `test_no_network.py` patches `socket.socket`/`urllib.request.urlopen` to raise, exercises the mocked-transport path, asserts no real socket is created. *(machine)*
13. `pyproject.toml` deselects `live` by default and registers the marker (no `PytestUnknownMarkWarning`); `python -m pytest -q -m live` **without** a key reports the live test **skipped, not errored/failed**. *(machine)*
14. **No secrets/footgun:** `grep -ri "ANTHROPIC_API_KEY" panel/ tests/` → nothing; key only from `OPENROUTER_API_KEY`/explicit arg; no key committed. *(machine + human)*
15. **Wave 1 regression:** `test_panel_verdict_lint.py` + `test_harness_smoke.py` unmodified and green; `verdict_lint.py`, `panel/schema/`, `gate.sh` untouched. *(machine + human)*
16. `panel/prices.py` docstring cites the verified doc by name+date, marks the table fallback-only; a test asserts it's non-empty and includes the smoke slug. *(machine)*
17. **Live smoke (opt-in only):** with a key, `python -m pytest -q -m live` makes exactly one real call at `max_tokens=16` and asserts **both** `tokens_out <= ~16` **and** `cost_usd is not None and cost_usd < 0.01`. Never in the default gate. *(opt-in)*

## Verification commands
```bash
python -m pytest -q                                   # primary gate (unchanged) — live deselected
python -m pytest -q tests/panel                        # scoped during dev
OPENROUTER_API_KEY=… python -m pytest -q -m live       # opt-in, budget-capped, NOT in the gate
grep -ri "ANTHROPIC_API_KEY" panel/ tests/             # expect no matches
```

## Out of scope
Orchestrator/fan-out + synthesis/union+arbiter prompts (Wave 3); async/parallel dispatch
(Wave 3 — separate dependency authorization); schema-aware parsing of structured outputs
into findings (Wave 3); any `PANEL_*` key, CLI, MCP entrypoint (Wave 4); `verdict_lint.py`/
`panel/schema/`/`gate.sh` edits; dashboard (Wave 5); provider-pin/Exacto/Kimi route tuning (Wave 3).

## Tier assignment
**IMPLEMENTER (Sonnet)** owns the whole wave — error classification, the 200-with-error
trap, retry/backoff, and cost-precedence are judgment work. **No BULK/Haiku slice** (even
`prices.py` requires reconciliation against the verified doc — a judgment task).
**REVIEWER (Opus 4.8)** verifies 1–17, special scrutiny on 4/12/13/14; escalates any
live-cost or dependency question to PLANNER.

## Loop budget
`MAX_IMPL_ATTEMPTS=3`, `MAX_REVIEW_CYCLES=2` (agent.config unchanged). The `live` smoke is
**outside** the loop budget — manual, opt-in, budget-capped, never run autonomously.

## Checkpoints
1. `panel/errors.py` + `classify()` with its unit table green (criteria 4–5) — the spine.
2. `panel/adapters.py` + `test_adapters.py` + `test_no_network.py` green (2–6, 12).
3. `panel/cost_meter.py` + `panel/prices.py` green (7–8, 16).
4. `panel/safe_retry.py` green (9–11).
5. `pyproject.toml` marker/addopts + full gate green + Wave 1 regression intact + footgun grep clean (1, 13, 14, 15).
6. **HUMAN:** opt-in live smoke run once (criterion 17); record observed `cost_usd`.

## Risks
- **Accidental live network in the gate.** → injectable `transport` seam + `addopts -m 'not live'` + dedicated `test_no_network.py` guard (criterion 12).
- **200-with-error slips through as success.** → classify from parsed body first; criterion 4 pins it.
- **Retry loops on a terminal error.** → `classify()` fail-closed → terminal; criterion 10 asserts zero-sleep raise; `max_total_wait_s=20.0` caps worst case even if misclassified.
- **Cost under-count when provider omits `usage.cost`.** → fallback price table, ground-truth precedence (criterion 8), doc+date cite (criterion 16); fallback hit only when API gives no cost.
- **Live smoke overspend / slug retired.** → `max_tokens=16` + `cost_usd<0.01` hard assert + re-verify-slug rule; skips (not fails) with no key.
- **`urllib` error-handling gap.** → default transport must catch `HTTPError` (has `.code`/body → parse+classify) **and** `URLError` (connection-level → transient), and still parse a 200 body for an embedded `error`.
- **Wave 1 breakage via `panel/__init__.py`.** → `panel/schema/` is data not a subpackage import; criterion 15 regression-pins it.

## Resolved design decisions
- **(a) stdlib `urllib`, NO runtime dependency.** One `POST`; the transport is mocked anyway; adding `requests`/`httpx` risks the Windows/`python` landmine and buys nothing testable. Wave 3's parallel dispatch authorizes its own dep (e.g. `httpx`) if needed — the injectable-transport seam makes a later swap cheap.
- **(b) Live smoke = `deepseek/deepseek-v4-flash` ($0.09/$0.18), `max_tokens=16`, `cost_usd<0.01`.** Re-verify slug/price live at implementation; if retired, pick the then-cheapest verified chat slug, keep the $0.01 ceiling.
- **(c) Cost cap = constructor default `DEFAULT_COST_CAP_USD=2.00`, no env fallback.** Wave 4 owns `PANEL_*`; an env read now would create a key Wave 4 must reconcile.
- **(d) Structured outputs = pass-through request-shape only.** Response parsing into findings is Wave 3.
- **(e) Live-smoke asserts both token cap and `usage.cost<0.01`.** Token cap bounds spend a priori; the cost assert proves the ground-truth accounting path end-to-end.
- **(f) Backoff: `max_attempts=4`, `base_delay_s=0.5`, `max_delay_s=8.0`, `max_total_wait_s=20.0`, jitter `delay*(0.5+0.5*rng())`.** Pre-jitter delays 0.5/1.0/2.0; injectable `sleep`/`rng`.
- **(scrutiny) Mock seam = injectable `transport` callable, not monkeypatched `urlopen`.** Default gate never constructs a real HTTP path; `test_no_network.py` is a hard tripwire.

## Decisions needing Joe's ratification
1. **Ship stdlib-only for Wave 2 (no `httpx`), defer any async-dispatch dependency to the Wave 3 spec.** *Recommended: yes, stdlib-only.* The injectable-transport seam makes a later swap cheap, so deferring is low-risk. (Say so now if you'd rather adopt `httpx` once, up front.)
2. **Live-smoke ceiling `cost_usd < 0.01` on `deepseek/deepseek-v4-flash`, manual/opt-in only.** *Recommended: accept.*
3. **`DEFAULT_COST_CAP_USD = 2.00` as the Wave 2 placeholder** until Wave 4's `PANEL_MAX_COST_USD`. *Recommended: accept.*

---

## Implementation deviations (reviewer-approved, 2026-07-07)
During implementation the `tests/panel/` directory — a package literally named
`panel` (via its `__init__.py`) — shadowed the real top-level `panel/` package in
`sys.modules`, breaking `import panel.*` once tests began importing the modules
in-process. Reviewer (Opus) ruled these the correct minimal fix, escalate:false:
- **Removed** `tests/panel/__init__.py` (added in Wave 1) and did **not** add the
  planned `tests/panel/live/__init__.py`. The test dirs are no longer packages.
- **Added** repo-root `conftest.py` (inserts repo root on `sys.path`) and
  `--import-mode=importlib` to `pyproject.toml` `addopts`, so pytest imports test
  modules by path without prepending their dirs — no shadowing, better isolation.
This does not affect Wave 1 collection, the live exclusion, or test isolation.
Also applied two reviewer nits: `classify()` now tolerates a stringified numeric
`error.code`; the live-smoke token bound tightened to `<= 20`.
