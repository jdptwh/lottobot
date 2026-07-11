---
name: asset-forge
description: Generate a visual asset (image) with the Atlas Cloud MCP, QA it against explicit acceptance criteria with a cross-family judge, and loop until it passes or escalates. Use whenever a task needs an image asset created — UI graphics, icons, illustrations, placeholder art.
---

# asset-forge — generate → QA → loop

Spec: docs/specs/asset_pipeline_spec.md (APPROVED 2026-07-09) · ROUTING.md Rule 13.
Hard rules:
- The QA judge is CROSS-FAMILY (enforced by `panel.asset_qa` — do not fight it).
- An exhausted loop ESCALATES to panel review, then the human. Never auto-accept
  a failing asset; never silently give up.

## 0. Preconditions (ALL config from `.claude/agent.config` — Rule 10, env wins)
- `ASSET_ENABLED` must be `1` — if `0`, REFUSE: report "asset pipeline is dormant
  (ASSET_ENABLED=0)" and stop. Do not generate anyway.
- Read the knobs and use them instead of the hardcoded defaults below:
  `ASSET_MODEL_DEFAULT`, `ASSET_MODEL_TEXTED`, `ASSET_QA_JUDGE` (pass as `--judge`
  unless `auto`), `ASSET_MAX_ATTEMPTS`, `ASSET_MAX_COST_USD`.
- The Atlas Cloud MCP (`atlascloud`) must be connected (registered in `.mcp.json`;
  if its tools are deferred, load them via ToolSearch first).
- `OPENROUTER_API_KEY` available (`.env` at repo root) — the QA judge runs over
  OpenRouter via `python -m panel.asset_qa`.

## 1. Establish the request contract (fill ALL of it before generating)
```
ASSET: <what it is, one line>
DESTINATION: <repo path where the file lands>
FORMAT/DIMENSIONS: <png/jpg, WxH or aspect>
STYLE: <constraints — palette (e.g. dashboard teal #4fe3c1), mood, references>
ACCEPTANCE CRITERIA:            <- checkable, explicit; the judge scores ONLY these
- <criterion 1, e.g. "transparent background">
- <criterion 2, e.g. "no text or lettering anywhere">
- <criterion 3, e.g. "reads clearly at 32x32">
```
Write the criteria to a scratch file (`.claude/state/asset_criteria_<name>.md`).

## 2. Pick the generator
- IMAGE default: `ASSET_MODEL_DEFAULT`; asset contains TEXT (labels, lettering,
  precise layout): `ASSET_MODEL_TEXTED`.
- VIDEO: `ASSET_VIDEO_MODEL_DEFAULT` (Seedance 2.0 — has NATIVE AUDIO; audio
  briefs stay on it unless `ASSET_VIDEO_MODEL_AUDIO` overrides). Budgets come
  from `ASSET_VIDEO_MAX_COST_USD` (not the image cap) — video is priced per
  second; check the model's rate before choosing duration.
- Discover the exact Atlas model id and its parameter schema with the MCP's
  model-discovery tool before generating — ids drift; never assume.

## 3. The loop (max 3 attempts, $1.00 total)
Per attempt:
1. Generate via the Atlas MCP's quick-generate tool with the current prompt
   (attempt 1 prompt = the contract distilled; include format/dimensions/style).
   Save the image to the DESTINATION path (or a scratch path until it passes).
2. Judge it:
   ```
   python -m panel.asset_qa --image <path> --criteria-file <criteria file> \
     --generator-model <atlas model id>
   # video assets (frame-sampled; frames from ASSET_VIDEO_QA_FRAMES):
   python -m panel.asset_qa --video <path> --criteria-file <criteria file> \
     --generator-model <atlas model id> --frames <n>
   ```
   VIDEO QA is VISUAL-TRACK ONLY: audio criteria fail closed and the QA JSON
   carries `audio_qa: "not-performed"` — if the brief has audio criteria, tell
   the human they must ear-check those (the sidecar records the limitation).
   Exit 0 = PASS. Exit 2 = REVISE — stdout JSON has `defects[]` and
   `reprompt_hint`. Exit 3 = error (fix the invocation, does not count as an attempt).
   Small assets (icons under ~64px): vision encoders degrade tiny images and the
   judge can rubber-stamp them (observed live 2026-07-09) — judge an upscaled
   copy (e.g. 256px nearest-neighbor) alongside, and trust the stricter verdict.
3. On REVISE: build the next prompt = previous prompt + "PREVIOUS ATTEMPT WAS
   REJECTED. Fix these defects: <defects>. <reprompt_hint>". Track spend
   (generation cost from the MCP result if reported, judge cost from the QA JSON).

Stop when: PASS, or 3 attempts used, or spend already at/over the cap. NOTE the
cost cap is a SOFT ceiling: it is checked BEFORE each attempt, so the final
attempt can push total spend past `ASSET_MAX_COST_USD` (bounded by one
generate+judge). Choose cheap generators/durations for early attempts.

## 4. Outcome
**PASS** → keep the passing image at DESTINATION. Write the provenance sidecar
`<asset>.forge.json`: `{status, escalate_to_panel:false, attempts:[{n, image,
prompt, qa, cost_usd}], best, cost_usd_total, criteria}` (same shape
`panel.asset_qa.ForgeLoop.result()` emits).

**EXHAUSTED** → ruling 2 applies, do BOTH:
1. Write the sidecar with `status:"EXHAUSTED", escalate_to_panel:true`, keeping
   the BEST-scoring candidate on disk.
2. Escalate to the panel, then stop for the human:
   ```
   python -m panel.cli review --task-id asset-<name> \
     --prompt-file <file: the contract + per-attempt defect history> \
     --attach <best candidate image>
   ```
   Report the panel verdict + the best candidate to the human. Do not retry
   further; do not wire the asset into anything.

## Never
- Judge with a same-family model (the helper blocks it — don't work around it).
- Inline base64 into prompts (use file paths / --attach).
- Commit an EXHAUSTED asset or wire it into UI without the human's approval.
