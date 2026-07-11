# Panel prompt templates — fill in and run

Copy the template into a gitignored prompt file, fill the brackets, run the command.
Text goes in the prompt file; **binary evidence (screenshots, mockups, PDFs) goes via
`--attach`** — don't paste base64 into the prompt.

---

## REVIEW gate — "here's what changed, tear it apart"

```bash
# fill this in, then:
PID="<task-id>-review"
python -m panel.cli review --task-id "$PID" \
  --prompt-file .claude/state/panel_prompt_${PID}.md \
  --attach <before.png> --attach <after.png>          # optional, repeatable
```

Prompt file (`.claude/state/panel_prompt_<PID>.md`):

```
CHANGE UNDER REVIEW: <one line — what this change does>

WHY: <the problem it solves / the spec item it implements>

SCOPE — files touched:
<paste `git diff --stat` output>

WHAT CHANGED (author's summary, honest — include shortcuts taken):
- <change 1 and the reasoning>
- <change 2 and the reasoning>

HOW IT WAS VERIFIED:
<tests run + results, manual checks done, anything NOT verified>

KNOWN RISKS / AREAS TO FOCUS ON:
- <where you're least confident>
- <what a hostile reviewer should poke at>

OUT OF SCOPE (do not flag): <things deliberately not addressed here>

FULL DIFF:
<paste `git diff` output — or generate the file with: git diff > prompt file, then
prepend the sections above>

ATTACHED (if any): <what each attachment shows, e.g. "before.png / after.png —
dashboard config tab before and after this change">
```

Fast path when you don't need the ceremony — pipe the diff, put context inline:

```bash
git diff | python -m panel.cli review --task-id quickcheck - \
  --attach after-screenshot.png
```

---

## PLAN gate — "here's the task, propose/critique the plan"

```bash
PID="<task-id>"
python -m panel.cli plan --task-id "$PID" \
  --prompt-file .claude/state/panel_prompt_${PID}.md \
  --attach <approved-mockup.png> --attach <spec.pdf>
```

Prompt file:

```
TASK: <one line — what is being built>

CONTEXT — the system this lands in:
<2-5 lines: stack, the component this touches, hard constraints (stdlib-only,
no new deps, API budget, etc.)>

DRAFT SPEC / INTENT:
<paste the draft spec, or describe the intended approach>

WHAT ALREADY EXISTS: <relevant current behavior, prior art in the repo>

OPEN QUESTIONS: <decisions you want the panel to weigh in on>

ACCEPTANCE: <how "done" will be verified>

ATTACHED (if any): <what each attachment is>
```

---

Reading the result: `.claude/state/panel_verdict.json` — `synthesis.artifact` (merged
plan) or `synthesis.findings` (review findings), `disagreement_summary` for
contradictions/blind spots, `diagnostics` for per-expert raw previews if something
was dropped. Exit code: 0 PASS · 1 FAIL · 2 REVISE/cost-cap.
