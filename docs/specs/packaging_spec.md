# SPEC — Package the harness properly (v5.1 "ship it")

**Status: APPROVED 2026-07-09 (touchpoint 1), recommendations ratified:**
watch-video vendored PINNED; Whisper key optional; setup.py copies the CLAUDE.md
template, the installer skill personalizes it.
Date: 2026-07-09. Author: lead (planner role).

## Goal
Make the harness a properly installable, self-contained unit: everything the agents
need (routed system, panel, asset pipeline, video-watching capability) lands in a
target project from one install path, with no machine-specific residue. Today the
install story (INSTALL.md / scripts/setup.py) predates the panel-adjacent
capabilities and the repo carries hardcoded-path packaging debt.

## Current debt (verified 2026-07-09)
- `scripts/atlas-mcp.cmd` hardcodes `C:\Users\JoeyD\...\nvm\v20.15.1`.
- `.mcp.json(.example)` hardcodes `C:\dev\panel-satellite\...`.
- `scripts/setup.py` knows about OPENROUTER/ANTHROPIC keys only — not
  ATLASCLOUD_API_KEY, not .mcp.json creation, not skills.
- INSTALL.md / README.agent-system.md don't mention Rule 13, asset-forge, --attach,
  the prompt templates, or the dashboard Assets tab.
- No test proves an install is self-contained (the gate only runs in THIS repo).

## New capability folded in: watch-video skill
Vendor [Newuxtreme/watch-video-skill](https://github.com/Newuxtreme/watch-video-skill)
(MIT) into `.claude/skills/watch-video/`, preserving THIRD_PARTY_NOTICES. What it
gives the harness: transcript (captions, else Whisper) + ffmpeg frame extraction
(scaled, ≤100 frames) synced by timestamp — works on local files (mp4/mov/mkv/webm/avi)
and yt-dlp-supported URLs. Harness roles:
- agents can absorb/critique video like a person (learn, copy, give visual feedback);
- the designated "eyes" for the FUTURE video-generation QA loop (separate spec —
  this spec only lands the watching capability).
Dependencies (ffmpeg/ffprobe, yt-dlp, optional Groq/OpenAI Whisper key) are OPTIONAL
at install: setup.py detects and reports, never blocks the core harness.

## Waves
1. **Portability fixes.** atlas-mcp.cmd resolves Node ≥20 dynamically (probe
   `node -v`; fall back to `NODE20_DIR` env override; error with instructions if
   neither). `.mcp.json.example` templated (`{{HARNESS_ROOT}}`); setup.py writes the
   real `.mcp.json` with resolved absolute paths + prompts for ATLASCLOUD_API_KEY
   (skippable — assets stay dormant without it). Gate stays green with no Atlas key.
2. **Installer completeness.** Define the harness MANIFEST (one source of truth,
   machine-readable): `.claude/` (agents, hooks, skills, agent.config with every
   `*_ENABLED=0`, **and `.claude/settings.json` — the Stop/SubagentStop gate-hook
   wiring + permission deny-list; amended 2026-07-09 after the self-audit found it
   omitted, which left installed harnesses with gate.sh but nothing firing it**),
   `panel/`, `tests/`, `conftest.py`, `pyproject.toml`, `scripts/`,
   `.mcp.json.example`, docs set (ROUTING.md, INSTALL.md, RUNBOOK, prompt templates,
   CLAUDE.md template), .gitignore entries. Build-config files a target may own
   (`pyproject.toml`, `conftest.py`, `.gitattributes`, `.claude/settings.json`) are
   GUARDED — shipped as `<name>.harness-template` when present, never clobbered
   (amended 2026-07-09). setup.py gains `--install-into <dir>`:
   copies the manifest into a target repo, resolves paths, inits state dirs, runs
   the gate THERE. Self-containment test: install into a pytest tmp dir, run the
   gate in a subprocess, assert green (skipped where bash unavailable).
3. **watch-video vendoring + docs.** Vendor the skill + notices; add dependency
   detection to setup.py (`ffmpeg -version`, `yt-dlp --version` → report table);
   INSTALL.md / README.agent-system.md rewritten to cover the FULL harness (panel,
   assets, watch-video, dashboard, prompt templates); CLAUDE.md-template for target
   projects updated the same way.

## Non-goals
- Video GENERATION (still its own future spec; this only lands the eyes).
- Publishing to a package registry (the unit is a repo-to-repo install).
- Auto-updating installed harnesses (installs are point-in-time copies by design —
  divergence is managed by re-install on explicit direction, per the Vice Studio rule).

## Open questions for the approver
1. Vendor watch-video PINNED into this repo (reproducible, offline installs,
   MIT-clean) vs fetch-latest at install time? **Recommend: vendor pinned.**
2. Whisper transcription key (Groq/OpenAI): leave fully optional (captions-only
   without it)? **Recommend: yes, optional.**
3. Should `--install-into` also write the target project's CLAUDE.md from the
   template with detected stack/verify commands (the agent-system-installer skill's
   job today), or leave CLAUDE.md authoring to the installer skill? **Recommend:
   setup.py copies the template; the installer skill personalizes it.**
