# SPEC: Winner-report alignment + location trends (descriptive)

**Author of record:** lead (cloud session) · 2026-07-22
**Status:** built and delivered with this spec (owner-directed batch build,
2026-07-22; pre-build spec touchpoint waived by the owner for this batch).
**Governing authorities:** maine-scratch-ev-spec.md §8 (polite scraping;
responsible-use framing binds every published surface);
`docs/specs/m6_v2_program_spec.md` house discipline (provenance, LF, offline
tests); M6a wayback precedent (one-time manual CLIs, resumable raw cache).

## Objective

Maine's winner publicity (Title 8 §374; the §378-B confidentiality carve-out
covers only $1M+ winners electing it) means claimed prizes are public, and
the Lottery's Winner Information page names winner, hometown, game, prize,
and the selling retailer + town. Align those reports — live captures plus
web.archive.org history — into one canonical dataset, then publish
probabilistic (empirical-Bayes shrunk) town/retailer trends.

## Design rules of record

1. **Dataset:** `data/winners/winners.jsonl`, one record per line, schema
   `data/schema/winner_record.schema.json`. `winner_key` = sha256 prefix of
   the normalized (names, town, game, prize, retailer) tuple — the page
   publishes no dates, so identity is the dedup key; `first_seen` = earliest
   capture date that showed the entry (earliest capture wins on merge).
2. **Parser:** text-pattern based (tag-stripped), tolerant of the curated
   page's real variance (missing prize/town/retailer-town, split claims,
   draw-game phrasing, typos, mangled apostrophes). Unstated fields are
   null — never guessed. `game_type` is conservative: "draw" only for the
   site's own draw-game names, "instant" only when the entry says so.
3. **Two strict layers:** offline parse/merge (tested; no network ever) vs.
   explicit owner-machine network CLIs:
   - `python -m scraper.winners fetch --as-of <D>` — ONE polite live
     request (project UA), merge.
   - `python -m scraper.winners wayback` — one-time CDX backfill
     (digest-collapsed, status-200, ≥2 s delay, resumable
     `data/winners/raw_cache/` — gitignored). Self-contained CDX client:
     `wayback_backfill.py` is never imported (purity test).
   Neither is referenced by `run_daily.py` or `daily.yml` (test-enforced).
4. **Trends:** `analysis/location_trends.py` → committed
   `data/insights/location_trends.json`. Purchase-town (where the ticket
   was SOLD) is the location signal of record; residence-town secondary;
   retailer counts descriptive. Per-capita rates use an embedded,
   source-labeled approximate 2020-Census table; Gamma-Poisson
   empirical-Bayes shrinkage (method-of-moments prior; wide unit-shape
   fallback when between-town variance is unmeasurable) with seeded
   posterior-draw 90% intervals; n<3 rows flagged `small_n`.
5. **Honesty (binding, §8):** every artifact and UI surface states that
   winner locations describe published PAST claims only and carry zero
   information about future tickets — every unsold ticket is uniformly
   random. The showcase is a curated rotating sample, not the statutory
   complete ledger; the artifact's caveats say so.

## File plan (touch nothing else)

`scraper/winners.py`, `data/schema/winner_record.schema.json`,
`data/winners/winners.jsonl` (seeded 2026-07-22 from the live page's
transcribed entries; see the fixture header), `analysis/location_trends.py`,
`data/insights/location_trends.json`,
`tests/scraper/fixtures/winners_showcase_2026-07-22.html`,
`tests/scraper/test_winners.py`, `tests/analysis/test_location_trends.py`,
`.gitignore` (+1 line), this spec, CLAUDE.md.

## Acceptance criteria

1. All 19 fixture entries parse; nulls where the page omits fields; split
   claims carry both names; schema-valid via `jsonschema`.
2. Merge idempotent; LF-only bytes; sorted (`first_seen`, `winner_key`);
   earliest `first_seen` wins.
3. Purity tests green (no run_daily/daily.yml reference, no
   wayback_backfill import); full pytest green offline.
4. Shrinkage sanity: an n=1 tiny-town raw rate is pulled toward the mean
   and cannot out-rank a large-sample town by raw-rate ratio; outputs
   deterministic for fixed seed.
5. Trends artifact regenerates byte-identically:
   `python -m analysis.location_trends --winners data/winners/winners.jsonl
   --as-of <D> --out data/insights/location_trends.json`.

## Owner runbook (network steps, owner-initiated only)

```
python -m scraper.winners wayback          # one-time backfill (resumable; LOCAL only, long-running)
python -m scraper.winners fetch --as-of $(date +%F)   # occasional refresh
python -m analysis.location_trends --winners data/winners/winners.jsonl \
    --as-of $(date +%F) --out data/insights/location_trends.json
```

Convenience paths (added 2026-07-23):
- **Windows one-shot:** `scripts\refresh_insights.cmd` — fetch + both
  artifacts + fast gate; commit is still a manual review step.
- **Actions button:** `.github/workflows/winners.yml` — workflow_dispatch
  ONLY (never scheduled; test-enforced): offline gate → one polite fetch →
  schema validation → trends rebuild → bot commit of exactly the two data
  files. `numpy` rides `requirements-dev.txt` (M6b Resolution 2 dev-only
  authorization; appended 2026-07-23).

## Out of scope

Adding winner fetches to `daily.yml` or ANY schedule (refresh stays
owner-triggered — dispatch button or local CLI); scraping any non-lottery
source; anything predictive.
