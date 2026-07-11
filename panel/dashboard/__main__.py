"""`python -m panel.dashboard` — launch the observe/config-only dashboard.

Deliberately separate from panel/cli.py: it shares no argparse subparser, is never
invoked by gate.sh or the CLI, and initiates no panel runs.
"""
from __future__ import annotations

import argparse
import sys

from panel.dashboard.server import make_server


def main(argv=None):
    p = argparse.ArgumentParser(prog="panel.dashboard",
                                description="Local observe/config dashboard for the panel satellite.")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8787)
    p.add_argument("--config", default=".claude/agent.config")
    p.add_argument("--verdict-path", default=None)
    p.add_argument("--cost-log", default=".claude/state/panel_cost_log.jsonl")
    args = p.parse_args(argv)
    try:
        httpd = make_server(args.host, args.port, config_path=args.config,
                            verdict_path=args.verdict_path, cost_log_path=args.cost_log)
    except ValueError as e:
        print(f"[panel.dashboard] {e}", file=sys.stderr)
        return 2
    host, port = httpd.server_address[0], httpd.server_address[1]
    print(f"[panel.dashboard] serving on http://{host}:{port}/  (Ctrl-C to stop)", file=sys.stderr)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
