## SPEC: M4a — `value_score` / `grade` pipeline extension (`scraper/compute.py`)

**Author of record:** PLANNER (`claude-fable-5`) · 2026-07-12
**Milestone:** M4 phase (a) — scoring computed in the pipeline so the M4b UI ("best pick + scored shortlist", owner-decided) renders data, never computes it. Rule 11 governs M4b, not this task — M4a has no UI surface.
**Authority:** maine-scratch-ev-spec.md §4 (additive-only contract), §8 (responsible-use tone — the reason strings below are the first user-facing prose and are planner-authored, binding); docs/specs/m3_ev_spec.md (semantics this extends; nothing there is reopened).
**Lead pre-dispatch verification (2026-07-12):** every pinned number below — worksheet A–G, the exact rated/dead/no-print-run/claim-lag sets, the AC-6 pinned top, the AC-7 distribution, and the AC-10 premise — machine-verified against the committed `data/latest.json`. Item G (682→68/B) confirmed.

## Objective

Extend `scraper/compute.py` so every game in `latest.json` additionally carries `value_score` (int 0–100 or null), `grade` (letter or null), `rated` (boolean), and `reason` (one-line string, always present). Scoring is daily-relative over the rateable games; non-rateable games are honestly excluded with a bucket-correct reason. Additive to the frozen §4 contract; the committed `data/latest.json` is regenerated from the same frozen fixture + `--as-of 2026-07-11` as M3. Offline, deterministic, no fetch path.

## Scoring semantics (rules of record)

**Rateable** iff ALL of: `dead_game` is `False` AND `"sold_out"` not in `flags` AND `print_run` is not `None` AND `ev_ratio` is not `None`. (A game_no absent from games.json is already `print_run: null` per M3 — no new crash paths.)

**Value index** (rateable only) = `min(max(ev_ratio, 0.0), 1.5) * WEIGHT[confidence]` with `WEIGHT = {"high": 1.0, "medium": 0.85, "low": 0.45}`, keyed off the existing M3 `confidence` field — never recomputed. The clamp exists ONLY inside this index; M3's never-clamp rule on published `ev_ratio` is unchanged. **Deliberate deviation from M3's raw-intermediate rule:** the index is computed from the PUBLISHED 6-dp `ev_ratio`, not the raw intermediate — so a human (and the M4b UI) can reproduce every score from `latest.json` alone. Document this in the module docstring.

**Daily-relative curve** over rateable indices: `value_score = round(40 + 55 * (idx - idx_min) / (idx_max - idx_min))`, Python built-in `round()` (round-half-even; no midpoint occurs on this fixture — see Risks). Result is a JSON **integer**, never a float.

**Degenerate curve** (`idx_max == idx_min`, e.g. exactly one rateable game): every rateable game gets `value_score = 68` (the curve's rounded midpoint), grade from the bands as usual (B). Rationale — with no comparison set, crowning the sole survivor "A 95" would be promotional (§8), especially if it is a claim-lag game; 68/B says "unrankable, unremarkable" and its `reason` still carries the honesty. Module constant `DEGENERATE_SCORE = 68`.

**Grade bands** on the rounded int score: `>=85 "A"`, `>=80 "A-"`, `>=75 "B+"`, `>=68 "B"`, `>=62 "B-"`, `>=52 "C"`, `>=42 "D"`, else `"F"`. Bands are a module constant table.

**Non-rateable:** `value_score` null, `grade` null, `rated` false. `reason` by first-match bucket precedence: `dead_game` → `sold_out` → `print_run is None` → residual (`ev_ratio is None`). (617 and 651 are both dead AND sold out — dead wins, by this order.)

**Rateable:** `rated` true; `reason` keyed: `"ev_out_of_range"` in flags → claim-lag string; else confidence high/medium/low string.

**Reason copy bank (planner-authored, BINDING — exact strings, module-level dict; tests assert exact equality, not substrings):**

| Key | String |
|---|---|
| `dead` | `"Top prize already claimed — the biggest advertised win can no longer be won."` |
| `sold_out` | `"Reported 0% unsold — effectively sold out; there is nothing left to buy."` |
| `no_print_run` | `"Print run unknown — expected value can't be computed; ranked by the relative unclaimed-money signal only."` |
| `no_data` | `"Not enough data to compute an expected value for this game."` |
| `claim_lag` | `"Looks better than it is: most unclaimed prize money is likely on tickets already sold but not yet claimed (claim lag)."` |
| `high` | `"Based on solid inventory data; the expected-value estimate is comparatively reliable."` |
| `medium` | `"Inventory is thinning; the expected-value estimate carries moderate uncertainty."` |
| `low` | `"Very little inventory data behind this estimate — treat this score with caution."` |

All ≤ 140 chars, non-promotional, no fabricated numerics. Implementer may NOT rewrite copy; wording changes come back to the planner.

**Output shape:** the four new keys are appended to each game object after `"confidence"`, in order `value_score`, `grade`, `rated`, `reason` (byte-stable diffs). Games array ordering (game_no asc) unchanged. `diff_gate` is untouched and continues to operate on `ev_ratio` only — value_score churn is expected daily and must never trip it.

## File plan (touch nothing else)

- `scraper/compute.py` — extend: rateability predicate, `WEIGHT`, index, curve (with degenerate branch), grade bands, copy bank, wiring into `compute_latest`. No CLI changes.
- `data/schema/latest.schema.json` — additive edit only, four optional properties on `$defs.game.properties`: `"value_score": {"type": ["integer", "null"]}`; `"grade": {"type": ["string", "null"], "enum": ["A", "A-", "B+", "B", "B-", "C", "D", "F", null]}` (closed enum incl. null — matches the `confidence` precedent and machine-checks the band mapping; `reason` deliberately NOT an enum so copy can evolve without schema churn); `"rated": {"type": "boolean"}`; `"reason": {"type": "string", "minLength": 1}`. The `required` list is frozen — untouched (M1's verbatim §4-example test must stay green).
- `data/latest.json` — regenerated committed artifact via the M3 CLI: `python -m scraper.compute --unclaimed tests/scraper/fixtures/unclaimed_prizes_2026-07-11.html --games data/games.json --as-of 2026-07-11 --out data/latest.json`.
- `tests/scraper/test_grading.py` — NEW file for all M4a tests (a new file makes "M3 suite green unmodified" verifiable as `git diff --stat` showing zero changes to `tests/scraper/test_compute.py`, not just a passing run).
- Do NOT touch `scraper/scrape.py`, `scraper/games.py`, `data/games.json`, any fixture, `tests/scraper/test_compute.py` / `test_scrape.py` / `test_games.py`, or anything under `site/` or `docs/mockups/`.

## Hand-check worksheet (lead machine-verified 2026-07-12)

Fixed daily constants on this fixture: `idx_min = 0.675` (= 1.5 × 0.45, shared by every rated `ev_out_of_range` game); `idx_max = 1.16240985` (game 630: 1.367541 × 0.85); span `0.48740985`.

**A. Game 630 — $500,000 ROYAL CASH (the hero / curve max).** ev_ratio 1.367541, confidence "medium". idx = 1.367541 × 0.85 = 1.16240985 = idx_max → `value_score` **95**, `grade` **"A"**, `rated` **true**, `reason` == `medium` string.

**B. Game 662 — COUNT \`EM UP (worked mid-curve arithmetic, medium confidence).** ev_ratio 1.287899, confidence "medium". idx = 1.287899 × 0.85 = 1.09471415. score = 40 + 55 × (1.09471415 − 0.675) / 0.48740985 = 40 + 55 × 0.8611113… = 87.3611… → **87**, `grade` **"A"**, `rated` **true**, `reason` == `medium` string.

**C. Game 706 — DOUBLE YOUR DOLLARS (claim-lag honesty, curve min).** ev_ratio 32.538542 (published unclamped, per M3), confidence "low", flags include `ev_out_of_range`. idx = min(32.538542, 1.5) × 0.45 = 0.675 = idx_min → `value_score` **40**, `grade` **"F"**, `rated` **true**, `reason` == `claim_lag` string exactly.

**D. Game 675 — BASEBALL (the lone D; high-confidence but weak value).** ev_ratio 0.731252, confidence "high". idx = 0.731252. score = 40 + 55 × 0.056252 / 0.48740985 = 40 + 6.3476… = 46.35 → **46**, `grade` **"D"**, `rated` **true**, `reason` == `high` string.

**E. Game 617 — HIGH ROLLER (bucket precedence: dead AND sold_out).** `dead_game` true, `sold_out` flag. `value_score` **null**, `grade` **null**, `rated` **false**, `reason` == `dead` string (dead outranks sold_out).

**F. Game 668 — CA$H CRU$H (no print run).** `print_run` null. Nulls, `rated` **false**, `reason` == `no_print_run` string.

**G. Game 682 — BIG MONEY SPECTACULAR (band-edge rounding).** ev_ratio 0.921596, confidence "high". idx = 0.921596. score = 40 + 55 × 0.246596 / 0.48740985 = 67.826… → **68** — lands exactly on the B band floor. `grade` **"B"**. (Lead-confirmed in the pre-dispatch machine check.)

## Acceptance criteria

1. All 65 games carry all four new fields; the document validates against the updated schema via `jsonschema`; the four keys appear after `confidence` in the pinned order.
2. **Exact rated set (38):** `rated` true for exactly {624, 630, 638, 647, 656, 661, 662, 674, 675, 677, 682, 685, 686, 687, 690, 692, 693, 694, 695, 696, 699, 702, 703, 705, 706, 708, 709, 711, 716, 717, 718, 720, 723, 725, 729, 730, 735, 737}.
3. **Exact non-rated buckets (27):** dead-reason set = {617, 632, 651, 654, 655, 660, 663, 667, 670, 671, 673, 676, 680, 683, 684, 691, 704, 707} (18, includes both sold-out games — precedence proven); no_print_run-reason set = {586, 648, 664, 668, 669, 681, 689, 697, 710} (9); sold_out and no_data buckets EMPTY on this fixture (asserted); all 27 have `value_score is None`, `grade is None`.
4. **Claim-lag set:** exactly {624, 638, 661, 690, 693, 694, 695, 696, 702, 703, 706} (the 11 rated `ev_out_of_range` games) have `value_score == 40`, `grade == "F"`, `reason` == the `claim_lag` string exactly.
5. **Worksheet A–G** asserted exactly (values above), including exact reason-string equality against the copy-bank constants.
6. **Pinned top of the curve:** 630→95 A, 662→87 A, 708→87 A, 685→85 A, 647→84 A-, 699→76 B+, 709→75 B+, 687→73 B, 705→73 B, 730→72 B, 711→70 B, 674→69 B, 682→68 B.
7. **Grade distribution on the fixture:** A 4, A- 1, B+ 2, B 6, B- 6, C 7, D 1, F 11 (38 total rated).
8. **Band-boundary unit test (synthetic):** for each band edge (85/80/75/68/62/52/42), construct indices yielding scores at the edge and one below, and assert the grade on both sides (pure function test on the score→grade mapping is acceptable and preferred).
9. **Degenerate-curve unit test (synthetic):** a single-rateable-game input yields `value_score == 68`, `grade == "B"`, no `ZeroDivisionError`; a rateable-OOR sole survivor still gets the `claim_lag` reason.
10. **Low-confidence rateable branch (synthetic):** a rateable game with confidence "low" and NO `ev_out_of_range` flag gets the `low` reason string (this branch has no fixture coverage — 100% of the fixture's low-confidence rated games are OOR).
11. Type discipline: `value_score` serializes as JSON integer or null (never a float like `95.0`); `reason` is a non-empty string for all 65; `rated` is a bool for all 65.
12. Determinism: two CLI runs byte-identical; the committed `data/latest.json` reproduces exactly via the M3 CLI invocation above; `diff_gate` behavior unchanged (existing M3 diff-gate tests green, untouched).
13. Schema edit additive-only: `required` untouched; M1's verbatim §4-example test green; `git diff` shows ZERO changes to `tests/scraper/test_compute.py`, `test_scrape.py`, `test_games.py`, and all fixtures.
14. Full gate `python -m pytest -q` green; no test touches the network (existing conftest socket guard covers the new file's directory).

## Verification commands
- `python -m pytest -q` (primary) · `python -m pytest -q tests/scraper` (dev loop)

## Out of scope
Any UI file, `site/`, `docs/mockups/` (M4b — mockup approval gates that task, not this one), `data/games.json`, `scraper/scrape.py`, `scraper/games.py`, workflow YAML and `data/history/` (M5), `ev_ratio_adjusted` and any claim-lag modeling beyond the reason string (M6), reordering the games array, re-tuning any M3 threshold, `pyproject.toml`, `requirements.txt`, `panel/`, `.claude/`, and every file not in the file plan.

## Tier assignment
IMPLEMENTER (sonnet) throughout — judgment work (bucket precedence, degenerate branch, copy-bank wiring). No BULK slice: no machine-verifiable subtask exists separable from the judgment work; the grading tests being written here ARE the machine check.

## Loop budget
Defaults (`.claude/agent.config`): MAX_IMPL_ATTEMPTS=3, MAX_REVIEW_CYCLES=2.

## Checkpoints
None mid-task (single-sitting scope). Lead commits once after review PASS and after the HUMAN verifies worksheet items A–G against the committed `data/latest.json` (second touchpoint). Note: the M3 3-game hand-check (touchpoint 2 of M3) is still outstanding per CLAUDE.md — it can be verified in the same sitting, but M4a's commit does not depend on it.

## Risks
- **Daily-relative scores are not comparable across days.** 95 today ≠ 95 tomorrow; the whole distribution re-anchors when the idx_max holder (currently 630) sells down or dies. Owner-accepted by design. M4b must never chart `value_score` over time as if absolute; M5 history keeps the raw fields, so nothing is lost.
- **A claim-lag game can only escape F via the degenerate curve** (all-rateable-OOR day), and even then carries the `claim_lag` reason. M4b hard rule (record it in the M4b spec): "best pick" selection must exclude `reason == claim_lag` games, keying on the reason/flags — never on score alone.
- **Rounding ties:** Python `round()` is round-half-even; no score on this fixture lands on an exact .5 (nearest is 682 at 67.826), and the published-6dp-input rule makes hand reproduction exact. If a future fixture ever produces a visible tie dispute, that's a constant to pin then, not now.
- **Copy drift:** the reason strings are now a de-facto UI contract. Schema deliberately leaves `reason` a free string so copy can be revised additively — but any revision is a planner-level change (§8 tone), and M4b must render the string verbatim, not re-derive it.
- **Score computed from published `ev_ratio` (6-dp) rather than raw** is a pinned, documented deviation from M3's rounding rule; worst-case drift vs. raw is ~1e-4 of a point — immaterial, and it buys exact reproducibility from `latest.json` alone.

---

### Resolution record (drafter's open questions)
1. **Test file:** new `tests/scraper/test_grading.py`; M3 test files provably untouched via git diff.
2. **Worksheet:** expanded to A–G (hero, worked medium-confidence arithmetic, claim-lag, lone D, dead/sold-out precedence, no-print-run, band-edge rounding). All arithmetic machine-verified by the lead pre-dispatch, including item G.
3. **Degenerate case:** 68/B, not 95 — §8 honesty over the draft's optimism.
4. **Reason copy:** planner-authored binding copy bank; exact-equality assertions.
5. **Grade schema:** closed enum `["A","A-","B+","B","B-","C","D","F", null]`.
