#!/usr/bin/env bash
# gate.sh v5 — deterministic verification gate (loop 3). Runs on agent completion
# via Claude Code hooks (settings.json). A non-zero exit blocks the stop and
# bounces the failure back to the agent — no human or top-tier tokens spent on
# machine-catchable failures. This is NOT a model; it is the floor under every tier.
#
# v4: commands now live in .claude/agent.config (single source of truth).
# v5: adds a panel-verdict lint branch (below) — no new config keys (PANEL_* are
#     Wave 4); the panel verdict is discovered by its hardcoded state path.
# Precedence: env var > agent.config > default (empty = slot skipped).
#   GATE 1  primary   — main correctness check (code: tests/build · docs:
#                       structure validator · data: schema check)
#   GATE 2  secondary — second check (lint / pluginval / integration)
#   GATE 3  surface   — UI smoke (Playwright) or another end-to-end check
#   GATE 4  panel     — if a panel_verdict.json exists, verdict_lint validates it

set -uo pipefail

[ -f CLAUDE.md ] || exit 0   # only gate repos that opted in

# ---- Layered config: env > agent.config > default ---------------------------
_env_verify="${CLAUDE_VERIFY_CMD-}"; _env_lint="${CLAUDE_LINT_CMD-}"; _env_ui="${CLAUDE_UI_VERIFY_CMD-}"
_env_panel_path="${PANEL_VERDICT_PATH-}"
[ -f .claude/agent.config ] && . .claude/agent.config
PRIMARY_CMD="${_env_verify:-${VERIFY_CMD:-}}"
SECONDARY_CMD="${_env_lint:-${LINT_CMD:-}}"
SURFACE_CMD="${_env_ui:-${UI_VERIFY_CMD:-}}"
# ------------------------------------------------------------------------------

run_gate () {
  local label="$1" cmd="$2"
  [ -z "$cmd" ] && return 0
  echo "[gate:$label] running: $cmd" >&2
  if bash -c "$cmd" >&2; then
    echo "[gate:$label] PASS" >&2
    return 0
  else
    echo "[gate:$label] FAIL — fix before completing. Do not mark this task done." >&2
    echo "[gate:$label] Resume protocol (ROUTING.md Rule 9): inspect git state before retrying — never replay the prompt blind." >&2
    exit 2   # exit 2 = block the stop, feed stderr back to the agent
  fi
}

run_gate "primary"   "$PRIMARY_CMD"
run_gate "secondary" "$SECONDARY_CMD"
run_gate "surface"   "$SURFACE_CMD"

# A repo with no verification surface runs on reviewer judgment alone, which
# ROUTING.md Rule 2 calls a defect.
if [ -z "$PRIMARY_CMD$SECONDARY_CMD$SURFACE_CMD" ]; then
  echo "[gate] WARNING: no verification surface configured — reviewer-only. Build one (see ROUTING.md Rule 2)." >&2
fi

# ---- GATE 4: panel verdict lint (v5) -----------------------------------------
# If the panel satellite left a verdict, validate it. A non-PASS panel verdict
# (FAIL/REVISE/cost-cap/malformed) is a HARD STOP TO THE HUMAN (Rule 12/Rule 5)
# — but ONLY while it is FRESH. The panel "advises, never the verdict of record"
# (Rule 12): once the REVIEWER records its verdict of record (VERDICT_PATH, written
# AFTER folding in the panel's findings), the panel verdict is CONSUMED and only
# warns. This prevents a single stale non-PASS verdict from wedging every future
# stop indefinitely (self-audit finding: no freshness/task-scoping). Resolve a
# fresh block by recording a reviewer verdict or archiving the panel verdict.
# Absent file → no-op (v4 behavior). Path: env > agent.config > default.
PANEL_VERDICT_FILE="${_env_panel_path:-${PANEL_VERDICT_PATH:-.claude/state/panel_verdict.json}}"
_RECORD_FILE="${VERDICT_PATH:-.claude/state/verdict.json}"
if [ -f "$PANEL_VERDICT_FILE" ]; then
  # Prefer `python` (Windows/agent.config convention); fall back to python3.
  _py="$(command -v python || command -v python3)"
  echo "[gate:panel] linting $PANEL_VERDICT_FILE" >&2
  if "$_py" .claude/hooks/verdict_lint.py "$PANEL_VERDICT_FILE" >&2; then
    echo "[gate:panel] PASS" >&2
  elif [ -f "$_RECORD_FILE" ] && [ "$_RECORD_FILE" -nt "$PANEL_VERDICT_FILE" ] \
       && "$_py" .claude/hooks/verdict_lint.py "$_RECORD_FILE" >/dev/null 2>&1; then
    # reviewer verdict of record is newer AND VALIDATES as a real verdict → the
    # panel advice has been incorporated. (An arbitrary/garbage file at
    # VERDICT_PATH must not release the block — audit fix.)
    echo "[gate:panel] WARNING: non-PASS panel verdict present but superseded by a newer VALID reviewer verdict ($_RECORD_FILE) — treated as consumed, not blocking. Archive $PANEL_VERDICT_FILE to silence." >&2
  else
    echo "[gate:panel] BLOCK — FRESH non-PASS panel verdict (FAIL/REVISE/cost-capped/malformed): hard stop to the human (Rule 12/Rule 5). Resolve it, record a reviewer verdict, or archive $PANEL_VERDICT_FILE. (ROUTING.md Rule 9: inspect state, don't replay.)" >&2
    exit 2
  fi
fi

echo "[gate] ALL PASS" >&2
exit 0
