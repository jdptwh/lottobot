"""panel/cli.py — the panel satellite entrypoint.

`python -m panel.cli plan|review --task-id ID [prompt | --prompt-file F | -]`.

Gated by PANEL_ENABLED (default "0"): disabled -> a true no-op (the orchestrator is
never imported or called, no file is written, exit 0). Enabled -> run the Wave 3
orchestrator, write a schema-valid panel_verdict.json to PANEL_VERDICT_PATH, and exit
with the SAME code verdict_lint.py would return on that file (mapping imported from
verdict_lint, never reimplemented). Stdlib only. The OpenRouter key is read from the
environment by the adapter; this CLI never touches ANTHROPIC_API_KEY.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

from panel.config import load_config
from panel.secrets import load_env

_REPO = Path(__file__).resolve().parents[1]


def _load_verdict_lint():
    """Import .claude/hooks/verdict_lint.py by path (it is __main__-guarded, so the
    import is side-effect-free) to reuse its exit-code mapping — one source of truth."""
    path = _REPO / ".claude" / "hooks" / "verdict_lint.py"
    spec = importlib.util.spec_from_file_location("_panel_verdict_lint", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _read_prompt(args) -> str:
    if args.prompt_file:
        return Path(args.prompt_file).read_text(encoding="utf-8")
    if args.prompt == "-":
        return sys.stdin.read()          # explicit stdin
    if args.prompt:
        return args.prompt
    return ""                            # no source -> caller errors (exit 2)


def _build_parser():
    parser = argparse.ArgumentParser(prog="panel.cli",
                                     description="Panel satellite — plan/review gates.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "review"):
        p = sub.add_parser(name, help=f"run the {name} panel")
        p.add_argument("prompt", nargs="?", default=None,
                       help="inline task prompt, or '-' for stdin (or use --prompt-file)")
        p.add_argument("--task-id", required=True)
        p.add_argument("--prompt-file", default=None)
        p.add_argument("--attach", action="append", default=[], metavar="PATH",
                       help="attach a file for the experts (repeatable): images "
                            "(png/jpg/jpeg/webp/gif), .pdf, audio (wav/mp3), or any "
                            "UTF-8 text file (inlined)")
        p.add_argument("--config", default=str(_REPO / ".claude" / "agent.config"))
        p.add_argument("--seed", type=int, default=0)
    return parser


def main(argv=None, call_model=None) -> int:
    args = _build_parser().parse_args(argv)
    load_env()  # pick up OPENROUTER_API_KEY from a gitignored .env (existing env wins)
    cfg = load_config(args.config)

    if not cfg.enabled:
        print("[panel] PANEL_ENABLED=0 — panel disabled; no verdict produced.", file=sys.stderr)
        return 0

    prompt = _read_prompt(args)
    if not prompt.strip():
        print("[panel] error: no task prompt (positional arg, --prompt-file, or stdin).",
              file=sys.stderr)
        return 2

    attachments = None
    if args.attach:
        from panel.attachments import build_parts
        try:
            attachments = build_parts(args.attach)
        except ValueError as e:
            print(f"[panel] error: {e}", file=sys.stderr)
            return 2
        print(f"[panel] attached {len(attachments)} file(s) for the experts", file=sys.stderr)

    # Import the orchestrator lazily so the disabled path never imports it.
    from panel import orchestrator

    if args.cmd == "plan":
        verdict = orchestrator.run_plan(
            args.task_id, prompt, list(cfg.plan_lineup), cfg.plan_synth,
            cap_usd=cfg.max_cost_usd, seed=args.seed, call_model=call_model,
            attachments=attachments)
    else:
        verdict = orchestrator.run_review(
            args.task_id, prompt, list(cfg.review_lineup), cfg.review_arbiter,
            cap_usd=cfg.max_cost_usd, seed=args.seed, call_model=call_model,
            attachments=attachments)

    out = Path(cfg.verdict_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(verdict, indent=2), encoding="utf-8")

    vl = _load_verdict_lint()
    err = vl.validate_panel_dict(verdict)
    code = 3 if err else vl.panel_exit_code(verdict)
    for note in verdict.get("disagreement_summary", {}).get("blind_spots", []):
        if str(note).startswith("dropped expert:"):
            print(f"[panel] WARNING {note}", file=sys.stderr)
    print(f"[panel] {args.cmd} verdict={verdict['verdict']} "
          f"cost=${verdict['cost_usd_total']} cap_breached={verdict['cost_cap_breached']} "
          f"-> {out} (exit {code})", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
