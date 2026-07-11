"""Line-preserving, validated editor for a fixed allowlist of .claude/agent.config keys.

Observe/config-only: this writes config, never runs anything. Every write validates ALL
updates first, then rewrites atomically (temp + os.replace), changing ONLY the matched
key lines and leaving every other line (comments, blanks, ordering, other keys)
byte-identical. Values are shell-metachar-rejected so nothing can break out of the
KEY="VALUE" quoting in the sourced file. No secret key is editable.
"""
from __future__ import annotations

import math
import os
import re
import tempfile

from panel.config import parse_config_file

_META = set('"\'\n\r$`\\')


def _no_meta(v):
    if any(c in _META for c in v):
        raise ValueError(f"value contains a forbidden character: {v!r}")
    return v


def _v_str(v):
    v = str(v).strip()
    if not v:
        raise ValueError("must be non-empty")
    return _no_meta(v)


def _v_posint(v):
    s = str(v).strip()
    if not re.fullmatch(r"[0-9]+", s) or int(s) < 1:
        raise ValueError(f"must be a positive integer >= 1, got {v!r}")
    return str(int(s))


def _v_float_pos(v):
    s = str(v).strip()
    try:
        f = float(s)
    except ValueError:
        raise ValueError(f"must be a number, got {v!r}")
    if not math.isfinite(f):
        raise ValueError(f"must be a finite number, got {v!r}")
    if not (f > 0):
        raise ValueError(f"must be > 0, got {v!r}")
    return _no_meta(s)


def _v_bool(v):
    s = str(v).strip().lower()
    if s in ("1", "true", "yes", "on"):
        return "1"
    if s in ("0", "false", "no", "off"):
        return "0"
    raise ValueError(f"must be a boolean, got {v!r}")


def _v_enum(allowed):
    allowed = frozenset(allowed)
    def _f(v):
        s = str(v).strip()
        if s not in allowed:
            raise ValueError(f"must be one of {sorted(allowed)}, got {v!r}")
        return s
    return _f


# The authoritative allowlist: roles + lineups + budgets + cost cap + safe panel toggles.
# Anything NOT here (secrets, *_PATH, VERIFY_CMD/LINT_CMD/UI_VERIFY_CMD, PANEL_PROVIDER/
# PANEL_ROUTING, arbitrary keys) is rejected.
EDITABLE_KEYS = {
    # roles
    "PLANNER_MODEL": _v_str, "DRAFTER_MODEL": _v_str, "IMPLEMENTER_MODEL": _v_str,
    "REVIEWER_MODEL": _v_str, "BULK_MODEL": _v_str,
    # lineups / synth / arbiter
    "PANEL_PLAN_LINEUP": _v_str, "PANEL_PLAN_SYNTH": _v_str,
    "PANEL_REVIEW_LINEUP": _v_str, "PANEL_REVIEW_ARBITER": _v_str,
    # loop budgets
    "MAX_IMPL_ATTEMPTS": _v_posint, "MAX_REVIEW_CYCLES": _v_posint, "MAX_BULK_RETRIES": _v_posint,
    # cost cap
    "PANEL_MAX_COST_USD": _v_float_pos,
    # panel toggles
    "PANEL_ENABLED": _v_bool,
    "PANEL_TRIGGER": _v_enum({"always", "novelty", "escalation"}),
    "PANEL_MODE_PLAN": _v_enum({"aggregate", "union"}),
    "PANEL_MODE_REVIEW": _v_enum({"aggregate", "union"}),
    # asset pipeline (Rule 13)
    "ASSET_ENABLED": _v_bool,
    "ASSET_MODEL_DEFAULT": _v_str, "ASSET_MODEL_TEXTED": _v_str,
    "ASSET_QA_JUDGE": _v_str,
    "ASSET_MAX_ATTEMPTS": _v_posint,
    "ASSET_MAX_COST_USD": _v_float_pos,
    # asset pipeline — video mode
    "ASSET_VIDEO_MODEL_DEFAULT": _v_str, "ASSET_VIDEO_MODEL_AUDIO": _v_str,
    "ASSET_VIDEO_MAX_COST_USD": _v_float_pos,
    "ASSET_VIDEO_QA_FRAMES": _v_posint,
}


def read_editable(config_path):
    """Return {key: current_value} for exactly the editable keys ('' if absent)."""
    vals = parse_config_file(config_path)
    return {k: vals.get(k, "") for k in EDITABLE_KEYS}


def validate_updates(updates):
    """Validate a dict of {key: value}. Returns {key: normalized_value} or raises
    ValueError (before any disk write) on the first invalid/non-allowlisted key."""
    if not updates:
        raise ValueError("no updates provided")
    out = {}
    for k, v in updates.items():
        if k not in EDITABLE_KEYS:
            raise ValueError(f"key is not editable: {k}")
        out[k] = EDITABLE_KEYS[k](v)
    return out


def _reassign(line, key, newval):
    """Rewrite a matched KEY=... line to KEY="newval", preserving indentation and any
    trailing inline comment."""
    m = re.match(r'^(\s*)' + re.escape(key) + r'\s*=\s*(.*)$', line)
    indent = m.group(1)
    rhs = m.group(2)
    qm = re.match(r'^(["\'])(.*?)\1(.*)$', rhs)
    if qm:
        tail = qm.group(3)
    else:
        cm = re.match(r'^([^#]*?)(\s*#.*)?$', rhs)
        tail = cm.group(2) or ""
    return f'{indent}{key}="{newval}"{tail}'


def apply_panel_updates(text, validated):
    """Return new file text with only the validated keys' values changed. Keys not
    present in the file are appended. All other lines are byte-identical."""
    lines = text.split("\n")
    seen = set()
    for i, line in enumerate(lines):
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key = s.split("=", 1)[0].strip()
        if key in validated:
            lines[i] = _reassign(line, key, validated[key])
            seen.add(key)
    missing = [k for k in validated if k not in seen]
    if missing:
        if lines and lines[-1] == "":
            lines.pop()  # avoid trailing blank drift
        for k in missing:
            lines.append(f'{k}="{validated[k]}"')
        lines.append("")
    return "\n".join(lines)


def write_editable(config_path, updates):
    """Validate then atomically rewrite config_path. On any validation error the file
    is left byte-identical (validation happens before the temp file is renamed)."""
    validated = validate_updates(updates)
    with open(config_path, encoding="utf-8") as f:
        text = f.read()
    new_text = apply_panel_updates(text, validated)
    d = os.path.dirname(os.path.abspath(config_path)) or "."
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".agentcfg.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(new_text)
        os.replace(tmp, config_path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
