## SPEC: M5 — Daily GitHub Action + history accumulation (`scraper/run_daily.py` + `.github/workflows/daily.yml`)

**Author of record:** PLANNER (`claude-fable-5`) · 2026-07-12
**Milestone:** M5 (spec §7). DoD: 7 consecutive green **scheduled** runs, `data/history/` accumulating. This task ships the automation and its gates; the 7-run streak is then *observed*, not asserted (Resolution 8, owner-visible).
**Governing authorities:** maine-scratch-ev-spec.md §4 (architecture: cron ~10:30 UTC, scrape → compute → commit; `data/history/YYYY-MM-DD.json`), §6 (gate failure semantics: fail → do not commit, open an issue, site keeps serving yesterday's data), §7 (M5 DoD), §8 (polite scraping: 1 request/day, identifying UA, robots.txt); docs/specs/m3_ev_spec.md + m4a_scoring_spec.md (pipeline semantics — nothing reopened); docs/pages_deploy.md (Pages serves from master root; bot pushes redeploy).
**Lead pre-dispatch facts (planner re-verified 2026-07-12):** repo public at `github.com/jdptwh/lottobot`; Pages live at `https://jdptwh.github.io/lottobot/site/`; M1–M4 green. `scraper.scrape` exposes `fetch` (robots.txt + UA + 30 s timeout, no retries), `parse`, `parser_gate`, exceptions `ParseError`/`GateError`/`RobotsDisallowed`; its CLI is `--fixture|--live`/`--out` and is NOT reused here (it emits null-EV M1 shape). `scraper.compute` exposes `compute_latest(snapshot, games_meta, as_of)` (runs `parser_gate` internally; produces the full M3+M4a doc) and `diff_gate(new_doc, prior_doc)`; its CLI requires `--as-of`. `jsonschema` is already a runtime dep (requirements.txt); the frozen fixture is `tests/scraper/fixtures/unclaimed_prizes_2026-07-11.html`; committed `data/latest.json` was generated from that fixture with `--as-of 2026-07-11`. `tests/scraper/conftest.py` autouse-blocks sockets. No `.github/` exists yet. `pyproject.toml` addopts: `-q -m 'not live' --import-mode=importlib`.

**Blast radius: HIGH** — unattended automation committing to a public repo that redeploys a public site. The failure semantics below are the milestone's integrity core and are non-negotiable: **any gate failure ⇒ exit 1 ⇒ zero files written ⇒ zero commits ⇒ one deduplicated GitHub issue; the site keeps serving the last-good data and its existing 48 h staleness banner covers prolonged outage.**

## Objective

1. `scraper/run_daily.py` — a **thin orchestrator** (Resolution 1): imports the existing M1/M3 functions (`fetch`, `parse`, `compute_latest`, `diff_gate`) plus `jsonschema.validate`, reimplements **zero** parsing/EV/scoring/gate logic, never shells out to the module CLIs, and writes `data/latest.json` + `data/history/{as_of}.json` **only after every gate passes**.
2. `.github/workflows/daily.yml` — cron `30 10 * * *` (after the ME ~5 AM ET snapshot in both DST regimes) + `workflow_dispatch`, running the orchestrator `--live`, committing as `github-actions[bot]`, opening a deduplicated failure issue on any red run.
3. Offline tests pinning both, and the first **runtime** enforcement of the §6.3 schema gate (Resolution 2 — §6.3's own text is "validated against JSON Schema **before commit**"; M5 is the first milestone where a runtime commit exists).

## Design rules of record — `scraper/run_daily.py`

The implementer executes these; design questions come back to the planner.

1. **CLI** (`python -m scraper.run_daily`):
   - `--fixture PATH` | `--live` — mutually exclusive, required (mirrors `scrape.py`).
   - `--games PATH` default `data/games.json`.
   - `--schema PATH` default `data/schema/latest.schema.json`.
   - `--out PATH` default `data/latest.json`.
   - `--prior PATH` default **the resolved value of `--out`** (Resolution 3).
   - `--history-dir PATH` default `data/history`.
   - `--as-of ISO_DATE` default **`datetime.now(timezone.utc).date().isoformat()`** (Resolution 6/11). The Action passes nothing (run-date truth); **every test passes it explicitly** (determinism).
2. **Pipeline order, exactly:** read prior bytes from `--prior` into memory (missing file ⇒ inert first run, stderr note, same wording spirit as compute's CLI) → obtain HTML (`--fixture` read, or exactly **one** `scraper.scrape.fetch()` call in `--live`) → `parse` → `compute_latest` (parser gate §6.1 fires inside it) → **schema gate §6.3**: `jsonschema.validate(new_doc, schema)` → **diff gate §6.4**: `diff_gate(new_doc, prior_doc)` if a prior was loaded → write `--out`, then write `--history-dir/{as_of}.json`. History content = **byte-identical copy of the same run's `latest.json`** (raw fields all present; fuels M6). `--history-dir` is `mkdir(parents=True, exist_ok=True)`-ed. JSON serialization identical to compute's CLI: `json.dumps(doc, indent=2)`, UTF-8.
3. **Failure semantics:** catch exactly `ParseError, GateError, RobotsDisallowed, requests.RequestException, jsonschema.ValidationError, json.JSONDecodeError, OSError` → print `error: {exc}` to stderr → `return 1`. **No write of any kind precedes the final write step.** A same-day re-run (manual dispatch after a green scheduled run) overwrites both files — last write wins for the day; the second run's `--prior` is the first run's output, so the diff gate still guards it.
4. **No runtime block on §6.2:** the math gate is fixture/test-time; at runtime, out-of-range EV publishes honestly flagged (`ev_out_of_range`), per M3. Do not add a runtime EV-range abort.
5. **No new runtime imports** beyond stdlib + the already-authorized `requests`/`jsonschema` (exception types / validate) and the two scraper modules. **`yaml` must never be imported anywhere under `scraper/`** (Resolution 9).

## Design rules of record — `.github/workflows/daily.yml`

The following YAML is the spec (implementer may adjust only whitespace/comments; any semantic change returns to the planner):

```yaml
name: daily
on:
  schedule:
    - cron: "30 10 * * *"
  workflow_dispatch:
permissions:
  contents: write
  issues: write
concurrency:
  group: daily-pipeline
  cancel-in-progress: false
jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install runtime deps
        run: pip install -r requirements.txt
      - name: Run daily pipeline (all gates enforced; no write on failure)
        run: python -m scraper.run_daily --live
      - name: Commit and push snapshot
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add data/latest.json data/history/
          git diff --cached --quiet || git commit -m "daily: snapshot $(date -u +%F)"
          git push
      - name: Open failure issue (deduplicated per day)
        if: failure()
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          gh label create daily-run-failure --description "Automated daily pipeline failure" --color B60205 || true
          TODAY=$(date -u +%F)
          if [ -z "$(gh issue list --state open --label daily-run-failure --search "in:title $TODAY" --json number --jq '.[].number')" ]; then
            gh issue create --title "Daily run failed: $TODAY" --label daily-run-failure --body "Automated daily pipeline failed on $TODAY (UTC).

          Run: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}

          No data was committed; the site keeps serving the last-good data/latest.json (the 48h staleness banner covers prolonged outage). Check the run log for which gate failed (parser / schema / diff / fetch)."
          fi
```

Hard rules the YAML embodies (also pinned by tests): triggers are **exactly** `schedule` + `workflow_dispatch` — never `push` (no recursion; doubly safe since `GITHUB_TOKEN` pushes don't trigger workflows); **no force-push anywhere**; `git add` names **only** `data/latest.json` and `data/history/`; `cancel-in-progress: false` (Resolution 7 — never kill a run mid-commit; queue instead); one scheduled run/day = one request to the unclaimed page (+ its robots.txt read, which §8's "respect robots.txt" requires) (Resolution 10). Failure-issue dedup key: open issue, label `daily-run-failure`, UTC date in title (Resolution 4). Bot identity: standard `github-actions[bot]` (Resolution 5).

## File plan (touch nothing else)

- `scraper/run_daily.py` — NEW (rules above).
- `.github/workflows/daily.yml` — NEW (YAML of record above).
- `tests/scraper/test_run_daily.py` — NEW; all offline, all under the existing autouse socket guard, all writes to `tmp_path`, every invocation passes `--as-of` except the AC-7 default test.
- `tests/workflow/test_daily_workflow.py` — NEW (new directory; no `__init__.py` needed under importlib mode). Parses `daily.yml` with `yaml.safe_load`. **Implementation note (pinned):** PyYAML loads the `on:` key as boolean `True` (YAML 1.1); resolve triggers via `doc.get("on", doc.get(True))`.
- `requirements-dev.txt` — NEW, exactly: `-r requirements.txt` + `pyyaml`. **PyYAML is hereby explicitly authorized as a TEST-ONLY dependency** (Resolution 9, satisfying CLAUDE.md's dependency rule); it must never appear in `requirements.txt` or any runtime import.
- `CLAUDE.md` — "Current state" update at CP4 (notes the 7-green calendar DoD is in observation).
- Do NOT touch: `scraper/scrape.py`, `scraper/compute.py`, `scraper/games.py`, `data/latest.json`, `data/games.json`, `data/schema/`, any fixture, any existing test file, `site/`, `docs/`, `panel/`, `.claude/`, `requirements.txt`, `pyproject.toml`. (`data/history/` is created at runtime by the Action, never committed empty — no `.gitkeep`.)

## Acceptance criteria

1. **Fixture happy path + zero-reimplementation proof:** `python -m scraper.run_daily --fixture tests/scraper/fixtures/unclaimed_prizes_2026-07-11.html --games data/games.json --as-of 2026-07-11 --out {tmp}/latest.json --history-dir {tmp}/history` exits 0; `{tmp}/latest.json` is **byte-identical to the committed `data/latest.json`**; `{tmp}/history/2026-07-11.json` is byte-identical to `{tmp}/latest.json`.
2. **Parser-gate failure:** a doctored fixture (< 40 game rows) → exit 1, stderr contains `parser gate`, neither `--out` nor any history file exists afterward.
3. **Schema-gate failure (first runtime §6.3 enforcement):** monkeypatch `scraper.run_daily.compute_latest`'s return (or pass `--schema` pointing at a schema the doc fails) → exit 1, no files written. A companion positive assertion: the happy path validated against the real `data/schema/latest.schema.json`.
4. **Diff-gate failure holds the commit:** prior doc doctored so >30% of paired games move `ev_ratio` by >0.2 → exit 1, stderr contains `diff gate`, no files written, the prior file's bytes unmodified.
5. **`--prior` default semantics:** run once into `{tmp}/latest.json` (green), then run again into the same `--out` with a doctored fixture that trips the diff gate **without passing `--prior`** → exit 1 (proves the default prior is the previous `--out` content); the first run's output remains intact. Also: first-ever run (no prior file) exits 0 with the inert-first-run stderr note.
6. **Single-fetch politeness:** with `scraper.run_daily`'s `fetch` reference monkeypatched to a counter returning the fixture HTML, `--live` exits 0 and the counter reads exactly 1; a monkeypatched `fetch` raising `requests.RequestException` → exit 1, no files written.
7. **`--as-of` default:** invoked without `--as-of` (fixture mode), the emitted `as_of` equals the UTC date captured in-test (accept either of the two dates bracketing the invocation — midnight race).
8. **Workflow pins** (`tests/workflow/test_daily_workflow.py`): trigger set == exactly `{"schedule", "workflow_dispatch"}`; cron == `"30 10 * * *"`; `permissions` == exactly `{contents: write, issues: write}`; concurrency group present with `cancel-in-progress` False; `python-version` == `"3.11"`; the pipeline step runs `python -m scraper.run_daily --live`; the commit step contains the literal `git add data/latest.json data/history/` and a plain `git push`; the strings `--force`, `-f origin`, and `push -f` appear nowhere; the failure step has `if: failure()`, references label `daily-run-failure`, and performs the `gh issue list` dedup before `gh issue create`; commit identity is the two pinned `github-actions[bot]` strings; `on: push` absent (implied by the trigger-set assertion).
9. **Runtime purity:** a test asserts no file under `scraper/` matches `^\s*(import|from)\s+yaml\b`; `requirements.txt` is byte-unchanged (git diff clean on it).
10. **Full gate:** `python -m pytest -q` green, fully offline; no file outside the file plan touched.
11. **Post-merge live verification (CP3, human-observed):** one `workflow_dispatch` run goes green end-to-end on GitHub: exactly one bot commit appears touching only `data/latest.json` + `data/history/{today}.json`; that push triggers **no** workflow run; the Pages site loads and shows the new `as_of`.
12. **CLAUDE.md** records: M5 automation shipped, streak observation started {date}, DoD = 7 consecutive green **scheduled** runs (manual dispatches neither count toward nor reset the streak; a red scheduled run resets it) — Resolution 8, owner-visible.

## Verification

- `python -m pytest -q` (primary gate) · `python -m pytest -q tests/scraper tests/workflow` (dev loop). Test env: `pip install -r requirements-dev.txt`.
- Live surface: CP3 manual dispatch (AC-11), then calendar observation of the Actions page for the streak.
- Note: the live scrape path itself is exercised for real only at CP3 — the offline tests prove orchestration and gates; `fetch()` is already M1-proven against the live page.

## Out of scope

Source-staleness detection (see Resolution 6 — M6/backlog); any change to parse/EV/scoring/gate logic, thresholds, or the schema; `ev_ratio_adjusted` / claim-lag modeling (M6); scratchdates / end-date scraping; Fast Play; retry/backoff logic in `fetch`; notifications beyond the failure issue; Pages configuration changes; history backfill or pruning; committing an empty `data/history/`; every file not in the file plan.

## Tier assignment

- `scraper/run_daily.py` + `daily.yml` + `tests/scraper/test_run_daily.py`: **IMPLEMENTER** — judgment work with high blast radius; the **reviewer must read `daily.yml` and the run_daily failure path end-to-end** (write-before-gate or any third `git add` path is a FAIL even with green tests).
- `tests/workflow/test_daily_workflow.py` + `requirements-dev.txt`: **BULK-eligible** — near-transcription of the pinned AC-8 assertion list; named machine check = suite green **plus** reviewer 1:1 diff of assertions against AC-8. Two failed BULK passes ⇒ promote to implementer (Rule 5).
- CLAUDE.md update: IMPLEMENTER (lead-applied at CP4 is also acceptable).

## Loop budget

Tightened below `.claude/agent.config` defaults for irreversibility of the live surface: **MAX_IMPL_ATTEMPTS=2, MAX_REVIEW_CYCLES=2**. CP3 failures do not consume implementation attempts blindly — a red CP3 dispatch is diagnosed from the Actions log first; a second red CP3 escalates to the planner.

## Checkpoints (Rule 9 resume points)

- **CP1 — Orchestrator green:** `run_daily.py` + `test_run_daily.py`, ACs 1–7 + 9–10; commit.
- **CP2 — Workflow green + reviewer PASS:** `daily.yml` + workflow tests + `requirements-dev.txt`, AC-8; reviewer verdict recorded; commit.
- **CP3 — Live proof (HUMAN in the loop):** merge/push to master; human (or lead with human watching) triggers one `workflow_dispatch`; AC-11 verified on GitHub. Any resulting bot commit is real state — a failed subsequent attempt resumes from it, never replays (Rule 9).
- **CP4 — Bookkeeping:** CLAUDE.md per AC-12. Task closes here; **milestone** closes at the 7th consecutive green scheduled run (second human touchpoint: owner confirms the streak from the Actions page).

## Risks

- **Unattended commits to a public repo** are the point and the danger. Containment is layered: gates abort before any write; the commit step can only ever stage two data paths; permissions are least-privilege (`contents`+`issues`); no force-push; no `on: push`. The reviewer's end-to-end read is the last line — tests can't catch a workflow that stages extra paths only on an untested branch.
- **as_of = run-date narrows what the staleness banner means** (Resolution 6): if the state's page silently stops refreshing, `source_timestamp` ages while `as_of` advances, and the site's 48 h banner stays quiet — it now signals *pipeline* failure only, exactly per §6.1's wording ("if `as_of` > 48h old"). Source staleness remains visible in `source_timestamp` on-page and in accumulated history (§9: "history will reveal"); an explicit source-staleness signal is deliberately deferred, not forgotten.
- **Push race:** a human push between checkout and `git push` fails the run → issue opened, next day self-heals. Accepted; no auto-rebase (keeps the workflow's write behavior trivially auditable).
- **Live-page drift** (the perennial §2 fragility): first manifests as a parser/diff-gate failure → issue, stale-but-honest site. That is the designed behavior, not an emergency.
- **Same-day double runs** (dispatch after schedule): last write wins for the day, diff-gated against the morning's output; history for the date is overwritten, not duplicated. Accepted and pinned.
- **`gh` CLI availability** is guaranteed on `ubuntu-latest`; the `gh label create ... || true` guard makes issue creation idempotent on the label.
- **DST:** 10:30 UTC = 6:30 EDT / 5:30 EST — after the ~5:00 AM ET snapshot in both regimes.
- **PyYAML `on:`→`True` key trap** is pinned in the file plan so the workflow test doesn't false-fail.

---

### Resolution record (drafter's open questions, planner-ruled)

1. **Orchestrator shape:** thin `run_daily.py` importing existing functions; zero logic reimplementation; no dump-HTML mode added to `scrape.py`. AC-1's byte-identity against the committed `data/latest.json` is the machine proof of "thin".
2. **Runtime schema gate:** in scope — §6.3 says "before commit" and M5 is the first runtime commit. `jsonschema` is already a runtime dep; zero new-dependency cost.
3. **`--prior` semantics pinned:** default `--prior` = the resolved `--out`; prior bytes read into memory at start; write happens only after all gates ⇒ no copy-aside workflow step needed (supersedes the draft's copy step — identical semantics, one fewer moving part). Missing prior = inert first run (matches M3's design).
4. **Failure-issue dedup:** one open issue per UTC day — label `daily-run-failure`, date in title, `gh issue list` check before create, label auto-created idempotently.
5. **Bot identity:** standard `github-actions[bot]` + noreply email. No PAT, no custom identity.
6. **as_of + daily-commit semantics (owner-visible):** `as_of` defaults to the run's UTC date (`--as-of` override used by all tests). Consequence accepted: the pipeline commits daily even if the source page lagged, so the 48 h banner signals **pipeline** health only; source staleness stays visible via the published `source_timestamp` and the history series. A dedicated source-staleness check is ruled OUT of M5 (no gold-plating) and recorded as an M6/backlog candidate. Override at spec approval if you want the banner to cover source lag now.
7. **Concurrency:** `group: daily-pipeline`, `cancel-in-progress: false` — never cancel a run that may be mid-commit; overlapping dispatches queue.
8. **Streak counting (owner-visible):** the 7-green DoD counts **scheduled runs only**; `workflow_dispatch` exists for verification/recovery and neither counts nor resets; a red scheduled run resets the streak.
9. **PyYAML:** authorized as an explicit TEST-ONLY dependency in new `requirements-dev.txt` (real parse beats regex); `requirements.txt` byte-unchanged; AC-9 forbids any runtime `yaml` import.
10. **Politeness assertion:** single-`fetch` counter test (AC-6) + the cron itself = §8's one request/day; robots.txt read per fetch is required by §8, not a violation.
11. **(Planner addition)** `--as-of` derivation pinned: UTC-now default in live/Action use, explicit flag in every test (AC-7). Without this pin the Action could not invoke compute-derived logic (compute's CLI requires `--as-of`), and tests would be nondeterministic.
