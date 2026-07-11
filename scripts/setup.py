#!/usr/bin/env python3
"""panel-satellite setup — configure API keys + verify the install. Stdlib only.

Usage:
  python scripts/setup.py                         # interactive: prompts for keys, runs the gate
  python scripts/setup.py --openrouter-key sk-... # non-interactive
  python scripts/setup.py --no-verify             # skip the pytest gate
  python scripts/setup.py --print                 # show current .env keys (names only) and exit

Writes keys to a GITIGNORED `.env` at the repo root (never to agent.config, never committed).
The panel reads OPENROUTER_API_KEY from there at runtime. The Claude/Anthropic key is for
Claude Code (the lead) — see the note below about the subscription/metering footgun.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".env"
MANIFEST = ROOT / "scripts" / "harness.manifest.json"


def _detect_node20_dir():
    """The Atlas shim needs Node 20+. If the ambient `node` already satisfies that,
    return None (no override needed). Otherwise look for the newest nvm-managed
    Node 20+ on this machine and return its directory for the shim's NODE20_DIR.
    Returns None when nothing is found — the shim then errors with instructions
    at connect time rather than at setup time (assets are optional)."""
    try:
        out = subprocess.run(["node", "-v"], capture_output=True, text=True,
                             timeout=15).stdout.strip()
        if out.startswith("v") and int(out[1:].split(".", 1)[0]) >= 20:
            return None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    candidates = []
    nvm = Path(os.environ.get("APPDATA", "")) / "nvm"
    for d in nvm.glob("v*"):
        try:
            ver = tuple(int(x) for x in d.name[1:].split("."))
        except ValueError:
            continue
        if ver and ver[0] >= 20 and (d / "node.exe").exists():
            candidates.append((ver, d))
    return str(max(candidates)[1]) if candidates else None


def render_mcp(root, atlas_key, node20_dir=None):
    """Render .mcp.json content from .mcp.json.example, resolving {{HARNESS_ROOT}}
    (as an absolute path for THIS install) and {{ATLASCLOUD_API_KEY}}, plus a
    NODE20_DIR override when the ambient node is too old. Parses the template as
    JSON and substitutes inside the object — no string-escaping games with
    Windows backslashes."""
    root = Path(root)
    cfg = json.loads((root / ".mcp.json.example").read_text(encoding="utf-8"))
    for server in cfg.get("mcpServers", {}).values():
        server["command"] = str(Path(
            server["command"].replace("{{HARNESS_ROOT}}", str(root))))
        env = server.get("env", {})
        for k, v in env.items():
            env[k] = v.replace("{{ATLASCLOUD_API_KEY}}", atlas_key)
        if node20_dir:
            env["NODE20_DIR"] = str(node20_dir)
    return json.dumps(cfg, indent=2) + "\n"


def write_mcp(root, atlas_key, node20_dir=None):
    """Write the gitignored .mcp.json for this install. Returns its Path."""
    p = Path(root) / ".mcp.json"
    p.write_text(render_mcp(root, atlas_key, node20_dir), encoding="utf-8")
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass
    return p


def _read_env():
    d = {}
    if ENV.exists():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s and not s.startswith("#") and "=" in s:
                k, _, v = s.partition("=")
                d[k.strip()] = v.strip().strip('"').strip("'")
    return d


def _write_env(d, path=None):
    path = ENV if path is None else Path(path)
    lines = [
        "# panel-satellite secrets — GITIGNORED, never commit this file.",
        "# The panel calls OpenRouter for every expert (incl. the Anthropic models via OpenRouter),",
        "# so OPENROUTER_API_KEY is all the panel needs.",
        "",
    ]
    if d.get("OPENROUTER_API_KEY"):
        lines.append(f'OPENROUTER_API_KEY="{d["OPENROUTER_API_KEY"]}"')
    if d.get("ANTHROPIC_API_KEY"):
        lines += [
            "",
            "# ANTHROPIC_API_KEY is for Claude Code (the lead), NOT the panel. Setting it in the",
            "# lead's environment can silently switch Claude Code from subscription to metered API",
            "# billing (V5_PLAN Key Finding 5). Keep the lead interactive/subscription unless you",
            "# deliberately want API billing. The panel process never uses this key.",
            f'ANTHROPIC_API_KEY="{d["ANTHROPIC_API_KEY"]}"',
        ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def install_into(target, *, force=False, atlas_key=None, openrouter_key=None,
                 anthropic_key=None, verify=True):
    """Install the harness (per scripts/harness.manifest.json) into `target`.

    Copies the manifest's dirs/files, ships the CLAUDE.md template (as CLAUDE.md
    when the target has none, else CLAUDE.md.harness-template — never clobbers a
    project's memory), creates state dirs, forces every *_ENABLED key dormant,
    appends missing gitignore lines, writes any provided keys INTO THE TARGET,
    then proves the install by running its own gate there. Returns an exit code."""
    target = Path(target).resolve()
    if target == ROOT:
        print("[install] error: target is this harness repo itself.", file=sys.stderr)
        return 2
    if not target.is_dir():
        print(f"[install] error: target directory does not exist: {target}", file=sys.stderr)
        return 2
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    marker = target / ".claude" / "agent.config"
    if marker.exists() and not force:
        print(f"[install] error: {target} already has a harness ({marker.relative_to(target)} "
              "exists). Re-run with --force to upgrade in place.", file=sys.stderr)
        return 2

    ignore = shutil.ignore_patterns(*man["copy_ignore"])
    for d in man["copy_dirs"]:
        shutil.copytree(ROOT / d, target / d, dirs_exist_ok=True, ignore=ignore)

    # Files a target project may legitimately own (build config, its own hook/perm
    # settings) are NEVER clobbered: if present, ship beside as <name>.harness-template
    # and flag for reconciliation. Everything else copies normally. (Audit fix:
    # previously all copy_files overwrote unconditionally — only CLAUDE.md was guarded.)
    guarded = set(man.get("guard_if_exists", []))
    reconciled = []
    for f in man["copy_files"]:
        (target / f).parent.mkdir(parents=True, exist_ok=True)
        if f in guarded and (target / f).exists():
            tmpl = target / (f + ".harness-template")
            shutil.copy2(ROOT / f, tmpl)
            reconciled.append(f)
        else:
            shutil.copy2(ROOT / f, target / f)

    dst = target / "CLAUDE.md"
    if dst.exists():
        dst = target / "CLAUDE.md.harness-template"
        reconciled.append("CLAUDE.md")
    shutil.copy2(ROOT / man["claude_md_template"], dst)

    for s in man["state_dirs"]:
        p = target / s
        p.mkdir(parents=True, exist_ok=True)
        (p / ".gitkeep").touch()

    # a fresh install NEVER arrives armed — capabilities are enabled by the human
    cfg = target / ".claude" / "agent.config"
    txt = cfg.read_text(encoding="utf-8")
    for key in man["force_dormant_keys"]:
        txt = re.sub(rf'^(\s*{re.escape(key)}\s*=\s*)"[^"]*"', r'\g<1>"0"', txt, flags=re.M)
    cfg.write_text(txt, encoding="utf-8")

    gi = target / ".gitignore"
    existing = gi.read_text(encoding="utf-8").splitlines() if gi.exists() else []
    missing = [ln for ln in man["gitignore_lines"] if ln not in existing]
    if missing:
        block = existing + ([""] if existing else []) + ["# agentic harness (installed)"] + missing
        gi.write_text("\n".join(block) + "\n", encoding="utf-8")

    keys = {}
    if openrouter_key:
        keys["OPENROUTER_API_KEY"] = openrouter_key
    if anthropic_key:
        keys["ANTHROPIC_API_KEY"] = anthropic_key
    if keys:
        _write_env(keys, path=target / ".env")
    if atlas_key:
        write_mcp(target, atlas_key, _detect_node20_dir())

    print(f"[install] harness v{man['version']} installed into {target}")
    if reconciled:
        print("[install] the target already had these files — the harness copies were "
              "shipped as <name>.harness-template and NOT applied; reconcile by hand:")
        for f in reconciled:
            print(f"    - {f}  ->  {f}.harness-template")
        if ".claude/settings.json" in reconciled:
            print("    NOTE: merge the harness's Stop/SubagentStop gate hooks and the "
                  "permission deny-list into your settings.json, or the gates won't fire.")
    if verify:
        print("[install] running the target's gate (python -m pytest -q) ...")
        r = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=str(target))
        if r.returncode != 0:
            print("[install] target gate FAILED — the install is not self-contained.",
                  file=sys.stderr)
            return r.returncode
        print("[install] target gate green — install verified.")
    return 0


def report_optional_deps():
    """Detect the OPTIONAL tool deps (watch-video skill: ffmpeg/ffprobe/yt-dlp).
    Report-only — the core harness never depends on them."""
    tools = {"ffmpeg": ["-version"], "ffprobe": ["-version"], "yt-dlp": ["--version"]}
    print("[setup] optional deps (watch-video skill; missing = that skill degrades, nothing else):")
    for tool, args in tools.items():
        try:
            r = subprocess.run([tool] + args, capture_output=True, text=True, timeout=20)
            ok = r.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            ok = False
        print(f"  {'OK  ' if ok else 'MISS'} {tool}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="setup.py", description="panel-satellite key setup + verify")
    p.add_argument("--openrouter-key", default=None)
    p.add_argument("--anthropic-key", default=None)
    p.add_argument("--atlas-key", default=None,
                   help="Atlas Cloud API key — writes the gitignored .mcp.json "
                        "(asset pipeline / image models); skippable, assets stay dormant")
    p.add_argument("--install-into", default=None, metavar="DIR",
                   help="install the harness (per scripts/harness.manifest.json) into a "
                        "target project directory, force everything dormant, and run its gate")
    p.add_argument("--force", action="store_true",
                   help="with --install-into: upgrade a target that already has a harness")
    p.add_argument("--no-verify", action="store_true")
    p.add_argument("--no-prompt", action="store_true")
    p.add_argument("--print", dest="show", action="store_true")
    args = p.parse_args(argv)

    if args.install_into:
        return install_into(args.install_into, force=args.force,
                            atlas_key=args.atlas_key, openrouter_key=args.openrouter_key,
                            anthropic_key=args.anthropic_key, verify=not args.no_verify)

    cur = _read_env()
    if args.show:
        print("Configured keys in .env:", ", ".join(sorted(cur)) or "(none)")
        print("Atlas MCP (.mcp.json):", "configured" if (ROOT / ".mcp.json").exists() else "not configured")
        return 0

    orl = args.openrouter_key
    ant = args.anthropic_key
    if not args.no_prompt and orl is None and not cur.get("OPENROUTER_API_KEY"):
        try:
            orl = input("OpenRouter API key (required for the panel) [blank to skip]: ").strip()
        except EOFError:
            orl = ""
    if not args.no_prompt and ant is None and not cur.get("ANTHROPIC_API_KEY"):
        try:
            ant = input("Anthropic/Claude API key (optional; for Claude Code, see warning) [blank to skip]: ").strip()
        except EOFError:
            ant = ""
    atlas = args.atlas_key
    if not args.no_prompt and atlas is None and not (ROOT / ".mcp.json").exists():
        try:
            atlas = input("Atlas Cloud API key (optional; asset pipeline / image models) [blank to skip]: ").strip()
        except EOFError:
            atlas = ""

    if orl:
        cur["OPENROUTER_API_KEY"] = orl
    if ant:
        cur["ANTHROPIC_API_KEY"] = ant
    if cur:
        _write_env(cur)
        print(f"[setup] wrote {ENV.relative_to(ROOT)} (gitignored): {', '.join(sorted(cur))}")
    else:
        print("[setup] no keys provided; .env unchanged. The panel stays dormant until OPENROUTER_API_KEY is set.")

    if atlas:
        node20 = _detect_node20_dir()
        mp = write_mcp(ROOT, atlas, node20)
        print(f"[setup] wrote {mp.relative_to(ROOT)} (gitignored): Atlas Cloud MCP registered "
              f"(connects on next session start)"
              + (f" — NODE20_DIR={node20} (ambient node < 20)" if node20 else ""))
    elif not (ROOT / ".mcp.json").exists():
        print("[setup] Atlas Cloud MCP not configured — the asset pipeline (asset-forge) "
              "stays dormant. Re-run with --atlas-key to enable later.")

    if not cur.get("OPENROUTER_API_KEY"):
        print("[setup] NOTE: OPENROUTER_API_KEY is not set — the panel cannot make live calls yet.")

    report_optional_deps()

    if not args.no_verify:
        print("[setup] running the gate (python -m pytest -q) ...")
        r = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=str(ROOT))
        if r.returncode != 0:
            print("[setup] gate FAILED — see output above.")
            return r.returncode
        print("[setup] gate green.")

    print("\nNext:")
    print("  • Dashboard (observe/config):  python -m panel.dashboard   -> http://127.0.0.1:8787/")
    print("  • Enable the panel when ready:  set PANEL_ENABLED=1 in .claude/agent.config (or the dashboard Config tab)")
    print("  • Prove the wire path (~1c):    python -m pytest -q -m live")
    print("  • See docs/RUNBOOK.md for the full safe-enable checklist.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
