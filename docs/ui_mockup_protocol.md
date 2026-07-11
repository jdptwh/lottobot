# UI Mockup Protocol (ROUTING.md Rule 11)

**Mandate:** Any task that produces or changes a user interface MUST ship an approved,
static HTML **mockup** *before* implementation begins. The mockup is the visual/interaction
contract: the built UI is not presentable until a **polish audit** confirms it matches the
approved mockup. This adds a UI-specific human review gate on top of the two standard
touchpoints (approve the spec, accept the result).

## When it triggers
Any task with UI acceptance criteria — a new screen, a redesign, or a "polish/UX" pass on
an existing screen. If a task touches rendered markup, layout, or interaction, it triggers.
Pure backend/API/data tasks with no rendered surface do NOT trigger.

## Reference study & the anti-generic mandate (do this BEFORE drawing)
The mockup's job is not merely to exist — it is to raise the first-pass quality bar so the
build lands *intentional and distinctive*, not like a default AI-generated UI. Before drawing:
- **Study 2–3 high-end, DOMAIN-RELEVANT references.** Look at how real, well-designed products
  in the same category (dev tooling, observability/telemetry consoles, control panels, CI/gate
  dashboards) actually look. Extract concrete, reusable design moves: the layout system, the
  type scale and pairing, the accent/colour strategy, the data-visualisation idioms (gauges,
  sparklines, status rings), spacing rhythm, and how state/severity is signalled.
- **Design to that bar, then push past it.** The target is a UI that could plausibly be mistaken
  for a real, designed product in its category — with its own visual identity — not a template.
- **Explicitly avoid the generic "AI-coded" look.** Red flags to reject: a flat grid of
  same-size dark cards with a single indigo/blue accent; plain boxed stats with no real data
  viz; no logo/identity; default system fonts with no type hierarchy; centred everything;
  emoji as iconography. If the mockup reads as "another AI dashboard," it fails this rule.
- **Adopt the reference's LAYOUT & INTERACTION paradigm, not just its palette.** If the
  reference is a compact, tabbed, single-view control panel, the redesign is compact,
  tabbed, and single-view — with the same information density and visual control style
  (segmented pickers, toggles, chips, gauges), not a long scrolling list. **Reskin ≠
  redesign:** taking the previous layout and only changing colours/spacing is an explicit
  failure of this rule. Rework the composition itself.
- **Stay honest.** Distinctiveness never means inventing data or capabilities. Visualise only
  what the system actually produces; never add a metric, chart, or control the build won't have.
- **Cite your references.** The mockup file must carry a short "design notes" comment naming the
  references studied and the specific moves borrowed, so the polish audit can check fidelity.

## The UI loop (inserted before IMPLEMENT for UI tasks)
1. **Spec** — as normal (drafter → planner → human approves the spec).
2. **Mockup** — the implementer (or designer tier) produces a self-contained static HTML
   mockup under `docs/mockups/<screen>_mockup.html`. It uses realistic sample data, needs no
   backend, and obeys the project's asset rules (for this repo: **no external CDN/JS/fonts**;
   inline CSS only; must render offline). It covers every state the real screen has
   (populated, empty, error/warning, and any cost/limit indicators).
3. **Mockup review gate (NEW human touchpoint)** — present the mockup to the human. The human
   approves it, requests changes, or rejects. **No buildout starts until the mockup is
   approved.** The approved mockup file is committed and becomes the acceptance target.
4. **Implement** — build the real UI to *match the approved mockup* (layout, hierarchy,
   affordances, states, copy). Deviations from the mockup require the human's ok.
5. **Polish audit (mandatory gate, before REVIEW/presentation)** — a side-by-side check of the
   built UI against the approved mockup, scored on the rubric below. The audit must pass, and
   its result is recorded, before the UI is presented for the accept touchpoint.

## Mockup quality bar (what "approvable" means)
A mockup is approvable when a reviewer can look at it and know exactly what to build:
- **Clear visual hierarchy** — the primary information (for this harness: the latest
  verdict + running cost vs. cap) reads first; secondary controls are subordinate.
- **Legible states** — populated, empty ("no verdict yet"), and warning/danger
  (cost-cap breached; "arms paid calls") are all shown or clearly indicated.
- **Grouped, labeled controls** — related config is grouped (e.g. Roles / Lineups /
  Budgets & Cost cap / Panel toggles) with inline helper text, not a flat form.
- **Obvious affordances** — save/apply, destructive/paid actions visibly flagged;
  enum fields are pickers, not free text.
- **Consistent, calm styling** — one type scale, one spacing scale, one accent color;
  adequate contrast; nothing cramped.
- **Honest** — sample data is representative; nothing implies a capability the build
  won't have (e.g. no "Run panel" control on an observe-only dashboard).

## Polish audit rubric (reviewer scores each; all must be "meets")
1. **Layout parity** — sections, order, and grouping match the approved mockup.
2. **State coverage** — populated / empty / warning-danger states render as designed.
3. **Hierarchy & legibility** — primary info is prominent; contrast and spacing are comfortable.
4. **Affordances & safety** — paid/destructive actions are flagged; enums are pickers; save is obvious.
5. **Copy & labels** — headings, helper text, and warnings match the mockup's intent.
6. **Constraint compliance** — no external assets (offline-clean); accessibility basics
   (labels tied to inputs, focus visible); no console errors.
7. **No scope creep / no capability drift** — the built UI exposes exactly what the mockup did.
8. **Distinctiveness (not-generic)** — the UI has an intentional visual identity appropriate to
   the domain; it does NOT read as a default AI-generated dark-card grid. Fails if generic.
9. **Reference fidelity** — the design demonstrably reflects the high-end references studied
   (layout system, type, accent strategy, data-viz idioms), per the mockup's cited design notes.
10. **Composition & density (reskin ≠ redesign)** — the LAYOUT and INTERACTION paradigm itself
    reflects the reference (e.g. compact single-view, tabs/segments, visual controls), at
    comparable information density. A restyle of the prior layout — same structure, new colours —
    fails outright, regardless of how polished the styling is.

A "does not meet" on any item blocks presentation; the implementer revises and the audit re-runs.

## Artifacts & where they live
- Mockups: `docs/mockups/<screen>_mockup.html` (committed once approved; the acceptance target).
- The spec's UI acceptance criteria reference the approved mockup by path.
- The polish-audit result is recorded in the reviewer verdict / task notes before accept.
