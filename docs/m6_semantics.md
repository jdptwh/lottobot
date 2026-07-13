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

### Prize-claim deadline (Game End vs. Last Cash Date)

**Source:** `tests/scraper/fixtures/scratchdates_2026-07-11.html` (frozen
fixture; live page `https://www.mainelottery.com/instant/scratchdates.html`,
titled "Maine State Lottery: Instant Ticket Game End Dates").

**The page's own column semantics** (quoted intro paragraph, immediately
above the table): "Here is information about the game ending dates for our
current instant ticket games. The Game End date is the date on which the
Maine State Lottery no longer has this ticket available for shipment to our
retail locations. The instant ticket game can still be sold by our lottery
retail agents after Game End Date." A table footnote adds: "**Lottery office
out of inventory. Agents can sell games after Game End Date." The table's
own column headers are `Game Number`, `Game Name`, `Game End**`, `Last Cash
Date` — the page names the second date column "Last Cash Date" but does not
itself define the term in prose (no sentence anywhere on the page says "N
year(s) after Game End" in words).

**Computed/verified relationship:** inspecting every row in the fixture
table (`Last Cash Date` column vs. `Game End**` column), the two dates are
identical calendar day-of-month, with `Last Cash Date` exactly **one year**
after `Game End` in every sampled row, e.g.:

| Game No. | Game Name | Game End | Last Cash Date |
|---|---|---|---|
| 707 | $60,000 CASHWORD | July 31, 2026 | July 31, 2027 |
| 704 | SILVER 7's | June 30, 2026 | June 30, 2027 |
| 697 | PATRIOTS | June 30, 2026 | June 30, 2027 |
| 683 | LADY LUCK | June 30, 2026 | June 30, 2027 |
| 710 | $500 CA$H! | May 31, 2026 | May 31, 2027 |
| 698 | $50 OR $100 | May 31, 2026 | May 31, 2027 |
| 684 | WINNING STREAK | April 30, 2026 | April 30, 2027 |
| 680 | ACE IN THE HOLE | April 30, 2026 | April 30, 2027 |

No row in the fixture deviates from the +1-year pattern. **Finding:** the
claim deadline for a Maine instant game is one calendar year after its
published Game End date — a relationship established here by direct
computation over the published table, not stated by the page in a single
declarative sentence (the page names the column but never spells out the
"+1 year" rule in prose). This is treated as an established fact (not a
"could not establish" item) because it holds without exception across the
sampled rows, but it is a page-computed inference, not a directly quoted
rule — flagged here for that distinction.

**Consequence for the program:** the claim-lag model's terminal boundary
(a game's unclaimed-dollar trail necessarily goes to zero) is one year past
Game End, giving a hard upper bound on the observation window per lifecycle
for Phase 1/2's distributed-lag work.

### Official meaning of "percent unsold" / "unclaimed"

**Source:** `tests/scraper/fixtures/unclaimed_prizes_2026-07-11.html` (frozen
fixture; live page `https://www.mainelottery.com/players_info/unclaimed_prizes.html`,
titled "Maine State Lottery: Instant Tickets > Unclaimed Prizes"). This page
carries only two pieces of prose: the intro line above the table and the
"Disclaimer" section below it — no glossary, footnote, or methodology
section defines the columns.

**Intro line (quoted in full):** "Below is the list of **top unclaimed
prizes** for current instant games as of July 10, 2026 5:00 AM." The table
columns are `Price Point`, `Game No.`, `Game Name`, `Percent Unsold`, `Total
Unclaimed`, `Top Prize Level(s)`, `Top Prize(s) Unclaimed` — the row-per-game
`Percent Unsold` and `Total Unclaimed` cells sit alongside a row-per-tier
breakdown of `Top Prize Level(s)` / `Top Prize(s) Unclaimed` (multiple
sub-rows per game, one per remaining top-prize tier).

**Disclaimer paragraph (quoted in full):** "It is the policy of the Maine
State Lottery to remove instant ticket games for sale once the top prize(s)
are sold out unless the secondary prizes are deemed significant. A current
list of top prizes remaining may be obtained from any Maine State Lottery
sales agent upon request. The information on this site is provided as a
service of the Maine State Lottery and is updated daily. While every attempt
is made to maintain an accurate list, the Maine State Lottery accepts no
responsibility for the use or dissemination of information contained herein.
In the event of a discrepancy between the information on this site and the
Maine Lottery **Official Outstanding Prize List**, the **Official Outstanding
Prize List shall prevail**."

**Findings established:**
- The page is explicitly a **"list of top unclaimed prizes"** (intro line),
  and its own retirement policy (disclaimer sentence 1) ties game removal to
  **top-prize** sellout, not overall ticket sellout — reinforcing that this
  page's frame of reference is the top-prize tier(s), not the game's full
  prize structure.
- The page is not itself authoritative in case of conflict: the disclaimer
  names a separate document, the "Official Outstanding Prize List," as the
  prevailing source — a document not consulted in this program (outside
  scraping scope; the non-scraping data request to the Lottery mentioned in
  the program spec risks section would be the path to it).
- The page states it is "updated daily" but does not state the update
  mechanism, source system, or whether "Percent Unsold" and "Total Unclaimed"
  are computed by the same process or independently.

**Finding: could not establish** (recorded explicitly as unresolved, per
program spec rule 6, to become stated model assumptions in Phase 1/2):
- **Whether `percent_unsold` is by ticket count or by dollar value.** Neither
  the intro line nor the disclaimer states the denominator or numerator basis
  for the percentage. The column is simply labeled "Percent Unsold" with no
  further definition anywhere on the page.
- **Whether `total_unclaimed` spans ALL prize tiers or only the listed top
  tiers.** The intro line's own wording — "list of **top** unclaimed prizes"
  — is itself ambiguous evidence: it could describe only the `Top Prize
  Level(s)` sub-rows (which are explicitly tier-by-tier), while
  `Total Unclaimed` sits in the same row as the per-game `Percent Unsold`
  cell and could plausibly be a broader, whole-game unclaimed-dollar figure.
  The page never resolves this either way. **This ambiguity is flagged
  honestly rather than resolved by assumption here** — Phase 1/2 must treat
  `total_unclaimed`'s tier coverage as an open question, not a fact.
- **Rounding conventions.** `Percent Unsold` is published to one decimal
  place (e.g. `13.8`, `0.0`) and `Total Unclaimed` to whole cents (e.g.
  `$3,061,780.00`), but the page states no rounding rule (round-half-up vs.
  truncation vs. banker's rounding) for either figure. The panel's
  `pu_interval` field (program spec rule 2) already treats the 0.1-point
  granularity as interval censoring for exactly this reason, rather than
  assuming exact rounding behavior.
