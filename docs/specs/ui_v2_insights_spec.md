# SPEC: Site v2 — three-view console (best pick / game insights / winner map)

**Author of record:** lead (cloud session) · 2026-07-22
**Status:** built and delivered with this spec. Mockup-of-record:
`docs/mockups/insights_v2_mockup.html` (embedded-data snapshot of the build,
renders offline; design notes in its header). The owner-directed batch build
compressed Rule 11's mockup-approval touchpoint into the batch ACCEPT/REJECT
— recorded, not precedent; the M4b mockup (99a4ee5) remains the identity
authority for view 1.
**Governing authorities:** `docs/ui_mockup_protocol.md` (rubric);
`docs/specs/m4b_site_spec.md` + `w2_v15_honesty_spec.md` (view-1 contract,
unchanged); §8 framing (binding on every view).

## Composition

`site/index.html` stays a single offline-clean file (no external assets, no
build step) and becomes a compact console: a sticky segmented control
switches three views —

1. **Best pick today** — the approved M4b/W2 page, structurally untouched
   (hero, shortlist, claim-lag, not-rated, price chips, explainer,
   staleness/error furniture, all binding copy).
2. **Game insights** — renders `../data/insights/complexity_burn.json`:
   stat-tile row; complexity×burn scatter (dots = lifecycles, categorical
   price-group colors, tooltips); Spearman interval-bar panel with the
   price-confounder callout; static burn-curve explainer; complexity table
   with mechanic chips.
3. **Winner map** — renders `../data/insights/location_trends.json`:
   stat-tile row; schematic Maine SVG (dot size = winners, sequential ramp =
   shrunk per-10k rate, approximate positions stated); shrunk town bars with
   90% whiskers + `n<3` badges; retailer table; coverage/honesty notes from
   the artifact's own caveats.

Views 2–3 lazy-fetch on first open; a missing artifact renders a
`.chart-empty` panel naming the generating command (never a broken chart).

## Data-viz rules (dataviz skill, applied)

Palette validated by the six-checks script on the cream surface `#fbf7ee`:
categorical `#2f8560 / #c98a2c / #ab4d79` (fixed order, entity-bound to
price groups; the gold slot's 2.74:1 contrast WARN is relieved with direct
labels + table views per the skill); diverging `#2f8560 / #b3542a` around a
neutral zero; sequential pine ramp (light→dark) for the map. Thin marks,
paper gaps/rings between fills, recessive grid, one axis per chart, legends
for multi-series, tooltips on every plot, text in ink tokens never series
colors.

## Honesty copy (binding additions)

- Insights intro + correlation note: descriptive-only; "price is the
  dominant gradient"; nothing predicts a win.
- Winner map intro, map sub, and footer: winner locations describe
  published past claims only, carry zero information about future tickets;
  every unsold ticket is uniformly random.

## Verification

- `tests/site/test_site_static.py` extended: fetch anchor amended to
  "exactly one fetch per committed artifact, nothing external"; v2 view +
  honesty-copy fragments pinned; mockup-of-record existence + MOCKup marker
  pinned; all M4b/W2 copy anchors unchanged and green.
- Browser smoke (performed at build): all three views render at 420px and
  1100px with zero console/page errors, live server and file:// (mockup).

## Out of scope

Any change to the M5 pipeline or `latest.json` contract; dark mode (site
has a single light identity); external tiles/fonts/libs of any kind.
