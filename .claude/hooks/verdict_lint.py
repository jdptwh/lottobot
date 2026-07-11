#!/usr/bin/env python3
"""verdict_lint.py (v5) — validates a structured verdict artifact.

Two contracts share this validator, dispatched on the top-level "source" key:
  * v4 REVIEWER verdict (no "source", or source != "panel"): UNCHANGED from v4.
  * v5 PANEL verdict ("source":"panel"): validated against
    panel/schema/panel_verdict.schema.json (hand-mirrored here — stdlib only).

Importable API (used by panel/cli.py so the exit mapping has ONE source of truth):
  * panel_exit_code(v) -> int   : mapping for a VALID panel dict (0/1/2).
  * validate_panel_dict(v) -> str|None : structural check (None = valid; else error).
Both are pure (no exit, no print). The script entrypoint (__main__) wraps them.

Exit codes:
  v4 path:   0 valid · 1 missing file · 2 malformed
  panel path: 0 PASS&!cost_cap · 1 FAIL · 2 REVISE or cost_cap · 3 malformed · 1 missing
  (panel exit 3 = malformed is distinct from v4 exit 2; on the panel path exit 2 means
   ONLY REVISE/cost-cap "needs human". gate.sh blocks on any non-zero.)

Usage: python3 .claude/hooks/verdict_lint.py [path]   (default .claude/state/verdict.json)
"""
import json
import sys

# ---- v4 reviewer-verdict contract (UNCHANGED) --------------------------------
REQUIRED = {
    "task": str, "verdict": str, "findings": list, "escalate": bool,
    "escalate_reason": str, "gates_rerun": bool, "review_cycle": int,
}
FINDING_KEYS = {"file": str, "line": int, "issue": str, "fix": str, "nit": bool}

# ---- v5 panel-verdict contract (mirrors panel_verdict.schema.json) -----------
PANEL_GATES = ("plan", "review")
PANEL_VERDICTS = ("PASS", "FAIL", "REVISE")
PANEL_SEVERITIES = ("critical", "major", "minor")
PANEL_ARBITER_RULINGS = ("upheld", "rejected", None)


def fail(msg):
    print(f"[verdict_lint] FAIL: {msg}", file=sys.stderr)
    sys.exit(2)


def panel_fail(msg):
    print(f"[verdict_lint] FAIL: {msg}", file=sys.stderr)
    sys.exit(3)


def _is_number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def panel_exit_code(v):
    """Map an ALREADY-VALID panel verdict dict to its exit code (0/1/2).
    cost_cap_breached (any verdict) -> 2; PASS -> 0; FAIL -> 1; REVISE -> 2."""
    if v.get("cost_cap_breached"):
        return 2
    verdict = v.get("verdict")
    if verdict == "PASS":
        return 0
    if verdict == "FAIL":
        return 1
    return 2


def validate_panel_dict(v):
    """Structurally validate a source=panel verdict. Returns None if valid, else an
    error string. Pure: no exit, no print (so panel/cli.py can reuse it)."""
    top = {"schema_version": str, "source": str, "gate": str, "task_id": str,
           "expert_opinions": list, "disagreement_summary": dict, "synthesis": dict,
           "verdict": str, "cost_cap_breached": bool}
    for key, typ in top.items():
        if key not in v:
            return f"missing required key: {key}"
        if not isinstance(v[key], typ):
            return f"key '{key}' must be {typ.__name__}, got {type(v[key]).__name__}"
    if "cost_usd_total" not in v or not _is_number(v["cost_usd_total"]):
        return "cost_usd_total missing or not a number"
    if v["gate"] not in PANEL_GATES:
        return f"gate must be one of {PANEL_GATES}, got {v['gate']!r}"
    if v["verdict"] not in PANEL_VERDICTS:
        return f"verdict must be one of {PANEL_VERDICTS}, got {v['verdict']!r}"
    if not v["expert_opinions"]:
        return "expert_opinions must be a non-empty list"
    for i, e in enumerate(v["expert_opinions"]):
        if not isinstance(e, dict):
            return f"expert_opinions[{i}] must be an object"
        for key, typ in (("model", str), ("summary", str)):
            if key not in e or not isinstance(e[key], typ):
                return f"expert_opinions[{i}].{key} missing or not {typ.__name__}"
        if "confidence" not in e or not _is_number(e["confidence"]):
            return f"expert_opinions[{i}].confidence missing or not a number"
    syn = v["synthesis"]
    if "synthesizer" not in syn or not isinstance(syn["synthesizer"], str):
        return "synthesis.synthesizer missing or not str"
    if "artifact" not in syn or not (syn["artifact"] is None or isinstance(syn["artifact"], str)):
        return "synthesis.artifact missing or not (str | null)"
    if "findings" in syn:
        if not isinstance(syn["findings"], list):
            return "synthesis.findings must be a list"
        for i, fnd in enumerate(syn["findings"]):
            if not isinstance(fnd, dict):
                return f"synthesis.findings[{i}] must be an object"
            if fnd.get("severity") not in PANEL_SEVERITIES:
                return f"synthesis.findings[{i}].severity must be one of {PANEL_SEVERITIES}"
            if "arbiter_ruling" in fnd and fnd["arbiter_ruling"] not in PANEL_ARBITER_RULINGS:
                return f"synthesis.findings[{i}].arbiter_ruling must be one of {PANEL_ARBITER_RULINGS}"
    return None


def validate_panel(v):
    """Script entry for the panel path: validate, print, exit with the mapped code."""
    err = validate_panel_dict(v)
    if err:
        panel_fail(err)
    n = len(v["expert_opinions"])
    if v["cost_cap_breached"]:
        print(f"[verdict_lint] OK — panel/{v['gate']} · verdict {v['verdict']} · "
              f"{n} expert(s) · COST CAP BREACHED → needs human")
    else:
        print(f"[verdict_lint] OK — panel/{v['gate']} · verdict {v['verdict']} · "
              f"{n} expert(s) · ${v['cost_usd_total']}")
    sys.exit(panel_exit_code(v))


def _force_utf8_output():
    """The human-readable output uses ·/—/→; the Windows console default codec
    (cp1252) can't encode those and a print would crash the process mid-run.
    Reconfigure to UTF-8 at the SCRIPT ENTRY only — never at import time, so
    panel/cli.py's by-path import of this module stays side-effect-free."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError, OSError):
            pass  # stream replaced/closed or reconfigure unavailable — leave as-is


def _main(argv=None):
    _force_utf8_output()
    argv = sys.argv if argv is None else argv
    path = argv[1] if len(argv) > 1 else ".claude/state/verdict.json"
    try:
        with open(path, encoding="utf-8") as f:
            v = json.load(f)
    except FileNotFoundError:
        print(f"[verdict_lint] MISSING: {path} — verdict artifact not emitted.", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        fail(f"invalid JSON: {e}")

    if isinstance(v, dict) and v.get("source") == "panel":
        validate_panel(v)  # exits

    # ---- v4 reviewer-verdict path (UNCHANGED from v4) ------------------------
    if not isinstance(v, dict):
        fail("top level must be an object")
    for key, typ in REQUIRED.items():
        if key not in v:
            fail(f"missing required key: {key}")
        if not isinstance(v[key], typ):
            fail(f"key '{key}' must be {typ.__name__}, got {type(v[key]).__name__}")
    if v["verdict"] not in ("PASS", "FAIL"):
        fail(f"verdict must be PASS or FAIL, got {v['verdict']!r}")
    if v["verdict"] == "FAIL" and not v["findings"]:
        fail("FAIL verdict requires at least one finding")
    if v["escalate"] and not v["escalate_reason"].strip():
        fail("escalate=true requires a non-empty escalate_reason")
    if not v["gates_rerun"]:
        fail("gates_rerun=false — reviewer must re-run verification itself (Gate Checklist #1)")
    if v["review_cycle"] < 1:
        fail("review_cycle must be >= 1")
    for i, fnd in enumerate(v["findings"]):
        if not isinstance(fnd, dict):
            fail(f"findings[{i}] must be an object")
        for key, typ in FINDING_KEYS.items():
            if key not in fnd or not isinstance(fnd[key], typ):
                fail(f"findings[{i}].{key} missing or not {typ.__name__}")
    nits = sum(1 for f in v["findings"] if f["nit"])
    print(f"[verdict_lint] OK — {v['verdict']} · cycle {v['review_cycle']} · "
          f"{len(v['findings'])} finding(s) ({nits} nit) · escalate={v['escalate']}")
    sys.exit(0)


if __name__ == "__main__":
    _main()
