"""Minimal stdlib loader for a gitignored `.env` file (no python-dotenv dependency).

Secrets (OPENROUTER_API_KEY, optionally ANTHROPIC_API_KEY) live in a `.env` file that is
gitignored — NEVER in agent.config (which is committed) and NEVER editable from the
observe/config dashboard. The CLI calls load_env() at startup so a key placed in .env is
picked up without a manual `export`. Existing environment variables always win (setdefault),
so an explicit `export` overrides the file.
"""
from __future__ import annotations

import os


def parse_env(text):
    """Parse KEY=VALUE lines (shell-style, optional quotes, # comments). Returns a dict."""
    out = {}
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        if s.startswith("export "):
            s = s[len("export "):].lstrip()
        key, _, val = s.partition("=")
        key, val = key.strip(), val.strip()
        if val and val[0] in "\"'":
            q = val[0]
            end = val.find(q, 1)
            val = val[1:end] if end != -1 else val[1:]
        elif "#" in val:
            val = val.split("#", 1)[0].strip()
        if key:
            out[key] = val
    return out


def load_env(path=".env", environ=None):
    """Load KEY=VALUE pairs from `path` into the environment WITHOUT overwriting existing
    values. Missing file is a silent no-op. Returns the list of key names loaded."""
    environ = os.environ if environ is None else environ
    try:
        with open(path, encoding="utf-8") as f:
            pairs = parse_env(f.read())
    except (FileNotFoundError, IsADirectoryError):
        return []
    loaded = []
    for k, v in pairs.items():
        if k not in environ:
            environ[k] = v
            loaded.append(k)
    return loaded
