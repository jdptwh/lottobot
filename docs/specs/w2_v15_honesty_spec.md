## SPEC: W2 — v1.5 honesty pass (upper-bound labeling, inventory intervals, sensitivity scenarios, launch-odds anchor)

**Author of record:** PLANNER (`claude-fable-5`) · 2026-07-13
**Origin:** M6 data-strategy panel verdict, plan point 4 (`docs/specs/m6_data_strategy_panel.md`) — ship v1.5 before fitting M6. The dissent ruling is binding here: **lag discounts are scenarios, never bounds** (the assumption-free lower bound is effectively zero; synthesis sided with Expert B). Nothing in this spec presents any discount as fitted, measured, or bounding.
**Authorities:** maine-scratch-ev-spec.md §4 (additive-only frozen contract), §8 (responsible-use tone — all new copy below is planner-authored and binding); `docs/specs/m4a_scoring_spec.md` and `docs/specs/m4b_site_spec.md` (binding; amended ONLY where the "Amendments of record" section below says so); `docs/specs/m5a_test_rebaseline_spec.md` (frozen-artifact discipline — extended, not reopened); `docs/specs/m5_daily_action_spec.md` (the bot owns `data/latest.json`; this task never touches it).
**Rule 11 applies:** the site has UI changes; the existing approved mockup is amended IN PLACE and the HUMAN approves the amended mockup before any `site/index.html` change (Resolution 7).
**Lead pre-dispatch verification (2026-07-13):** worksheet A–C machine-verified against the frozen artifact + `data/games.json` — every pinned number exact, including the 630 s0.5 half-up midpoint. One prose correction applied: `overall_odds_launch` coverage is **56/65 active games** (the 58 figure counted the two pre-launch articles).

## Objective

Make the live product tell the truth about what it knows, in three moves plus one new anchor — all additive, all offline-deterministic:

1. **Upper-bound labeling:** naive EV is an UPPER BOUND on unclaimed prize value per estimated unsold ticket, and every user-facing surface says so (short cue on the hero, full form in the explainer).
2. **Interval-ized inventory:** the state's 0.1-point `percent_unsold` rounding is propagated into published intervals for remaining tickets and EV ratio (interval censoring made visible; never "exact daily sales").
3. **Sensitivity scenarios:** three pinned what-if claim-lag discounts published per game as `ev_scenarios` — labeled as illustrative scenarios, never bounds, never a fitted correction. `ev_ratio_adjusted` stays `null` until M6 ships through its point-7 release gate.
4. **Launch odds anchor:** the printed "overall odds of winning any prize: 1 in N" from `data/games.json` is carried through the pipeline and displayed. Full launch/book EV is NOT computable today (see Resolution 3) and is explicitly deferred to M6 Phase-0 prize-table recovery.

Plus one integrity amendment: highly depleted games become ineligible for "best pick" (panel point 4; Resolution 6).

## Amendments of record (explicit; nothing else in M4a/M4b is reopened)

- **M4a:** scoring semantics, formula, weights, bands, degenerate rule — **UNCHANGED** (Resolution 5). The copy bank is EXTENDED with the new binding strings below; the eight existing strings are byte-unchanged.
- **M4b amendment 1 (eligibility predicate):** `eligible(g) := g.rated === true && !g.flags.includes("ev_out_of_range") && !g.flags.includes("low_inventory")`. Flag-keyed, per the M4b triple-lock discipline. (Resolution 6, owner-visible.)
- **M4b amendment 2 (section):** the claim-lag section generalizes to **"Excluded from best pick"** = all `rated && !eligible` games (claim-lag + depleted). Partition invariant preserved: eligible ∪ excluded ∪ not-rated = all 65. The verbatim claim-lag caveat ("…warning sign, not a tip.") is retained unchanged as its subheading, followed by the new depletion sentence (copy bank).
- **M4b amendment 3 (detail sheet):** gains the EV-range row, the scenario block, the launch-odds row, and upper-bound qualifiers on EV labels. `ev_ratio_adjusted` still renders "— pending (v2)" unchanged.
- **M4b amendment 4 (explainer):** one sentence inserted (copy bank); the rest verbatim as shipped.
- **M4b amendment 5:** the detail-sheet note "Launch-odds comparison pending (v2)." is replaced by the launch-odds row plus the book-EV pending note (copy bank).

## Design rules (pipeline — rules of record)

**New fields, appended to every game object after `"reason"`, in this pinned order** (byte-stable diffs, M4a precedent): `remaining_tickets_min`, `remaining_tickets_max`, `ev_ratio_min`, `ev_ratio_max`, `ev_scenarios`, `overall_odds_launch`. Additive to the frozen §4 contract; schema `required` untouched.

**Interval propagation (Resolution 2 — publish BOTH pairs):** published `percent_unsold` at 1 dp means the true percent lies in `[p − 0.05, p + 0.05]` (closed both ends; conservative), clipped to `[0.0, 100.0]`.
- `remaining_tickets_min = round(max(p − 0.05, 0.0) * print_run / 100)` (int); `remaining_tickets_max = round(min(p + 0.05, 100.0) * print_run / 100)` (int). Python built-in `round()`; float dust at ~1e-7 tickets is immaterial and the worksheet values are the authority.
- `ev_ratio_max = round(total_unclaimed / remaining_tickets_min / price, 6)` — computed FROM the published int `remaining_tickets_min` (fewer tickets ⇒ higher EV). `ev_ratio_min = round(total_unclaimed / remaining_tickets_max / price, 6)`. This is the M4a-style documented deviation from M3's raw-intermediate rule, made so a human can reproduce both ends from `latest.json` alone; document it in the module docstring.
- **Nullity:** all four fields are `null` iff `ev_ratio` is `null` (intervals are pure math propagation — they ARE computed for dead and OOR games with non-null `ev_ratio`). Guard: if `remaining_tickets_min == 0`, `ev_ratio_max` is `null` (unbounded above; never publish infinity or a fake cap).

**Sensitivity scenarios (Resolutions 4 + 9):** module constant `SCENARIO_CLAIMED_SHARES = (0.5, 0.8, 0.95)` (the panel's defaults, pinned). For each game with non-null `ev_ratio`, `ev_scenarios` is a 3-element array ordered by ascending share: `{"assumed_claimed_share": s, "ev_ratio": v}` where `v` is computed by **exact integer-decimal arithmetic** to kill float-midpoint ambiguity (s = 0.5 hits a decimal midpoint whenever the 6th dp of `ev_ratio` is odd): let `n = round(ev_ratio * 10**6)` (exact int of the published value); `v = ((n * (100 − share_pct)) + 50) // 100 / 1_000_000` — half-up rounding to 6 dp, hand-reproducible from `latest.json` alone. `ev_scenarios` is `null` (never `[]`) when `ev_ratio` is `null`. Semantics: "if share s of unclaimed value sits on already-sold tickets, unsold-stock EV ratio would be `ev_ratio × (1 − s)`". Data carries numbers only; labels live in the site copy bank. `ev_ratio_adjusted` remains `null` everywhere — no code path may write it (M6 release-gate property).

**Launch odds anchor (Resolution 3):** `overall_odds_launch` = `games.json` `overall_odds` for the game_no (currently 56/65 active games non-null), `null` when absent — carried verbatim, never computed. `compute_latest` now consumes a third key from `games_meta` (`print_run`, `top_prize_value`, `overall_odds`); missing game_no still never crashes.

**Untouched semantics:** `ev_ratio` (never clamped), scoring/grades/reasons (M4a), rateability, confidence, flags vocabulary (no new flags), `diff_gate` (operates on `ev_ratio` only — the new fields must never trip or enter it), CLI surface (no new arguments).

## Design rules (site — rules of record)

- **Feature detection (version-skew guard):** the bot owns `data/latest.json`; the site deploys before the next daily run writes the new fields. All new rendering goes through one named function `normalizeGame(g)` that, when `ev_ratio_min` is `undefined` on a game, supplies `null`/absent-safe defaults so the page renders exactly the pre-W2 view — no crash, no "undefined" text. Lint anchors the function name; the reviewer reads the guard end-to-end.
- **Eligibility + excluded section** per M4b amendments 1–2. `isEligible` gains the `low_inventory` check; new `isExcluded(g) := g.rated === true && !isEligible(g)`. Excluded rows show their real grade + score + verbatim `reason` — scored but unrankable, honestly displayed, never in hero/shortlist.
- **Hero card** gains one muted qualifier line (copy bank `qual_hero`), below the reason. Short — the full form lives in the explainer.
- **Detail sheet:** EV labels become "EV per ticket (upper-bound est.)" and "EV ratio (upper-bound est.)"; new row "EV ratio range" rendering `ev_ratio_min`–`ev_ratio_max` at 2 dp each ("—" for any null end; a collapsed range like "0.80 – 0.80" is correct and honest — tight interval); new row "Overall odds at launch" rendering "1 in {overall_odds_launch}" (verbatim number, e.g. "1 in 3.52"; "—" when null); scenario block rendering the three scenarios with the copy-bank label template and 2-dp values, closed by the `scenario_disclaimer` line; the `book_ev_pending` note replaces "Launch-odds comparison pending (v2).".
- **Explainer:** `explainer_upper_bound` sentence inserted immediately after the first sentence of the shipped explainer; everything else byte-unchanged.
- Scenario values and intervals are **rendered, never recomputed**, and never charted or time-seriesed (M4a risk rule extends to them).

**Copy bank additions (planner-authored, BINDING — exact strings; implementer may not reword):**

| Key | String |
|---|---|
| `qual_short` | `"upper-bound est."` |
| `qual_hero` | `"Built on an upper-bound EV estimate — the true expected value is lower."` |
| `explainer_upper_bound` | `"That expected value is an upper bound on unclaimed prize value per estimated unsold ticket — some unclaimed prizes sit on tickets already sold but not yet claimed, so the true expected value is lower."` |
| `interval_label` | `"EV ratio range"` |
| `interval_sublabel` | `"from the state's 0.1-point inventory rounding"` |
| `scenario_heading` | `"What if some of it is already claimed-in-waiting?"` |
| `scenario_label` (template) | `"If {pct}% of unclaimed value is on already-sold tickets"` (pct ∈ {50, 80, 95}) |
| `scenario_disclaimer` | `"Illustrative scenarios, not bounds — no measurement yet says which assumption is right."` |
| `launch_odds_label` | `"Overall odds at launch (any prize)"` |
| `book_ev_pending` | `"Full launch (book) EV needs the complete prize table — pending (M6)."` |
| `excluded_heading` | `"Excluded from best pick"` |
| `depleted_note` | `"Nearly sold-out games are also excluded: with so few tickets left, the estimate is too unstable to rank."` |

## File plan (touch nothing else)

- `scraper/compute.py` — extend: interval fields, `SCENARIO_CLAIMED_SHARES` + integer-decimal scenario computation, `overall_odds_launch` passthrough, docstring updates (deviation notes). No CLI changes, no scoring changes.
- `data/schema/latest.schema.json` — additive optional properties on `$defs.game.properties`: `remaining_tickets_min`/`remaining_tickets_max` `{"type": ["integer","null"]}`; `ev_ratio_min`/`ev_ratio_max` `{"type": ["number","null"]}`; `ev_scenarios` `{"type": ["array","null"], "minItems": 3, "maxItems": 3, "items": {object, required ["assumed_claimed_share","ev_ratio"], "assumed_claimed_share" enum [0.5, 0.8, 0.95], "ev_ratio" number}}`; `overall_odds_launch` `{"type": ["number","null"]}`. `required` list untouched (M1's verbatim §4-example test stays green).
- `tests/scraper/fixtures/latest_2026-07-11.json` — **RE-FROZEN IN PLACE at CP1** (Resolution 8): regenerate via `python -m scraper.compute --unclaimed tests/scraper/fixtures/unclaimed_prizes_2026-07-11.html --games data/games.json --as-of 2026-07-11 --out tests/scraper/fixtures/latest_2026-07-11.json` (LF bytes, guaranteed by the m5a `newline="\n"` fix). The lead runs the **additive-only check** before committing: parse both versions, strip the six new keys from every game in the new artifact, assert deep-equality with the old — recorded in the CP1 commit message.
- `tests/scraper/test_v15_honesty.py` — NEW file for all pipeline W2 tests (M3/M4a/M5a test files provably untouched via `git diff --stat`, per M4a precedent).
- `tests/site/test_site_static.py` — extended (this file's classes are the designated home per m5a): `TestFrozenArtifactRegression` gains the worksheet exacts below; `TestContract` gains **conditional** invariants only (`if "ev_ratio_min" in g:` style — a guard that fires fully once the bot writes v1.5 data, never a count, never a game_no pin against the live file); the lint gains the new required substrings: `upper-bound est.`, `true expected value is lower`, `Excluded from best pick`, `not bounds`, `at launch`, `pending (M6)`, `normalizeGame` (build only), and for the mockup the "MOCKUP ONLY" marker rule is unchanged.
- `docs/mockups/best_pick_mockup.html` — AMENDED IN PLACE (Resolution 7): qualifier line, EV-range row, scenario block, launch-odds row, excluded-section rename + depletion note, explainer sentence, sample data extended with the new fields (worksheet values for 720/630/702; others may be synthesized consistently). Human approves the amended mockup before build (Rule 11 third touchpoint).
- `site/index.html` — amended ONLY after mockup approval, per the site design rules above.
- Do NOT touch: `data/latest.json` (bot-owned), `data/games.json`, `data/history/`, HTML fixtures, `scraper/scrape.py`, `scraper/games.py`, `scraper/run_daily.py`, `.github/`, existing test files other than `tests/site/test_site_static.py`, `docs/specs/*` (prior specs are amended by THIS document, not edited), `panel/`, `.claude/`.

## Hand-check worksheet (lead machine-verified 2026-07-13; asserted exactly at AC-4)

All inputs from the current frozen artifact + `data/games.json`.

**A. Game 720 — CROSSWORD (healthy game: tight interval).** p 89.2, print_run 1,560,000, total_unclaimed 5,572,450, price 5, ev_ratio 0.800916, overall_odds 3.52.
`remaining_tickets_min` = round(89.15 × 15,600) = **1,390,740**; `remaining_tickets_max` = **1,392,300**.
`ev_ratio_max` = round(5,572,450/1,390,740/5, 6) = **0.801365**; `ev_ratio_min` = round(5,572,450/1,392,300/5, 6) = **0.800467**.
Scenarios (n = 800,916): s0.5 → **0.400458**; s0.8 → **0.160183**; s0.95 → **0.040046**. `overall_odds_launch` = **3.52**.

**B. Game 630 — $500,000 ROYAL CASH (the hero; midpoint case: 6th dp odd, s0.5 rounds half-up).** p 11.2, print_run 960,000, total_unclaimed 2,940,760, price 20, ev_ratio 1.367541, overall_odds 2.84.
`remaining_tickets_min` = round(11.15 × 9,600) = **107,040**; `remaining_tickets_max` = **108,000**.
`ev_ratio_max` = **1.373673**; `ev_ratio_min` = **1.361463**.
Scenarios (n = 1,367,541): s0.5 = (68,377,050+50)//100 = 683,771 → **0.683771** (exact decimal midpoint 0.6837705, half-up by the integer rule — the reason the rule exists); s0.8 → **0.273508**; s0.95 → **0.068377**. `overall_odds_launch` = **2.84**.

**C. Game 702 — HOLIDAY $500S (depleted claim-lag game: the interval blows wide — the honesty exhibit).** p 0.4, print_run 960,000, total_unclaimed 166,190, price 5, ev_ratio 8.655729 (published unclamped per M3), overall_odds 3.56.
`remaining_tickets_min` = round(0.35 × 9,600) = **3,360**; `remaining_tickets_max` = **4,320**.
`ev_ratio_max` = round(166,190/3,360/5, 6) = **9.892262**; `ev_ratio_min` = round(166,190/4,320/5, 6) = **7.693981**.
Scenarios (n = 8,655,729): s0.5 → **4.327865** (midpoint 4.3278645, half-up); s0.8 → **1.731146**; s0.95 → **0.432786**. `overall_odds_launch` = **3.56**. Intervals and scenarios ARE computed for OOR games — propagation is orthogonal to rating.

## Acceptance criteria

1. All 65 games in the re-frozen artifact carry all six new fields in the pinned key order after `reason`; the document validates against the updated schema; the additive-only check (strip six keys ⇒ deep-equal old artifact) passed at CP1 and is recorded in the commit message.
2. **Nullity coupling** (frozen artifact + synthetic): `ev_ratio == null ⟺ remaining_tickets_min/max == null ⟺ ev_ratio_min == null ⟺ ev_scenarios == null`; `ev_ratio_max` additionally `null` iff `remaining_tickets_min == 0` (synthetic test — no fixture case); `overall_odds_launch` independent of all of it (586 → null; 720 → 3.52).
3. **Ordering/coherence invariants** (every non-null game, frozen artifact AND conditionally on live data): `remaining_tickets_min ≤ remaining_tickets ≤ remaining_tickets_max`; `ev_ratio_min ≤ ev_ratio ≤ ev_ratio_max`; `ev_scenarios` exactly 3 items, shares ascending (0.5, 0.8, 0.95), scenario `ev_ratio` strictly decreasing and every one `< ev_ratio`; `ev_ratio_adjusted` still `null` for all 65.
4. **Worksheet A–C asserted exactly** (every pinned number above) against the re-frozen artifact in `tests/scraper/test_v15_honesty.py`.
5. **Integer-decimal scenario rule** unit-tested synthetically: an `ev_ratio` with odd 6th dp yields the half-up result at s0.5 (e.g. 1.000001 → 0.500001, never 0.500000); a `float`-naive implementation fails this test.
6. **Scoring untouched:** every `value_score`/`grade`/`rated`/`reason` byte in the re-frozen artifact identical to the prior artifact (implied by AC-1's additive-only check; also directly asserted: 630 → 95/A, OOR set still 11, rated set still 38). `diff_gate` tests green unmodified.
7. **Eligibility amendment:** the frozen-artifact excluded-by-`low_inventory`-only set is EMPTY (machine-asserted — the amendment changes nothing on current data; eligible remains 27, top eligible 630); synthetic tests carry the semantics: a rated, in-range, `low_inventory` game is NOT eligible, IS in the excluded partition, retains its score/grade and `low` reason; live-file invariant extended: top eligible never carries `ev_out_of_range` OR `low_inventory`.
8. **Version-skew tolerance:** `normalizeGame` present (lint) and reviewer-read: a game object without the six new fields renders the pre-W2 view with no crash and no "undefined" text; conditional `TestContract` invariants skip cleanly on pre-W2 live data and fire fully on v1.5 data.
9. **Verbatim copy:** every copy-bank string above rendered exactly (lint pins the stable fragments listed in the file plan); the eight M4a reason strings and all M4b verbatim strings (framing, caveat, footer, "— pending (v2)") byte-unchanged; the claim-lag caveat remains the excluded section's subheading with `depleted_note` following it.
10. **No fitted anything:** no code path writes `ev_ratio_adjusted`; no discount is labeled a bound, correction, or estimate anywhere in data or UI (reviewer-read + the `not bounds` lint anchor).
11. Determinism: two CLI runs byte-identical; the re-frozen artifact reproduces exactly via the pinned CLI invocation (LF bytes); `git diff --stat` shows zero changes to `tests/scraper/test_compute.py`, `test_run_daily.py`, `test_grading.py`, `test_scrape.py`, `test_games.py`, and all HTML fixtures.
12. Full gate `python -m pytest -q` green; no network in any test; no file outside the file plan touched.

## UI acceptance criteria

1. Amended mockup approved by the human BEFORE any `site/index.html` change (checkable from git history); build matches the amended mockup; all 10 polish-audit rubric items "meets", recorded in the reviewer verdict before presentation.
2. Hero unchanged in hierarchy; the qualifier line present, muted, one line at 390 px. Zero console errors across populated / stale / error / empty-scope states, including a legacy-data (pre-W2 fields) sample if exercised.
3. Detail sheet: EV-range row ("0.80 – 0.80" tight-case and "7.69 – 9.89" wide-case both demonstrated in the mockup via 720 and 702), scenario block with disclaimer, launch-odds row, upper-bound qualifiers on both EV labels; nulls render "—".
4. Excluded section: heading + retained caveat + `depleted_note`; all excluded games show grade/score/reason; partition lossless (no game vanishes — the pre-amendment bug class AC-7's synthetic tests exist to kill).
5. Responsive floor 390 px, touch targets ≥44 px, disclosures keyboard-operable, information never color-alone — unchanged M4b bars, re-audited.

## Verification commands

- `python -m pytest -q` (primary gate) · `python -m pytest -q tests/scraper tests/site` (dev loop)
- Manual: `python -m http.server 8208` from repo root → `http://localhost:8208/site/`; amended mockup opens from `file://`.
- Human gates: amended-mockup approval (before build); polish audit recorded (before presentation); accept.

## Out of scope

Any fitted or calibrated claim-lag correction, `ev_ratio_adjusted` computation, and the M6 model/release gate; full launch/book EV (M6 Phase-0 prize-table recovery — Resolution 3); W1 Wayback work; any scoring-formula, weight, band, or threshold change (Resolution 5); new flags or `games.json` regeneration; `data/latest.json`, `data/history/`, `.github/` (bot-owned surfaces); the Lottery data-request email (owner action); score-over-time visualization; every file not in the file plan.

## Tier assignment

IMPLEMENTER (sonnet) throughout — interval/scenario semantics, the re-freeze discipline, the partition amendment, and the version-skew guard are all judgment work whose tests are being written in the same change. No BULK slice: no machine-verifiable subtask exists that is separable from that judgment (the schema edit is four lines coupled to the pipeline change; the lint additions are coupled to markup the implementer writes).

## Loop budget

Defaults (`.claude/agent.config`): `MAX_IMPL_ATTEMPTS=3`, `MAX_REVIEW_CYCLES=2`. Mockup human-revision rounds separate, capped at 3 before planner escalation (M4b precedent). Budget exhaustion ⇒ escalate to planner as a wrong-sizing signal, not more attempts.

## Checkpoints (Rule 9 resume points)

- **CP1 — Pipeline + re-freeze:** `compute.py`, schema, re-frozen artifact (additive-only check recorded), `tests/scraper/test_v15_honesty.py` + frozen-artifact exacts green; commit. Resume point for all UI work.
- **CP2 — Amended mockup approved (HARD GATE, Rule 11):** human approves; commit. No `site/index.html` edits before this.
- **CP3 — Site build + full gates:** `site/index.html`, `tests/site` extensions, polish audit passed and recorded, reviewer PASS; commit.
- **Accept:** human loads locally + on a phone; checks the 702 detail sheet (wide interval + scenarios + disclaimer) and the hero qualifier; is told explicitly that the LIVE page shows the new rows only after the next daily bot run writes v1.5 data (version-skew is by design). Lead updates CLAUDE.md "Current state".

## Risks

- **Version skew is the sharpest edge:** the site deploys up to ~24h before the bot writes the new fields. Hence `normalizeGame`, conditional invariants, and the accept-gate disclosure. A crash here would blank the public page — the reviewer must actually read the guard, not trust the lint.
- **Re-freezing the frozen artifact** is exactly the m5a landmine class. Mitigated by: single artifact of record (no drift between twins), the CP1 additive-only machine check, unchanged byte-identity test logic, and AC-6's direct old-value assertions. A second artifact was rejected — two "frozen truths" invite divergence.
- **Float midpoints:** s = 0.5 scenarios hit exact decimal midpoints on half of all games; the integer-decimal rule makes them deterministic and hand-checkable. Interval divisions keep M3's `round(x, 6)` precedent; the worksheet is the authority if a dispute ever surfaces.
- **Honesty vs. fright:** three discount rows could read as "the site says EV is really 0.04." The disclaimer line and scenario framing exist to prevent that reading; wording changes are planner-only.
- **The eligibility guard changes nothing on today's data** — which is precisely when lazy implementations pass. AC-7's synthetic tests are the real carrier of the semantics (same rationale as M4b's triple lock).
- **`overall_odds` provenance is unverified officialdom** (panel minor finding): values come from the state's own game articles (some via Wayback). Displayed verbatim as "at launch," never combined into any computation — the honest ceiling until M6 Phase-0.
- **Interval ends at 2 dp collapse for healthy games** ("0.80 – 0.80"): correct behavior, communicates tightness; full 6-dp values remain in the data for anyone who looks.

---

### Resolution record (the draft's 9 open questions)

1. **Wording (upper-bound cue):** planner-authored binding copy bank above. Short hero cue (`qual_hero`), full technical form in the explainer (`explainer_upper_bound`), `qual_short` on EV labels. Exact-string lint anchors.
2. **Interval shape:** publish BOTH pairs — `remaining_tickets_min/max` (int) and `ev_ratio_min/max` (6 dp), with the EV ends computed from the published ticket ends so every number is hand-reproducible from `latest.json` alone.
3. **Launch EV** *(owner-visible)*: full book EV is NOT computable today (print runs + top-prize values held; complete prize tables not). v1.5 ships the honest anchor: `overall_odds_launch` verbatim from `games.json`. Book EV explicitly deferred to M6 Phase-0; `book_ev_pending` says so in the UI.
4. **Scenario percentages:** pinned `SCENARIO_CLAIMED_SHARES = (0.5, 0.8, 0.95)` as a named constant, with the exact label template and binding disclaimer. Scenarios, never bounds — the dissent ruling is load-bearing.
5. **Score formula:** NO change for v1.5. M4a is not reopened; AC-6 machine-proves the scoring bytes are untouched.
6. **`low_inventory` guard** *(owner-visible)*: ADDED. Panel point 4 says depleted/unstable games are ineligible for best pick, and the current predicate has a real hole — a 2%-unsold, in-range, low-confidence game would reach the shortlist with a fitted-looking score. Explicit M4b predicate amendment (flag-keyed); the section generalizes to "Excluded from best pick"; partition stays lossless; synthetic tests carry the semantics (frozen fixture has zero such games — machine-asserted). Games stay scored and honestly displayed — excluded, not hidden. Override at spec approval if unwanted.
7. **Mockup:** in-place amendment of `docs/mockups/best_pick_mockup.html`; the HUMAN approves the amended mockup (Rule 11 third touchpoint) at CP2 before any build.
8. **Frozen artifact:** re-frozen IN PLACE at CP1 with a recorded additive-only machine check (strip new keys ⇒ deep-equal old bytes); byte-identity tests re-target it with logic unchanged; worksheet exacts live against the re-frozen artifact; live-file `TestContract` gains conditional invariants only — no counts, no game_no pins (m5a rule 3).
9. **`ev_ratio_adjusted`:** confirmed — scenarios are the NEW additive `ev_scenarios` field; `ev_ratio_adjusted` stays `null` until M6 ships through its point-7 release gate, and AC-10 makes writing it a test failure.
