# SPEC: Fast Play EV extension (v1 — relative-signal launch)

**Status:** FINAL — planner-reviewed and owned; owner APPROVED 2026-07-27
(chat touchpoint). Implementer dispatch authorized.
**Author of record:** planner (Fable 5) · 2026-07-27 · supersedes the
spec-drafter draft of 2026-07-27.
**Governing authorities:** maine-scratch-ev-spec.md §4 (latest.json is a
FROZEN contract — never modified by this task), §6 (gate discipline, extended
by analogy to a new artifact), §8 (polite scraping: 1 req/day/page,
responsible-use framing binds every published surface);
docs/reports/edge_research_2026-07-26.md (Fast Play finding — note its 2-1
vote on "identical format": treat format identity as UNVERIFIED until the
fixture is in hand); docs/specs/winners_location_spec.md (additive
isolated-module precedent); docs/specs/m4a_scoring_spec.md +
scraper/compute.py (scoring conventions extended by analogy, not shared
code); docs/ui_mockup_protocol.md + docs/specs/ui_v2_insights_spec.md (the
site is a segmented-view console; Fast Play is the 4th view);
docs/specs/m6a_noncash_addendum.md (tolerant prize-level shape reused here).
**Panel:** not invoked — this is a drop-in extension of a proven, shipped
methodology to a same-publisher page, not a novel architecture
(PANEL_TRIGGER=novelty not met). Escalations route normally.

---

## Objective

Extend the daily pipeline to scrape, gate, and publish Maine's Fast Play
unclaimed/unsold disclosure as a new additive artifact
(`data/fastplay.json`) and a 4th site view, using the scratch pipeline's
methodology and honesty discipline. **v1 posture (binding):** no print-run
source exists yet for Fast Play, so v1 ships with `print_run: null` for
every game, ranks by `relative_score` (the relative unclaimed-money signal)
only, and publishes NO ev_ratio, NO value_score, and NO grade for any game —
the scoring machinery is wired and tested but dormant until a follow-on task
lands per-game metadata. Progressive-jackpot games are additionally flagged
and permanently non-rateable in v1 with an honest, binding reason string —
never a silently wrong EV number.

---

## Design decisions of record (resolve the draft's open questions)

**D1 — v1 EV posture (draft Q1).** `data/fastplay_games.json` is created in
this task as the metadata seam: `{"games": {}}` (empty), schema-shaped like
`data/games.json` (`print_run`, `top_prize_value`, `overall_odds`, all
nullable). `compute_fastplay` joins against it exactly as
`scraper.compute.compute_latest` joins `games.json` (absent game_no ==
all-null meta; never a crash). At launch every game therefore takes the
`no_print_run` path: `ev_ratio: null`, `rated: false`, `value_score: null`,
`grade: null`, reason from the copy bank below. A "Fast Play print-run /
odds discovery" follow-on task (out of scope here) can light up EV and
grades with ZERO code change by populating that file. The UI and copy are
designed for the all-ungraded state as the NORMAL launch state, not an
error state.

**D2 — Progressive games and the jackpot spike (draft Q2).** Two binding
rules:
- Progressive-flagged games are non-rateable in v1 UNCONDITIONALLY:
  `ev_ratio` is forced null for them in code (guard, not just data), because
  the page does not publish the jackpot dollar value and it is unverified
  whether the published dollar column includes any jackpot amount — an EV
  computed from it would be silently wrong in an unknown direction.
  `percent_unsold`, `total_unclaimed`, `relative_score`, and top-prize
  counts are still published (raw arithmetic on published fields).
- The jackpot-value discovery spike is DOCUMENTATION-ONLY and NON-BLOCKING:
  it records whether/where a live jackpot dollar value is scrapable and
  recommends scoping for a follow-on task. Even if a source is found, this
  task does NOT implement a second fetch (politeness surface stays one
  Fast Play request/day; a jackpot scrape is its own future task with its
  own spec). "Not found — ship non-rateable" is an acceptable outcome, not
  a failure. Budget: 1 attempt (see Loop budget).

**D3 — Sanity floors (draft Q3).**
- `MIN_GAMES_FASTPLAY = 20` — fixed now. The memo verified 28–30 active
  games on 2026-07-25; 20 is a 71%-of-low-end cushion, the same philosophy
  as scratch's 40-of-65.
- `MIN_TOTAL_UNCLAIMED_FASTPLAY` — set from the fixture at CP1 by pinned
  formula: `0.25 × (sum of total_unclaimed across the frozen fixture)`,
  rounded DOWN to one significant figure (e.g. fixture sum $3.71M →
  $927,500 → floor $900,000). The constant's source (fixture date +
  observed sum + formula) is recorded in a comment beside it AND asserted
  in a CP1 test. Rationale: catches units-off and truncated-table parse
  breakage while tolerating a shrinking game family.

**D4 — daily.yml failure isolation (draft Q4).** Independent failure
domains inside the single existing workflow:
- New step, placed AFTER "Run daily pipeline" and BEFORE the commit step:
  `name: Run Fast Play pipeline (all gates enforced; no write on failure)`,
  `id: fastplay`, `continue-on-error: true`,
  `run: python -m scraper.fastplay --live`.
- A Fast Play failure MUST NOT redden the job: the scratch commit, the
  streak semantics, and the existing `daily-run-failure` issue mechanism
  are untouched. Failed Fast Play run writes nothing (fail-closed), so the
  commit step simply commits an unchanged `data/fastplay.json`.
- Fast Play failures are NOT silent: a new step
  `name: Open Fast Play failure issue (deduplicated per day)`,
  `if: steps.fastplay.outcome == 'failure'`, mirrors the existing dedup
  pattern under its own label `fastplay-run-failure` (create-label ||
  true, `gh issue list` dedup before `gh issue create`).
- Commit step's `git add` line becomes exactly:
  `git add data/latest.json data/history/ data/fastplay.json data/fastplay_history/`
  — both new paths exist in-tree from CP2 (see D6), so `git add` can never
  error on a missing path.
- Accepted asymmetry: if the SCRATCH step fails, the Fast Play step is
  skipped that day (default step semantics). A scratch failure usually
  means a site-wide problem; one missed Fast Play day is acceptable and
  keeps the workflow simple.

**D5 — Checkpoint structure (draft Q5).** Collapsed, not re-split into an
M1/M2/M3/M4a ladder: the methodology is proven, the family is small, and D1
removed the print-run dependency that motivated scratch's phasing. Six
checkpoints (below), each a commit and a Rule 9 resume point.

**D6 — Artifact + orchestration shape.** `scraper/fastplay.py` is its own
thin orchestrator (no run_daily analog needed): CLI order is parse →
parser gate → compute → schema-validate → write `--out` then
`--history-dir/{as_of}.json` (byte-identical), with run_daily's failure
semantics verbatim: NO write of any kind before the final write step; any
of ParseError / GateError / RobotsDisallowed / requests.RequestException /
jsonschema.ValidationError / json.JSONDecodeError / OSError → `error: {exc}`
on stderr, exit 1. CLI defaults: `--out data/fastplay.json`,
`--history-dir data/fastplay_history`, `--as-of` defaults to today's UTC
date (tests always pass it explicitly). All writes pin
`encoding="utf-8", newline="\n"` (CRLF landmine). `data/fastplay.json` and
the first `data/fastplay_history/<fixture-as-of>.json` are committed at CP2,
regenerated from the frozen fixture.

**D7 — No diff gate in v1 (explicit, so the reviewer doesn't flag its
absence).** The scratch diff gate is ev_ratio-based; with ev_ratio null
everywhere in v1 it would be inert by construction. v1 ships parser gate +
schema gate only. A relative_score- or percent-based diff gate is deferred
to the task that first publishes non-null Fast Play EV.

**D8 — Allowed coupling (pinned).** `scraper/fastplay.py` MAY import from
`scraper.scrape` ONLY: `USER_AGENT`, `FETCH_TIMEOUT_S`, `ParseError`,
`GateError`, `RobotsDisallowed`. It MUST NOT import `parse`, `parser_gate`,
`build_latest`, `fetch`, or anything from `scraper.compute` — the two
pipelines stay independently regenerable and the scratch curve is
untouchable. Fast Play defines its own copies of the scoring constants
(`SCORE_WEIGHT`, `SCORE_EV_RATIO_CLAMP`, `SCORE_CURVE_FLOOR/SPAN`,
`DEGENERATE_SCORE`, `GRADE_BANDS`, `GRADE_DEFAULT`) and a test asserts
they are EQUAL to `scraper.compute`'s (intentional-parity drift test:
divergence is allowed only via a spec amendment that updates the test).

**D9 — Progressive detection is structural (pinned).** Fast Play's
prize-level cell parser is tolerant BY DEFAULT (unlike scratch, where
tolerance is a wayback-only opt-in): a non-numeric top-prize-level cell
(observed live as "JACKPOT") yields the m6a shape
`{"level": null, "level_label": "<verbatim, whitespace-normalized>",
"remaining": <int>}` instead of raising. A game gets the
`"progressive_jackpot"` flag iff ANY of its top_prizes items has
`level: null`. No name-based matching ("PROGRESSIVE" in the game name is
fragile and not the rule). The fixture review at CP1 must confirm every
name-contains-PROGRESSIVE game did receive the flag; a mismatch is a
finding to report, not silently patch.

**D10 — Two stop-and-report conditions (binding on the implementer).**
Report to the planner and STOP (do not guess — CLAUDE.md rule) if, at
fixture capture:
1. The Fast Play page's dollar column is NOT unclaimed-equivalent in
   semantics to the scratch page's "Total Unclaimed" (the memo's own text
   says "total unsold dollars" — if it is genuinely a different measure,
   the field name, honesty copy, and §8 framing all change).
2. The table structure diverges materially from the scratch 7-cell layout
   (different column count/order, no continuation-row pattern). Cosmetic
   differences (class names, header text) are the implementer's judgment;
   structural ones come back to the planner.
Absent either condition, the field keeps the name `total_unclaimed` and
the scratch upper-bound honesty framing applies verbatim.

---

## Binding copy bank (planner-authored — exact strings; do not reword)

`FASTPLAY_REASONS` in `scraper/fastplay.py`:

```python
FASTPLAY_REASONS = {
    "progressive_jackpot": (
        "Jackpot value isn't published on the state's Fast Play page — "
        "expected value can't be computed for this progressive game."
    ),
    "dead": (
        "Top prize already claimed — the biggest advertised win can no "
        "longer be won."
    ),
    "sold_out": (
        "Reported 0% unsold — effectively sold out; there is nothing left "
        "to buy."
    ),
    "no_print_run": (
        "Total ticket quantity unknown for this Fast Play game — expected "
        "value can't be computed; ranked by the relative unclaimed-money "
        "signal only."
    ),
    "no_data": "Not enough data to compute an expected value for this game.",
}
```

Bucket precedence (first match wins):
`progressive_jackpot` → `dead` → `sold_out` → `no_print_run` → `no_data`.
The `dead`, `sold_out`, and `no_data` strings are deliberately verbatim
copies of the scratch copy bank (family-neutral); `no_print_run` is
reworded for terminal-generated games; `progressive_jackpot` is new. These
strings are the acceptance targets for artifact `reason` fields AND the
site view's non-rateable copy.

---

## File plan (touch nothing else)

- `scraper/fastplay.py` (NEW) — self-contained module per D6/D8/D9:
  `fetch` (URL `https://www.mainelottery.com/fastplay/unclaimed_fastplay.html`,
  own robots.txt check, shared UA constant, 30s timeout, no retries),
  `parse` (tolerant prize levels by default), `parser_gate` (D3 floors),
  `compute_fastplay` (join vs `data/fastplay_games.json`; ev/flags/
  confidence/scoring by analogy to compute.py; D2 progressive guard;
  `FASTPLAY_REASONS`), CLI (`--fixture`/`--live`, `--out`, `--history-dir`,
  `--as-of`, `--schema`).
- `data/schema/fastplay.schema.json` (NEW) — own JSON Schema, parallel to
  `latest.schema.json` but permitting `level: null` + `level_label` in
  top_prizes and requiring the v1 field set (see AC-5). Never merged into
  the frozen latest.schema.json.
- `data/fastplay_games.json` (NEW, committed) — `{"games": {}}` metadata
  seam per D1.
- `data/fastplay.json` (NEW, committed at CP2 from the frozen fixture).
- `data/fastplay_history/` (NEW dir, committed at CP2 with the fixture-day
  snapshot).
- `tests/scraper/fixtures/unclaimed_fastplay_<capture-date>.html` (NEW) —
  frozen fixture, one-time polite pull (§8 exception precedent: identifying
  UA, ≥2s delay if more than one request proves necessary), provenance
  header comment (date, URL, UA) per the winners-fixture convention.
- `tests/scraper/test_fastplay.py` (NEW) — parse/gate/compute/copy-bank/
  purity/constants-parity tests + a hand-check worksheet test in the
  `test_grading.py` style (pick 3 fixture games incl. one progressive; the
  worksheet math must be reproducible from `data/fastplay.json` alone).
- `docs/reports/fastplay_jackpot_source_spike.md` (NEW) — D2 spike report.
- `docs/mockups/fastplay_mockup.html` (NEW) — Rule 11 mockup, human-approved
  BEFORE any site/index.html change (hard stop).
- `site/index.html` (MODIFIED) — 4th segmented view "Fast Play": lazy-fetch
  `../data/fastplay.json` on first open; `.chart-empty` fallback naming
  `python -m scraper.fastplay --fixture ...` if the artifact is missing;
  views 1–3 byte-untouched except the segmented-control addition.
- `tests/site/test_site_static.py` (MODIFIED) — ALLOWED_FETCHES gains
  `../data/fastplay.json` (count becomes 4); 4th-view label + binding
  Fast Play copy fragments pinned; all pre-existing anchors unchanged.
- `.github/workflows/daily.yml` (MODIFIED) — per D4 exactly.
- `tests/workflow/test_daily_workflow.py` (MODIFIED) — pins: fastplay step
  name/id/`continue-on-error: true`/exact run command; new failure-issue
  step's `if` expression, label, and list-before-create order; extended
  `git add` line; ALL existing assertions still pass unmodified.
- `CLAUDE.md` — "Current state" update at completion.
- `requirements.txt` / `requirements-dev.txt` — NO changes (requests,
  beautifulsoup4, jsonschema already authorized).

---

## Acceptance criteria

1. **Parse:** `parse()` on the frozen fixture yields ≥ `MIN_GAMES_FASTPLAY`
   (20) games in page order, every row carrying `game_no`/`name`/`price`/
   `percent_unsold`/`total_unclaimed` and ≥1 top_prizes item; progressive
   rows yield `level: null` + `level_label` (D9) without raising;
   continuation rows attach to the preceding game; orphan continuation and
   malformed cells raise `ParseError` with a named cell.
2. **Gate:** `parser_gate()` raises `GateError` naming the failed check on:
   count < 20, any missing required field, or
   sum(total_unclaimed) ≤ `MIN_TOTAL_UNCLAIMED_FASTPLAY` (constant set at
   CP1 by the D3 formula; a test asserts the constant equals the formula
   applied to the fixture).
3. **Progressive handling:** every fixture game whose top_prizes contain a
   null level carries `"progressive_jackpot"` in `flags`, has
   `ev_ratio: null` forced by the D2 guard, `rated: false`, and
   `reason == FASTPLAY_REASONS["progressive_jackpot"]` (exact string).
4. **v1 dormancy:** with the committed empty `data/fastplay_games.json`,
   EVERY game in `data/fastplay.json` has `print_run: null`,
   `ev_ratio: null`, `value_score: null`, `grade: null`, `rated: false`,
   and a reason drawn exactly from `FASTPLAY_REASONS` under the pinned
   precedence; `relative_score` is non-null for every game with
   `percent_unsold > 0` and null at 0. A separate unit test feeds
   synthetic metadata (non-null print_run) through `compute_fastplay` and
   proves the full scoring path (flags, confidence, curve, degenerate
   case, grade bands) works, so D1's follow-on is data-only.
5. **Schema:** `data/fastplay.json` validates against
   `data/schema/fastplay.schema.json`; the schema REQUIRES per game:
   `game_no, name, price, percent_unsold, total_unclaimed, top_prizes,
   print_run, remaining_tickets, ev_per_ticket, ev_ratio,
   ev_ratio_adjusted (const null), relative_score, dead_game, flags,
   confidence, value_score, grade, rated, reason` — and top-level
   `as_of, source_timestamp, games`.
6. **Constants parity:** the D8 drift test passes (Fast Play scoring
   constants == scraper.compute's).
7. **Copy bank:** `FASTPLAY_REASONS` matches this spec byte-for-byte
   (pinned in a test).
8. **CLI/orchestration:** the D6 failure semantics hold — a failing gate/
   schema leaves `--out` and `--history-dir` untouched (test: run against
   a corrupted fixture, assert exit 1 and no file mtime change); a
   successful run writes both files byte-identically with LF newlines.
9. **Spike report:** `docs/reports/fastplay_jackpot_source_spike.md`
   states, with cited URL(s) or an explicit "not found", whether a live
   progressive-jackpot dollar value is published anywhere scrapable, and
   records the D2 recommendation for the follow-on task. It also records
   the CP1 column-semantics finding (D10.1).
10. **Workflow:** daily.yml matches D4 exactly; the extended
    `tests/workflow/test_daily_workflow.py` is green AND every
    pre-existing assertion in that file passes unmodified.
11. **Politeness:** exactly one Fast Play page request per `--live` run;
    robots.txt honored; shared identifying UA; tests never touch the
    network (existing socket-guard conftest covers the new test module —
    verified by running the new tests with it active).
12. **Isolation:** `data/latest.json`, `data/schema/latest.schema.json`,
    `scraper/scrape.py`, `scraper/compute.py`, `scraper/run_daily.py` are
    byte-for-byte unchanged (`git diff --stat` proof at review).
13. **Full gate:** `python -m pytest -q` (FULL suite, not the fast-subset
    stop-gate) green before each checkpoint commit.
14. **No live-artifact pins:** no test asserts fixture-specific counts/
    game_nos/bytes against `data/fastplay.json` at its live path — the
    daily bot rewrites it. Live-file tests assert invariants only; exact
    regression pins target the frozen fixture or a fixture-derived
    artifact under `tests/` (m5a rule, extended to this artifact).

---

## UI acceptance criteria

- CP4 hard stop: `docs/mockups/fastplay_mockup.html` committed and
  HUMAN-APPROVED before any `site/index.html` edit. Mockup cites 2–3
  domain references and design notes per docs/ui_mockup_protocol.md, uses
  the site's existing palette/tokens, and MUST depict the true launch
  state: all games ungraded, ranked by the relative signal, progressives
  in a separately labeled group.
- Core flow ≤2 interactions: open console → "Fast Play" segment → list
  renders.
- The view explains, above the fold, that Fast Play games are ranked by
  the relative unclaimed-money signal only and why no EV/grades are shown
  (copy consistent with `FASTPLAY_REASONS["no_print_run"]`).
- Progressive games render in their own labeled group with the exact
  `progressive_jackpot` copy-bank string — never a fabricated number,
  never a blank/broken row.
- Upper-bound honesty framing (§8) present, consistent with the scratch
  view's language.
- States: loaded, artifact-missing (`.chart-empty` naming the generating
  command), stale/error consistent with existing furniture.
- Zero console errors at 420px and 1100px; readable at 420px with no
  horizontal scroll on the primary list; offline-clean (no external
  assets); views 1–3 visually and behaviorally unchanged.
- Built view passes the polish audit vs. the approved mockup (Rule 11 /
  review-checklist item 7) before presentation.

---

## Verification commands

- `python -m pytest -q` — primary gate (FULL suite; the stop-gate's
  analysis-excluded subset is not sufficient for checkpoint commits).
- `python -m pytest -q tests/scraper/test_fastplay.py tests/site/test_site_static.py tests/workflow/test_daily_workflow.py` — fast dev loop.
- `python -m scraper.fastplay --fixture tests/scraper/fixtures/unclaimed_fastplay_<date>.html --as-of <date> --out data/fastplay.json` then
  `python -c "import json,jsonschema; jsonschema.validate(json.load(open('data/fastplay.json')), json.load(open('data/schema/fastplay.schema.json')))"` — artifact regeneration + schema check (regeneration must be byte-identical to the committed artifact).
- Manual browser smoke: `docs/mockups/fastplay_mockup.html` and built
  `site/index.html` at 420px/1100px, zero console errors (file:// and
  local server).

---

## Out of scope

- Any change to `data/latest.json`, `latest.schema.json`,
  `scraper/scrape.py`, `scraper/compute.py`, `scraper/run_daily.py`,
  `scraper/games.py`, the scratch curve, or the scratch copy bank.
- Implementing a jackpot-value scrape or any second daily fetch (D2 —
  spike documents only; follow-on task).
- Populating `data/fastplay_games.json` with real print runs/odds
  (follow-on task; D1 seam only).
- A Fast Play diff gate (D7 — deferred until non-null EV exists).
- NH / MA / VT work; the Abrams–Garibaldi screener; winners pipeline.
- Any predictive framing anywhere in Fast Play copy.
- New workflows, new schedules, dark mode, external fonts/CDN/JS.

---

## Tier assignment

| Work item | Tier | Machine check (if BULK) |
|---|---|---|
| Fixture capture (one-time polite pull + D10 checks) | IMPLEMENTER | — manual/network; two stop-and-report conditions |
| `scraper/fastplay.py` parse + gate + compute | IMPLEMENTER | new page structure unverified; tolerant-level + progressive judgment |
| `data/schema/fastplay.schema.json` | BULK-eligible AFTER CP1 freezes the field set | `jsonschema.validate` in the regeneration command + AC-5 test fails instantly on a malformed schema |
| `daily.yml` step + workflow test extension | BULK-eligible AFTER the CLI exists and D4 is frozen here | `tests/workflow/test_daily_workflow.py` pins step name/id/continue-on-error/command/label/git-add |
| Jackpot spike (research; no machine gate — reviewer-only surface per Rule 2) | IMPLEMENTER | — doc-only, non-blocking, 1 attempt |
| Mockup | IMPLEMENTER (Rule 11 human gate) | — |
| Site view build + polish audit | IMPLEMENTER | site static tests + Rule 7 UI smoke + polish audit rubric |

---

## Loop budget

Defaults from `.claude/agent.config`: `MAX_IMPL_ATTEMPTS=3`,
`MAX_REVIEW_CYCLES=2` for the pipeline and site work. TIGHTENED: the
jackpot spike gets exactly **1 attempt** — its output is a report, "not
found" is a valid result, and an exhausted search must return to the
planner as a scope note inside the report, never burn further attempts.
Budget exhaustion anywhere else escalates per Rule 5; a second exhaustion
on the same checkpoint returns to the planner as a wrong-sizing signal,
not a request for more attempts.

---

## Checkpoints (each = one commit = Rule 9 resume point)

- **CP1** — Fixture captured (provenance header; D10 conditions cleared or
  reported), `parse` + `parser_gate` + floors (D3 constant derived and
  documented) + parse/gate tests green.
- **CP2** — `compute_fastplay` + copy bank + schema + committed
  `data/fastplay_games.json`, `data/fastplay.json`,
  `data/fastplay_history/<as_of>.json`; AC-3..8 green; regeneration
  byte-identical.
- **CP3** — Jackpot spike report delivered (doc-only; does not gate CP2 or
  CP4; may land any time after CP1).
- **CP4** — Mockup committed and **human-approved** (hard stop; no CP5
  work before approval).
- **CP5** — Site 4th view built; site tests extended and green; polish
  audit passed.
- **CP6** — daily.yml wired per D4; workflow tests green; full
  `python -m pytest -q` green; CLAUDE.md updated. Owner acceptance
  follows; first green live run of the fastplay step is observed on the
  next scheduled daily run (not a blocking criterion — workflow behavior
  is test-pinned, and D4 guarantees a red fastplay step cannot damage the
  scratch pipeline).

---

## Risks

1. **"Identical format" is a 2-1-vote claim.** The page may differ
   structurally or semantically ("unsold" vs "unclaimed" dollars) from
   scratch. Mitigated by D10's stop-and-report conditions at CP1 — the
   cheapest possible point to catch it.
2. **Total Unclaimed's jackpot treatment is unknown** for progressive
   rows (included at current value? at seed? excluded?). Mitigated by D2:
   progressives are unconditionally non-rateable in v1, and the spike
   report must record whatever the page reveals.
3. **All-ungraded launch state could read as broken.** Mitigated by the
   mockup depicting it as the designed state with explanatory copy
   (UI criteria) and the owner approving exactly that at CP4.
4. **`continue-on-error` can mask failures.** Mitigated by the dedicated
   `fastplay-run-failure` issue step keyed on step outcome (D4) and its
   test pins; a silent-failure regression would fail the workflow test.
5. **`git add` on a missing path fails the commit step.** Mitigated by
   committing both artifact paths at CP2, before CP6 wires the workflow.
6. **CRLF byte-identity landmine** (Windows dev, LF-committed artifacts).
   Mitigated by pinning `newline="\n"` on every write (D6) and the
   byte-identical regeneration check.
7. **Live-artifact test pinning** (m5a incident class). Mitigated by
   AC-14.
8. **Progressive misdetection** if a non-progressive game ever carries a
   non-numeric prize cell (noncash prize, scratch-style). Consequence is
   conservative (game becomes non-rateable with honest copy — never a
   wrong number); fixture review at CP1 plus the D9 name-vs-flag
   cross-check bounds it.
9. **Scoring-constant drift** between the two pipelines. Mitigated by the
   D8 parity test; intentional divergence requires a spec amendment.
