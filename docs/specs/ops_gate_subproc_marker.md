# OPS: contention-proof the per-turn gate (subproc marker) — 2026-07-27

Root cause (2026-07-27, two consecutive red Stop-gates): the _find_bash
resolver fix (commit 2f9c280) un-skipped the subprocess-spawning test files
that had silently skipped on Windows (bare "bash" resolved to the System32
WSL stub). tests/test_gate_hardening.py (13 tests, each spawning bash/git
trees) and tests/test_packaging.py::test_install_into_produces_a_green_
standalone_harness (nested harness install + FULL nested pytest, which now
also runs the un-skipped tests inside the installed copy) push the
"fast" subset past the gate's 900s timeout; the two F's are the
elapsed-time-sensitive tests failing under that load. All green in
isolation (verified exit 0) — the failure only manifests under the gate.

## Task
1. Register a `subproc` pytest marker (pytest.ini or pyproject — wherever
   this repo configures pytest; check for an existing markers section).
2. Mark with `@pytest.mark.subproc` (module-level pytestmark additions are
   fine where the whole file qualifies):
   - every test in tests/test_gate_hardening.py
   - every test in tests/panel/test_gate_panel_path.py
   - tests/test_packaging.py::test_install_into_produces_a_green_standalone_harness
3. .claude/agent.config: VERIFY_CMD becomes
   `python -m pytest -q --ignore=tests/analysis -m "not subproc"`
   and extend the POLICY comment: subproc-marked tests (nested pytest /
   bash-spawning gate tests) are excluded from the per-turn stop-gate
   because they overrun the 900s budget on Windows and false-fail under
   overlapping gate runs; they remain in the FULL pre-commit/CI suite.
4. CLAUDE.md: extend the existing gate landmine bullet with one sentence
   recording the subproc exclusion and why.
5. Verify: (a) `python -m pytest -q --ignore=tests/analysis -m "not subproc"`
   fully green and materially faster (report wall time; expect ~3 min);
   (b) `python -m pytest --collect-only -q -m subproc | tail -3` shows the
   marked tests are still collected by the full suite (report count);
   (c) no other file touched.
6. Commit exactly: pytest config file, the three test files, .claude/
   agent.config, CLAUDE.md, this spec file. Message:
   "gate: exclude subproc-heavy tests from per-turn stop-gate (900s
   overrun, 2026-07-27)" + standard co-author trailer. git push (plain;
   fetch+rebase if rejected).

## Constraints
- Do NOT change gate.sh, any test logic/assertions, or the full-suite
  definition. Marker + config + docs only.
- If the fast subset is still red after exclusion, STOP and report the
  failing tests verbatim — do not fix tests in this task.
