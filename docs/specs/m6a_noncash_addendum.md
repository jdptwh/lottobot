## SPEC ADDENDUM: M6a noncash-prize (vehicle) parse failures — planner arbitration
**Governs:** the CP2 corrective work item under `docs/specs/m6_v2_program_spec.md` Phase 0
**Author of record:** PLANNER (`claude-fable-5`) · 2026-07-13 · escalation: AC-7 shortfall (135 < 150), single failure class (53 captures, all vehicle-prize cells: CHEVROLET CAMARO 2SS ×30, FORD F-150 LARIAT SUPERCREW ×22, FORD EXPLORER LIMITED HYBRID ×1; 2015–2018 + one 2020)

### Ruling

1. **Tolerance lives in `scraper/scrape.py` as an opt-in parameter** — `parse(html, *, prize_level_tolerant=False)`. A wrapper in `wayback_backfill.py` is rejected: the failure occurs mid-row inside `parse`'s row walk (including the continuation-row path), so a wrapper would duplicate the entire table parse — exactly the drift the panel-vs-site contract split does not license. Unconditional extension is rejected: production must keep failing loudly if Maine ever runs a vehicle game again — a separate, considered decision. The middle path gives one parse implementation, byte-identical production behavior at the default, and an explicit opt-in only `wayback_backfill.py` uses.
2. **Noncash representation (panel schema only):** in tolerant mode, a non-numeric top-prize cell yields `{"level": null, "level_label": "<cell text verbatim, whitespace-normalized>", "remaining": <int>}`. `panel_record.schema.json` changes are additive: `level` becomes `["integer","null"]`; optional `level_label` (string); a `level: null` item MUST carry `level_label` (schema-enforced). New **required** record-level field `has_noncash_prize` (boolean): true iff any `top_prizes` item has `level: null`. The frozen site schema (`data/schema/latest.schema.json`) is untouched — these games never enter `latest.json`.
3. **`total_unclaimed` semantics:** whether the page's dollar total includes vehicle value is **unknowable from the page alone**. The record does not guess — the `has_noncash_prize` flag exists so Phase 1 excludes or sensitivity-tests those lifecycles (panel blind spot 1 guidance). `docs/m6_semantics.md` gains an entry naming the three vehicle prizes as concrete instances and recording this as an explicit "could not establish" item.
4. **AC-7 restated (bar unchanged):** ≥ 150 in-era captures parsed — expected 188 of ~190 after this fix. The 2 permanent fetch failures are recorded in the run log as acceptable losses; the log still accounts for every capture (parsed / duplicate / era-skipped / fetch-failed / parse-failed with URL).
5. **This is a one-class fix, not a program change.** Free-ticket, annuity, or any other future noncash form is NOT being generalized here; a new non-numeric cell class should still surface as a logged parse failure for human review (tolerant mode is generic to non-numeric cells by mechanism, but no new tolerance policy beyond this parameter is created).

### Design rules

1. `_parse_prize_level` gains `tolerant: bool = False`; on failure with `tolerant=True` it returns the sentinel/label instead of raising; with `tolerant=False` behavior and the `ParseError` message are byte-identical to today. `parse` threads the flag to **both** call sites (game row and continuation row).
2. `wayback_backfill.py` calls `parse(html, prize_level_tolerant=True)`, sets `has_noncash_prize` per record, and bumps `PARSER_VERSION` to `"scraper.scrape@2"` (output shape changed; the re-run rewrites all records so the version is uniform).
3. The re-run is a **pure cache re-parse**: `run_backfill` against the existing `data/panel/raw_cache/` — cache-first means zero new fetches; zero requests to any host is the expectation, and the near-instant runtime plus log confirm it.
4. `build_panel.py` passes `top_prizes` through opaquely — expected unchanged. If it turns out to validate or transform prize items, stop and report; do not widen scope silently.

### File plan (touch nothing else)

- `scraper/scrape.py` — MODIFIED (rule 1 only; no other edits).
- `scraper/wayback_backfill.py` — MODIFIED (rule 2).
- `data/schema/panel_record.schema.json` — MODIFIED, additive (ruling 2).
- `tests/scraper/fixtures/wayback/` — NEW frozen fixture: one real cached 2015–2018-era capture containing a vehicle prize cell.
- `tests/scraper/test_scrape.py` — NEW tests only; zero edits to existing tests.
- `tests/scraper/test_wayback_backfill.py` — NEW tests for the tolerant record shape + flag + schema validation.
- `data/panel/wayback_observations.jsonl` — regenerated artifact (committed).
- `docs/m6_semantics.md` — one addendum entry (ruling 3).
- `CLAUDE.md` — "Current state" at close.
- Do NOT touch: `scraper/compute.py`, `scraper/build_panel.py`, `scraper/run_daily.py`, `scraper/games.py`, `.github/workflows/daily.yml`, `data/latest.json`, `data/schema/latest.schema.json`, `data/history/`, `site/`, `requirements.txt`, any existing test or fixture.

### Acceptance criteria

1. **Production invariance:** full `python -m pytest -q` green with zero modifications to pre-existing tests/fixtures; a new test asserts default-mode `parse` on the vehicle fixture raises `ParseError` with the existing `malformed prize-level cell` message.
2. **Tolerant equivalence:** on an all-cash fixture, tolerant and default output are equal (structural equality test).
3. **Tolerant parse of the vehicle fixture:** the affected game's prize item has `level: null`, `level_label` verbatim (whitespace-normalized), integer `remaining`; other games in the capture parse identically to before.
4. **Schema:** regenerated records all validate; a `level: null` item without `level_label` is schema-rejected (negative test); `has_noncash_prize` present on every record, true exactly for vehicle-prize games.
5. **Re-run (CP2 retake, human-observed):** pure cache re-parse, zero live fetches; **≥ 150 parsed (expected 188)**; the 2 permanent fetch failures logged as acceptable losses; all records carry `parser_version: "scraper.scrape@2"`.
6. `docs/m6_semantics.md` entry per ruling 3.

### Out of scope

Any change to production `parse` default behavior; free-ticket/annuity generalization; era-versioned parsers; `build_panel.py` (unless rule 4's stop fires); the frozen site schema; valuing vehicles in EV anywhere, ever.

### Tier / budget

**IMPLEMENTER** (touches the frozen M1 parser — reviewer must verify production-path invariance line by line; AC-1/AC-2 are the machine half). Loop budget tightened: MAX_IMPL_ATTEMPTS=2, MAX_REVIEW_CYCLES=2.

### Checkpoint

**CP2a** — code + schema + tests green offline; commit. **CP2b** — regenerated `wayback_observations.jsonl` committed with the run log summary in the commit message; AC-7 satisfied. M6a then resumes at the original spec's CP3 (canonical panel + semantics note + owner touchpoint) unchanged.

### Rule-4a amendment (planner-ruled 2026-07-13, after the rule-4 stop fired)

The required `has_noncash_prize` field made two surfaces outside the original
file plan unsatisfiable: `scraper/build_panel.py` (daily-record builder) and
`tests/scraper/test_build_panel.py` (synthetic record helpers). Ruling: daily
records emit `has_noncash_prize: false` **by construction** — they derive from
`data/latest.json`, whose games passed the strict production parser, which
rejects any non-numeric prize cell, so a vehicle prize cannot exist in that
data. The file plan is extended by exactly those two files (the record-builder
line + helper/test updates). Daily records correctly retain
`parser_version: "scraper.scrape@1"` (the strict parser is unchanged; `@2`
marks tolerant-mode wayback records only). AC-7 additions: (a) every daily
record asserts `has_noncash_prize is False`; (b) a wayback record's flag value
survives `merge_panel` verbatim (never recomputed). The implementer's
pre-amendment stop-and-report was correct conduct and does not count against
MAX_IMPL_ATTEMPTS.
