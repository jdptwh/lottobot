# SPEC: Ticket-complexity scoring + lifecycle burn-rate study (descriptive)

**Author of record:** lead (cloud session) · 2026-07-22
**Status:** built and delivered with this spec (owner-directed batch build,
2026-07-22; the owner waived the pre-build spec touchpoint for this batch —
recorded, not precedent). Owner ACCEPT/REJECT applies to the whole batch.
**Governing authorities:** `docs/specs/m6_v2_program_spec.md` (M6b outcome is
binding: `CONFIRMATORY_INFERENCE_RETIRED=True` — descriptive claims only);
`docs/m6_semantics.md` (field semantics); maine-scratch-ev-spec.md §8
(responsible-use framing binds every published surface).

## Objective

Quantify, descriptively, whether **ticket complexity** (price, prize
structure, play mechanics) travels with the **burn rate** of a game's prize
money — how unclaimed dollars decline as inventory sells — and with how much
money / how many top prizes are still outstanding when a game leaves the
unclaimed-prizes board ("ends with outstanding winners").

## Constructs of record

1. **Complexity** — per lifecycle:
   - *Structural* components (every panel lifecycle, from its own first
     observation + `data/games.json` where covered): `price`,
     `n_top_tiers`, `log10_top_prize`, `top_prize_to_price`, `overall_odds`.
   - *Mechanic* components (only games covered by the frozen maine.gov
     article fixtures, `tests/scraper/fixtures/games/`): `match_rules`,
     `reveal_rules`, `max_multiplier`, `two_sided`, `instruction_words`.
   - `complexity_index` = mean of available z-scored components mapped by a
     FIXED transform (z −2.5→0, +2.5→100, clamped). Research index, not the
     M4a score; `mechanics` is null (never guessed) where no article maps.
2. **Burn** — per usable arc (≥5 obs, first obs ≥50% unsold), all relative
   to the arc's own first observation, no interpolation:
   - `burn_gap`: trapezoid-average of `u − (1 − s)` (u = unclaimed$ share of
     start; s = share of starting inventory sold). >0 = money lingers
     (slow burn / claim lag); <0 = money exits ahead of sales.
   - `u_last`, `top_value_survival`, `tier_attrition`: outstanding money /
     value-weighted top-prize mass / tiers claimed out at the LAST sighting.
3. **Censoring rule (binding):** presence on the unclaimed page implies
   outstanding prizes (claimed-out games/tiers are de-listed — no panel
   record ever shows zero top prizes remaining). "Ends with outstanding
   winners" is therefore quantified, never a binary vs. a comparison group
   the source cannot produce. `exited_unobserved` arcs are last-sighting
   censored; the `near_complete` cohort (exited, last pu ≤5%) is the
   terminal-state proxy.

## Deliverables (file plan — touch nothing else)

- `analysis/complexity.py` — NEW: constructs, Spearman + seeded bootstrap
  CIs (numpy, dev-only), price-band strata, CLI.
- `data/insights/complexity_burn.json` — NEW committed artifact
  (deterministic; inputs' sha256 + params + caveats embedded).
- `tests/analysis/test_complexity.py` — NEW: synthetic arcs with known burn
  shapes (machine gate per Rule 2/4), mechanics parser, determinism,
  noncash-tier guards.
- `docs/reports/complexity_burn_report.md` — findings write-up.
- This spec; CLAUDE.md "Current state".

## Acceptance criteria

1. Synthetic arcs of known shape produce metrics of the right sign
   (uniform ≈ 0, slow-burner > 0.4, fast-burner < 0); unusable arcs → null.
2. Mechanics parse ≥50 of the 58 frozen articles; games without articles
   carry `mechanics: null`.
3. Artifact regeneration is byte-identical for fixed (panel, seed, as-of):
   `python -m analysis.complexity --panel data/panel/panel.jsonl --games
   data/games.json --articles tests/scraper/fixtures/games --as-of <D>
   --out data/insights/complexity_burn.json`.
4. No NaN anywhere in the artifact (degenerate correlations publish null).
5. Purity: nothing under `scraper/` imports `analysis`; `requirements.txt`
   byte-unchanged; full pytest green offline.
6. Every published correlation carries n, CI, and a note; the artifact's
   `caveats` include the descriptive-only and censoring statements above.

## Out of scope

Any confirmatory/significance claim; any per-tier lower-tier hazard; any
runtime (`scraper/`, `daily.yml`) wiring; play-mechanic scraping beyond the
frozen fixtures (a new-game article refresh is an owner CLI decision).
