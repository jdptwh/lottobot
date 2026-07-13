# CLAUDE.md — Maine Scratch-Off EV Ranker (lottobot)
# Installed by the panel-satellite agentic harness (v5.1).

## What this project is
A daily-updated, shareable web tool that ranks every active Maine Lottery instant
game by expected value per dollar, using the state's published unclaimed-prize and
percent-unsold data. Spec: `maine-scratch-ev-spec.md` (the authority — its §4
`latest.json` schema is a frozen contract, §6 gates are hard pass/fail, §7
milestones M1–M6 define build order). Architecture: GitHub Actions cron + static
GitHub Pages site — no servers, no keys, no accounts. "Shipped" = M5: seven
consecutive green daily Action runs publishing rankings at a public URL, with the
responsible-use framing of §8 prominent in the UI.

The **agentic harness** is installed: the routed agent system (planner /
spec-drafter / implementer / reviewer / grunt + verification gates + verdict
discipline), the multi-model panel satellite it can call at the plan/review gates
(Rule 12), and the asset pipeline for generated visual assets (Rule 13). Every
capability is DORMANT by default (`PANEL_ENABLED=0`, `ASSET_ENABLED=0`) — until
enabled, this repo behaves as a plain routed-agent project.

## Current state (correct as needed)
- Last completed: M4 built awaiting owner acceptance — M4a scoring pipeline
  (e4a8b7a: value_score/grade/rated/reason, daily-relative curve, binding copy
  bank, reviewer PASS cycle 1) + M4b best-pick site (6321ed4: hero + scored
  shortlist per owner-approved mockup 99a4ee5, flag-keyed claim-lag exclusion,
  polish audit 10/10, reviewer FAIL→fix→PASS cycle 2). Owner REJECTED the
  original table-concept M4 (superseded; recorded in m4b_site_spec.md).
  Full routed loop enforced since 2026-07-12: drafter→planner→owner-approves→
  implementer→reviewer→owner-accepts; lead orchestrates only, never absorbs
  roles (owner-corrected, see memory). M3 at 48d333e, M2 446399d, M1 eaefaa4.
- M4 ACCEPTED by owner 2026-07-12 (phone check green). Repo pushed public to
  github.com/jdptwh/lottobot (owner-approved; secrets sweep clean; owner ran
  the push himself — agent git-push stays denied by settings.json). Pages LIVE:
  https://jdptwh.github.io/lottobot/site/ (master / root). Worksheet
  hand-checks (m4a A–G, m3 3-game) remain available to the owner any time.
- M5 AUTOMATION LIVE: spec a62ea14 → build ee0dc3a (reviewer PASS cycle 1,
  zero findings) → CP3 green 2026-07-13: owner-triggered workflow_dispatch
  produced the first bot commit ("daily: snapshot 2026-07-13"), live site
  self-updated with freshly scraped data (source July 12), all gates enforced
  at runtime. STREAK OBSERVATION: 7 consecutive green SCHEDULED runs = M6-
  eligible "shipped" (manual dispatches neither count nor reset; red scheduled
  run resets). First scheduled run: 2026-07-13 10:30 UTC.
- In progress: streak observation (check the Actions tab / daily-run-failure
  issues).
- Next up: M6 — claim-lag model v2 (needs ~30 accumulated history snapshots,
  so earliest ~mid-August 2026). Backlog: bump actions/checkout+setup-python
  versions (Node-20 deprecation warning, cosmetic; planner-gated YAML change);
  source-staleness signal (m5 Resolution 6).
- Blocked on: calendar (streak) — no agent work pending.

## Conventions
- Stack / language: Python 3.11 target (3.12 local OK); scraper deps `requests` +
  `beautifulsoup4` (spec-authorized, scraper only — harness stays stdlib-only);
  site is vanilla single-file HTML/JS, no build step.
- Verification surface: `python -m pytest -q` (harness suite + project tests).
  Spec §6 gates are implemented as pytest tests + pipeline checks: parser gate
  (≥40 games, required fields, >$50M floor), math gate (EV ∈ (0, 1.5) on frozen
  2026-07 fixture), schema gate (latest.json vs JSON Schema), diff gate (>30% of
  games moving EV ratio >0.2 in a day holds the commit).
- Polite scraping (§8): 1 request/day to the unclaimed page, identifying UA
  string, respect robots.txt. Tests NEVER hit the network (frozen fixtures only).
- Verification commands and loop budgets: defined ONCE in `.claude/agent.config`
  (gate.sh sources it; env vars override per session — ROUTING.md Rule 10).

## Routing
Follow ROUTING.md. Summary: PLANNER owns specs + arbitrates escalations;
SPEC-DRAFTER drafts cheaply; IMPLEMENTER does judgment work; REVIEWER reviews and
escalates hard calls; BULK takes only machine-verifiable work. Route by
verifiability. Two human touchpoints: approve the spec, accept the result.
The panel is invoked at the plan/review gates per Rule 12 (PANEL_ENABLED /
PANEL_TRIGGER; advises, never the verdict of record) — see
docs/panel_integration.md. Visual assets go through asset-forge per Rule 13
(ASSET_ENABLED; cross-family QA; exhausted loops escalate to panel then human).
Loop budgets (`.claude/agent.config`) bound every autonomous run; failed loops
resume from git state, never replay (Rule 9).

## Keys (never in this file, never committed)
- `OPENROUTER_API_KEY` in gitignored `.env` — all the panel needs.
- `ATLASCLOUD_API_KEY` in gitignored `.mcp.json` — asset pipeline (optional).
- NEVER export `ANTHROPIC_API_KEY` in the lead's environment (metering footgun).

## Definition of done
- [ ] Verification commands pass (loop 3 gate green)
- [ ] Acceptance criteria from the spec checked off
- [ ] No files touched outside the spec
- [ ] UI work (Rule 11): mockup approved BEFORE build; polish audit vs. the mockup
- [ ] CLAUDE.md "Current state" updated

## Do not
- Add runtime dependencies without spec authorization.
- Route Claude Code subagents through a provider gateway.
- Export ANTHROPIC_API_KEY in the lead's environment.
- Refactor beyond the task's declared scope; guess on ambiguous specs — stop and ask.
