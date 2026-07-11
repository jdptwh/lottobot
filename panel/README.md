# panel — the headless multi-model panel satellite

A small, stateless component the v4 routed agent system calls **as a tool** at its
plan/spec and QA gates. It fans a task out to a mixed-provider panel of experts via
OpenRouter, aggregates (PLAN: synthesis; REVIEW: union + arbiter), meters cost, and
writes a `panel_verdict.json` that flows through the existing `verdict_lint.py` and
`gate.sh`. It augments Claude Code — it does not replace the gates or the
two-touchpoint discipline.

## Disabled by default
`PANEL_ENABLED="0"` (the default in `.claude/agent.config`) makes the satellite a
**no-op**: the CLI writes nothing, never calls a model, and exits 0 — reproducing v4
behavior exactly. Set `PANEL_ENABLED="1"` to activate it.

## Usage
```
python -m panel.cli plan   --task-id T "inline task prompt"
python -m panel.cli plan   --task-id T --prompt-file spec.md
python -m panel.cli review --task-id T -            # read prompt from stdin
python -m panel.cli plan   --task-id T --prompt-file spec.md \
       --attach mockup.png --attach design.pdf --attach ROUTING.md   # repeatable

# --attach sends files to the EXPERTS (not synth/arbiter — no double-billing):
#   images png/jpg/jpeg/webp/gif · .pdf (OpenRouter file-parser) · audio wav/mp3
#   · any UTF-8 text file (inlined with a filename banner). Caps: 10MB/file,
#   2MB/text file, 20MB total — oversize/unsupported files fail BEFORE any spend.
```
On success (enabled) the CLI writes the verdict to `PANEL_VERDICT_PATH` and exits with
the **same code `verdict_lint.py` returns** on that file:

| verdict / state              | exit |
|------------------------------|------|
| PASS (and not cost-capped)   | 0    |
| FAIL                         | 1    |
| REVISE, or cost_cap_breached | 2    |
| malformed verdict            | 3    |

`gate.sh` independently lints `PANEL_VERDICT_PATH` when the file is present (GATE 4),
so a non-zero verdict blocks the stop even if the caller ignores the CLI's exit code.

## Configuration (`.claude/agent.config`, layered env > file > default)
| key | default | meaning |
|---|---|---|
| `PANEL_ENABLED` | `0` | `1` activates the panel; `0` is a no-op |
| `PANEL_TRIGGER` | `novelty` | `always\|novelty\|escalation` — surfaced for the lead; not enforced here |
| `PANEL_PROVIDER` | `openrouter` | provider gateway |
| `PANEL_ROUTING` | `exacto` | routing hint |
| `PANEL_MODE_PLAN` | `aggregate` | PLAN aggregation mode |
| `PANEL_MODE_REVIEW` | `union` | REVIEW aggregation mode |
| `PANEL_MAX_COST_USD` | `2.00` | per-invocation cost cap (checked after the expert phase) |
| `PANEL_VERDICT_PATH` | `.claude/state/panel_verdict.json` | where the verdict is written / gate.sh reads |
| `PANEL_PLAN_LINEUP` | `anthropic/claude-fable-5,openai/gpt-5.6-sol` | PLAN expert slugs |
| `PANEL_PLAN_SYNTH` | `anthropic/claude-opus-4.8` | PLAN synthesizer |
| `PANEL_REVIEW_LINEUP` | `anthropic/claude-opus-4.8,openai/gpt-5.6-sol,openai/gpt-5.6-terra` | REVIEW reviewer slugs |
| `PANEL_REVIEW_ARBITER` | `anthropic/claude-fable-5` | REVIEW arbiter |

Slugs are full OpenRouter dotted IDs (verified 2026-07-09). A configured slug absent
from the fallback price table only prints a warning — cost truth is the live
`usage.cost` from OpenRouter, so an unknown-but-valid new slug still runs.

## Secrets
The OpenRouter key is read **only** from the `OPENROUTER_API_KEY` environment variable
by the adapter. Never set `ANTHROPIC_API_KEY` in the panel's environment — with
`claude -p` present that key silently reroutes billing to the metered API
(V5_PLAN Key Finding 5). No secret is ever written to the verdict file or logs.
