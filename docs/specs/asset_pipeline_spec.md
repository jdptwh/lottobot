# SPEC — Asset pipeline: Atlas Cloud MCP + generate→QA→loop skill

**Status: APPROVED 2026-07-09 (touchpoint 1) with rulings:**
1. QA judge is CROSS-FAMILY by design — the judge model must come from a different
   provider family than the generator (bias avoidance). "auto" picks accordingly.
2. An exhausted loop ESCALATES TO PANEL REVIEW (asset + defect history attached),
   then manual approval. Never auto-accept, never silent-stop.
3. Wave 2 live smoke budget: $0.25 per run.
Scope note: this builds in C:\dev\panel-satellite ONLY; the Vice Studio install is
updated only on explicit direction.
Date: 2026-07-09. Author: lead (planner role).

## Goal
Let the agent harness CREATE visual assets (UI graphics, icons, illustrations,
placeholder art) when a project needs them, using image models via the Atlas Cloud
MCP (Nano Banana 2/Pro, GPT Image 2, Flux 2, Seedream 5, ...), with a QA pass that
scores each asset against the request and a bounded regenerate loop — so what lands
in the repo is what was asked for, not the first thing the model emitted.

## What already exists (verified 2026-07-09)
- Atlas Cloud MCP registered at `C:\Vice Studio\.mcp.json` (`atlascloud-mcp` via
  `atlas-mcp.cmd`, Node 20 shim). Exposes model discovery, per-model parameter
  schemas, media upload, one-step quick-generate. Key now gitignored.
- `panel/attachments.py` — images→content-parts, reusable for the QA judge.
- `panel/adapters.py` `call_model` — OpenRouter call with cost truth; reusable
  for a cheap multimodal judge WITHOUT new dependencies.
- Rule 11 (mockup-before-build) and the routed agent system (planner/implementer/
  reviewer) in both repos.

## Design

### A. Component placement
The pipeline is HARNESS-side (skill + small stdlib helper), NOT panel-satellite
core: the satellite stays read-only/stateless. The helper lives in the satellite
repo (it reuses adapters/attachments and gets gate coverage there); the skill
instructs agents how to drive it plus the Atlas MCP tools.

### B. The loop (skill: `asset-forge`)
1. **Request contract** (the skill's fill-in): subject, purpose, style constraints,
   dimensions/format, destination path, and ACCEPTANCE CRITERIA (explicit,
   checkable: "no text artifacts", "transparent background", "matches dashboard
   teal #4fe3c1", ...).
2. **Generate** via Atlas MCP quick-generate. Model routing default:
   `google/nano-banana-2-pro` for photoreal/UI compositions; `openai/gpt-image-2`
   when the asset contains TEXT (labels, lettering) or needs precise layout;
   overridable per request.
3. **QA judge** (`panel/asset_qa.py`, stdlib): sends the generated image (via the
   existing attachment parts) + the acceptance criteria to a cheap multimodal
   judge (default `openai/gpt-5.6-luna` — $1/$6) with a strict schema:
   `{verdict: PASS|REVISE, score: 0-1, defects: [{criterion, problem}], reprompt_hint}`.
   Local validation, tolerant parse — same belt-and-suspenders as the panel.
4. **Loop**: on REVISE, fold `defects` + `reprompt_hint` into a revised generation
   prompt; regenerate. Bounded by `ASSET_MAX_ATTEMPTS` (default 3) and
   `ASSET_MAX_COST_USD` (default 1.00) — on exhaustion, keep the best-scoring
   candidate, write the defect list, STOP (human decides; never loop forever).
5. **Provenance sidecar**: `<asset>.forge.json` — prompt lineage, model, attempts,
   QA verdicts, per-attempt cost. Auditable like a panel verdict.

### C. Config (new agent.config keys, editable in the dashboard later — NOT wave 1)
`ASSET_ENABLED` (default 0), `ASSET_MODEL_DEFAULT`, `ASSET_MODEL_TEXTED`,
`ASSET_QA_JUDGE`, `ASSET_MAX_ATTEMPTS`, `ASSET_MAX_COST_USD`.

### D. Routing integration (Rule 13, after skill works)
When an approved spec calls for visual assets, the IMPLEMENTER runs asset-forge
per asset; generated assets attach to the panel review (existing `--attach`) when
the change is UI-bearing. Rule 11 is unchanged — mockup approval stays human.

## Waves (each gated, specs approved one at a time)
1. **asset_qa.py + tests** (mocked judge; schema/loop/budget logic — no MCP, no net).
2. **asset-forge skill** (.claude/skills/) driving Atlas MCP + the QA helper; live
   smoke: one cheap generate→QA cycle, budget-capped.
3. **Config keys + Rule 13 + docs**; dashboard editor rows for ASSET_* (Rule 11
   mockup update first).

## Non-goals
- No video generation (Atlas supports it; separate spec if wanted).
- No auto-commit of assets — the implementer places them; the human accepts the result.
- The panel satellite core gains NO write paths.

## Open questions for the approver
1. Judge model: cheap luna default, or same-family-as-generator to avoid style bias?
2. Should exhausted loops escalate to a full panel review (3 pro reviewers on an
   image is ~$0.30-0.60) or always stop at the human?
3. Wave 2 live smoke budget: propose $0.25 cap per run.
