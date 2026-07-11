# SPEC: M2 — Print-run scrape → `data/games.json` (satellite S1)

**Author of record:** PLANNER (`claude-fable-5`) · 2026-07-11
**Milestone:** M2 (spec §7) — DoD: ≥80% of active games have `print_run`; rest fall back gracefully.
**Authority:** panel composition S1; spec §8 documented exception (owner-approved 2026-07-11).

## Objective

Parse the frozen per-game article fixtures into `data/games.json` — per-game static
metadata (print run, overall odds, on-sale date) keyed by `game_no` — plus game end
dates from the scratchdates fixture. All parsing is offline against fixtures; the
build never fetches. (Fixture acquisition already happened under the §8 exception;
`tests/scraper/fixtures/games/PROVENANCE.json` records source of every article —
`live` 2026-07-11 pull or `wayback` snapshot. Print runs are launch-time constants,
so archived copies are authoritative.)

## Source structure (binding, from the frozen fixtures)

**Article pages** (`tests/scraper/fixtures/games/article_<id>.html`):
- `Game #647` — game number (anchor field; always present).
- Print run label VARIES by article era — THREE formats exist in the fixtures:
  `Tickets Printed 960,000` (737), `Ticket printed: 5,400,000` (647),
  `Tickets Printed - 840,000` (638). Match case-insensitively:
  `Tickets?\s+printed\s*[-:]?\s*([\d,]+)`. Missing ⇒ `print_run: null`.
- Fixture inventory (measured 2026-07-11, binding for criterion 2): 58 article
  fixtures (35 live + 23 wayback), ALL 58 yield a print run under the tolerant
  regex; 56 of the 65 active games are covered = **86.2%**. The 9 active games
  without any article (586, 648, 664, 668, 669, 681, 689, 697, 710) take the
  null fallback. Two articles cover not-yet-active games (714, 721) — include.
- `OVERALL ODDS OF WINNING 1:3.58` (may contain commas in the odds figure on
  some games, e.g. `1:180,000` appears for HIGHEST INSTANT PRIZE ODDS — parse
  floats tolerant of commas; do NOT confuse the two labels).
- `On Sale - July 2, 2026` or `On Sale: August 1, 2024` — tolerate both.
- `Maximum Award: $500` — top prize value.
- Game name: the article `<h1>`/title heading (crumb trail ends with it too).

**Scratchdates** (`tests/scraper/fixtures/scratchdates_2026-07-11.html`):
`table.tbstriped` rows: Game Number, Game Name, Game End, Last Cash Date. Name
spellings differ slightly from the unclaimed page (`SILVER 7's` vs `SILVER 7S`) —
join on `game_no` only, never on name.

## File plan (touch nothing else)

- `scraper/games.py` — article + scratchdates parsers, `build_games()` assembler,
  CLI (`python -m scraper.games --fixtures-dir ... --out data/games.json`).
- `data/games.json` — the built artifact (committed; this is the point of M2).
- `tests/scraper/test_games.py` — test surface (below).
- `tests/scraper/fixtures/games/` + `scratchdates_2026-07-11.html` +
  `pricepages/` + `PROVENANCE.json` — already frozen; committed with this task.
  Implementer treats ALL fixtures as read-only inputs.

## `data/games.json` shape (per game_no key, string keys per JSON)

```json
{
  "as_of": "2026-07-11",
  "games": {
    "737": {
      "game_no": 737, "name": "FIND $500!", "price": 5.0,
      "print_run": 960000, "overall_odds": 3.58,
      "top_prize_value": 500, "on_sale": "2026-07-02",
      "end_date": null, "last_cash_date": null,
      "source": "wayback|live", "article_id": "13352637"
    }
  }
}
```
- `price` from the price-point page the article was tiled on when known, else
  null (wayback-recovered articles: derive from unclaimed-page price by game_no
  at build time — pass the M1 snapshot in).
- Any missing/unparseable field ⇒ null, never a crash (fragility rule §2).
- Dates ISO-formatted; unparseable date strings ⇒ null.

## Acceptance criteria

1. `build_games()` over the frozen fixtures yields an entry for every article
   fixture, keyed by game_no, with no exceptions raised.
2. **Gate (M2 DoD): ≥80% of active games** (the 65 game_nos in the M1 unclaimed
   fixture) **have non-null `print_run`**. The build asserts this and the test
   suite proves it; a `coverage` block in games.json records the numbers.
3. Label tolerance: game 737 (new format) parses `print_run == 960000`; game 647
   (old format `Ticket printed:`) parses `print_run == 5400000`, `overall_odds
   == 3.32`, on_sale `2024-08-01`.
4. Odds parsing never confuses `HIGHEST INSTANT PRIZE ODDS` with
   `OVERALL ODDS OF WINNING`; comma-bearing odds parse correctly.
5. Scratchdates: every row parses (game_no int, ISO dates); games absent from
   scratchdates get null end dates; join is by game_no only.
6. Active games with NO article fixture appear in games.json with all-null
   metadata and `"source": null` (graceful fallback per §2) — enumerated in
   `coverage.missing`.
7. Determinism: two builds byte-identical (sorted keys, no timestamps beyond
   `as_of` passed in).
8. No test touches the network (existing conftest socket guard covers the dir).
9. Full gate `python -m pytest -q` green.

## Verification commands
- `python -m pytest -q` (primary) · `python -m pytest -q tests/scraper` (dev loop)

## Out of scope
EV math (M3), any UI, workflow YAML, refetching anything, `pyproject.toml`,
`panel/`, `.claude/`, price derivation beyond the two sources named above.

## Tier assignment
IMPLEMENTER (sonnet). No BULK slice.

## Loop budget
Defaults (3 impl attempts / 2 review cycles).

## Checkpoints
None mid-task; lead commits after review PASS.

## Risks
- Wayback snapshots may render odd markup variants — parser must be tolerant
  (nulls, not crashes) and the coverage gate is the real check.
- Two articles reference non-active games (714, 721 — launched but not yet on
  the unclaimed page): include them in games.json; they'll matter within weeks.
- Name mismatches across sources are expected; game_no is the only join key.
