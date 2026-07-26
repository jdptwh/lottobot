# OPS: gate v5.2 close-out (commit + push) — 2026-07-26

One-shot operational task. Everything is already implemented and verified in
the working tree by the lead session; this task VERIFIES, COMMITS, PUSHES.
No design decisions. No files touched beyond the list below.

## Background (one paragraph)
The Stop/SubagentStop hooks run gate.sh after every turn. The full pytest
suite outgrew the gate's 900s timeout (tests/analysis/test_phase1_synthetic.py
alone ≈ 23 min of M6b permutation nulls), so every gate run went red and the
owner's desktop session "spun" after every reply. Fixes now in tree:
gate.sh v5.2 (clean-skip: fingerprint the tree on ALL PASS, skip instantly
when unchanged; kill switch GATE_SKIP_CLEAN=0), agent.config VERIFY_CMD now
excludes tests/analysis from the per-turn gate (full suite = explicit
pre-commit/CI; it ran green end-to-end tonight, exit 0, ~30 min), and both
gate test files fixed to resolve a REAL bash by full path (Windows System32
WSL-stub shadowing made them silently skip on the owner's machine).

## Changeset to commit (exactly these files)
- .claude/hooks/gate.sh                      (v5.2 + empty-grep pipefail fix)
- .claude/agent.config                       (VERIFY_CMD fast subset + note)
- tests/test_gate_hardening.py               (v5.2 pins + bash resolver)
- tests/panel/test_gate_panel_path.py        (bash resolver + python-on-PATH)
- CLAUDE.md                                  (edit per below, then commit)
- docs/specs/ops_gate_v52_closeout.md        (this file)

## Steps
1. Edit .claude/agent.config: in the comment block above VERIFY_CMD, replace
   the words "TEMP 2026-07-25 (owner session):" with "POLICY (owner-accepted
   2026-07-26):" — wording only, no functional change.
2. Edit CLAUDE.md: in the "Landmines" section, append this bullet verbatim:
   - The full pytest suite exceeds the gate's 900s timeout
     (tests/analysis/test_phase1_synthetic.py ≈ 23 min of permutation nulls).
     The per-turn Stop-gate therefore runs VERIFY_CMD with
     --ignore=tests/analysis (agent.config POLICY note); the FULL suite is a
     pre-commit/CI surface, run it explicitly. gate.sh v5.2 clean-skip makes
     unchanged-tree stops instant (fingerprint in .claude/state/, pinned by
     tests/test_gate_hardening.py). Windows: never spawn bare "bash" from
     Python tests — System32's WSL stub shadows Git bash and the suite
     silently skips (both gate test files carry the _find_bash resolver).
3. Verify: `python -m pytest -q --ignore=tests/analysis` must be fully green
   (this includes both gate test files, now un-skipped). Do NOT run
   tests/analysis (green in tonight's full run; 30 min; out of scope).
4. `git add` exactly the six files listed above. `git commit -m "harness:
   gate v5.2 clean-skip + fast-subset stop-gate (owner responsiveness
   incident 2026-07-25/26)"` with the standard co-author trailer.
5. `git push` (plain; force-push denied). If rejected non-fast-forward:
   `git fetch` then `git rebase origin/master` then push again.
6. Report: commit SHA on origin/master, test counts, anything skipped.

## Constraints
- Touch NOTHING outside the six listed files.
- If the verify in step 3 is red, STOP and report the failure output; do not
  fix, do not commit.
