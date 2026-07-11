# SPEC: M1 — Unclaimed-prizes scraper + fixture tests (satellite S1)

**Author of record:** PLANNER (`claude-fable-5`) · 2026-07-11
**Milestone:** M1 (spec §7) — DoD: parses live page and frozen fixture identically; passes gates 1 & 3.
**Charter:** panel composition S1 (`docs/panel/panel-composition.md`), approved 2026-07-11.

## Objective

Parse the Maine Lottery unclaimed-prizes page into structured game records, enforce
the §6.1 parser gate, and emit a §4-schema-conformant `latest.json` shape (EV fields
null — EV math is M3/S2). All tests run offline against the frozen fixture.

## Source-page structure (from the frozen fixture — binding on the parser)

Fixture: `tests/scraper/fixtures/unclaimed_prizes_2026-07-11.html` (already frozen
from the single polite 2026-07-11 fetch; robots.txt is 404 ⇒ unrestricted).

- Timestamp line: `<p>` containing `as of July 10, 2026 5:00 AM` (capture the
  phrase after "as of ", trimmed — this is `source_timestamp`).
- Data table: `<table class="tbstriped">`; header row of `<th>`; data rows of
  exactly 7 `<td>`: Price Point (`$1.00`), Game No. (`668`), Game Name,
  Percent Unsold (`6.1`), Total Unclaimed (`$96,620.00`),
  Top Prize Level (`$1000`), Top Prize(s) Unclaimed (`5`).
- **Continuation rows:** first 5 cells whitespace-only ⇒ the row's (level, count)
  appends to the PREVIOUS game's `top_prizes`. A continuation row with no
  preceding game row is a parse error.
- Real edge cases in the fixture the parser MUST handle: game 690's name is
  literally `$` (blank-detection must use whitespace-only cells, never `$`/name
  heuristics); names contain `$` and backticks (`CA$H CRU$H`, `COUNT `EM UP`);
  prize levels up to `$1000000`; counts up to 6325.

## File plan (touch nothing else)

- `scraper/__init__.py` — empty package marker.
- `scraper/scrape.py` — parser, gate, latest-builder, polite fetch, CLI.
- `data/schema/latest.schema.json` — the §4 frozen contract as JSON Schema
  (draft 2020-12). PLANNER note: panel doc assigned this to S2; it is pulled
  forward into M1 because gate 3 requires it. Additive-only from here on.
- `tests/scraper/conftest.py` — fixture loader + socket-blocking autouse guard
  (mirror the no-network discipline of `tests/panel/test_no_network.py`).
- `tests/scraper/test_scrape.py` — the M1 test surface (below).
- `requirements.txt` — `requests`, `beautifulsoup4`, `jsonschema` (jsonschema is
  test/pipeline-only; authorized by §6.3's "validated against JSON Schema").
  Do NOT touch `pyproject.toml` (harness packaging tests depend on it).

## Public API (`scraper/scrape.py`)

- `parse(html: str) -> dict` — `{"source_timestamp": str, "games": [Game, ...]}`
  in page order. `Game` = `{"game_no": int, "name": str, "price": float,
  "percent_unsold": float, "total_unclaimed": float,
  "top_prizes": [{"level": int, "remaining": int}, ...]}`. Money/percent parsing
  strips `$`/commas; malformed cells, wrong cell counts, a missing table, or an
  orphan continuation row raise `ParseError` (defensive, §2 fragility note).
- `parser_gate(snapshot: dict) -> None` — raises `GateError` naming the failed
  check: `< 40` games; any missing/None required field
  (price, game_no, percent_unsold, total_unclaimed); or
  `sum(total_unclaimed) <= 50_000_000`.
- `build_latest(snapshot: dict, as_of: str) -> dict` — §4 shape: per game add
  `print_run/remaining_tickets/ev_per_ticket/ev_ratio/ev_ratio_adjusted = None`,
  `dead_game = False`, `flags = []`, `confidence = "low"`. Top-level `as_of`
  (ISO date) + `source_timestamp`.
- `fetch(url: str = PAGE_URL) -> str` — UA
  `MaineScratchEVRanker/0.1 (personal open-data project; contact: jdptwh@gmail.com)`;
  checks robots.txt via `urllib.robotparser` first (404 ⇒ allowed) and refuses if
  disallowed; 30 s timeout; NO retries (§8: one request/day; the Action handles
  failure by not committing).
- CLI `python -m scraper.scrape [--fixture PATH | --live] [--out PATH]` — parse →
  gate → write `build_latest` JSON (out or stdout). Gate/parse failure ⇒ nonzero
  exit, nothing written.

## Acceptance criteria

1. Parsing the frozen fixture yields **≥ 40** games (fixture holds 60+).
2. Every parsed game has non-null `price`, `game_no`, `percent_unsold`,
   `total_unclaimed` (gate 1).
3. `sum(total_unclaimed) > $50M` on the fixture (gate 1; game 718 alone is $58.5M).
4. Spec §4 example cross-check: game 706 parses to price 5.0, percent_unsold 0.3,
   total_unclaimed 468555.0, top_prizes `[{100000,1},{10000,1},{1000,1}]`.
5. Edge cases: game 690 name == `"$"` with top_prizes `[{2000,1}]`; game 718
   folds to exactly 7 tiers (incl. `{1000000,4}` and `{500,6325}`).
6. `source_timestamp == "July 10, 2026 5:00 AM"`; parse is deterministic
   (two parses compare equal).
7. Gate failures raise: truncated table (< 40 games) and a synthetic
   below-floor snapshot both raise `GateError`; orphan continuation row and
   malformed cells raise `ParseError`.
8. Gate 3: `build_latest(...)` output validates against
   `data/schema/latest.schema.json` via `jsonschema`; the §4 example object from
   the spec (verbatim) also validates. `confidence` restricted to
   `high|medium|low`; nullable fields per §4; `additionalProperties` permitted
   (additive-only contract).
9. No test touches the network (socket guard in conftest proves it). One
   `@pytest.mark.live` test (excluded by default addopts) fetches the live page,
   parses, and passes `parser_gate` — the M1 "live == fixture" check, run
   manually at most once/day.
10. Full gate `python -m pytest -q` green (harness suite + new tests).

## Verification commands
- `python -m pytest -q` (primary, from `.claude/agent.config`)
- `python -m pytest -q tests/scraper` (fast loop while developing)

## Out of scope
Print runs / `games.json` (M2), EV math (M3), any UI (M4), workflow YAML (M5),
Fast Play, `pyproject.toml`, anything under `panel/` or `.claude/`.

## Tier assignment
IMPLEMENTER (sonnet) — judgment work. No BULK slice (fixture already frozen).

## Loop budget
Defaults: MAX_IMPL_ATTEMPTS=3, MAX_REVIEW_CYCLES=2.

## Checkpoints
None mid-task (single-sitting scope). The lead commits once after review PASS —
do not commit from the implementer.

## Risks
- Hand-maintained HTML: whitespace-only continuation cells could someday carry
  stray `&nbsp;` — treat `\xa0` as whitespace.
- The page's "as of" date may lag the fetch date (fixture: fetched 07-11, page
  says 07-10) — `source_timestamp` is page truth; `as_of` is run date; never
  conflate them.
- `$25` price point currently has zero games — do not hardcode price-point lists.
