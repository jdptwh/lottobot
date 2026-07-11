# SPEC: M3 — EV v1 (`scraper/compute.py`) → `data/latest.json` (satellite S2)

**Author of record:** PLANNER (`claude-fable-5`) · 2026-07-11
**Milestone:** M3 (spec §7) — DoD: rankings match hand-calculated spot checks on 3 games (human verifies against the worksheet below).
**Math authority:** maine-scratch-ev-spec.md §3 (v1 naive EV), §4 (frozen `latest.json` contract, additive-only), §6.2 (math gate), §6.4 (diff gate).

## Objective

Join the M1 unclaimed-prizes snapshot (frozen fixture
`tests/scraper/fixtures/unclaimed_prizes_2026-07-11.html`, parsed via the existing
`scraper.scrape.parse`) with the M2 metadata in `data/games.json`, compute naive EV
per §3 v1, and emit the first REAL `data/latest.json` (M1 defined the shape with
null EV fields; M3 fills them). All computation is offline and deterministic; the
build never fetches. `ev_ratio_adjusted` stays `null` until M6.

## Source structure & join (binding)

- **Snapshot truth** (per game, from the unclaimed page): `game_no`, `name`,
  `price`, `percent_unsold`, `total_unclaimed`, `top_prizes`. These fields in
  `latest.json` come ONLY from the snapshot — the join never overwrites them.
  `price` for `ev_ratio` is the snapshot price (what a ticket costs today), not
  the games.json price.
- **Metadata joined from `data/games.json`** by `game_no` (string keys there;
  int here — convert; never join on name): exactly two fields are consumed:
  `print_run` and `top_prize_value`. Ignore the rest for M3.
- 56 of the 65 active games have non-null `print_run`; the 9 articleless games
  (586, 648, 664, 668, 669, 681, 689, 697, 710) have `print_run: null` and take
  the relative-score fallback (below). Game 617 has `percent_unsold == 0.0` in
  the frozen fixture — the division-by-zero guard case.
- An active game_no absent from games.json entirely (possible for future new
  games) is treated identically to `print_run: null` — never a crash (§2
  fragility rule).

## File plan (touch nothing else)

- `scraper/compute.py` — EV computation, flag/confidence rules, diff gate, CLI.
- `data/latest.json` — the built artifact (committed; this is the point of M3),
  built by the CLI from the frozen fixture + committed `data/games.json` with
  `--as-of 2026-07-11`.
- `data/schema/latest.schema.json` — **additive edit only** (explicitly in-plan):
  add TWO optional properties to `$defs.game.properties`:
  `"relative_score": {"type": ["number", "null"]}` and
  `"top_prize_odds_now": {"type": ["number", "null"]}`. Do NOT add them to the
  `required` list — the `required` list is frozen, and the M1 test that validates
  the verbatim §4 example object (which lacks these fields) must stay green.
- `tests/scraper/test_compute.py` — test surface (acceptance criteria below).
- Do NOT touch `scraper/scrape.py`, `scraper/games.py`, `data/games.json`, any
  fixture, or `tests/scraper/test_scrape.py` / `test_games.py`.

## `latest.json` field semantics (per game; M3 rules of record)

All published floats are `round(x, 6)` of full-precision intermediates; each
field rounds independently (never compute from an already-rounded value).

- `remaining_tickets` = `round(percent_unsold * print_run / 100)` as an **int**
  (tickets are integral; percent is 1-dp so integer rounding loses nothing).
  `null` when `print_run` is null.
- `ev_per_ticket` = `total_unclaimed / remaining_tickets`. `null` when
  `remaining_tickets` is null **or 0** (0% unsold = sold out; EV for a buyer is
  undefined — there is nothing to buy; this is the 617 guard, its own case, not
  an error).
- `ev_ratio` = `ev_per_ticket / price` (primary sort key for the UI). `null`
  whenever `ev_per_ticket` is null. **Never clamped, never dropped, never
  repurposed** — out-of-range values publish as computed, loudly flagged (§6.2:
  "flags for review rather than publishing silently").
- `relative_score` **(new, additive)** = `total_unclaimed / percent_unsold`
  (units: unclaimed $ per % unsold). Computed for EVERY game with
  `percent_unsold > 0`, `null` at 0. This is the §2 fallback ranking signal for
  null-print-run games. It is NOT comparable to `ev_ratio` (it scales with print
  run); a null-print-run game never masquerades as computed: its `ev_ratio`
  stays `null`, it carries the `no_print_run` flag, and `confidence` is `"low"`.
  The M4 UI must render it in its own column, never in the EV column.
- `top_prize_odds_now` **(new, additive)** = `remaining_tickets / r_top` where
  `r_top` is the `remaining` count of the highest `level` in `top_prizes` with
  `remaining >= 1`. `null` if `remaining_tickets` is null/0, no such tier
  exists, or the game is dead. (§3's "vs. launch odds" comparison is NOT
  computable in v1 — launch top-prize counts were never scraped; M2 captured
  only overall odds. Deferred to backlog with the prize-table scrape; do not
  fake it from `overall_odds`.)
- `dead_game` = `true` iff `top_prize_value` (from games.json) is non-null AND
  no entry in `top_prizes` has `level >= top_prize_value` with `remaining >= 1`.
  Null `top_prize_value` ⇒ `false` (unknown ≠ dead; conservative).
- `flags` (exact enumeration; array sorted alphabetically for determinism):
  - `"low_inventory"` — `0 < percent_unsold < 5.0`.
  - `"sold_out"` — `percent_unsold == 0.0`.
  - `"anomaly_candidate"` — `ev_ratio` non-null and `> 0.85` (§5's banner
    threshold; the §3 claim-lag caveat case).
  - `"ev_out_of_range"` — `ev_ratio` non-null and NOT in the open interval
    (0, 1.5) (§6.2 marker; any such game must also carry `anomaly_candidate`
    by arithmetic, since 1.5 > 0.85 and inputs are positive).
  - `"no_print_run"` — `print_run` is null.
  - `dead_game` is the boolean field, never duplicated into `flags`.
- `confidence` (§4: driven by print-run availability + percent_unsold floor;
  §3: confidence widens as percent_unsold → 0):
  - `"high"` — `print_run` non-null AND `percent_unsold >= 15.0` AND `ev_ratio`
    in (0, 1.5).
  - `"medium"` — `print_run` non-null AND `5.0 <= percent_unsold < 15.0` AND
    `ev_ratio` in (0, 1.5).
  - `"low"` — everything else (null print run, `percent_unsold < 5.0`, sold
    out, or out-of-range `ev_ratio`).
- `ev_ratio_adjusted` = `null` (M6).
- Ordering: `games` array sorted by `game_no` ascending. Ranking is a UI concern
  (M4 sorts client-side); ascending game_no keeps git diffs stable, which the
  §6.4 diff gate and the M5 history time series depend on.

Thresholds are module constants (`PCT_LOW_INVENTORY = 5.0`,
`PCT_HIGH_CONFIDENCE = 15.0`, `EV_RATIO_ANOMALY = 0.85`,
`EV_RATIO_RANGE = (0.0, 1.5)`, `DIFF_MOVE = 0.2`, `DIFF_SHARE = 0.30`). The 5.0
and 15.0 floors are planner-set (the project spec leaves them open); they are
tunable constants, not schema.

## Public API (`scraper/compute.py`)

- `compute_latest(snapshot: dict, games_meta: dict, as_of: str) -> dict` —
  `snapshot` is `scraper.scrape.parse` output; `games_meta` is the loaded
  `data/games.json` dict. Returns the full `latest.json` document. Runs
  `scraper.scrape.parser_gate` on the snapshot first (§6.1 still guards).
- `diff_gate(new_doc: dict, prior_doc: dict) -> None` — §6.4. Pair games by
  `game_no`; a pair counts only if `ev_ratio` is non-null in BOTH documents.
  Raise `GateError` (reuse from `scraper.scrape`) if pairs > 0 and the share of
  pairs with `|Δev_ratio| > 0.2` exceeds 0.30. Zero pairs ⇒ pass.
- CLI `python -m scraper.compute --unclaimed PATH --games PATH --as-of DATE
  [--prior PATH] [--out PATH]` — parse HTML → parser gate → compute → diff gate
  against `--prior` if that file exists (missing/omitted ⇒ note to stderr, gate
  inert — wire-but-dormant, exactly like M2's approach; there is no "yesterday"
  until M5's second run) → write JSON (`indent=2`, out or stdout). Any gate
  failure ⇒ nonzero exit, nothing written. No fetch path exists in this module.

## Hand-check worksheet (3 games + the zero-guard case)

All inputs below are read from the frozen fixture and committed
`data/games.json`; the implementer's output must match these values exactly
(after 6-dp rounding), and the human spot-checks the same arithmetic (M3 DoD).
(Lead-verified against the real data 2026-07-11 before this spec was accepted.)

**A. Game 720 — CROSSWORD (clean, high confidence).**
price 5.00, percent_unsold 89.2, total_unclaimed 5,572,450.00, print_run
1,560,000, top_prize_value 60,000, top_prizes {60000:5, 10000:10, 1000:69, 500:315}.
- remaining_tickets = 0.892 × 1,560,000 = **1,391,520**
- ev_per_ticket = 5,572,450 / 1,391,520 = 4.00457773… → **4.004578**
- ev_ratio = 4.00457773 / 5 = 0.80091555… → **0.800916** (in (0,1.5) ✓; note it
  sits just under the 0.85 anomaly line — assert no `anomaly_candidate`)
- top_prize_odds_now = 1,391,520 / 5 = **278304.0** · relative_score =
  5,572,450 / 89.2 = **62471.412556**
- dead_game **false** (60000-tier has 5 left) · flags **[]** · confidence
  **"high"** (89.2 ≥ 15, ratio in range)

**B. Game 702 — HOLIDAY $500S (very-low-unsold anomaly; math-gate case).**
price 5.00, percent_unsold 0.4, total_unclaimed 166,190.00, print_run 960,000,
top_prize_value 500, top_prizes {500:36}.
- remaining_tickets = 0.004 × 960,000 = **3840**
- ev_per_ticket = 166,190 / 3,840 = 43.27864583… → **43.278646**
- ev_ratio = 8.65572917… → **8.655729** — far outside (0,1.5); published as
  computed, NOT clamped
- top_prize_odds_now = 3,840 / 36 = **106.666667** · relative_score =
  166,190 / 0.4 = **415475.0**
- dead_game **false** (level 500 ≥ top_prize_value 500, 36 left) · flags
  **["anomaly_candidate", "ev_out_of_range", "low_inventory"]** · confidence
  **"low"** (this is the §5 claim-lag illusion: those prizes are almost surely
  on already-sold tickets)

**C. Game 668 — CA$H CRU$H (null-print-run fallback).**
price 1.00, percent_unsold 6.1, total_unclaimed 96,620.00, print_run null,
top_prize_value null, top_prizes {1000:5}.
- remaining_tickets **null** · ev_per_ticket **null** · ev_ratio **null**
  (never fabricated)
- relative_score = 96,620 / 6.1 = 15,839.34426… → **15839.344262**
- top_prize_odds_now **null** · dead_game **false** (top prize unknown) · flags
  **["no_print_run"]** · confidence **"low"**

**D. Game 617 — HIGH ROLLER (zero-division guard + dead game).**
price 5.00, percent_unsold 0.0, total_unclaimed 124,140.00, print_run 1,320,000,
top_prize_value 100,000, top_prizes {1000:2}.
- remaining_tickets = **0** (int) · ev_per_ticket / ev_ratio / relative_score /
  top_prize_odds_now all **null** (0% unsold = sold out; no ZeroDivisionError
  may escape)
- dead_game **true** (max live level 1000 < top_prize_value 100000) · flags
  **["sold_out"]** · confidence **"low"**

## Acceptance criteria

1. `compute_latest` over the frozen fixture + committed `data/games.json`
   returns all 65 active games, sorted by `game_no` ascending, and the document
   validates against `data/schema/latest.schema.json` via `jsonschema` (gate 3).
2. **Hand-check A (720):** every worksheet value above asserted exactly.
3. **Hand-check B (702):** values, flags, and `confidence == "low"` asserted
   exactly; `ev_ratio` is the computed 8.655729 (proves no clamping).
4. **Hand-check C (668):** nulls, `relative_score == 15839.344262`,
   `no_print_run` flag, `confidence == "low"` asserted.
5. **Zero guard D (617):** builds without exception; `remaining_tickets == 0`,
   EV fields null, `sold_out` flag, `dead_game is True`.
6. All 9 null-print-run games (586, 648, 664, 668, 669, 681, 689, 697, 710)
   have `ev_ratio is None`, carry `no_print_run`, `confidence == "low"`, and
   `relative_score` non-null iff their `percent_unsold > 0`.
7. **Math gate (§6.2), as a pytest on the frozen fixture:** every non-null
   `ev_ratio` either lies in (0, 1.5) or carries BOTH `ev_out_of_range` and
   `anomaly_candidate` with `confidence == "low"`; and ≥ 20 games have
   `ev_ratio` in (0, 1.5). If the fixture yields fewer than 20 in-range games,
   STOP and escalate to the planner — that is a data surprise, not a threshold
   to weaken.
8. `dead_game` rule proven: true for 617; false for 720, 702, and every
   null-`top_prize_value` game.
9. **Diff gate (§6.4):** unit tests against synthetic prior documents built
   in-test (no new fixture files): (a) prior absent/omitted ⇒ CLI succeeds with
   a stderr note (inert first run); (b) < 30% of paired games moving > 0.2 ⇒
   pass; (c) > 30% moving > 0.2 ⇒ `GateError` and CLI writes nothing;
   (d) null-`ev_ratio` games are excluded from both numerator and denominator.
10. Determinism: two CLI runs byte-identical; the committed `data/latest.json`
    is reproduced exactly by
    `python -m scraper.compute --unclaimed tests/scraper/fixtures/unclaimed_prizes_2026-07-11.html --games data/games.json --as-of 2026-07-11`;
    no timestamps beyond the passed `as_of` (`source_timestamp` is page truth
    from the fixture: `"July 10, 2026 5:00 AM"`).
11. Schema edit is additive-only: the two new properties are optional, the
    `required` list is untouched, and the ENTIRE existing suite — including
    M1's verbatim §4-example validation — stays green.
12. No test touches the network (existing conftest socket guard covers the
    directory). Full gate `python -m pytest -q` green.

## Verification commands
- `python -m pytest -q` (primary) · `python -m pytest -q tests/scraper` (dev loop)

## Out of scope
Claim-lag / `ev_ratio_adjusted` (M6), launch-odds comparison ("odds shift" —
needs prize-table data we don't have; backlog), any UI (M4), workflow YAML and
`data/history/` (M5), any fetching, ranking order beyond game_no sorting,
`pyproject.toml`, `requirements.txt`, `panel/`, `.claude/`, and every file not
in the file plan.

## Tier assignment
IMPLEMENTER (sonnet) — judgment work (guards, flag semantics, gate wiring). No
BULK slice: there is no machine-verifiable subtask separable from the judgment
work; the math gate itself is being built here.

## Loop budget
Defaults (`.claude/agent.config`): MAX_IMPL_ATTEMPTS=3, MAX_REVIEW_CYCLES=2.

## Checkpoints
None mid-task (single-sitting scope). Lead commits once after review PASS and
after the HUMAN verifies the three hand-checks against the worksheet — that
human check IS the M3 definition of done, the second touchpoint.

## Risks
- **Anomaly values at the top of naive rankings** (702 at 8.66, 706 at ~32):
  published honestly with flags + low confidence; M4 must sort/present with the
  claim-lag caveat (§5 banner). Do not "fix" this in M3 by suppressing data.
- **Float determinism:** 6-dp rounding of full-precision intermediates keeps
  JSON reprs stable across Python 3.11/3.12; the byte-identity criterion is the
  proof.
- **`top_prize_value` parse quirks** (M2 "Maximum Award" regex) could cause
  dead-game false negatives; the rule is deliberately conservative (null ⇒ not
  dead). A false POSITIVE would need `top_prize_value` to overstate the real
  top prize — no fixture shows this; the `level >= top_prize_value` guard also
  protects against understatement.
- **Page typos** (e.g. `percent_unsold > 100`) are not special-cased in M3; the
  §6.1 parser gate, §6.2 range flagging, and §6.4 diff gate are the defense.
  If one appears in production, it surfaces as an `ev_out_of_range` or diff-gate
  hold, which is the designed behavior.
- The 0.85 anomaly threshold and 5/15 confidence floors are first-cut constants;
  M6's adjusted EV will revisit them. Changing them later touches no schema.
