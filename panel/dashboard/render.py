"""Server-side HTML for the panel dashboard — a compact, tabbed control panel.

Matches the approved mockup docs/mockups/dashboard_mockup.html (ROUTING.md Rule 11).
Everything is server-rendered from real data; all model/verdict-derived text is passed
through html.escape. No external CSS/JS/CDN — inline CSS + inline SVG, CSS-only tabs
(no JavaScript). The editable controls associate with the config <form> via the HTML5
`form=` attribute so the CSS-only tab/segment radios are never submitted.
"""
from __future__ import annotations

import math
from html import escape as _e

from panel.dashboard.config_writer import EDITABLE_KEYS
from panel.prices import VERIFIED_PRICES

_ENUM_CHOICES = {
    "PANEL_TRIGGER": ["novelty", "always", "escalation"],
    "PANEL_MODE_PLAN": ["aggregate", "union"],
    "PANEL_MODE_REVIEW": ["union", "aggregate"],
}
_ROLE_KEYS = ["PLANNER_MODEL", "REVIEWER_MODEL", "IMPLEMENTER_MODEL", "DRAFTER_MODEL", "BULK_MODEL"]
_LINEUP_KEYS = ["PANEL_PLAN_LINEUP", "PANEL_PLAN_SYNTH", "PANEL_REVIEW_LINEUP", "PANEL_REVIEW_ARBITER"]
# multi-pick lineups render as checkbox chips; single-pick roles render as selects
_MULTI_KEYS = {"PANEL_PLAN_LINEUP", "PANEL_REVIEW_LINEUP"}
_SELECT_KEYS = {"PANEL_PLAN_SYNTH", "PANEL_REVIEW_ARBITER"}
# options for the routed-agent role dropdowns; these mirror .claude/agents/*.md
# frontmatter vocabulary (Claude Code model names), not OpenRouter slugs. The
# currently-configured value is always offered too, so hand-edits round-trip.
_ROLE_OPTIONS = ["claude-fable-5", "claude-opus-4-8", "opus", "sonnet", "haiku"]
# asset pipeline (Rule 13). Generator ids are ATLAS CLOUD model ids; the judge list
# mirrors panel.asset_qa.JUDGE_POOL but is hardcoded here — the dashboard must never
# import asset_qa (it imports the orchestrator; import-graph test forbids it).
_ASSET_GEN_OPTIONS = ["google/nano-banana-2-pro", "google/nano-banana-2",
                      "openai/gpt-image-2", "bfl/flux-2", "bytedance/seedream-5"]
_ASSET_JUDGE_OPTIONS = ["auto", "openai/gpt-5.6-luna", "google/gemini-3.1-flash-lite",
                        "anthropic/claude-opus-4.8"]
_ASSET_VIDEO_OPTIONS = ["bytedance/seedance-2.0-fast", "bytedance/seedance-2.0-pro",
                        "google/veo-3.1", "kling/kling-3.0-standard", "openai/sora-2"]
_ASSET_SELECTS = [("ASSET_MODEL_DEFAULT", _ASSET_GEN_OPTIONS),
                  ("ASSET_MODEL_TEXTED", _ASSET_GEN_OPTIONS),
                  ("ASSET_QA_JUDGE", _ASSET_JUDGE_OPTIONS),
                  ("ASSET_VIDEO_MODEL_DEFAULT", _ASSET_VIDEO_OPTIONS),
                  ("ASSET_VIDEO_MODEL_AUDIO", _ASSET_VIDEO_OPTIONS)]
_ASSET_TXT_KEYS = ["ASSET_MAX_ATTEMPTS", "ASSET_MAX_COST_USD",
                   "ASSET_VIDEO_MAX_COST_USD", "ASSET_VIDEO_QA_FRAMES"]
_BUDGET_KEYS = ["PANEL_MAX_COST_USD", "MAX_IMPL_ATTEMPTS", "MAX_REVIEW_CYCLES", "MAX_BULK_RETRIES"]
_TOGGLE_ENUMS = ["PANEL_TRIGGER", "PANEL_MODE_PLAN", "PANEL_MODE_REVIEW"]
_SEV_RANK = {"critical": 0, "major": 1, "minor": 2}


def _f(x, default=0.0):
    try:
        v = float(x)
        return v if math.isfinite(v) else default
    except (TypeError, ValueError):
        return default


def _ring(pct, color, size, r):
    circ = 2 * math.pi * r
    off = circ * (1 - max(0.0, min(1.0, pct / 100.0)))
    c = size / 2.0
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" aria-hidden="true">'
            f'<circle cx="{c}" cy="{c}" r="{r}" fill="none" stroke="#172422" stroke-width="4"/>'
            f'<circle cx="{c}" cy="{c}" r="{r}" fill="none" stroke="{color}" stroke-width="4" '
            f'stroke-linecap="round" stroke-dasharray="{circ:.1f}" stroke-dashoffset="{off:.1f}" '
            f'transform="rotate(-90 {c} {c})"/></svg>')


def _sparkline(vals, w=64, h=24):
    if not vals:
        vals = [0, 0]
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    n = len(vals)
    step = w / max(1, n - 1)
    pts = " ".join(f"{i*step:.0f},{h - 2 - (v-lo)/span*(h-4):.0f}" for i, v in enumerate(vals))
    last_x = (n - 1) * step
    last_y = h - 2 - (vals[-1] - lo) / span * (h - 4)
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" preserveAspectRatio="none" aria-hidden="true">'
            f'<polyline points="{pts}" fill="none" stroke="#26b598" stroke-width="2"/>'
            f'<circle cx="{last_x:.0f}" cy="{last_y:.0f}" r="2.4" fill="#67d0fd"/></svg>')


def _badge(verdict):
    v = _e(str(verdict or "—"))
    cls = v if v in ("PASS", "FAIL", "REVISE") else ""
    return f'<span class="vbadge {cls}">{v}</span>'


def _sev(sev):
    s = _e(str(sev or ""))
    cls = s if s in _SEV_RANK else "minor"
    return f'<span class="sev {cls}"><span class="d"></span>{s}</span>'


_STYLE = """
:root{--bg:#070b0c;--app:#0a1113;--panel:#0d1618;--panel2:#101d1e;--raise:#12211f;
--line:#172422;--line2:#213230;--hair:rgba(255,255,255,.04);--ink:#eaf4f0;--ink2:#9fb4ac;
--ink3:#61756e;--ink4:#405049;--teal:#4fe3c1;--teal2:#26b598;--tealink:#04140f;--cyan:#67d0fd;
--pass:#4fe3a1;--pass-bg:rgba(79,227,161,.10);--pass-line:rgba(79,227,161,.32);
--fail:#ff5d6c;--fail-bg:rgba(255,93,108,.10);--fail-line:rgba(255,93,108,.34);
--revise:#f5c451;--revise-bg:rgba(245,196,81,.10);--revise-line:rgba(245,196,81,.32);
--amber:#f5c451;--red:#ff5d6c;--mono:ui-monospace,"SFMono-Regular",Menlo,Consolas,monospace;
--sans:"Segoe UI",system-ui,-apple-system,Roboto,Helvetica,Arial,sans-serif;--r:16px;--r-sm:11px;--r-xs:8px;
--soft:inset 0 1px 0 var(--hair),0 10px 26px rgba(0,0,0,.36);}
*{box-sizing:border-box}html,body{margin:0}
body{min-height:100vh;background:radial-gradient(1000px 500px at 82% -12%,rgba(79,227,193,.10),transparent 60%),radial-gradient(760px 420px at 4% 2%,rgba(103,208,253,.06),transparent 55%),var(--bg);color:var(--ink);font:13.5px/1.5 var(--sans);-webkit-font-smoothing:antialiased;display:flex;justify-content:center;padding:26px}
.lab{font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:var(--ink3);font-weight:600}.mono{font-family:var(--mono)}
.tabr{position:absolute;opacity:0;pointer-events:none}
.app{width:100%;max-width:1160px;background:linear-gradient(180deg,var(--app),#080e0f);border:1px solid var(--line);border-radius:22px;box-shadow:var(--soft);overflow:hidden;display:flex;flex-direction:column;min-height:720px}
.top{display:flex;align-items:center;gap:14px;padding:16px 22px;border-bottom:1px solid var(--line)}
.brand{display:flex;align-items:center;gap:12px}.brand .name{font-weight:650;letter-spacing:.24em;font-size:13px}.brand .sub{color:var(--ink3);font-size:10px;letter-spacing:.2em;text-transform:uppercase}
.grow{flex:1}.status{display:inline-flex;align-items:center;gap:8px;padding:6px 12px;border-radius:999px;border:1px solid var(--line2);background:var(--panel);font-size:11.5px;font-weight:600;color:var(--ink2)}
.status .dot{width:7px;height:7px;border-radius:50%;background:var(--ink3)}.status.on .dot{background:var(--pass);box-shadow:0 0 8px var(--pass)}.status.rw{color:var(--ink3)}
.iconbtn{width:33px;height:33px;border-radius:9px;border:1px solid var(--line2);background:var(--panel);color:var(--ink2);display:grid;place-items:center;cursor:pointer}.iconbtn:hover{border-color:var(--teal2);color:var(--teal)}
.tabs{display:flex;gap:4px;padding:8px 16px 0;border-bottom:1px solid var(--line);background:linear-gradient(180deg,rgba(79,227,193,.03),transparent)}
.tabs label{padding:11px 16px 13px;color:var(--ink3);font-size:12.5px;font-weight:600;cursor:pointer;border-bottom:2px solid transparent;border-radius:8px 8px 0 0;user-select:none;display:inline-flex;gap:8px;align-items:center}
.tabs label:hover{color:var(--ink2);background:rgba(255,255,255,.02)}.tabs label .c{font-family:var(--mono);font-size:10px;color:var(--ink4);background:var(--panel);border:1px solid var(--line2);border-radius:6px;padding:0 6px;line-height:16px}
#tab-ov:checked~.app .tabs label[for=tab-ov],#tab-vd:checked~.app .tabs label[for=tab-vd],#tab-ct:checked~.app .tabs label[for=tab-ct],#tab-cf:checked~.app .tabs label[for=tab-cf]{color:var(--ink);border-bottom-color:var(--teal)}
.stage{padding:18px 22px 22px;flex:1}.view{display:none}
#tab-ov:checked~.app .view.ov,#tab-vd:checked~.app .view.vd,#tab-ct:checked~.app .view.ct,#tab-cf:checked~.app .view.cf{display:block}
.card{background:linear-gradient(180deg,var(--panel2),var(--panel));border:1px solid var(--line);border-radius:var(--r);box-shadow:var(--soft);padding:16px}
.ch{display:flex;align-items:center;gap:9px;margin-bottom:12px}.ch h2{margin:0;font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--ink2);font-weight:650}.ch .m{margin-left:auto;color:var(--ink3);font-size:10.5px}
.vbadge{display:inline-block;font-weight:750;letter-spacing:.5px;padding:4px 12px;border-radius:8px;font-size:13px;color:var(--ink2);background:var(--raise);border:1px solid var(--line2)}
.vbadge.PASS{color:var(--pass);background:var(--pass-bg);border-color:var(--pass-line)}.vbadge.FAIL{color:var(--fail);background:var(--fail-bg);border-color:var(--fail-line)}.vbadge.REVISE{color:var(--revise);background:var(--revise-bg);border-color:var(--revise-line)}
.gate-chip{font-family:var(--mono);font-size:11px;color:var(--teal);background:rgba(79,227,193,.08);border:1px solid var(--line2);padding:3px 9px;border-radius:7px}
.chip{display:inline-flex;align-items:center;gap:7px;padding:5px 10px;border-radius:999px;background:var(--raise);border:1px solid var(--line2);font-family:var(--mono);font-size:11.5px;color:var(--ink2)}
.chip .av{width:14px;height:14px;border-radius:50%;flex:0 0 auto;background:linear-gradient(135deg,#4fe3c1,#26b598)}
.meter{display:flex;align-items:center;gap:8px}.meter .track{flex:1;height:5px;border-radius:99px;background:#081210;border:1px solid var(--line2);overflow:hidden}.meter .track>i{display:block;height:100%;background:linear-gradient(90deg,var(--teal2),var(--teal))}.meter .n{font-family:var(--mono);font-size:10.5px;color:var(--ink3)}
.sev{display:inline-flex;align-items:center;gap:7px;font-weight:600}.sev .d{width:8px;height:8px;border-radius:50%}
.sev.critical{color:var(--fail)}.sev.critical .d{background:var(--fail);box-shadow:0 0 8px var(--fail)}.sev.major{color:var(--amber)}.sev.major .d{background:var(--amber);box-shadow:0 0 8px var(--amber)}.sev.minor{color:var(--ink2)}.sev.minor .d{background:var(--ink3)}
table{width:100%;border-collapse:collapse;font-size:12px}thead th{text-align:left;color:var(--ink3);font-weight:600;font-size:9.5px;letter-spacing:.12em;text-transform:uppercase;padding:6px 8px;border-bottom:1px solid var(--line2)}
tbody td{padding:8px;border-bottom:1px solid var(--line);color:var(--ink2)}tbody tr:last-child td{border-bottom:0}.ruling.up{color:var(--pass);font-weight:600}.ruling.na{color:var(--ink4)}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.kpi{background:linear-gradient(180deg,var(--panel2),var(--panel));border:1px solid var(--line);border-radius:var(--r-sm);padding:13px 14px;box-shadow:var(--soft)}
.kpi .r{display:flex;align-items:center;justify-content:space-between}.kpi .v{font-family:var(--mono);font-size:23px;font-weight:600;letter-spacing:-.5px;margin:8px 0 1px}.kpi .s{color:var(--ink3);font-size:10.5px}.kpi .warn{color:var(--amber)}
.ov-grid{display:grid;grid-template-columns:1.35fr 1fr;gap:14px;margin-top:14px}.stack{display:flex;flex-direction:column;gap:14px}
.flags{display:flex;flex-direction:column;gap:8px}.flag{display:flex;align-items:center;gap:10px;padding:9px 11px;border-radius:var(--r-xs);border:1px solid var(--line2);background:var(--raise);font-size:11.5px}
.flag .fi{width:8px;height:8px;border-radius:50%;flex:0 0 auto}.flag.warn{border-color:var(--revise-line);background:var(--revise-bg)}.flag.warn .fi{background:var(--amber);box-shadow:0 0 8px var(--amber)}.flag.info .fi{background:var(--ink3)}.flag .s{margin-left:auto;color:var(--ink3);font-family:var(--mono);font-size:10px}
.pipeline{display:flex;align-items:center;gap:8px;margin-top:4px;flex-wrap:wrap}.pnode{display:flex;align-items:center;gap:7px;padding:6px 11px;border-radius:999px;border:1px solid var(--line2);background:var(--raise);font-size:11px;color:var(--ink2)}.pnode .d{width:7px;height:7px;border-radius:50%;background:var(--teal)}.pline{flex:1;min-width:14px;height:1px;background:linear-gradient(90deg,var(--teal2),transparent)}
.seg{display:inline-flex;background:#081210;border:1px solid var(--line2);border-radius:9px;padding:3px;gap:2px}
.seg label{padding:6px 11px;border-radius:7px;font-size:11.5px;color:var(--ink3);cursor:pointer;font-family:var(--mono)}
.seg input{position:absolute;opacity:0;pointer-events:none}.seg input:checked+label{background:linear-gradient(180deg,var(--teal),var(--teal2));color:var(--tealink);font-weight:650}
.switch{display:inline-flex;align-items:center;gap:10px}.switch input{position:absolute;opacity:0}
.switch .tk{width:44px;height:24px;border-radius:99px;background:#0a1412;border:1px solid var(--line2);position:relative;transition:.15s;cursor:pointer;display:inline-block}
.switch .tk::after{content:"";position:absolute;top:2px;left:2px;width:18px;height:18px;border-radius:50%;background:var(--ink3);transition:.15s}
.switch input:checked+.tk{background:var(--fail-bg);border-color:var(--fail-line)}.switch input:checked+.tk::after{left:22px;background:var(--fail)}.switch .lb{font-family:var(--mono);font-size:12px;color:var(--ink2)}
.cfg-in{width:100%;padding:8px 10px;background:#081210;border:1px solid var(--line2);color:var(--ink);border-radius:8px;font:12px var(--mono)}.cfg-in:focus{outline:none;border-color:var(--teal2);box-shadow:0 0 0 3px rgba(79,227,193,.14)}
select.cfg-in{appearance:none;-webkit-appearance:none;background-image:linear-gradient(45deg,transparent 50%,var(--ink3) 50%),linear-gradient(135deg,var(--ink3) 50%,transparent 50%);background-position:calc(100% - 16px) 55%,calc(100% - 11px) 55%;background-size:5px 5px;background-repeat:no-repeat;cursor:pointer}
.multi{display:flex;flex-wrap:wrap;gap:6px}.multi input{position:absolute;opacity:0;pointer-events:none}
.multi label{padding:6px 11px;border-radius:999px;border:1px solid var(--line2);background:#081210;font:11.5px var(--mono);color:var(--ink3);cursor:pointer;user-select:none}
.multi label:hover{border-color:var(--teal2);color:var(--ink2)}
.multi input:checked+label{background:linear-gradient(180deg,var(--teal),var(--teal2));border-color:var(--teal2);color:var(--tealink);font-weight:650}
.fld{margin-bottom:12px}.fld .l{font-size:11.5px;color:var(--ink);font-weight:600;margin-bottom:2px}.fld .h{font-size:10.5px;color:var(--ink3);margin:0 0 6px}
.bad .cfg-in{border-color:var(--fail-line);box-shadow:0 0 0 3px rgba(255,93,108,.12)}.bad .e{color:var(--fail);font-size:10.5px;margin-top:4px}
.warnrow{display:flex;gap:10px;align-items:center;padding:9px 12px;border-radius:var(--r-xs);border:1px solid var(--fail-line);background:var(--fail-bg);color:#ffd7db;font-size:11.5px;margin-top:10px}
.locked{display:flex;align-items:center;gap:8px;color:var(--ink3);font-size:10.5px;border-top:1px dashed var(--line2);padding-top:10px;margin-top:12px}
.savebar{display:flex;align-items:center;gap:12px;margin-top:14px}.btn{padding:9px 18px;border-radius:10px;border:0;cursor:pointer;font-weight:650;font-size:12.5px;background:linear-gradient(180deg,var(--teal),var(--teal2));color:var(--tealink);box-shadow:0 6px 16px rgba(38,181,152,.28)}.savebar .note{color:var(--ink3);font-size:10.5px}
.msg{padding:9px 12px;border-radius:var(--r-xs);font-size:11.5px;margin-bottom:12px}.msg.ok{color:var(--pass);background:var(--pass-bg);border:1px solid var(--pass-line)}.msg.err{color:var(--fail);background:var(--fail-bg);border:1px solid var(--fail-line)}
.cfseg{position:absolute;opacity:0;pointer-events:none}.subnav{display:inline-flex;gap:3px;background:#081210;border:1px solid var(--line2);border-radius:10px;padding:3px;margin-bottom:14px}
.subnav label{padding:7px 13px;border-radius:8px;font-size:11.5px;color:var(--ink3);cursor:pointer;font-weight:600}
#cs-tog:checked~.subnav label[for=cs-tog],#cs-rol:checked~.subnav label[for=cs-rol],#cs-lin:checked~.subnav label[for=cs-lin],#cs-ast:checked~.subnav label[for=cs-ast],#cs-bud:checked~.subnav label[for=cs-bud]{background:var(--raise);color:var(--ink);border:1px solid var(--line2)}
.sv{display:none}#cs-tog:checked~.segwrap .sv.tog,#cs-rol:checked~.segwrap .sv.rol,#cs-lin:checked~.segwrap .sv.lin,#cs-ast:checked~.segwrap .sv.ast,#cs-bud:checked~.segwrap .sv.bud{display:block}
.duo{display:grid;grid-template-columns:1fr 1fr;gap:14px 20px}.foot{color:var(--ink4);font-size:10.5px;padding:12px 22px;border-top:1px solid var(--line)}
@media(max-width:820px){.kpis{grid-template-columns:1fr 1fr}.ov-grid,.duo{grid-template-columns:1fr}}
"""


_HELP = {
    "PANEL_TRIGGER": "When the lead invokes a panel",
    "PANEL_MODE_PLAN": "PLAN aggregation", "PANEL_MODE_REVIEW": "REVIEW aggregation",
    "PLANNER_MODEL": "Spec authority / arbiter", "REVIEWER_MODEL": "Senior reviewer",
    "IMPLEMENTER_MODEL": "Judgment work", "DRAFTER_MODEL": "Cheap first-draft",
    "BULK_MODEL": "Machine-verifiable grunt",
    "PANEL_PLAN_LINEUP": "PLAN experts (comma-separated)", "PANEL_PLAN_SYNTH": "PLAN synthesizer",
    "PANEL_REVIEW_LINEUP": "REVIEW reviewers", "PANEL_REVIEW_ARBITER": "Adjudicates disputed findings",
    "PANEL_MAX_COST_USD": "Per-invocation cap · finite, &gt; 0", "MAX_IMPL_ATTEMPTS": "int ≥ 1",
    "MAX_REVIEW_CYCLES": "int ≥ 1", "MAX_BULK_RETRIES": "int ≥ 1",
    "ASSET_ENABLED": "Master switch · asset-forge refuses to run when 0",
    "ASSET_MODEL_DEFAULT": "Generator · photoreal / UI comps",
    "ASSET_MODEL_TEXTED": "Generator when the asset bears text",
    "ASSET_QA_JUDGE": "auto = cross-family pick (bias guard)",
    "ASSET_MAX_ATTEMPTS": "generate→judge attempts · int ≥ 1",
    "ASSET_MAX_COST_USD": "per-asset loop cap · finite, &gt; 0",
    "ASSET_VIDEO_MODEL_DEFAULT": "Video generator · Seedance 2.0 has native audio",
    "ASSET_VIDEO_MODEL_AUDIO": "Override seam for audio-critical briefs",
    "ASSET_VIDEO_MAX_COST_USD": "per-video loop cap · priced per second",
    "ASSET_VIDEO_QA_FRAMES": "frames sampled per judge call · int ≥ 1",
}


def _kpis(v, cost, editable):
    present = bool(v) and v.get("present", True)
    verdict = v.get("verdict") if present else None
    ring_c = {"PASS": "#4fe3a1", "FAIL": "#ff5d6c", "REVISE": "#f5c451"}.get(verdict, "#405049")
    run_cost = _f(v.get("cost_usd_total")) if present else 0.0
    cap = _f(editable.get("PANEL_MAX_COST_USD"), 2.0) or 2.0
    breached = bool(present and v.get("cost_cap_breached"))
    pct = min(100.0, run_cost / cap * 100.0) if cap > 0 else 0.0
    cap_c = "#ff5d6c" if breached or pct >= 100 else ("#f5c451" if pct >= 80 else "#4fe3c1")
    entries = cost.get("entries") or []
    spark_vals = [_f(e.get("cost_usd_total")) for e in entries] or [0, 0]
    total = _f(cost.get("total_usd"))
    count = int(cost.get("count") or 0)
    return (
        '<div class="kpis">'
        f'<div class="kpi"><div class="r"><span class="lab">Verdict</span>{_ring(100 if present else 0, ring_c, 24, 15)}</div>'
        f'<div class="v">{_badge(verdict)}</div><div class="s">{_e(str(v.get("gate","—")) if present else "no verdict")} gate</div></div>'
        f'<div class="kpi"><div class="r"><span class="lab">This run</span></div>'
        f'<div class="v">${run_cost:.2f}</div><div class="s">{_e(str(len(v.get("expert_opinions",[])) ) if present else "0")} expert(s)</div></div>'
        f'<div class="kpi"><div class="r"><span class="lab">Cap headroom</span>{_ring(pct, cap_c, 38, 16)}</div>'
        f'<div class="v{" warn" if pct>=80 else ""}">{pct:.0f}%</div><div class="s">${run_cost:.2f} / ${cap:.2f} cap</div></div>'
        f'<div class="kpi"><div class="r"><span class="lab">Runs</span>{_sparkline(spark_vals)}</div>'
        f'<div class="v">{count}</div><div class="s">cumulative ${total:.2f}</div></div>'
        '</div>'
    )


def _reviewer_card(e):
    conf = _f(e.get("confidence"))
    return ('<div style="background:var(--raise);border:1px solid var(--line2);border-radius:11px;padding:12px">'
            '<div style="display:flex;justify-content:space-between;gap:8px">'
            f'<span class="mono" style="color:var(--teal);font-size:11.5px">{_e(str(e.get("model","")))}</span>'
            f'<span class="lab">{_e(str(e.get("role","")))}</span></div>'
            f'<p style="color:var(--ink2);font-size:12px;margin:8px 0 10px">{_e(str(e.get("summary","")))}</p>'
            f'<div class="meter"><div class="track"><i style="width:{conf*100:.0f}%"></i></div>'
            f'<span class="n">{conf:.2f}</span></div></div>')


def _findings_rows(findings):
    if not findings:
        return '<tr><td colspan="4" style="color:var(--ink3)">No findings.</td></tr>'
    rows = []
    for f in findings:
        rule = f.get("arbiter_ruling")
        rcell = (f'<span class="ruling up">upheld</span>' if rule == "upheld"
                 else (f'<span class="ruling na">rejected</span>' if rule == "rejected"
                       else '<span class="ruling na">not disputed</span>'))
        src = ", ".join(str(s) for s in (f.get("source_models") or [])) or "—"
        rows.append(f'<tr><td>{_sev(f.get("severity"))}</td>'
                    f'<td>{_e(str(f.get("issue","") or f.get("id","")))}</td>'
                    f'<td class="mono" style="color:var(--ink3)">{_e(src)}</td><td>{rcell}</td></tr>')
    return "".join(rows)


def _overview(v, cost, editable):
    present = bool(v) and v.get("present", True)
    kpis = _kpis(v, cost, editable)
    if not present:
        left = ('<div class="card"><div class="ch"><h2>Latest verdict</h2></div>'
                '<p style="color:var(--ink3)">No panel_verdict.json yet. (populated when the lead writes one.)</p></div>')
    else:
        experts = v.get("expert_opinions", [])
        chips = "".join(f'<span class="chip"><span class="av"></span>{_e(str(e.get("model","")).split("/")[-1])} · '
                        f'{_f(e.get("confidence")):.2f}</span>' for e in experts)
        syn = v.get("synthesis") or {}
        findings = syn.get("findings") or []
        top = ""
        if findings:
            f0 = sorted(findings, key=lambda f: _SEV_RANK.get(f.get("severity"), 3))[0]
            top = (f'<div style="margin-top:12px;color:var(--ink2);font-size:12px">{_sev(f0.get("severity"))} &nbsp;'
                   f'{_e(str(f0.get("issue","")))}</div>')
        left = ('<div class="card"><div class="ch"><h2>Latest verdict</h2>'
                f'<span class="gate-chip">{_e(str(v.get("gate","")).upper())}</span></div>'
                '<div style="display:flex;align-items:center;gap:10px;margin-bottom:12px">'
                f'{_badge(v.get("verdict"))}<span class="mono" style="color:var(--ink3);font-size:11.5px">{_e(str(v.get("task_id","")))}</span></div>'
                '<div class="pipeline"><span class="pnode"><span class="d"></span> experts</span><span class="pline"></span>'
                f'<span class="pnode"><span class="d"></span> {_e(str(v.get("gate","")))}</span><span class="pline"></span>'
                f'<span class="pnode"><span class="d" style="background:#4fe3a1"></span> {_badge(v.get("verdict"))}</span></div>'
                f'<div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:14px">{chips}</div>{top}</div>')
    total = _f(cost.get("total_usd"))
    count = int(cost.get("count") or 0)
    flags = []
    cap = _f(editable.get("PANEL_MAX_COST_USD"), 2.0) or 2.0
    run_cost = _f(v.get("cost_usd_total")) if present else 0.0
    if present and (v.get("cost_cap_breached") or (cap > 0 and run_cost / cap >= 0.8)):
        flags.append('<div class="flag warn"><span class="fi"></span> Cost near/over cap<span class="s">now</span></div>')
    enabled = str(editable.get("PANEL_ENABLED", "0")).strip() in ("1", "true", "on", "yes")
    flags.append(f'<div class="flag info"><span class="fi"></span> Panel {"active" if enabled else "dormant"} · PANEL_ENABLED={"1" if enabled else "0"}<span class="s">config</span></div>')
    right = ('<div class="stack"><div class="card"><div class="ch"><h2>Cost</h2><span class="m">dashboard log</span></div>'
             f'<div class="mono" style="font-size:24px;font-weight:600">${total:.2f}</div>'
             f'<div class="lab" style="letter-spacing:.1em;margin-top:2px">{count} run(s)</div></div>'
             f'<div class="card"><div class="ch"><h2>System flags</h2></div><div class="flags">{"".join(flags)}</div></div></div>')
    return f'<section class="view ov">{kpis}<div class="ov-grid">{left}{right}</div></section>'


def _verdict_view(v):
    present = bool(v) and v.get("present", True)
    if not present:
        return '<section class="view vd"><div class="card"><div class="ch"><h2>Latest verdict</h2></div><p style="color:var(--ink3)">No verdict yet.</p></div></section>'
    experts = v.get("expert_opinions", [])
    cards = "".join(_reviewer_card(e) for e in experts)
    syn = v.get("synthesis") or {}
    findings = sorted(syn.get("findings") or [], key=lambda f: _SEV_RANK.get(f.get("severity"), 3))
    art = syn.get("artifact")
    art_html = (f'<div class="ch" style="margin-top:16px"><h2>Synthesis artifact</h2></div>'
                f'<pre style="white-space:pre-wrap;background:#081210;border:1px solid var(--line2);border-radius:10px;padding:12px;font:11.5px var(--mono);color:var(--ink2);margin:0">{_e(str(art))}</pre>'
                if art else "")
    dis = v.get("disagreement_summary") or {}
    nblind = len(dis.get("blind_spots") or [])
    ncontra = len(dis.get("contradictions") or [])
    return (
        '<section class="view vd"><div class="ov-grid" style="grid-template-columns:1.4fr 1fr;margin-top:0">'
        '<div class="card"><div class="ch"><h2>Reviewers</h2><span class="m">seeded order · identity-stripped</span></div>'
        f'<div class="duo">{cards}</div>'
        '<div class="ch" style="margin-top:16px"><h2>Findings</h2><span class="m">union · arbiter on disputed</span></div>'
        '<table><thead><tr><th>Severity</th><th>Finding</th><th>Source</th><th>Arbiter</th></tr></thead>'
        f'<tbody>{_findings_rows(findings)}</tbody></table>{art_html}</div>'
        '<div class="stack"><div class="card"><div class="ch"><h2>Verdict</h2></div>'
        f'<div style="text-align:center;padding:6px 0 12px">{_badge(v.get("verdict"))}'
        f'<div class="s" style="margin-top:10px">exit-mapped · gate {_e(str(v.get("gate","")))}</div></div></div>'
        '<div class="card"><div class="ch"><h2>Disagreement</h2></div><div class="flags">'
        f'<div class="flag info"><span class="fi"></span> Contradictions<span class="s">{ncontra}</span></div>'
        f'<div class="flag info"><span class="fi"></span> Blind spots<span class="s">{nblind}</span></div></div></div></div>'
        '</div></section>'
    )


def _cost_view(v, cost, editable):
    cap = _f(editable.get("PANEL_MAX_COST_USD"), 2.0) or 2.0
    run_cost = _f(v.get("cost_usd_total")) if (v and v.get("present", True)) else 0.0
    pct = min(100.0, run_cost / cap * 100.0) if cap > 0 else 0.0
    cap_c = "#ff5d6c" if pct >= 100 else ("#f5c451" if pct >= 80 else "#4fe3c1")
    entries = cost.get("entries") or []
    rows = "".join(
        f'<tr><td class="mono">{_e(str(e.get("task_id","")))}</td><td>{_e(str(e.get("gate","")))}</td>'
        f'<td>{_sev("minor") if e.get("verdict")=="PASS" else _sev("major")}<span class="mono" style="margin-left:6px">{_e(str(e.get("verdict","")))}</span></td>'
        f'<td class="mono">${_f(e.get("cost_usd_total")):.2f}</td></tr>' for e in entries) \
        or '<tr><td colspan="4" style="color:var(--ink3)">No runs observed yet.</td></tr>'
    return (
        '<section class="view ct"><div class="ov-grid" style="grid-template-columns:1fr 1.3fr;margin-top:0">'
        '<div class="card" style="display:flex;flex-direction:column;align-items:center;justify-content:center">'
        '<div class="ch" style="align-self:flex-start"><h2>Cap headroom</h2></div>'
        f'{_ring(pct, cap_c, 150, 16)}'
        f'<div class="mono" style="font-size:24px;font-weight:600;margin-top:12px">${run_cost:.2f} <span style="color:var(--ink3);font-size:14px">/ ${cap:.2f}</span></div>'
        f'<div class="s">{pct:.0f}% of per-invocation cap · latest run</div></div>'
        '<div class="stack"><div class="card"><div class="ch"><h2>Cost log</h2>'
        '<span class="m">.claude/state/panel_cost_log.jsonl</span></div>'
        '<table><thead><tr><th>Task</th><th>Gate</th><th>Verdict</th><th>Cost</th></tr></thead>'
        f'<tbody>{rows}</tbody></table></div></div></div></section>'
    )


def _switch(key, editable, help_text):
    on = str(editable.get(key, "0")).strip() in ("1", "true", "on", "yes")
    return (f'<div class="fld"><div class="l">{key}</div><p class="h">{help_text}</p>'
            '<label class="switch">'
            f'<input type="hidden" name="{key}" value="0" form="cfg">'
            f'<input type="checkbox" name="{key}" value="1" form="cfg"{" checked" if on else ""}>'
            f'<span class="tk"></span><span class="lb">{"1 — enabled" if on else "0 — disabled"}</span></label></div>')


def _seg(key, editable):
    cur = str(editable.get(key, "")).strip()
    opts = _ENUM_CHOICES[key]
    if cur not in opts:
        cur = opts[0]
    inner = "".join(
        f'<input type="radio" name="{key}" id="{key}-{c}" value="{c}" form="cfg"{" checked" if c==cur else ""}>'
        f'<label for="{key}-{c}">{_e(c)}</label>' for c in opts)
    return (f'<div class="fld"><div class="l">{key}</div><p class="h">{_HELP.get(key,"")}</p>'
            f'<div class="seg">{inner}</div></div>')


def _slug_options(editable):
    """Dropdown vocabulary: the verified price table (known-good OpenRouter slugs)
    plus whatever is currently configured, so an exotic hand-edited slug still
    round-trips instead of being silently swapped on save."""
    opts = set(VERIFIED_PRICES)
    for key in _MULTI_KEYS | _SELECT_KEYS:
        opts.update(x.strip() for x in str(editable.get(key, "")).split(",") if x.strip())
    return sorted(opts)


def _select(key, editable, options):
    cur = str(editable.get(key, "")).strip()
    opts = list(options)
    if cur and cur not in opts:
        opts.insert(0, cur)      # never rewrite an unknown value just by saving
    inner = "".join(
        f'<option value="{_e(o, quote=True)}"{" selected" if o == cur else ""}>{_e(o)}</option>'
        for o in opts)
    return (f'<div class="fld"><div class="l">{key}</div><p class="h">{_HELP.get(key, "")}</p>'
            f'<select class="cfg-in" name="{key}" form="cfg">{inner}</select></div>')


def _multi(key, editable, options):
    cur = {x.strip() for x in str(editable.get(key, "")).split(",") if x.strip()}
    boxes = "".join(
        f'<input type="checkbox" name="{key}" id="{key}-{i}" value="{_e(o, quote=True)}" '
        f'form="cfg"{" checked" if o in cur else ""}>'
        f'<label for="{key}-{i}">{_e(o)}</label>' for i, o in enumerate(options))
    # hidden blank keeps the key in the POST when nothing is checked, so the
    # writer rejects an empty lineup instead of silently leaving it unchanged
    return (f'<div class="fld"><div class="l">{key}</div><p class="h">{_HELP.get(key, "")}</p>'
            f'<input type="hidden" name="{key}" value="" form="cfg">'
            f'<div class="multi">{boxes}</div></div>')


def _txt(key, editable, message=""):
    val = _e(str(editable.get(key, "")), quote=True)
    bad = key == "PANEL_MAX_COST_USD" and any(w in message.lower() for w in ("finite", "number", "> 0", "cost"))
    err = '<div class="e">must be a finite number &gt; 0 — file left unchanged</div>' if bad else ""
    return (f'<div class="fld{" bad" if bad else ""}"><div class="l">{key}</div>'
            f'<p class="h">{_HELP.get(key,"")}</p>'
            f'<input class="cfg-in" name="{key}" value="{val}" form="cfg">{err}</div>')


def _config_view(editable, message=""):
    toggles = (_switch("PANEL_ENABLED", editable, "Master switch · dormant no-op by default")
               + "".join(_seg(k, editable) for k in _TOGGLE_ENUMS))
    assets = (_switch("ASSET_ENABLED", editable, _HELP["ASSET_ENABLED"])
              + '<div class="duo">'
              + "".join(_select(k, editable, opts) for k, opts in _ASSET_SELECTS)
              + "".join(_txt(k, editable) for k in _ASSET_TXT_KEYS)
              + '</div>')
    roles = '<div class="duo">' + "".join(_select(k, editable, _ROLE_OPTIONS)
                                          for k in _ROLE_KEYS) + '</div>'
    slugs = _slug_options(editable)
    lineups = '<div class="duo">' + "".join(
        _multi(k, editable, slugs) if k in _MULTI_KEYS else _select(k, editable, slugs)
        for k in _LINEUP_KEYS) + '</div>'
    budgets = '<div class="duo">' + "".join(_txt(k, editable, message) for k in _BUDGET_KEYS) + '</div>'
    msg = ""
    if message:
        cls = "err" if message.lower().startswith("error") or "must" in message.lower() else "ok"
        msg = f'<div class="msg {cls}">{_e(message)}</div>'
    return (
        '<section class="view cf">'
        '<form id="cfg" method="POST" action="/api/config"></form>'
        '<input class="cfseg" type="radio" name="cfseg" id="cs-tog" checked>'
        '<input class="cfseg" type="radio" name="cfseg" id="cs-rol">'
        '<input class="cfseg" type="radio" name="cfseg" id="cs-lin">'
        '<input class="cfseg" type="radio" name="cfseg" id="cs-ast">'
        '<input class="cfseg" type="radio" name="cfseg" id="cs-bud">'
        '<nav class="subnav"><label for="cs-tog">Toggles</label><label for="cs-rol">Roles</label>'
        '<label for="cs-lin">Lineups</label><label for="cs-ast">Assets</label>'
        '<label for="cs-bud">Budgets &amp; cap</label></nav>'
        f'{msg}'
        '<div class="segwrap">'
        f'<div class="sv tog"><div class="card"><div class="ch"><h2>Panel toggles</h2><span class="m">behaviour</span></div>{toggles}'
        '<div class="warnrow"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex:0 0 auto"><path d="M12 3 2 20h20L12 3z"/><path d="M12 10v4"/><circle cx="12" cy="17.5" r=".6" fill="currentColor" stroke="none"/></svg>'
        '<span><b>Enabling</b> arms real, paid OpenRouter calls on the next gate.</span></div></div></div>'
        f'<div class="sv rol"><div class="card"><div class="ch"><h2>Roles</h2><span class="m">models</span></div>{roles}</div></div>'
        f'<div class="sv lin"><div class="card"><div class="ch"><h2>Lineups</h2><span class="m">OpenRouter slugs</span></div>{lineups}</div></div>'
        f'<div class="sv ast"><div class="card"><div class="ch"><h2>Asset pipeline</h2><span class="m">asset-forge · Rule 13</span></div>{assets}'
        '<div class="warnrow"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex:0 0 auto"><path d="M12 3 2 20h20L12 3z"/><path d="M12 10v4"/><circle cx="12" cy="17.5" r=".6" fill="currentColor" stroke="none"/></svg>'
        '<span>An <b>exhausted</b> loop escalates to panel review, then the human — never auto-accepts.</span></div></div></div>'
        f'<div class="sv bud"><div class="card"><div class="ch"><h2>Budgets &amp; cost cap</h2><span class="m">limits</span></div>{budgets}</div></div>'
        '</div>'
        '<div class="locked"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>'
        ' Locked (edit by hand only): PANEL_PROVIDER · PANEL_ROUTING · PANEL_VERDICT_PATH · VERIFY_CMD · LINT_CMD · UI_VERIFY_CMD · secrets</div>'
        '<div class="savebar"><button class="btn" type="submit" form="cfg">Save to agent.config</button>'
        '<span class="note">Writes only allowlisted keys · comments &amp; other keys preserved byte-for-byte · atomic (temp + replace)</span></div>'
        '</section>'
    )


def render_index(verdict, cost, editable, message=""):
    present = bool(verdict) and verdict.get("present", True)
    enabled = str(editable.get("PANEL_ENABLED", "0")).strip() in ("1", "true", "on", "yes")
    cap = _f(editable.get("PANEL_MAX_COST_USD"), 2.0) or 2.0
    run_cost = _f(verdict.get("cost_usd_total")) if present else 0.0
    pct = min(100, int(run_cost / cap * 100)) if cap > 0 else 0
    logo = ('<svg width="30" height="30" viewBox="0 0 30 30" aria-hidden="true">'
            '<circle cx="15" cy="15" r="11" fill="none" stroke="#26b598" stroke-width="1.4" opacity=".55"/>'
            '<ellipse cx="15" cy="15" rx="13.5" ry="6" fill="none" stroke="#4fe3c1" stroke-width="1.3" transform="rotate(-28 15 15)"/>'
            '<circle cx="15" cy="15" r="3.2" fill="#4fe3c1"/><circle cx="26" cy="9" r="1.8" fill="#67d0fd"/></svg>')
    refresh = ('<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">'
               '<path d="M21 12a9 9 0 1 1-2.64-6.36M21 3v6h-6"/></svg>')
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>panel satellite — mission control</title><style>{_STYLE}</style></head><body>'
        '<input class="tabr" type="radio" name="tab" id="tab-ov" checked>'
        '<input class="tabr" type="radio" name="tab" id="tab-vd">'
        '<input class="tabr" type="radio" name="tab" id="tab-ct">'
        '<input class="tabr" type="radio" name="tab" id="tab-cf">'
        '<div class="app"><div class="top"><div class="brand">'
        f'{logo}<div><div class="name">PANEL&nbsp;SATELLITE</div><div class="sub">mission control</div></div></div>'
        '<span class="grow"></span>'
        f'<span class="status{" on" if enabled else ""}"><span class="dot"></span> Panel {"active" if enabled else "dormant"}</span>'
        '<span class="status rw">observe · config</span>'
        f'<a class="iconbtn" title="Refresh" aria-label="Refresh" href="/">{refresh}</a></div>'
        '<nav class="tabs"><label for="tab-ov">Overview</label><label for="tab-vd">Verdict</label>'
        f'<label for="tab-ct">Cost <span class="c">{pct}%</span></label><label for="tab-cf">Config</label></nav>'
        '<main class="stage">'
        f'{_overview(verdict, cost, editable)}{_verdict_view(verdict)}{_cost_view(verdict, cost, editable)}{_config_view(editable, message)}'
        '</main>'
        '<div class="foot">observe / config only · CSS-only tabs (no JS) · offline (inline CSS + SVG)</div>'
        '</div></body></html>'
    )
