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
- 2026-07-13 marathon: PANEL armed + first live run ($1.24, FAIL against the
  project spec's own sec-3-v2 model — per-tier claim-lag unidentifiable;
  record: docs/specs/m6_data_strategy_panel.md). W1 Wayback recon GO. W2 v1.5
  honesty pass SHIPPED+ACCEPTED (upper-bound labeling, EV intervals,
  scenarios-not-bounds, launch-odds anchor, low_inventory exclusion; live on
  the public site). M6 v2 program specced (m6_v2_program_spec.md, M6a-M6d
  evidence-gated). M6a COMPLETE+ACCEPTED: research panel data/panel/panel.jsonl
  (13,652 records, 482 game lifecycles 2015-2026), noncash-prize arbitration
  (m6a_noncash_addendum.md — production parser invariant, opt-in tolerant
  mode), semantics note (tier-coverage ambiguity = stated Phase-1 assumption),
  worksheet docs/reports/m6a_panel_worksheet.md. First SCHEDULED run green
  (streak day 1 of 7).
- In progress: M6b detectability study (synthetic-recovery test surface first,
  then pooled distributed-lag over the panel; ends in HARD OWNER STOP on the
  report).
- Next up: on M6b GO + owner ruling — M6c sub-spec (planner) then offline fit.
  Backlog: Node-20 action-version bump; source-staleness signal; excluded-
  toggle wording when a depleted game first appears; Lottery data request
  (owner declined for now — would resolve the tier-coverage ambiguity).
- Blocked on: M6b report (in build), then the owner's hard-stop ruling.

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
- Pin fixture-specific counts/game_nos/bytes against data/latest.json in tests —
  the M5 bot rewrites it daily. Live-file tests assert invariants only; exact
  regression pins target tests/scraper/fixtures/latest_2026-07-11.json
  (m5a spec, 2026-07-13 incident).

## Landmines
- While the repo gate is RED, the SubagentStop hook bounces EVERY subagent's
  completion — including read-only agents (planner/drafter) that cannot fix a
  red gate; they loop until force-ended and their final message may be lost.
  During a red gate: dispatch only agents whose task makes the gate green, and
  recover trapped read-only output via SendMessage resume afterward.
- Windows Path.write_text without newline="\n" emits CRLF — breaks byte-identity
  vs LF-committed artifacts. All pipeline CLI writes pin newline="\n" (m5a).
- The lead's Stop-hook gate races concurrent background implementers: a red
  sample of another agent's in-flight tree is noise. Authoritative gates are
  each agent's own completion gate + the lead's pre-commit run (2026-07-13).
