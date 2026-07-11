# Panel Composition — Maine Scratch-Off EV Ranker spec run

**Synthesized by:** `claude-fable-5` (PLANNER role, per `.claude/agent.config`)
**Date:** 2026-07-11
**Source spec:** `maine-scratch-ev-spec.md` v0.1 (Owner: Joe)
**Status:** DRAFT — awaiting human approval. No satellite starts work before approval.

---

## 1. Composition rationale

The spec decomposes cleanly along its own milestone boundaries (§7) and gate
boundaries (§6). Four specialist satellites cover the build; the harness's fixed
roles (PLANNER / REVIEWER / BULK) wrap every satellite task. Two spec properties
drive the composition:

1. **The `latest.json` schema (§4) is a frozen contract.** It is the only
   interface between the pipeline satellites (S1, S2) and the frontend satellite
   (S3), and between the repo and the public site. It gets its own JSON Schema
   file first, so every satellite validates against the same artifact.
2. **The gates (§6) are deterministic and machine-checkable.** Each gate is
   implemented as pytest tests + pipeline checks and wired into the harness's
   verification surface (`VERIFY_CMD` in `.claude/agent.config`). A satellite's
   output is accepted only when its gates pass — **no gate, no merge.**

## 2. Satellite roster

### S1 — SCRAPER (parsing / data acquisition)
- **Milestones:** M1, M2
- **Charter:** Own everything that touches mainelottery.com. `scraper/scrape.py`
  fetches and defensively parses `players_info/unclaimed_prizes.html` into raw
  snapshot records. `scraper/games.py` (M2) scrapes per-game detail pages once
  per game to derive `print_run ≈ total_prizes_at_launch × overall_odds`, cached
  in `data/games.json`, with `print_run: null` fallback when a page lacks data.
  Maintains frozen HTML fixtures; live fetch and fixture parse must yield
  identical structures.
- **Inputs:** spec §2 (sources), §6.1 (parser gate), §8 (polite scraping:
  1 request/day to the unclaimed page, identifying UA string, robots.txt);
  frozen fixture `tests/scraper/fixtures/unclaimed_prizes_<date>.html`.
- **Acceptance criteria (gates 1, 3):**
  - Parse of the frozen fixture yields **≥ 40 games**.
  - Every row has `price`, `game_no`, `percent_unsold`, `total_unclaimed`.
  - Sum of `total_unclaimed` across games **> $50M** sanity floor.
  - Parser failure ⇒ no `latest.json` write (yesterday's data keeps serving).
  - All tests run offline against fixtures; **zero network in the test suite.**
- **Out of scope:** EV math, site rendering, workflow YAML, Fast Play pages.

### S2 — PIPELINE (EV math / data contract)
- **Milestones:** M3, M6
- **Charter:** `scraper/compute.py` implements EV v1 (§3): `remaining_tickets`,
  `ev_per_ticket`, `ev_ratio`, `top_prize_odds_now`, `dead_game`, flags,
  `confidence`. Emits `data/latest.json` conforming to the frozen §4 schema
  (fields only ever added, never deleted; nulls where data is missing) and
  writes `data/history/YYYY-MM-DD.json` snapshots. M6 adds the claim-lag v2
  discount model calibrated from snapshot deltas, publishing `ev_ratio_adjusted`
  alongside naive.
- **Inputs:** §3 math, §4 schema (first deliverable: `data/schema/latest.schema.json`
  formalizing the contract), §6.2–6.4 gates, S1's parsed records, `games.json`.
- **Acceptance criteria (gates 2, 3, 4):**
  - Unit tests on the frozen 2026-07 fixture; **EV ratios ∈ (0, 1.5)**;
    out-of-range values flag for review, never publish silently.
  - `latest.json` validates against the JSON Schema before any commit.
  - Diff gate: >30% of games changing `ev_ratio` by >0.2 in one day ⇒ hold the
    commit as probable parse breakage.
  - M3 DoD: rankings match hand-calculated spot checks on 3 games (human check).
- **Out of scope:** fetching HTML, UI, deploy workflow.

### S3 — FRONTEND (static site)
- **Milestone:** M4
- **Charter:** `site/index.html` — single-file, no build step, reads
  `../data/latest.json`. Sortable table (game, price, naive + adjusted EV ratio,
  % unsold, top prizes remaining, flags), price-point tabs, hide-dead-games
  toggle, row expansion with prize tiers + odds shift, anomaly banner
  (`ev_ratio > 0.85` or `anomaly_candidate`) with the claim-lag caveat inline,
  staleness banner when `as_of` > 48h old, mobile-first, §8 footer (methodology,
  source attribution + "Official Outstanding Prize List prevails" disclaimer,
  responsible-play line + 1-800-GAMBLER).
- **Rule 11 (mandatory):** a static mockup `docs/mockups/ev_ranker_mockup.html`
  is approved by the human **before** buildout; the approved mockup is the
  acceptance target; a passing polish audit (`docs/ui_mockup_protocol.md`)
  precedes presentation.
- **Acceptance criteria:** renders a fixture `latest.json` correctly (including
  the null-EV / low-confidence row from §4's example); usable at mobile
  viewport; honest framing sentence in the header; deployed on Pages (M4 DoD).
- **Out of scope:** any change to the `latest.json` schema (frozen; additions go
  through PLANNER).

### S4 — OPS (CI / workflow / publication)
- **Milestone:** M5
- **Charter:** `.github/workflows/daily.yml` — cron ~10:30 UTC (after the ME
  5 AM refresh): scrape → compute → gates → commit `latest.json` + history
  snapshot. Gate failure ⇒ no commit, open a GitHub issue via the Action, site
  keeps serving yesterday's data. Pages deployment config. Git history is the
  v2 time series — history snapshots must accumulate.
- **Inputs:** §4 architecture, §6 failure semantics, §8 cadence (exactly one
  unclaimed-page request per day).
- **Acceptance criteria:** workflow validates (actionlint or equivalent);
  the pipeline entrypoint runs green locally end-to-end against fixtures with
  gates enforced in the exit path; M5 DoD (7 consecutive green scheduled runs,
  history accumulating) is tracked post-deploy on the calendar.
- **Out of scope:** parser/math internals.

## 3. Harness wrapping (applies to every satellite)

- **PLANNER (`claude-fable-5`)** writes the per-milestone spec (file plan,
  acceptance criteria, tier assignment, loop budget, checkpoints) and
  arbitrates escalations. Human approves each spec (touchpoint 1).
- **IMPLEMENTER (`sonnet`)** executes satellite charters; **BULK (`haiku`)**
  takes only machine-verifiable grunt work (fixture freezing, boilerplate).
- **REVIEWER (`claude-opus-4-8`)** reviews every satellite deliverable, writes
  machine-validated `verdict.json`; `gate.sh` runs `VERIFY_CMD` on completion.
  Loop budgets per `.claude/agent.config` (3 impl attempts / 2 review cycles).
- Human accepts each milestone (touchpoint 2). **Stop-and-report after M1.**
- **Multi-model panel satellite:** stays **dormant** (`PANEL_ENABLED=0`, no
  keys). Recommended future trigger under `PANEL_TRIGGER=novelty`: the M6
  claim-lag model design is the one genuinely novel/high-judgment component in
  this spec and the natural first panel invocation, if Joe enables the panel
  and configures `OPENROUTER_API_KEY` by then. Never auto-enabled.

## 4. Build order & dependencies

```
M1 S1 scraper + fixtures        [gates 1,3]  ← start here; stop & report when green
M2 S1 print-run scrape          [≥80% coverage, graceful fallback]
M3 S2 EV v1 + latest.json       [gates 2,3,4; 3-game hand check]   needs M1 (+M2 print runs)
M4 S3 static site               [Rule 11 mockup → build → polish]  needs M3 schema+fixture
M5 S4 daily Action + Pages      [7 green runs]                     needs M1–M4
M6 S2 claim-lag v2              [≥~30 snapshots accumulated]       needs M5 history
```

## 5. Verification gate matrix

| Spec gate | Mechanism | Owning satellite | Runs at |
|---|---|---|---|
| §6.1 Parser | pytest on frozen fixture + runtime guard in pipeline | S1 | every `VERIFY_CMD`; every Action run |
| §6.2 Math | pytest fixture tests, EV ∈ (0, 1.5) | S2 | every `VERIFY_CMD` |
| §6.3 Schema | JSON Schema validation pre-commit | S2 | every `VERIFY_CMD`; every Action run |
| §6.4 Diff | pipeline check vs. yesterday's `latest.json` | S2 (logic) / S4 (wiring) | every Action run |

## 6. Global constraints

- Python 3.11 target; runtime deps limited to `requests` + `beautifulsoup4`
  (scraper only, spec-authorized). Site: vanilla HTML/JS, no build step.
- No servers, no accounts, no tracking, no monetization (v1).
- `latest.json` schema changes are additive-only and PLANNER-gated.
- Tests never touch the network; polite-scraping rules (§8) bind all live code.
- Out of scope for this run: Fast Play games, volatility metric, urgency score
  (§3 v3 backlog), any subscription/business direction (§8).
