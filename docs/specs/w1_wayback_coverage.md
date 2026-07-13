# W1: Wayback coverage report — unclaimed_prizes.html (2026-07-13)

**Method:** CDX query (digest-collapsed, status 200) + parse-compatibility
samples across eras using the production M1 parser. Read-only lead recon per
panel plan point 2; raw numbers in the session scratchpad, headline facts here.

## Findings

- **287 unique captures, 2005 → 2026.** Per-year: single digits pre-2012,
  peak 19–30/yr in 2015–2019, **only 6–12/yr in 2022–2026**.
- **Cadence is MONTHLY-scale, not daily.** 2023+: 33 captures, median gap
  33 days, max gap 150 days, 25 gaps exceed 14 days. The archive is nowhere
  near a daily panel and must be treated as an irregular-interval series
  (exactly the panel's point-5 design assumption).
- **Parser compatibility by era:** current parser cleanly parses 2017 (66
  games), 2019 (73 games), and 2026 captures. 2013 fails (older column
  semantics — "PAC-MAN" era prize-cell format) and 2005 fails (no "as of"
  line). Usable era without a new parser: **~2015–2026, roughly 200 captures**;
  pre-2015 would need era-versioned parsers for marginal value.

## Verdict on the backfill (gates the M6 spec)

**GO, with bounded expectations.** The archive cannot provide fine-grained
(daily) claim-lag deltas — the lag kernel's short-time behavior still depends
on our own accumulating daily history. What ~200 monthly-scale captures DO
buy, and why backfill remains the right first acquisition:

1. **Complete game lifecycles** (dozens of games observed launch → sellout →
   disappearance) — lifecycle-phase pooling, end-of-life behavior, and the
   held-out-lifecycle backtests the panel's release gate (point 7) requires.
2. **Long-horizon pooled lag information:** monthly deltas still constrain a
   pooled dollar-weighted lag kernel at coarse scale (the panel's model is
   explicitly built for irregular intervals).
3. **Sales-velocity priors** and validation data for the current confidence
   bands (panel quick-win 4).
4. **Survivorship truth:** games that vanished between captures are
   interval-censored exits — usable, if modeled as such, never as clean exits.

**Implication for M6 scheduling:** backfill (~200 fetches from web.archive.org,
zero load on the state site) is a normal specced task; the M6 model spec should
assume {coarse historical panel + growing daily panel}, and its evidence-gated
release will bind primarily on the daily panel's accumulation for the
short-lag component.
