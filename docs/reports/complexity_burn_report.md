# Report: Ticket complexity × burn rate (descriptive study, 2026-07-22)

**Spec:** `docs/specs/complexity_burnrate_spec.md` · **Artifact:**
`data/insights/complexity_burn.json` · **Reproduce:**
`python -m analysis.complexity --panel data/panel/panel.jsonl --games
data/games.json --articles tests/scraper/fixtures/games --as-of 2026-07-22
--out data/insights/complexity_burn.json` (deterministic, seed 20260722).

**Standing constraint:** descriptive only. Confirmatory lag inference is
retired for this panel (M6b, `CONFIRMATORY_INFERENCE_RETIRED=True`). Every
number below is a Spearman rank association with a seeded bootstrap 95%
interval — no significance claims, no causes, no predictions.

## Data

482 lifecycles (2015–2026) in `data/panel/panel.jsonl`; **393 usable burn
arcs** (≥5 obs, first obs ≥50% unsold); **232 near-complete endings**
(exited, last sighting ≤5% unsold — the honest terminal-state proxy; only
15 arcs have a page-confirmed terminal record); **56 current-era games**
with play-mechanic components parsed from the frozen maine.gov articles.

A semantics fact that shapes everything: **presence on the unclaimed page
implies outstanding prizes** — claimed-out games/tiers are de-listed, so no
record ever shows zero top prizes remaining. "Ends with outstanding
winners" is therefore a quantity (how much remained at the last sighting),
never a binary against a comparison group the source cannot produce.

## Findings

1. **Typical burn is slightly slow.** Median burn gap +0.053 (mean +0.063):
   unclaimed money usually sits a little ABOVE the instant-claim diagonal
   while inventory sells — the aggregate claim-lag signature, visible
   descriptively without fitting anything.
2. **What a game leaves behind at its last sighting:** median 9.3% of its
   starting unclaimed dollars, and a median 2.8% of its value-weighted
   top-prize mass, with 48% tier attrition association below.
3. **Pooled, complexity tracks cleaner burn** — complexity vs burn gap
   ρ = −0.37 [−0.46, −0.28] (n=393); vs money left at the end ρ = −0.45
   [−0.56, −0.33] (n=232); vs top-prize survival ρ = −0.35 [−0.45, −0.24];
   vs top tiers claimed out ρ = +0.48 [+0.37, +0.59]. Bigger, more complex
   tickets burn cleaner and leave less behind.
4. **…but price is the dominant gradient.** Price alone vs burn gap:
   ρ = −0.39 [−0.48, −0.30] — as strong as the full index. Within single
   price bands the association mostly fades or flips: $1 games −0.34
   [−0.57, −0.05]; $2 +0.01 [−0.26, +0.29]; $3 +0.30 [−0.09, +0.63];
   $5 +0.18 [−0.05, +0.40]; $10–30 +0.17 [−0.19, +0.53]. **Read the pooled
   numbers as "the price tier drives burn," not as a complexity dial.**
   The one band with signal, $1 games, is where complexity varies most
   relative to price.
5. **Burn gap and top-prize survival barely correlate** (ρ = +0.05
   [−0.05, +0.16]): how fast the dollars burn and whether top prizes stay
   alive are close to independent margins — "available winners" is not a
   proxy for "money on sold-but-unclaimed tickets."
6. **Archetypes** (for the UI's scatter): slowest burners HOLIDAY $1,000S
   ($10, +0.63), JURASSIC PARK ($10, +0.54); fastest "8" ($2, −0.04),
   BASEBALL ($2, −0.02). Most complex current games: $70 MILLION SUPREME
   ($30, index 94), MAINE MILLIONS ($30, 85); least: CA$H IN ($1, 36).

## Caveats (carried in the artifact)

Curated-page censoring as above; `exited_unobserved` arcs are last-sighting
censored; mechanics cover only current-era fixture games; wayback arcs are
irregular-interval (trapezoid over observed points, never interpolated);
the complexity index is heavily price-loaded by construction — the
within-band strata are the honest read.
