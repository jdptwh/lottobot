# SPEC (corrective): M5a — test re-baseline after first live bot commit

**Authorship record:** PLANNER (`claude-fable-5`) as escalation arbiter, 2026-07-13.
Authored during the gate-wedge incident (see Landmine note in CLAUDE.md): the
planner's full-form draft was trapped in its transcript when the red repo gate
bounced its read-only stop; its binding rules were delivered across two arbiter
messages and are recorded here by the lead verbatim-in-substance. Implementation
preceded this document's persistence by necessity (the lead's own stop was
gate-blocked); the reviewer verified the implementation against these rules
(verdict `m5a-rebaseline` PASS, cycle 1, zero findings).

## Root cause of record

Until M5, the committed `data/latest.json` was definitionally the frozen-fixture
output — every byte-identity and fixture-count test could target the committed
file. M5's first live bot commit (`6cae74f`, 2026-07-13) made `data/latest.json`
a LIVE, daily-changing artifact, permanently divorcing it from the frozen
fixture. Three tests broke; the divergence also exposed a real Windows bug:
`Path.write_text` newline translation produced CRLF output from `run_daily.py`
and `compute.py --out` on Windows (Linux/Action output was always LF and is
unchanged).

## Binding design rules (planner-ruled)

1. **Frozen regression artifact:** `tests/scraper/fixtures/latest_2026-07-11.json`
   = the exact bytes of `git show e4a8b7a:data/latest.json` (the last
   fixture-derived committed artifact, pre-bot). LF-only. Reviewer-verified
   byte-identical (sha256 6068…6de48).
2. **Fixture-regression tests re-point** to the frozen artifact (renamed
   accordingly): `test_cli_reproduces_the_frozen_regression_artifact_exactly`
   (test_compute.py), `test_fixture_happy_path_byte_identical_to_frozen_regression_artifact`
   (test_run_daily.py). Assertion logic unchanged; only the target stabilized.
3. **Live-file tests assert INVARIANTS only** (`tests/site/test_site_static.py`
   `TestContract`): schema/types/coherence, guarded single-claim-lag-reason
   (`if reasons:` — a guard that still fires whenever OOR games exist, not a
   skip), top-eligible-never-carries-`ev_out_of_range` (the selection-integrity
   invariant, valid on any day's data), flags vocabulary, ordering, ISO `as_of`.
   NO exact counts, game numbers, or byte pins against `data/latest.json` —
   repo-wide residue audit required and performed (zero residue).
4. **Fixture-pinned exacts re-home** to a new `TestFrozenArtifactRegression`
   class against the frozen artifact: `len(oor_games) == 11`, top eligible ==
   game 630 with `value_score == 95`. Nothing deleted — every original
   assertion survives re-homed or invariant-ized (mapping in the implementer
   report; reviewer-audited).
5. **LF determinism:** `newline="\n"` on all three CLI write sites
   (`run_daily.py` ×2, `compute.py` ×1). Linux/Action bytes unchanged
   (`newline=None` already emitted LF there); Windows now matches. No other
   scraper change permitted.
6. **Untouchable:** `data/` (bot-owned `latest.json` especially), schema,
   HTML fixtures, `site/`, `.github/`, scoring/EV logic.

## Supersession record

M5 spec AC-1's wording "byte-identical to the committed `data/latest.json`" is
superseded: the regression target is now the frozen artifact of rule 1. The
M5 AC was correct at review time and became unsatisfiable at the first bot
commit by design; this spec is the amendment of record.

## Verification

`python -m pytest -q` fully green (gate hook satisfied); reviewer verdict
`m5a-rebaseline` PASS cycle 1, gates_rerun true, zero findings; independent
frozen-artifact byte check and repo-wide residue audit recorded in the verdict
walkthrough.
