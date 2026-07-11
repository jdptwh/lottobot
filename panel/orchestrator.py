"""panel/orchestrator.py — the panel core (Wave 3).

Stateless, read-only. Fans a task out to a mixed-provider expert panel over the
Wave 2 `call_model` (wrapped in `call_with_retry`), meters cost with `CostMeter`,
and assembles a schema-valid `panel_verdict` dict for both gates:

  * run_plan   -> aggregator synthesis: experts propose plans; a synthesizer merges
                  them into one artifact + a disagreement summary.
  * run_review -> union + arbiter: reviewers produce findings independently; findings
                  are unioned/deduped; an arbiter adjudicates ONLY disputed findings.

Design rulings (docs/specs/wave3_spec.md): (a) stdlib ThreadPoolExecutor over the
sync call_model (no httpx); (b) verdict DERIVED deterministically from structured
fields; (c) returns the dict, writes no file; (d) disputed iff reviewers conflict on
severity or stance; (e) requests response_format json_schema but validates locally;
(f) seeded shuffle then collect by submission index (never completion order);
(g) partial failure: proceed iff >=2 survive, else structured REVISE.

Untrusted model output is defensively sanitized before it enters the emitted verdict
(unknown severities dropped, confidences clamped to [0,1], contradictions normalized
to the schema shape) so the returned dict always validates against
panel/schema/panel_verdict.schema.json. The panel never writes files and never
mutates inputs, so retries stay safe.

Expert parsing is TOLERANT (`_coerce_expert`): a large/free-form prompt often pushes
a model to answer in prose or a fenced ```json block, or to fill the task's own
findings schema instead of our envelope. Rather than dropping such a response
(parsed=None) or emitting it with an empty summary — either of which can starve the
>=2-survivor rule and collapse the panel to a non-forming REVISE — we recover JSON
from fences/embedded spans, synthesize a summary from findings, or capture prose into
the summary. Every raw response (previously discarded) is logged and surfaced in a
non-contract `diagnostics` block so drops are diagnosable from the artifact alone.
"""
from __future__ import annotations

import json
import logging
import random
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from panel.adapters import call_model as _default_call_model
from panel.cost_meter import CostMeter, DEFAULT_COST_CAP_USD
from panel.errors import PanelError, TerminalProviderError
from panel.safe_retry import call_with_retry

_log = logging.getLogger("panel.orchestrator")

_PROMPTS = Path(__file__).resolve().parent / "prompts"
_SEVERITY_RANK = {"critical": 0, "major": 1, "minor": 2}

# Tolerant-parsing knobs. Large free-form prompts push mixed-provider models to
# return prose or fenced JSON instead of the exact envelope; rather than silently
# dropping/emptying those (which starves the >=2-survivor rule), we recover what we
# can. `_MIN_PROSE_CHARS` is the floor below which non-JSON output is treated as
# noise (a refusal / stray token) rather than a usable opinion.
_FENCE_RE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.DOTALL)
_MIN_PROSE_CHARS = 40
_PROSE_SUMMARY_CAP = 1200
_RAW_PREVIEW_CAP = 4000
_ALT_SUMMARY_KEYS = ("summary", "analysis", "assessment", "overview", "review", "opinion")
_ALT_REC_KEYS = ("recommendation", "recommendations", "advice", "decision")
_ALT_ISSUE_KEYS = ("issue", "problem", "finding", "where", "title", "description")

# Strict-mode structured-output schemas. OpenAI (and OpenAI-compatible routes)
# REJECT a strict json_schema unless every object sets additionalProperties:false
# and lists every property in required — a bare {"type":"object"} is a 400, which
# is terminal (no retry), which silently dropped those experts from the panel.
# Keyword set is kept to the strict-mode-safe subset (type/enum/properties/
# required/items/additionalProperties); numeric bounds are enforced locally.
# Tolerant parsing above is the belt; these schemas are the suspenders — enforced
# where the route supports them, harmless (with the 400 fallback) where it doesn't.
def _obj(props):
    return {"type": "object", "properties": props, "required": list(props),
            "additionalProperties": False}


_STR = {"type": "string"}
_PLAN_FINDING = _obj({"severity": {"type": "string", "enum": ["critical", "major", "minor"]},
                      "issue": _STR})
_REVIEW_FINDING = _obj({"issue": _STR,
                        "severity": {"type": "string", "enum": ["critical", "major", "minor"]},
                        "file": _STR, "line": {"type": "integer"},
                        "stance": {"type": "string", "enum": ["issue", "not_an_issue"]}})


def _rf(name, schema):
    return {"type": "json_schema",
            "json_schema": {"name": name, "strict": True, "schema": schema}}


_PLAN_EXPERT_RF = _rf("expert_plan", _obj({
    "summary": _STR, "recommendation": _STR, "plan": _STR,
    "confidence": {"type": "number"},
    "findings": {"type": "array", "items": _PLAN_FINDING}}))
_REVIEW_EXPERT_RF = _rf("expert_review", _obj({
    "summary": _STR, "confidence": {"type": "number"},
    "findings": {"type": "array", "items": _REVIEW_FINDING}}))
_SYNTH_RF = _rf("synthesis", _obj({
    "artifact": _STR,
    "consensus_points": {"type": "array", "items": _STR},
    "contradictions": {"type": "array",
                       "items": _obj({"topic": _STR,
                                      "positions": {"type": "array",
                                                    "items": _obj({"label": _STR, "stance": _STR})}})},
    "unique_insights": {"type": "array", "items": _obj({"label": _STR, "insight": _STR})},
    "blind_spots": {"type": "array", "items": _STR},
    "rationale": _STR,
    "findings": {"type": "array", "items": _PLAN_FINDING}}))
_ARBITER_RF = _rf("rulings", _obj({
    "rulings": {"type": "array",
                "items": _obj({"id": _STR,
                               "ruling": {"type": "string", "enum": ["upheld", "rejected"]}})}}))


def _call_structured(call_model, slug, messages, rf, *, max_tokens, api_key):
    """call_with_retry, requesting structured output — but if the route rejects the
    request outright (HTTP 400, e.g. a provider that dislikes the json_schema
    payload), fall back ONCE to the same call without response_format. The prompts
    already demand a single JSON object and parsing is tolerant + validated locally,
    so the panel prefers a parseable-but-unenforced answer over dropping the expert."""
    try:
        return call_with_retry(
            lambda: call_model(slug, messages, response_format=rf,
                               max_tokens=max_tokens, api_key=api_key))
    except TerminalProviderError as e:
        if e.code != 400 or rf is None:
            raise
        _log.warning("panel structured-output rejected (400) slug=%s — retrying without response_format", slug)
        return call_with_retry(
            lambda: call_model(slug, messages, response_format=None,
                               max_tokens=max_tokens, api_key=api_key))


def _load_template(name):
    return (_PROMPTS / name).read_text(encoding="utf-8")


def _label(i):
    return chr(ord("A") + i)


def _try_dict(text):
    """json.loads(text) if it yields a dict, else None."""
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    return obj if isinstance(obj, dict) else None


def _balanced_object(text):
    """First balanced {...} span in text (string/escape aware), or None. Lets us
    recover a JSON object a model wrapped in prose ('Here is my review: {...}')."""
    if not isinstance(text, str):
        return None
    start = text.find("{")
    if start < 0:
        return None
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def _extract_dict(text):
    """Best-effort JSON object from model output. Returns (dict, how) where how is
    'json' | 'fenced-json' | 'embedded-json', or (None, None). Tries strict parse,
    then ```json fences, then the first balanced-brace span."""
    if not isinstance(text, str) or not text.strip():
        return None, None
    d = _try_dict(text)
    if d is not None:
        return d, "json"
    for block in _FENCE_RE.findall(text):
        d = _try_dict(block)
        if d is not None:
            return d, "fenced-json"
    span = _balanced_object(text)
    if span is not None:
        d = _try_dict(span)
        if d is not None:
            return d, "embedded-json"
    return None, None


def _parse_loose(text):
    """Tolerant dict-or-{} parse for synthesizer/arbiter output (which can also
    arrive fenced or prose-wrapped)."""
    d, _ = _extract_dict(text)
    return d or {}


def _first_str(obj, keys):
    for k in keys:
        v = obj.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _summary_from_findings(obj):
    """Synthesize a one-line summary from a findings-shaped payload (the common
    'model answered the task's own findings schema, not our envelope' case)."""
    fs = obj.get("findings")
    if not isinstance(fs, list):
        return ""
    issues = []
    for f in fs:
        if isinstance(f, dict):
            t = _first_str(f, _ALT_ISSUE_KEYS)
            if t:
                issues.append(t)
        elif isinstance(f, str) and f.strip():
            issues.append(f.strip())
    if not issues:
        return ""
    head = "; ".join(issues[:3])
    more = f" (+{len(issues) - 3} more)" if len(issues) > 3 else ""
    return f"{len(issues)} finding(s): {head}{more}"


def _coerce_expert(text):
    """Turn raw expert output into a usable payload dict, tolerantly.

    Returns (payload, note). `payload` is None ONLY when `text` carries no usable
    signal (empty, or trivially short non-JSON noise); otherwise it is a dict whose
    'summary' is guaranteed non-empty, so a well-meaning-but-off-format response
    survives instead of being dropped or emptied. Recovery order: direct JSON ->
    fenced JSON -> embedded JSON -> prose-captured-into-summary."""
    obj, how = _extract_dict(text)
    if obj is not None:
        summary = (_first_str(obj, _ALT_SUMMARY_KEYS)
                   or _summary_from_findings(obj)
                   or _first_str(obj, _ALT_REC_KEYS))
        recommendation = _first_str(obj, _ALT_REC_KEYS)
        findings = obj.get("findings") if isinstance(obj.get("findings"), list) else []
        if summary or findings:
            payload = dict(obj)
            payload["summary"] = summary or "(structured findings only; no summary field returned)"
            payload["recommendation"] = recommendation
            return payload, how
        # a dict with no usable content ({} / unknown keys only) -> try prose below
    stripped = (text or "").strip()
    if len(stripped) >= _MIN_PROSE_CHARS:
        return ({"summary": stripped[:_PROSE_SUMMARY_CAP], "recommendation": "",
                 "plan": "", "confidence": 0.0, "findings": []}, "prose")
    return None, ("empty" if not stripped else "noise")


def _listify(x):
    """A model-supplied field is only iterable if it is actually a list. `x or []`
    is NOT enough — a truthy non-list ({"findings": 1}, {"rulings": "x"}) is
    parseable JSON that would crash a `for` (audit cycle-3 fix). Everything that
    iterates untrusted model output goes through here."""
    return x if isinstance(x, list) else []


def _num(x, default=0.0):
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else default


def _clamp01(x):
    return max(0.0, min(1.0, _num(x, 0.0)))


def _clean_findings(raw):
    """Keep only findings with a recognized severity (drop unknowns so a bad model
    severity can never poison the emitted verdict or fail the gate)."""
    out = []
    for f in _listify(raw):
        if isinstance(f, dict) and f.get("severity") in _SEVERITY_RANK:
            out.append({"severity": f["severity"], "issue": str(f.get("issue", ""))})
    return out


def _normalize_contradictions(raw):
    """Coerce contradictions to [{topic, positions:[{label,stance}]}] so the emitted
    dict is schema-valid while preserving truthiness for the J1 verdict rule."""
    out = []
    for c in _listify(raw):
        if isinstance(c, dict):
            positions = [{"label": str(p.get("label", "")), "stance": str(p.get("stance", ""))}
                         for p in _listify(c.get("positions")) if isinstance(p, dict)]
            out.append({"topic": str(c.get("topic", "")), "positions": positions})
        else:
            out.append({"topic": str(c), "positions": []})
    return out


def _dispatch_experts(lineup, system_prompt, user_prompt, *, rf, call_model, meter, seed,
                      api_key, max_tokens, max_workers, attachments=None):
    """Dispatch each expert once in a SEEDED-shuffled order; collect by submission
    index (not completion order). Meters every successful ModelResult.

    `attachments` (optional list of multimodal content parts — see
    panel/attachments.py) go to the EXPERTS ONLY: the synthesizer/arbiter work
    from the experts' structured outputs, so the panel never pays image/PDF
    input twice per gate. A model that can't take a part fails with a provider
    error and surfaces through the normal dropped-expert diagnostics."""
    order = list(lineup)
    random.Random(seed).shuffle(order)
    user_content = ([{"type": "text", "text": user_prompt}] + list(attachments)
                    if attachments else user_prompt)
    messages = [{"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}]

    def _one(slug):
        return _call_structured(call_model, slug, messages, rf,
                                max_tokens=max_tokens, api_key=api_key)

    results = [None] * len(order)
    with ThreadPoolExecutor(max_workers=max_workers or len(order)) as ex:
        future_to_idx = {ex.submit(_one, slug): i for i, slug in enumerate(order)}
        for fut, i in future_to_idx.items():
            slug = order[i]
            try:
                res = fut.result()
            except PanelError as e:
                _log.warning("panel expert ERROR slug=%s error=%s", slug, e)
                results[i] = {"slug": slug, "index": i, "result": None, "parsed": None,
                              "raw": None, "note": "provider-error", "error": str(e)}
                continue
            meter.add(res)
            parsed, note = _coerce_expert(res.content)
            raw = res.content or ""
            if parsed is None:
                # Raw response is otherwise discarded — log it (WARNING reaches stderr
                # via logging's last-resort handler even with no configured handler) so
                # a real-run drop is diagnosable instead of a silent "fewer than 2".
                _log.warning("panel expert DROPPED slug=%s tokens_out=%s note=%s raw=%r",
                             slug, res.tokens_out, note, raw[:_RAW_PREVIEW_CAP])
            else:
                _log.info("panel expert OK slug=%s tokens_out=%s recovered=%s summary_len=%d",
                          slug, res.tokens_out, note, len(str(parsed.get("summary", ""))))
            results[i] = {"slug": slug, "index": i, "result": res, "parsed": parsed,
                          "raw": raw, "note": note,
                          "error": None if parsed is not None else f"unparseable expert output ({note})"}
    return results


def _expert_opinion(entry, role):
    r, p = entry["result"], entry["parsed"]
    return {
        "model": entry["slug"], "role": role,
        "summary": str(p.get("summary", "")),
        "recommendation": str(p.get("recommendation", "")),
        "confidence": _clamp01(p.get("confidence")),
        "tokens_in": r.tokens_in if r.tokens_in is not None else 0,
        "tokens_out": r.tokens_out if r.tokens_out is not None else 0,
        "cost_usd": r.cost_usd if r.cost_usd is not None else 0.0,
    }


def _drop_reason(entry):
    """'<slug> — <why>' for a dropped expert, so blind_spots names the cause."""
    return f"{entry['slug']} — {entry.get('error') or 'no usable output'}"


def _diagnostics(entries):
    """Compact, bounded per-expert record (kept OUT of the gate contract but IN the
    emitted verdict under a non-required 'diagnostics' key) so a run's drops and
    recoveries stay inspectable from the artifact alone — the raw response is no
    longer discarded."""
    experts = []
    for e in entries:
        res = e.get("result")
        raw = e.get("raw")
        experts.append({
            "model": e["slug"],
            "survived": e["parsed"] is not None,
            "recovered_via": e.get("note"),
            "error": e.get("error"),
            "tokens_out": res.tokens_out if res is not None else None,
            "raw_preview": raw[:_RAW_PREVIEW_CAP] if isinstance(raw, str) else None,
            "raw_truncated": bool(isinstance(raw, str) and len(raw) > _RAW_PREVIEW_CAP),
        })
    return {"experts": experts}


def _derive_plan_verdict(findings, contradictions):
    sev = {f.get("severity") for f in findings}
    if "critical" in sev:
        return "FAIL"
    if "major" in sev or contradictions:
        return "REVISE"
    return "PASS"


def _derive_review_verdict(findings):
    # Fail closed on disputed findings the arbiter did NOT explicitly reject: an
    # "upheld" or an UNRULED (None — e.g. the arbiter call failed / was unparseable)
    # disputed finding still counts toward the verdict. Only an explicit "rejected"
    # drops it. (Audit fix: previously only "upheld" counted, so a failed arbiter
    # silently dropped disputed criticals and could flip the verdict to PASS.)
    eff = [f for f in findings if (not f.get("disputed")) or f.get("arbiter_ruling") != "rejected"]
    sev = {f.get("severity") for f in eff}
    if "critical" in sev:
        return "FAIL"
    if "major" in sev:
        return "REVISE"
    return "PASS"


def _structured_failure(task_id, gate, survivors_entries, role, meter, dropped):
    opinions = [_expert_opinion(e, role) for e in survivors_entries if e["parsed"] is not None]
    if not opinions:
        opinions = [{"model": "panel/none", "role": role,
                     "summary": "Panel could not form: fewer than 2 experts returned usable output.",
                     "recommendation": "", "confidence": 0.0,
                     "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0}]
    return {
        "schema_version": "5.0", "source": "panel", "gate": gate, "task_id": task_id,
        "expert_opinions": opinions,
        "disagreement_summary": {"consensus_points": [], "contradictions": [], "unique_insights": [],
                                 "blind_spots": [f"dropped expert: {d}" for d in dropped]},
        "synthesis": {"synthesizer": "panel/none", "artifact": None,
                      "rationale": "Fewer than two experts survived; a single opinion is not a panel.",
                      "findings": []},
        "verdict": "REVISE",
        "cost_usd_total": round(meter.total, 10), "cost_cap_breached": meter.breached,
    }


def _cap_breach_verdict(task_id, gate, opinions, disagreement, synthesizer, meter, findings=None):
    findings = findings or []
    return {
        "schema_version": "5.0", "source": "panel", "gate": gate, "task_id": task_id,
        "expert_opinions": opinions, "disagreement_summary": disagreement,
        "synthesis": {"synthesizer": synthesizer, "artifact": None,
                      "rationale": "Cost cap breached during the expert phase; synthesis was not run.",
                      "findings": findings},
        "verdict": _derive_plan_verdict(findings, disagreement.get("contradictions", []))
                   if gate == "plan" else _derive_review_verdict(findings),
        "cost_usd_total": round(meter.total, 10), "cost_cap_breached": True,
    }


def run_plan(task_id, task_prompt, lineup, synthesizer, *, cap_usd=DEFAULT_COST_CAP_USD,
             seed=0, call_model=None, api_key=None, max_tokens=None, max_workers=None,
             attachments=None):
    call_model = call_model or _default_call_model
    meter = CostMeter(cap_usd=cap_usd)
    entries = _dispatch_experts(lineup, _load_template("expert_plan.md"), task_prompt,
                                rf=_PLAN_EXPERT_RF, call_model=call_model, meter=meter,
                                seed=seed, api_key=api_key,
                                max_tokens=max_tokens, max_workers=max_workers,
                                attachments=attachments)
    survivors = [e for e in entries if e["parsed"] is not None]
    dropped = [_drop_reason(e) for e in entries if e["parsed"] is None]
    diag = _diagnostics(entries)

    if len(survivors) < 2:
        v = _structured_failure(task_id, "plan", survivors, "expert", meter, dropped)
        v["diagnostics"] = diag
        return v

    opinions = [_expert_opinion(e, "expert") for e in survivors]
    if meter.breached:
        disagreement = {"consensus_points": [], "contradictions": [], "unique_insights": [],
                        "blind_spots": [f"dropped expert: {d}" for d in dropped]}
        v = _cap_breach_verdict(task_id, "plan", opinions, disagreement, synthesizer, meter)
        v["diagnostics"] = diag
        return v

    anon = []
    for pos, e in enumerate(survivors):
        p = e["parsed"]
        anon.append({"label": f"Expert {_label(pos)}", "summary": p.get("summary", ""),
                     "recommendation": p.get("recommendation", ""), "plan": p.get("plan", ""),
                     "findings": p.get("findings", [])})
    synth_user = "TASK:\n" + task_prompt + "\n\nANONYMOUS EXPERT PLANS:\n" + json.dumps(anon, indent=2)
    synth_messages = [{"role": "system", "content": _load_template("plan_aggregate.md")},
                      {"role": "user", "content": synth_user}]
    synth_res = _call_structured(call_model, synthesizer, synth_messages, _SYNTH_RF,
                                 max_tokens=max_tokens, api_key=api_key)
    meter.add(synth_res)

    # Fail closed when the synthesizer produced NO parseable output. _parse_loose
    # would coerce garbage to {}, which yields empty findings and a false PASS
    # (audit fix). A plan we could not synthesize is not a passing plan -> REVISE.
    synth_obj, _synth_how = _extract_dict(synth_res.content)
    if synth_obj is None:
        return {
            "schema_version": "5.0", "source": "panel", "gate": "plan", "task_id": task_id,
            "expert_opinions": opinions,
            "disagreement_summary": {"consensus_points": [], "contradictions": [],
                                     "unique_insights": [],
                                     "blind_spots": ["synthesizer produced no parseable output"]
                                                    + [f"dropped expert: {d}" for d in dropped]},
            "synthesis": {"synthesizer": synthesizer, "artifact": None,
                          "rationale": "Synthesizer output was unparseable; no plan could be "
                                       "certified. Escalating for human review.",
                          "findings": []},
            "verdict": "REVISE",
            "cost_usd_total": round(meter.total, 10), "cost_cap_breached": meter.breached,
            "diagnostics": diag,
        }
    synth = synth_obj

    findings = _clean_findings(synth.get("findings"))
    contradictions = _normalize_contradictions(synth.get("contradictions"))
    disagreement = {
        "consensus_points": [str(x) for x in _listify(synth.get("consensus_points"))],
        "contradictions": contradictions,
        "unique_insights": [u for u in _listify(synth.get("unique_insights")) if isinstance(u, dict)],
        "blind_spots": [str(x) for x in _listify(synth.get("blind_spots"))]
                       + [f"dropped expert: {d}" for d in dropped],
    }
    artifact = synth.get("artifact")
    return {
        "schema_version": "5.0", "source": "panel", "gate": "plan", "task_id": task_id,
        "expert_opinions": opinions, "disagreement_summary": disagreement,
        "synthesis": {"synthesizer": synthesizer,
                      "artifact": artifact if isinstance(artifact, str) else "",
                      "rationale": str(synth.get("rationale", "Merged expert plans.")),
                      "findings": findings},
        "verdict": _derive_plan_verdict(findings, contradictions),
        "cost_usd_total": round(meter.total, 10), "cost_cap_breached": meter.breached,
        "diagnostics": diag,
    }


def _finding_key(f):
    # `line` is untrusted model output: int("abc") would crash the union
    # (audit fix) — coerce safely, default 0.
    try:
        line = int(f.get("line", 0) or 0)
    except (TypeError, ValueError):
        line = 0
    return (str(f.get("issue", "")).strip().lower(), str(f.get("file", "")), line)


def _union_findings(survivors):
    groups = {}
    for e in survivors:
        slug = e["slug"]
        for f in _listify(e["parsed"].get("findings")):
            if not isinstance(f, dict) or f.get("severity") not in _SEVERITY_RANK:
                continue
            key = _finding_key(f)
            g = groups.setdefault(key, {"severities": set(), "stances": set(), "source_models": set(),
                                        "issue": f.get("issue", ""), "file": f.get("file", ""),
                                        "line": f.get("line", 0)})
            g["severities"].add(f.get("severity"))
            g["stances"].add(f.get("stance", "issue"))
            g["source_models"].add(slug)

    findings = []
    for i, (key, g) in enumerate(sorted(
            groups.items(),
            key=lambda kv: (min(_SEVERITY_RANK[s] for s in kv[1]["severities"]), kv[0]))):
        severity = min(g["severities"], key=lambda s: _SEVERITY_RANK[s])
        disputed = (len(g["severities"]) > 1) or ("issue" in g["stances"] and "not_an_issue" in g["stances"])
        try:
            line = int(g["line"] or 0)
        except (TypeError, ValueError):
            line = 0
        findings.append({"id": f"F{i + 1}", "severity": severity, "confidence": 0.0,
                         # issue/file/line are IN the emitted verdict — a finding
                         # without its text is unactionable (audit fix: these were
                         # only carried in stripped _-keys, so non-PASS verdicts
                         # shipped as bare ids + severities).
                         "issue": str(g["issue"]), "file": str(g["file"]), "line": line,
                         "source_models": sorted(g["source_models"]), "disputed": disputed,
                         "arbiter_ruling": None, "_issue": g["issue"],
                         "_severities": sorted(g["severities"], key=lambda s: _SEVERITY_RANK[s])})
    return findings


def run_review(task_id, task_prompt, lineup, arbiter, *, cap_usd=DEFAULT_COST_CAP_USD,
               seed=0, call_model=None, api_key=None, max_tokens=None, max_workers=None,
               attachments=None):
    call_model = call_model or _default_call_model
    meter = CostMeter(cap_usd=cap_usd)
    entries = _dispatch_experts(lineup, _load_template("expert_review.md"), task_prompt,
                                rf=_REVIEW_EXPERT_RF, call_model=call_model, meter=meter,
                                seed=seed, api_key=api_key,
                                max_tokens=max_tokens, max_workers=max_workers,
                                attachments=attachments)
    survivors = [e for e in entries if e["parsed"] is not None]
    dropped = [_drop_reason(e) for e in entries if e["parsed"] is None]
    diag = _diagnostics(entries)

    if len(survivors) < 2:
        v = _structured_failure(task_id, "review", survivors, "reviewer", meter, dropped)
        v["diagnostics"] = diag
        return v

    opinions = [_expert_opinion(e, "reviewer") for e in survivors]
    disagreement = {"consensus_points": [], "contradictions": [], "unique_insights": [],
                    "blind_spots": [f"dropped expert: {d}" for d in dropped]}
    findings = _union_findings(survivors)

    # Prose-recovered reviewers kept the panel from collapsing, but their FINDINGS
    # channel is lost — "no structured findings" from prose is not evidence of a
    # clean change. If NO reviewer delivered structured output, an empty union
    # must not read as PASS: fail closed to REVISE with the reason on record
    # (audit fix). Structured reviewers present -> prose peers only warn.
    prose = [e["slug"] for e in survivors if e.get("note") == "prose"]
    structured = [e for e in survivors if e.get("note") != "prose"]
    if prose:
        disagreement["blind_spots"].append(
            "reviewer(s) answered in prose (findings channel lost): " + ", ".join(prose))
    if not structured and not findings:
        v = _structured_failure(task_id, "review", survivors, "reviewer", meter,
                                dropped + [f"{s} — prose only, findings channel lost"
                                           for s in prose])
        v["diagnostics"] = diag
        return v

    if meter.breached:
        # Preserve the union findings collected BEFORE the breach (audit fix: passing
        # [] made _derive_review_verdict return PASS, discarding real criticals).
        # Disputed items are unarbitrated here -> counted fail-closed.
        clean = [{k: v for k, v in f.items() if not k.startswith("_")} for f in findings]
        v = _cap_breach_verdict(task_id, "review", opinions, disagreement, arbiter, meter,
                                findings=clean)
        v["diagnostics"] = diag
        return v

    disputed = [f for f in findings if f["disputed"]]
    if disputed:
        arb_payload = [{"id": f["id"], "issue": f["_issue"], "conflicting_severities": f["_severities"]}
                       for f in disputed]
        arb_messages = [{"role": "system", "content": _load_template("review_arbiter.md")},
                        {"role": "user", "content": json.dumps({"disputed_findings": arb_payload}, indent=2)}]
        # The arbiter is a SINGLE call outside the per-expert executor, so a
        # provider failure (PanelError) or a malformed-but-parseable payload
        # ({"rulings": null}) must NOT crash the review — both leave the disputed
        # findings unruled, which _derive_review_verdict now counts fail-closed
        # (audit fix: previously an arbiter 500 raised out of run_review, and
        # `.get("rulings", [])` returned None on an explicit null and crashed).
        arb_obj = None
        try:
            arb_res = _call_structured(call_model, arbiter, arb_messages, _ARBITER_RF,
                                       max_tokens=max_tokens, api_key=api_key)
            meter.add(arb_res)
            arb_obj, _arb_how = _extract_dict(arb_res.content)
        except PanelError as e:
            _log.warning("panel arbiter ERROR: %s — disputed findings left unresolved", e)
        # ids must be hashable strings — a malformed ruling like {"id": []} would
        # TypeError as a dict key (audit fix); non-str ids are dropped -> unruled
        # -> fail-closed via _derive_review_verdict.
        rulings = ({r["id"]: r.get("ruling") for r in _listify(arb_obj.get("rulings"))
                    if isinstance(r, dict) and isinstance(r.get("id"), str)}
                   if arb_obj is not None else {})
        for f in findings:
            if f["disputed"]:
                rule = rulings.get(f["id"])
                f["arbiter_ruling"] = rule if rule in ("upheld", "rejected") else None
        # An unadjudicated dispute is NOT silently dropped (fixed in
        # _derive_review_verdict); surface WHY so the human sees it.
        unruled = [f["id"] for f in findings if f["disputed"] and f["arbiter_ruling"] is None]
        if unruled:
            disagreement["blind_spots"].append(
                "arbiter did not rule on disputed finding(s): " + ", ".join(unruled)
                + " — counted as unresolved (fail-closed)")

    verdict = _derive_review_verdict(findings)
    clean_findings = [{k: v for k, v in f.items() if not k.startswith("_")} for f in findings]
    return {
        "schema_version": "5.0", "source": "panel", "gate": "review", "task_id": task_id,
        "expert_opinions": opinions, "disagreement_summary": disagreement,
        "synthesis": {"synthesizer": arbiter, "artifact": None,
                      "rationale": "Union of independent reviewer findings; arbiter adjudicated disputed items.",
                      "findings": clean_findings},
        "verdict": verdict,
        "cost_usd_total": round(meter.total, 10), "cost_cap_breached": meter.breached,
        "diagnostics": diag,
    }
