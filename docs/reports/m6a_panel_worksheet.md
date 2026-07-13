# M6a panel spot-check worksheet (AC-8, owner touchpoint)

Purpose: a human-verifiable sanity check of `data/panel/panel.jsonl` — three
named game lifecycles traced across their observations, chosen to cover the
three `lifecycle_status` values the merge assigns (program spec rule 2 /
AC-4/AC-8). All numbers below are recomputed directly from the committed
`data/panel/panel.jsonl` (13,652 lines), not asserted from memory.

## Headline panel stats (recomputed from `data/panel/panel.jsonl`)

- **Total records:** 13,652
- **By source:** 13,587 `wayback` + 65 `daily` = 13,652
- **Distinct wayback captures (unique `capture_url` / unique `obs_date` among
  wayback records):** 192
- **Daily records:** 65, all sharing a single `obs_date` (one daily run to
  date — M5's history is one day old as of this panel build)
- **Distinct game lifecycles (`game_key`):** 482
- **`lifecycle_status` distribution (per record, not per lifecycle):**
  - `active`: 13,232
  - `exited_unobserved`: 398
  - `exited_observed`: 22
- **Noncash-prize records** (any `top_prizes` entry with `level: null`): 69

These match the figures cited in the M6a task brief (13,652 records, 192
wayback captures + 65 daily-game records, 482 distinct game lifecycles, 69
noncash-prize records) — independently recomputed here.

## Chosen games and why

1. **`295:money-madness`** — a completed lifecycle, launch-decline-sellout
   arc reaching `exited_observed`. Chosen because it has the largest
   observation count (62) of any `exited_observed` lifecycle in the panel,
   giving the clearest, most granular launch-to-exit curve to hand-check.
2. **`184:$20,000-jumbo-bucks`** — an `exited_unobserved` game: it has the
   most observations of any `exited_unobserved` lifecycle (113) and spans
   the full 2015-era wayback window (2015-01-01 through 2019-08-24), then
   the game simply stops appearing in later captures with no terminal 0%
   record — a textbook interval-censored exit.
3. **`586:25x-the-cash`** — the long-running active game with the greatest
   calendar span among currently `active` lifecycles with ≥5 observations
   (2023-03-21 to 2026-07-13, ~1,210 days / 34 observations). No presently
   active game's observation history reaches back to the 2015-era wayback
   captures (the oldest wayback-to-today active game only starts in 2023),
   so this is the "longest span" fallback the task brief anticipates.

## 1. `295:money-madness` — completed lifecycle (`exited_observed`)

62 total observations, all `wayback` source, 2016-01-10 through 2018-09-28.

| obs_date | source | percent_unsold | total_unclaimed | lifecycle_status |
|---|---|---|---|---|
| 2016-01-10 | wayback | 89.9 | 4,231,060.00 | active |
| 2016-03-09 | wayback | 58.3 | 2,874,755.00 | active |
| 2016-06-14 | wayback | 38.3 | 1,864,690.00 | active |
| 2016-09-29 | wayback | 24.6 | 1,219,595.00 | active |
| 2016-12-07 | wayback | 20.1 | 996,045.00 | active |
| 2017-03-15 | wayback | 14.0 | 747,765.00 | active |
| 2017-06-11 | wayback | 7.5 | 525,680.00 | active |
| 2017-08-26 | wayback | 1.9 | 335,210.00 | active |
| 2017-09-26 | wayback | 0.1 | 234,940.00 | active |
| 2017-10-11 | wayback | 0.0 | 203,255.00 | active |
| 2018-01-28 | wayback | 0.0 | 72,460.00 | active |
| 2018-09-28 | wayback | 0.0 | 68,200.00 | **exited_observed** |

**What it shows:** a clean, monotonically-declining `percent_unsold` curve
from 89.9% down to 0.0% between January 2016 and October 2017 (game sells
out of new stock), followed by a long tail of nearly a year (Oct 2017–Sep
2018) where `percent_unsold` stays pinned at 0.0% while `total_unclaimed`
keeps slowly declining (4,231,060 -> 68,200 over the full run) as remaining
prizes are claimed. The build_panel merge correctly labels the final record
`exited_observed` because the terminal observation shows the 0%-unsold
state directly (program spec rule 2 definition), not an inferred gap.

## 2. `184:$20,000-jumbo-bucks` — `exited_unobserved`

113 total observations, all `wayback` source, 2015-01-01 through
2019-08-24.

| obs_date | source | percent_unsold | total_unclaimed | lifecycle_status |
|---|---|---|---|---|
| 2015-01-01 | wayback | 4.5 | 440,536.00 | active |
| 2015-06-21 | wayback | 24.7 | 1,693,459.00 | active |
| 2016-02-04 | wayback | 6.4 | 680,249.00 | active |
| 2016-02-22 | wayback | 28.8 | 2,615,606.00 | active |
| 2016-09-29 | wayback | 18.4 | 1,762,046.00 | active |
| 2017-06-25 | wayback | 9.0 | 1,006,638.00 | active |
| 2018-01-28 | wayback | 4.7 | 667,706.00 | active |
| 2018-08-01 | wayback | 0.0 | 288,500.00 | active |
| 2018-09-09 | wayback | 0.1 | 241,887.00 | active |
| 2019-01-06 | wayback | 0.1 | 227,045.00 | active |
| 2019-06-23 | wayback | 0.1 | 224,588.00 | active |
| 2019-08-24 | wayback | 0.1 | 224,177.00 | **exited_unobserved** |

**What it shows:** an unusual mid-life jump — `percent_unsold` rises from
6.4% (2016-02-04) back up to 28.8% (2016-02-22) with `total_unclaimed`
nearly quadrupling in the same window (680,249 -> 2,615,606), consistent
with a new print run/second batch being added to this game rather than a
data error (the panel's job is to record the published figures, not
normalize them). After that second decline the game plateaus at 0.1%
unsold with slowly shrinking `total_unclaimed` through mid-2019, then simply
never appears in a later capture — there is no terminal record showing 0%
unsold or an explicit end marker, so `build_panel.py` correctly assigns
`exited_unobserved` rather than `exited_observed`: the game's true final
unclaimed value at retirement is never directly observed, exactly the
interval-censored-exit case program spec rule 2 requires this status for.

## 3. `586:25x-the-cash` — long-running active game

34 total observations: 33 `wayback` + 1 `daily`, 2023-03-21 through
2026-07-13 (current).

| obs_date | source | percent_unsold | total_unclaimed | lifecycle_status |
|---|---|---|---|---|
| 2023-03-21 | wayback | 56.7 | 7,095,135.00 | active |
| 2023-06-06 | wayback | 35.1 | 4,823,980.00 | active |
| 2023-07-10 | wayback | 27.1 | 3,958,345.00 | active |
| 2023-10-04 | wayback | 9.7 | 1,906,470.00 | active |
| 2024-03-03 | wayback | 43.5 | 9,999,550.00 | active |
| 2024-08-08 | wayback | 32.9 | 7,717,710.00 | active |
| 2025-01-20 | wayback | 23.0 | 5,537,680.00 | active |
| 2025-06-15 | wayback | 16.4 | 4,129,640.00 | active |
| 2025-12-23 | wayback | 13.8 | 3,072,755.00 | active |
| 2026-04-10 | wayback | 13.8 | 3,064,345.00 | active |
| 2026-06-25 | wayback | 13.8 | 3,061,975.00 | active |
| 2026-07-13 | **daily** | 13.8 | 3,061,780.00 | active |

**What it shows:** the same reprint pattern as game 184 appears here at
larger scale — `percent_unsold` declines from 56.7% to 9.7% through 2023,
then jumps back up to 43.5% at 2024-03-03 with `total_unclaimed` roughly
quintupling (1,906,470 -> 9,999,550), consistent with a substantial new
print run under the same game name/number. Since late 2025 the game has sat
essentially flat at 13.8% unsold with `total_unclaimed` drifting down by only
tens of thousands of dollars per observation — a near-dormant late-life
plateau, still `active` because no exit or vanish has occurred. This
lifecycle is also the one bridging the two panel sources directly: its final
`wayback` record (2026-06-25) and its first `daily` record (2026-07-13,
today's M5 pipeline output) show a consistent, continuous decline
(3,061,975.00 -> 3,061,780.00), a useful cross-source continuity check.
