# Install — the agentic harness (v5.1)

A portable **agentic harness**: the routed agent system (planner / implementer /
reviewer + verification gates), the multi-model **panel satellite** it calls at the
plan/review gates, the **asset pipeline** (Atlas Cloud image models + cross-family
QA loop, Rule 13), and the **watch-video** skill (frame-level video analysis).
**Stdlib-only at runtime** (no pip dependencies; `pytest` only for the test gate).
Every capability is **dormant by default** (`PANEL_ENABLED=0`, `ASSET_ENABLED=0`)
and does nothing until you switch it on and provide keys.

## Quickest start (you have Python 3.10+)
```
cd panel-satellite
python scripts/setup.py            # prompts for keys (all skippable), reports optional deps, runs the gate
python -m panel.dashboard          # open http://127.0.0.1:8787/  (observe / configure)
```
That's it — everything stays a no-op until you flip `PANEL_ENABLED` / `ASSET_ENABLED`.

## Installing INTO another project (the harness is the product)
```
python scripts/setup.py --install-into C:\path\to\your\project
```
Copies the harness manifest (`scripts/harness.manifest.json`) into the target:
agents, hooks, skills (asset-forge, watch-video), panel, tests, docs, dormant
`agent.config`; ships `CLAUDE.md` from the template ONLY if the target has none
(else `CLAUDE.md.harness-template` — your project memory is never clobbered);
appends gitignore rules; **forces every `*_ENABLED` key to 0**; then runs the
target's own gate to prove the install. Add `--force` to upgrade an existing
install, `--openrouter-key/--atlas-key` to configure keys in the target in one
shot. Personalize the target's CLAUDE.md afterwards (the agent-system-installer
skill does this well).

## Installing with Cowork ("drop it in a repo and ask Cowork to install it")
1. Unzip this into a folder and open that folder in Cowork.
2. Tell Cowork: **"Install the panel-satellite in this folder following INSTALL.md."**
   Cowork will: verify Python, help you set your API keys (writing a gitignored `.env`), run the
   test gate to confirm everything is green, and show you how to launch the dashboard.
3. (Recommended) `git init` in the folder first so the agent system's resume-not-replay safety
   has an undo. The `.claude/` agent system is included and active.

## API keys (where they go, and why)
Keys live in a **gitignored `.env`** at the repo root — never in `agent.config` (which is
committed) and never in the dashboard (which locks secrets out by design). Two ways to set them:

- **Setup script (recommended):**
  ```
  python scripts/setup.py --openrouter-key sk-or-...   # non-interactive
  python scripts/setup.py                              # interactive prompts
  python scripts/setup.py --print                      # list configured key names
  ```
- **Or create `.env` by hand:**
  ```
  OPENROUTER_API_KEY="sk-or-..."
  ```

The CLI auto-loads `.env` at startup (an existing `export` in your shell always wins). You can
also just `export OPENROUTER_API_KEY=...` instead of using `.env`.

### Which key does what
- **OPENROUTER_API_KEY** — *all the panel needs.* The panel calls OpenRouter for every expert,
  including the Anthropic models (Opus/Fable) routed through OpenRouter. The asset pipeline's
  QA judge also runs over OpenRouter.
- **ATLASCLOUD_API_KEY** — asset GENERATION (image models: Nano Banana 2/Pro, GPT Image 2,
  Flux 2, Seedream 5, …) via the Atlas Cloud MCP. Lives in the gitignored `.mcp.json`
  (written by `setup.py --atlas-key`; template: `.mcp.json.example`). Optional — without it
  the asset pipeline stays dormant.
- **Groq/OpenAI Whisper key** — optional, only for watch-video transcription of videos with
  no captions. Without it the skill uses native captions when present.

### Optional tool deps (watch-video skill only)
`ffmpeg` + `ffprobe` (frame extraction) and `yt-dlp` (downloads). `setup.py` detects and
reports them; missing tools degrade only that skill. Node 20+ is needed for the Atlas MCP —
the shim (`scripts/atlas-mcp.cmd`) resolves it automatically (`NODE20_DIR` overrides).
- **ANTHROPIC / Claude API key** — this is for **Claude Code (the lead)**, not the panel. ⚠️
  Setting `ANTHROPIC_API_KEY` in the lead's environment can silently switch Claude Code from your
  subscription to **metered API billing** (a documented footgun that cost one user $1,800 in two
  days). Keep the lead interactive/subscription unless you deliberately want API billing. The
  panel process never reads this key. `setup.py` will store it in `.env` if you provide it, with
  this warning — but does not export it into Claude Code for you.

## Verify the install
```
python -m pytest -q                # full gate: mocked, offline, zero cost (should be all green)
```

## Enable it for real (costs money — your call)
See **docs/RUNBOOK.md** for the full checklist. Short version: keep the lead interactive with no
`ANTHROPIC_API_KEY` exported, set `OPENROUTER_API_KEY`, prove the wire path with
`python -m pytest -q -m live` (~1¢), then set `PANEL_ENABLED=1` and `PANEL_TRIGGER=novelty`
(dashboard Config tab or edit `.claude/agent.config`).

## What's inside
- `panel/` — adapters, orchestrator, cost meter, safe-retry, CLI, config, dashboard.
- `.claude/` — the v4 routed agent system (roles, gate hooks, verdict validation, agent.config).
- `docs/` — `RUNBOOK.md`, `ui_mockup_protocol.md`, wave specs, the approved dashboard mockup.
- `tests/` — the pytest gate (unit + UI smoke).

Requires only Python 3.10+. Windows note: the gate uses `python -m pytest`; under WSL/Git Bash
where only `python3` exists, override `CLAUDE_VERIFY_CMD`/`CLAUDE_UI_VERIFY_CMD`.
