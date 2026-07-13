# M6 semantics note

Sourced facts (with URLs/quotes) and explicit "could not establish" items
about what the Maine Lottery's published unclaimed-prizes figures actually
mean. Governed by `docs/specs/m6_v2_program_spec.md` Phase 0 design rule 6
(the fuller three-question research pass — official "percent unsold"/
"unclaimed" meaning, the prize-claim deadline, and noncash/annuity/
free-ticket treatment in general — is a separate CP3 item under that spec;
this file is structured so entries can be appended there without
renumbering). Unresolved items are stated model assumptions for Phase 1/2,
never silent guesses (program spec §Risks).

## Entries

### Ruling 3 — noncash (vehicle) prizes in `total_unclaimed` (docs/specs/m6a_noncash_addendum.md)

**Question:** does the page's `total_unclaimed` dollar figure for a game
whose top prize is a physical item (a vehicle) include an assessed dollar
value of that item, or only the cash-denominated prize tiers beneath it?

**Concrete instances observed in the wayback backfill** (all pre-2015-era
Maine instant games whose top-prize-level cell is a vehicle name, not a
dollar amount — the class of parse failure `scraper/wayback_backfill.py`'s
`prize_level_tolerant` opt-in now handles instead of raising):

- **CHEVROLET CAMARO 2SS** — game 229 "CAMARO" ($5, observed 2015-01-01
  capture), ×30 across the backfilled captures.
- **FORD F-150 LARIAT SUPERCREW** — ×22 across the backfilled captures.
- **FORD EXPLORER LIMITED HYBRID** — ×1 (one 2020-era capture).

**Finding: could not establish.** The unclaimed-prizes HTML page itself
states only a single `Total Unclaimed` dollar figure per game and does not
document its own composition rule for noncash top prizes anywhere on the
page (no legend, footnote, or disclaimer text distinguishes cash-only from
cash-plus-item totals). No other public Maine Lottery page consulted in this
program states the valuation convention either. This is therefore recorded
as an explicit "could not establish" item, not inferred either way.

**Consequence for the panel and downstream analysis:** `data/schema/panel_record.schema.json`
adds a required `has_noncash_prize` boolean (true iff any `top_prizes` item
has `level: null`, i.e. a noncash cell) precisely so Phase 1/2 can exclude
or sensitivity-test these lifecycles rather than have the pooled kernel
silently absorb an unknown, possibly large, valuation bias (program spec
panel blind spot 1 guidance). Vehicles are never assigned an EV anywhere in
this program, in any phase.
