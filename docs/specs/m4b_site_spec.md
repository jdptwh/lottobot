## SPEC: M4b — Static site (`site/index.html`): best pick + scored shortlist (UI milestone, Rule 11)

**Author of record:** PLANNER (`claude-fable-5`) · 2026-07-12
**Milestone:** M4 phase (b) — the public face. DoD (spec §7 M4, as amended by the owner): renders `latest.json` as a best-pick + scored-shortlist page, mobile-usable, Pages-READY.
**Concept of record (owner-decided 2026-07-12):** one hero "today's best pick" card (grade + score + reason), a short scored shortlist, progressive disclosure for everything else, a price filter, and a de-emphasized not-rated area. The dense sortable-table concept (`docs/specs/m4_site_spec.md`, `docs/mockups/ev_ranker_mockup.html`, both untracked) is **REJECTED** — the user shouldn't have to parse a dataset.
**Governing authorities:** maine-scratch-ev-spec.md §4 (architecture + frozen contract), §8 (responsible use — non-negotiable copy), §1 (framing: "least bad today", never a win predictor); §5 as amended by the owner-approved deviation note below; `docs/specs/m4a_scoring_spec.md` (scoring semantics, copy bank, pinned values — BINDING, nothing there is reopened); `docs/ui_mockup_protocol.md` (Rule 11).
**Rule 11 applies in full:** the FIRST work item is `docs/mockups/best_pick_mockup.html`. No `site/index.html` buildout until the HUMAN approves the mockup; the approved mockup is the acceptance target; the 10-item polish audit gates presentation.

## Objective

Ship a single-file, no-build, offline-clean, mobile-first static page (`site/index.html`) that fetches `../data/latest.json` once at runtime and answers one question in one glance: **which Maine scratch game is the least-bad buy today** — via a hero card, a ranked shortlist of scored cards, an honestly-labeled claim-lag section, and a subordinate not-rated area. The page RENDERS pipeline output; it never re-derives scores, grades, reasons, or eligibility semantics beyond the pinned predicates below. Pages-READY; enabling Pages is a documented one-step human action (`docs/pages_deploy.md`). Automation is M5.

## Dependency & data contract (binding; the JS reads exactly this)

**Hard dependency — M4a lands first.** As of this writing `data/latest.json` lacks `value_score`/`grade`/`rated`/`reason` (grep-verified). Sequencing (Resolution 1): the **mockup MAY be built now** against M4a's lead-machine-verified pinned values (sample data == real future data); **`site/index.html` buildout and the contract test are BLOCKED until M4a's commit exists.** Do not start build-phase work before that commit.

Consumed per game (M3 fields, semantics per `docs/specs/m3_ev_spec.md`): `game_no`, `name`, `price`, `percent_unsold` (1-dp as published), `total_unclaimed`, `top_prizes` (`{level, remaining}` desc — the full published tier list), `print_run` (int|null), `remaining_tickets` (int|null), `ev_per_ticket` (num|null), `ev_ratio` (num|null), `ev_ratio_adjusted` (always null in v1 — render "—" labeled "pending (v2)" in expansion, never blank-as-zero), `relative_score` (num|null — appears ONLY in the no-print-run bucket's expansion, labeled a relative signal, never as an EV or score), `top_prize_odds_now` (num|null — "1 in {N, comma-grouped}", labeled current-inventory odds), `dead_game`, `flags` (five-value vocabulary; unknown flag renders as a generic chip, never a crash), `confidence`. Top level: `as_of`, `source_timestamp`, `games` (65, game_no asc — ordering for display is THIS page's job).

New M4a fields: `value_score` (int 0–100 | null), `grade` ("A"…"F" | null, closed enum), `rated` (bool), `reason` (non-empty string, rendered **verbatim** — no JS rewording, truncation with ellipsis only via expandable affordance).

**Eligibility predicate (rule of record — M4a's binding hard rule, implemented here):**
`eligible(g) := g.rated === true && !g.flags.includes("ev_out_of_range")`
Hero and shortlist draw ONLY from eligible games. Claim-lag exclusion keys on the **flag**, never on score alone and never on the reason string (flags are frozen vocabulary; reason copy may evolve). The contract test cross-checks that on real data every rated `ev_out_of_range` game carries the `claim_lag` reason, so flag-keying and reason semantics provably agree.

Current-data ground truth (lead-verified via M4a): hero = 630 "A 95"; next: 662 A 87, 708 A 87, 685 A 85, 647 A- 84, 699 B+ 76, 709 B+ 75, 687 B 73, 705 B 73, 730 B 72. Eligible = 27 (38 rated − 11 claim-lag). Not-rated = 27: dead-reason 18 (incl. both sold-out games, per M4a precedence), no_print_run 9.

## UI concept — rules of record

1. **Hero card** — the highest-scoring ELIGIBLE game in the current price scope: grade + score (e.g. "A · 95") as the primary read, name + game_no, price, and the `reason` string verbatim. Tie at the top: `value_score` desc, then `game_no` asc (Resolution 5) — deterministic, same rule as the shortlist.
2. **Price filter re-scopes the whole page, hero included** (Resolution 6). Chips derived from distinct `price` values in the data + "All" (current data: $1 $2 $3 $5 $10 $20 $30 — **no hardcoded $25**). With a price active, the hero label changes scope honestly (e.g. "Best $5 pick today" vs. "Today's best pick"). If a price scope has ZERO eligible games, the hero area renders an honest empty state ("No rateable games at $X today" + pointer to the sections below) — it NEVER promotes a claim-lag or not-rated game to fill the slot. *(Owner-visible ruling: a filter the hero ignores would confuse — "show me best $5" means the page answers for $5. Override at spec approval if unwanted.)*
3. **Shortlist** (Resolution 2): eligible games minus the hero, `value_score` desc, tie `game_no` asc. **Ranks 2–10 visible** (9 cards — the owner asked for "~10" including the hero); a "Show all rated games" disclosure reveals the remaining eligible games (currently 17). Each card: rank, grade + score, name + game_no, price, verbatim reason. Cards expand (tap/click, keyboard-operable) to: full `top_prizes` tiers with counts, `percent_unsold`, `total_unclaimed`, `ev_per_ticket`, `ev_ratio` (2 dp), `ev_ratio_adjusted` as "— pending (v2)", `top_prize_odds_now` as "1 in N" with a "launch-odds comparison pending" note, `print_run`, flag chips with plain-language expansions; every null renders "—".
4. **Claim-lag section** — the 11 rated `ev_out_of_range` games, BELOW the shortlist, visually muted but complete: header with count, the §5/§8 caveat verbatim as its subheading (AC-9), list collapsed by default with a disclosure; each row shows grade + score (F · 40), name, price, and the `claim_lag` reason verbatim. Honest, present, never in hero/shortlist.
5. **Not-rated area** (Resolution 3) — subordinate but accessible, at the bottom: games **grouped into buckets by their exact `reason` string as found in the data** (not a hardcoded bucket list — copy revisions and future buckets flow through). Bucket header = the verbatim reason string + count; under it, every `rated: false` game as a compact row (name, game_no, price), collapsed by default with disclosure. All 27 appear; the reason renders once per bucket, not 27 times (the strings within a bucket are identical by construction — the contract test asserts this grouping is lossless). `relative_score` appears only inside no-print-run rows' detail, labeled.
6. **No user-facing sort controls.** Ordering is the score, period — sorting was the rejected concept's paradigm. (§5 deviation, noted below.)
7. **`value_score` is never charted, sparklined, or time-seriesed** (M4a risk: daily-relative, not comparable across days). The explainer says so.
8. **Header:** wordmark/identity; "as of {as_of}" rendered FROM the fetched JSON (never hardcoded); `source_timestamp` as the state's snapshot time; the framing sentence verbatim: *"Ranks every active Maine scratch game by the expected value of a ticket bought today — it cannot predict a win, and every scratch game loses money on average."*
9. **Claim-lag caveat, verbatim (binding, carried from the rejected spec):** *"Caution: "unclaimed" prizes are often on already-sold tickets awaiting redemption, so naive EV overstates value — most severely on nearly-sold-out games. Treat an unusually high EV as a warning sign, not a tip."*
10. **"How the score works" explainer, planner-authored, verbatim (Resolution 7):** *"The score (0–100) compares each game's naive expected value per dollar against every other rateable Maine scratch game today, discounted when the inventory data behind it is thin. Grades are fixed bands on that score. Scores are relative and re-anchor every day — a 95 today is not a 95 tomorrow, and no score predicts a win. Every scratch game loses money on average; the best pick is only the least bad."* Rendered as a compact disclosure near the hero. Implementer may not reword; changes come back to the planner.
11. **Staleness banner** shown iff `Date.now() − Date.parse(as_of + "T00:00:00Z") > 48*3600*1000`, showing the last-good `as_of` date (§6.1 honesty mechanism; carried verbatim from the rejected spec).
12. **Error state:** failed fetch or unparseable JSON renders a designed panel ("couldn't load today's data" + link to mainelottery.com) — never a blank page or console-only failure.
13. **Footer, verbatim requirements (carried):** one-line methodology summary + link-free claim-lag pointer; *"Data: Maine State Lottery"* linking `https://www.mainelottery.com/players_info/unclaimed_prizes.html`; *"The Maine State Lottery's Official Outstanding Prize List prevails over anything shown here."*; *"This tool cannot predict winners. All scratch games are negative-expected-value under normal conditions. If gambling is a problem for you or someone you know, call 1-800-GAMBLER."*

## Reference study directive (do BEFORE drawing)

Study 2–3 high-end references for **editorial "our pick" / recommendation-card UIs** — e.g. Wirecutter-style "Our pick / Runner-up / Also great" hierarchy, a weather-app hero-plus-detail composition, a credit-card or ISP comparison "best for X" card stack, or a sports "best bets" card feed. Extract concrete moves: hero-card dominance vs. subordinate list rhythm, grade/badge typography (`font-variant-numeric: tabular-nums` for all figures), disclosure affordances, price-segment control styling, muted-section treatment. The page needs its own identity (wordmark, e.g. "Maine Scratch EV"; Maine-appropriate accent strategy) and must NOT read as a default AI dashboard: no flat grid of same-size dark cards, no default indigo-on-dark, no emoji iconography, no centered-everything. Reskin ≠ redesign. **Cite references + borrowed moves in a "design notes" HTML comment in the mockup** — polish-audit items 8–10 score against it.

## Mockup requirements (FIRST work item; gated on human approval)

`docs/mockups/best_pick_mockup.html` — one self-contained file: inline CSS/JS only, zero external requests, renders from `file://`. Embeds sample data as an inline JS constant (no fetch): the REAL committed M3 fields overlaid with M4a's pinned values for the pinned sets (hero 630 A 95; the top-10; all 11 claim-lag F 40 with the exact `claim_lag` string; both non-rated buckets with the exact `dead`/`no_print_run` strings); remaining eligible scores may be synthesized consistent with M4a's pinned grade distribution (A 4, A- 1, B+ 2, B 6, B- 6, C 7, D 1, F 11). The mockup is the design contract, not a data mirror — it is not regenerated when M4a lands. It must demonstrate, live in the file:

1. Every element of "UI concept" above: hero (with reason), price chips (no $25), shortlist ranks 2–10 + show-all disclosure, at least one card shown EXPANDED with the full detail set, the claim-lag section with verbatim caveat, the bucketed not-rated area (one no_print_run row's detail showing labeled `relative_score`), explainer, header with framing sentence, footer with all verbatim strings.
2. **All states**, via a clearly-labeled switcher marked "MOCKUP ONLY — not in build": (a) fresh/populated; (b) stale (≥48h banner); (c) error panel; (d) **empty price scope** — a price with zero eligible games showing the honest empty-hero state.
3. **Mobile-first proof:** designed ≤390 px presentation — hero + first shortlist cards fit with no horizontal page scroll; touch targets ≥44 px; expansion carries the secondary detail.
4. The design-notes comment per the directive.

**Approval gate (Rule 11 third touchpoint):** human approves / requests changes / rejects. Max 3 revision rounds, then STOP and escalate to the planner. The approved mockup is committed and becomes the acceptance target. No `site/index.html` work before approval.

## File plan (touch nothing else)

- `docs/mockups/best_pick_mockup.html` — NEW, first work item.
- `site/index.html` — NEW (new directory), ONLY after mockup approval AND M4a's commit. Single file, vanilla inline HTML/CSS/JS, no build step, no external loaded resources (external `<a href>` to mainelottery.com and the GAMBLER tel line allowed and required). Exactly one `fetch(` and its target is `../data/latest.json`. Selection logic lives in one named function `isEligible` (lint-anchored, reviewer-read).
- `tests/site/test_site_static.py` — NEW:
  - **Contract test** (runs against the M4a-regenerated `data/latest.json`; lands at CP2): every field the JS dereferences exists with correct type/nullability per the contract above; `value_score` int|null (never float), `grade` in the closed enum|null, `rated` bool, `reason` non-empty for all 65; invariants `rated ⟺ value_score non-null ⟺ grade non-null`; every rated `ev_out_of_range` game's reason == the `claim_lag` string exactly (flag/reason agreement); grouping games by exact `reason` string is lossless over the 65; `flags ⊆` the five-value vocabulary (drift = deliberate failure forcing UI review); `games` non-empty, game_no-ascending; `as_of` ISO-parses; on current data: top eligible by (score desc, game_no asc) is 630, and no eligible game carries `ev_out_of_range`.
  - **Offline-clean + required-content lint**, parametrized over BOTH mockup and build (stdlib `html.parser` + regex, no new deps; design carried from the rejected spec): no external URLs in `<script src>`, `<link href>`, `<img src>`, `<iframe>`, `srcset`, CSS `@import`, `url(...)` (external `<a href>` allowed); required substrings: `1-800-GAMBLER`, `Official Outstanding Prize List prevails`, `cannot predict`, `as of`, `mainelottery.com`, `warning sign, not a tip`, `no score predicts a win`; for `site/index.html` additionally: exactly one `fetch(` targeting `../data/latest.json`, an `isEligible` definition referencing both `rated` and `ev_out_of_range`, and the "MOCKUP ONLY" switcher marker ABSENT; for the mockup additionally: the marker PRESENT.
  - **`docs/pages_deploy.md` lint:** required substrings pin root publishing, the `/site/` URL shape, and port 8208 (this is the named machine check justifying the BULK slice below).
- `docs/pages_deploy.md` — NEW, carried near-verbatim from the rejected spec: Settings → Pages → "Deploy from a branch" → `master` / root; URL shape `https://<owner>.github.io/lottobot/site/`; root publishing REQUIRED (the `../data/latest.json` path depends on it — never the `/docs` option); private-repo plan restriction note; local preview `python -m http.server 8208` from repo root → `http://localhost:8208/site/` (fetch fails on `file://`; 8207 is the panel dashboard).
- **Disposal (Resolution 4):** the lead DELETES the two rejected untracked artifacts — `docs/specs/m4_site_spec.md` and `docs/mockups/ev_ranker_mockup.html` — when committing THIS spec, noting the deletion in the commit message. They were never committed; the rejection and everything carried forward are recorded here.
- Do NOT touch: `scraper/`, `data/` (any file — `latest.json` is read-only input), `data/schema/`, existing tests, `.github/`, `panel/`, `.claude/`, `docs/specs/m4a_scoring_spec.md`.

## Acceptance criteria

1. **Mockup approved first:** the approved mockup is committed before any `site/index.html` content exists in git history (checkable from the log).
2. **Layout parity:** the build matches the approved mockup — sections, order, hierarchy, affordances, copy, states. All 10 polish-audit rubric items score "meets"; result recorded in the reviewer verdict before presentation. Deviations require prior human OK.
3. **Hero:** renders the highest-scoring eligible game in scope with grade, score, name + game_no, price, verbatim reason. On current data at "All": game 630, "A · 95", the `medium` reason string. Tie-break score desc → game_no asc.
4. **Binding exclusion:** hero and shortlist populate ONLY via `isEligible` (flag-keyed, per the predicate of record). Lint asserts the function's presence and flag reference; the contract test asserts flag/reason agreement and 630-at-top on real data; the reviewer reads the selection path end-to-end (score-alone selection is a FAIL even if output coincides).
5. **Shortlist:** eligible minus hero, score desc / game_no asc; ranks 2–10 visible (current data: 662, 708, 685, 647, 699, 709, 687, 705, 730 in that order); show-all disclosure reveals the rest; cards carry rank, grade+score, name, price, verbatim reason; expansion carries the full detail set with nulls as "—".
6. **Claim-lag section:** all 11 games (624, 638, 661, 690, 693, 694, 695, 696, 702, 703, 706), F · 40, verbatim `claim_lag` reason, verbatim caveat subheading, muted, below the shortlist, disclosure-collapsed, never in hero/shortlist.
7. **Not-rated area:** all 27 `rated:false` games present, bucketed by exact data-derived reason string with counts (current data: 18 dead-reason incl. 617/651, 9 no_print_run), subordinate, disclosure-collapsed, `relative_score` only in no-print-run detail and labeled.
8. **Price chips** derived from data + All; no $25 chip may appear; filter re-scopes hero, shortlist, claim-lag, and not-rated; hero label reflects scope; zero-eligible scope shows the honest empty-hero state.
9. **Verbatim copy:** framing sentence, caveat, explainer, footer strings exactly as specified; `reason` strings rendered verbatim everywhere; `value_score` never charted/time-seriesed; `ev_ratio_adjusted` renders "— pending (v2)"; `relative_score` never appears as an EV or score.
10. **Staleness banner** per the 48h rule with last-good `as_of`; **error state** per the mockup — never blank.
11. **Unknown-flag tolerance:** a flag outside the known vocabulary renders as a generic chip; rendering never throws (reviewer reads the path).
12. **Numbers:** currency comma-grouped with $; `percent_unsold` 1 dp as published; `ev_ratio` 2 dp; odds "1 in {N, comma-grouped}"; scores integers.
13. **Machine gates:** both test groups in `tests/site/test_site_static.py` green; full `python -m pytest -q` green; no file outside the file plan touched; M4a's `data/latest.json` and schema untouched by this task.

## UI acceptance criteria

1. Core flow ≤3 interactions; the hero answer is visible at ZERO interactions on load.
2. Zero console errors across populated / stale / error / empty-scope states.
3. Responsive floor 390 px: no horizontal page scroll; hero + first cards fully legible; touch targets ≥44 px (chips, disclosures, card expansion).
4. Accessibility basics: labels tied to controls, visible focus states, disclosures keyboard-operable, information never color-alone (grades carry text).
5. Mockup covers all four states via the "MOCKUP ONLY" switcher; the marker is lint-verified absent from the build.
6. Polish audit: all 10 rubric items "meets" (including distinctiveness, reference fidelity, composition/density) before presentation.

## Verification

- `python -m pytest -q` (primary gate) · `python -m pytest -q tests/site` (dev loop).
- Manual: `python -m http.server 8208` from repo root → `http://localhost:8208/site/`; mockup opens from `file://`.
- Human gates: mockup approval (before build), polish audit recorded (before presentation), phone check + optional Pages enable per `docs/pages_deploy.md` (at accept).
- No headless browser exists or is required; JS correctness is carried by the contract test freezing the data shape, the lint anchors, a deliberately small render path the reviewer reads, and the two human gates. Accepted residual risk for a no-build static page.

## Out of scope

M5 (daily Action, cron, `data/history/`, deploy automation — if repo visibility blocks Pages, deployment pairs with M5 without failing M4b); any change to `latest.json`, its schema, `compute.py`, or M4a logic; `ev_ratio_adjusted` computation and launch-odds comparison (M6); any full-dataset sortable table (superseded concept) or user-facing sort controls; score-over-time visualization; permalinks/URL state, dark-mode toggles, analytics, service workers; frameworks, build tooling, external assets of any kind; deleting anything beyond the two named rejected artifacts.

**Owner-approved deviation from §5 (record):** "sortable table" and per-row anomaly banner superseded by the best-pick concept and the claim-lag section; carried forward intact: price filter, expansion detail, staleness rule, claim-lag caveat, mobile-first mandate, footer requirements. §4, §6, §8 fully binding. §3-v3's "per-price best pick" is delivered early via the re-scoping hero.

## Tier assignment

- Mockup: IMPLEMENTER (design-judgment work, Rule 11).
- Build + tests: IMPLEMENTER (state handling, honest-empty logic, responsive composition, selection path).
- `docs/pages_deploy.md`: **BULK** (Resolution 8) — near-verbatim reuse of planner-specified content, machine-checked by the pages-deploy lint above. If the BULK pass fails its lint twice, it moves to the implementer per Rule 5.
- No other BULK: the lint tests are small and coupled to markup choices the implementer makes.

## Loop budget

Defaults (`.claude/agent.config`): `MAX_IMPL_ATTEMPTS=3`, `MAX_REVIEW_CYCLES=2`. Mockup human-revision rounds are separate, capped at 3 before planner escalation. A failed polish audit consumes a review cycle.

## Checkpoints (Rule 9 resume points)

- **CP0 — M4a landed (external precondition):** M4a's commit exists with the regenerated `data/latest.json`. Gates the BUILD phase only; the mockup may proceed before CP0 against pinned values.
- **CP1 — Mockup approved (HARD GATE):** human approves; commit the mockup (the mockup-side lint may land here; the contract test waits for CP0 data). Rule 11 third touchpoint. Resume point if the build fails.
- **CP2 — Build + gates green:** `site/index.html` + full `tests/site` + `docs/pages_deploy.md`; polish audit passed and recorded; reviewer PASS; commit.
- **Accept:** human loads locally AND on a phone (the gas-station test), checks hero honesty + §8 framing, optionally enables Pages. Lead updates CLAUDE.md "Current state".

## Risks

- **The exclusion predicate is the milestone's integrity core.** On current data, score-alone selection happens to produce identical output (claim-lag = 40 = curve min) — which is exactly why a lazy implementation would pass every visible check and then crown a claim-lag game on a future degenerate-curve day (M4a: sole-survivor OOR gets 68/B). Hence AC-4's triple lock: lint anchor, contract cross-check, mandatory reviewer read.
- **Hero-rescoping edge:** a price scope with zero eligible games must degrade to the honest empty state, never "borrow" from claim-lag/not-rated. Mockup state (d) exists to make this failure impossible to miss.
- **No browser automation:** a JS regression could pass every machine gate. Mitigations as in Verification; residual risk accepted.
- **Copy drift:** reason strings, caveat, framing, explainer, and footer are verbatim contracts; lint pins stable fragments; wordsmithing beyond them only via mockup approval (design copy) or planner (reason/§8 copy).
- **Daily re-anchoring:** scores aren't comparable across days; the explainer says so and rule 7 bans time-series rendering. M5 history preserves raw fields, so nothing is lost.
- **Relative fetch path fragility:** `../data/latest.json` requires Pages root publishing; `docs/pages_deploy.md` states it and the lint pins the fetch target.
- **`file://` fetch failure** will confuse local checkers — the http.server instruction and the built-in error panel cover it.
- **Staleness math** uses the client clock vs UTC-midnight `as_of`; skew shifts onset by hours, never days — acceptable at a 48h threshold.
- **M6 forward-compatibility:** unknown-flag tolerance and the always-"pending" adjusted-EV slot keep the page honest when new flags/values arrive.

---

### Resolution record (drafter's open questions)

1. **Sequencing:** M4a implements first; mockup may proceed now against M4a's lead-verified pinned values; build + contract test block on M4a's commit (CP0).
2. **Shortlist size:** hero + ranks 2–10 visible (owner asked for "~10"); show-all disclosure for the remaining eligible games. Nothing hidden, nothing walled.
3. **Not-rated granularity:** bucketed by exact data-derived reason string (headers carry the verbatim reason + count), every game listed as a compact row inside its bucket.
4. **Disposal:** delete both rejected untracked artifacts at this spec's commit, deletion noted in the commit message.
5. **Hero tie-break:** score desc, game_no asc — same deterministic rule as the shortlist.
6. **Filter semantics:** the price filter re-scopes the entire page including the hero ("Best $5 pick today"), with an honest empty-hero state for zero-eligible scopes. Marked owner-visible at spec approval.
7. **Explainer copy:** planner-authored, verbatim, binding (rules-of-record item 10).
8. **pages_deploy.md as BULK:** confirmed, with a named machine check (the pages-deploy substring lint) per Rule 1.
