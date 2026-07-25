#!/usr/bin/env bash
# gate.sh v5.1 — deterministic verification gate (loop 3). Runs on agent completion
# via Claude Code hooks (settings.json). A non-zero exit blocks the stop and
# bounces the failure back to the agent — no human or top-tier tokens spent on
# machine-catchable failures. This is NOT a model; it is the floor under every tier.
#
# v4:   commands now live in .claude/agent.config (single source of truth).
# v5:   adds a panel-verdict lint branch (below) — no new config keys (PANEL_* are
#       Wave 4); the panel verdict is discovered by its hardcoded state path.
# v5.1: anti-wedge hardening (CLAUDE.md landmines, 2026-07-13/22 incidents):
#       (a) honors the hook protocol's `stop_hook_active` flag from stdin JSON —
#           when Claude Code reports this stop is ALREADY a hook-forced
#           continuation, a red gate WARNS instead of blocking again, so a
#           red repo can bounce an agent at most once per stop instead of
#           wedging every completion (the read-only-agent deadlock);
#       (b) every gate command runs under `timeout` (GATE_TIMEOUT_SECS,
#           env > agent.config > default 900) so a hung verify command can
#           never wedge a stop indefinitely.
#       Both degrade to exact v5 behavior when stdin is empty or `timeout`
#       is unavailable.
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
_env_gate_timeout="${GATE_TIMEOUT_SECS-}"
[ -f .claude/agent.config ] && . .claude/agent.config
PRIMARY_CMD="${_env_verify:-${VERIFY_CMD:-}}"
SECONDARY_CMD="${_env_lint:-${LINT_CMD:-}}"
SURFACE_CMD="${_env_ui:-${UI_VERIFY_CMD:-}}"
TIMEOUT_SECS="${_env_gate_timeout:-${GATE_TIMEOUT_SECS:-900}}"
# ------------------------------------------------------------------------------

# ---- Hook payload (v5.1a): detect a hook-forced continuation -----------------
# Claude Code sends the hook payload as JSON on stdin; `"stop_hook_active": true`
# means THIS stop already happened once and was blocked by a Stop/SubagentStop
# hook — blocking again risks an unbounded bounce loop (the documented wedge:
# read-only agents that cannot fix a red gate loop until force-ended). Reading
# is best-effort and can never hang: bounded by `timeout 1`, skipped when no
# timeout binary exists. Empty/absent payload → strict v5 blocking behavior.
STOP_HOOK_ACTIVE=0
if [ ! -t 0 ] && command -v timeout >/dev/null 2>&1; then
  _hook_json="$(timeout 1 cat 2>/dev/null || true)"
  case "$_hook_json" in
    *'"stop_hook_active":true'*|*'"stop_hook_active": true'*)
      STOP_HOOK_ACTIVE=1 ;;
  esac
fi

# In anti-wedge mode a red gate cannot block again; it must still be LOUD.
soft_or_hard_fail () {
  # $1 = label for the message
  if [ "$STOP_HOOK_ACTIVE" = "1" ]; then
    echo "[gate:$1] WARNING (anti-wedge): gate is RED but this stop is already a hook-forced continuation (stop_hook_active) — NOT blocking again. The repo gate remains RED: fix it before shipping; do not mark the task done. (CLAUDE.md landmine: red gates must not wedge read-only agents.)" >&2
    GATE_SOFT_FAILED=1
    return 0
  fi
  return 1
}
GATE_SOFT_FAILED=0

run_gate () {
  local label="$1" cmd="$2" rc
  [ -z "$cmd" ] && return 0
  echo "[gate:$label] running: $cmd" >&2
  if command -v timeout >/dev/null 2>&1; then
    timeout --foreground "$TIMEOUT_SECS" bash -c "$cmd" >&2
    rc=$?
  else
    bash -c "$cmd" >&2
    rc=$?
  fi
  if [ "$rc" -eq 0 ]; then
    echo "[gate:$label] PASS" >&2
    return 0
  fi
  if [ "$rc" -eq 124 ]; then
    echo "[gate:$label] TIMEOUT after ${TIMEOUT_SECS}s — the verify command hung; treating as FAIL (raise GATE_TIMEOUT_SECS in .claude/agent.config if the suite is legitimately slower)." >&2
  fi
  echo "[gate:$label] FAIL — fix before completing. Do not mark this task done." >&2
  echo "[gate:$label] Resume protocol (ROUTING.md Rule 9): inspect git state before retrying — never replay the prompt blind." >&2
  soft_or_hard_fail "$label" && return 0
  exit 2   # exit 2 = block the stop, feed stderr back to the agent
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
    soft_or_hard_fail "panel" || exit 2
  fi
fi

if [ "$GATE_SOFT_FAILED" = "1" ]; then
  echo "[gate] RED (soft) — released only to prevent a stop-hook wedge; the gate is NOT green." >&2
  exit 0
fi
echo "[gate] ALL PASS" >&2
exit 0
