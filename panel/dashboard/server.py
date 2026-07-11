"""Localhost-only, stdlib http.server dashboard. Observe/config ONLY — there is NO
route, form, or code path that initiates a panel run or imports the orchestrator/CLI.

Routes (the ONLY routes): GET / , GET /api/verdict , GET /api/cost , GET /api/config ,
POST /api/config. Everything else -> 404; wrong method on a known path -> 405.
"""
from __future__ import annotations

import json
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from panel.config import load_config
from panel.dashboard import costlog
from panel.dashboard.config_writer import read_editable, write_editable
from panel.dashboard.render import render_index

_LOOPBACK = {"127.0.0.1", "localhost", "::1"}

# Lineup fields render as checkbox groups: the browser submits one value per
# checked box, and the config value is the comma-joined set. Everything else
# keeps last-value-wins (the PANEL_ENABLED hidden-0 + checkbox-1 pattern).
_JOINED_KEYS = {"PANEL_PLAN_LINEUP", "PANEL_REVIEW_LINEUP"}


def _form_updates(raw):
    qs = urllib.parse.parse_qs(raw, keep_blank_values=True)
    return {k: ",".join(x for x in v if x.strip()) if k in _JOINED_KEYS else v[-1]
            for k, v in qs.items()}


def _resolve_verdict_path(server):
    if server.verdict_path:
        return server.verdict_path
    return load_config(server.config_path, warn=False).verdict_path


def _current_verdict(server):
    """Read the verdict file read-only; record it in the cost log (idempotent)."""
    path = _resolve_verdict_path(server)
    try:
        with open(path, encoding="utf-8") as f:
            v = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"present": False}
    v["present"] = True
    costlog.observe(server.cost_log_path, v)
    return v


class _Handler(BaseHTTPRequestHandler):
    server_version = "panel-dashboard/1.0"

    def log_message(self, *a):  # silence default stderr logging
        pass

    def _send_json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html, status=200):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _page(self, message="", status=200):
        s = self.server
        self._send_html(render_index(_current_verdict(s), costlog.tally(s.cost_log_path),
                                     read_editable(s.config_path), message), status)

    def do_GET(self):
        s = self.server
        path = urllib.parse.urlparse(self.path).path
        if path == "/":
            self._page()
        elif path == "/api/verdict":
            self._send_json(_current_verdict(s))
        elif path == "/api/cost":
            self._send_json(costlog.tally(s.cost_log_path))
        elif path == "/api/config":
            self._send_json(read_editable(s.config_path))
        else:
            self._send_json({"error": "not found"}, 404)

    def _origin_ok(self):
        """CSRF guard: a browser sends Origin on state-changing cross-site POSTs.
        Reject any Origin that is not loopback so a page the user visits cannot
        drive /api/config. Absent Origin (curl, the CLI, tests) has no CSRF vector
        and is allowed; the bind is loopback-only regardless (make_server)."""
        origin = self.headers.get("Origin")
        if not origin:
            return True
        return urllib.parse.urlparse(origin).hostname in _LOOPBACK

    def do_POST(self):
        # ALWAYS drain the request body before responding — replying without
        # reading pending bytes makes Windows RST the socket, so the client sees
        # ConnectionResetError instead of the status (flaky smoke).
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        path = urllib.parse.urlparse(self.path).path
        if path != "/api/config":
            self._send_json({"error": "not found"}, 404)
            return
        if not self._origin_ok():
            self._send_json({"error": "cross-origin POST refused"}, 403)
            return
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip()
        try:
            if ctype == "application/json":
                updates = json.loads(raw or "{}")
                if not isinstance(updates, dict):
                    raise ValueError("body must be a JSON object")
            else:
                updates = _form_updates(raw)
            write_editable(self.server.config_path, updates)
        except ValueError as e:
            if ctype == "application/json":
                self._send_json({"error": str(e)}, 400)
            else:
                self._page(message=f"error: {e}", status=400)
            return
        if ctype == "application/json":
            self._send_json({"ok": True})
        else:
            self.send_response(303)          # redirect back to the page after a form save
            self.send_header("Location", "/")
            self.end_headers()


def make_server(host="127.0.0.1", port=8787, *, config_path, verdict_path=None, cost_log_path):
    """Build (but do not serve) the dashboard server. Refuses any non-loopback host."""
    if host not in _LOOPBACK:
        raise ValueError(f"refusing to bind non-loopback host {host!r}; use 127.0.0.1/localhost")
    httpd = ThreadingHTTPServer((host, port), _Handler)
    httpd.config_path = config_path
    httpd.verdict_path = verdict_path
    httpd.cost_log_path = cost_log_path
    return httpd
