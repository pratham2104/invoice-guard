"""Local-only HTTP server: JSON API plus one static page."""

from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import dashboard, engine, evalset, incident
from .scenarios import SCENARIOS

# DNS-rebinding defence: a browser tab on attacker.example that rebinds to 127.0.0.1 still sends
# "Host: attacker.example", so only these literal local names (with or without a port) are served.
# Consequence: serve(host=...) bound to a non-loopback address is reachable by IP only if the client
# sends one of these Host values, i.e. this UI is meant for same-machine access or an SSH tunnel.
ALLOWED_HOST_RE = re.compile(r"^(?:127\.0\.0\.1|localhost|\[::1\])(?::[0-9]{1,5})?$", re.I)

STATIC = Path(__file__).parent / "static"
PAYGUARD_STATIC = STATIC / "payguard"
REPO_ROOT = Path(__file__).resolve().parent.parent
# Gate results written by scripts/verify_hackathon.py. Served verbatim; never synthesised.
GATES_PATH = REPO_ROOT / "artifacts" / "runtime-verification" / "verify.json"

# Exact-match allow-list of static files (no path joining from user input).
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
}


class Handler(BaseHTTPRequestHandler):
    server_version = "phantomshift/0.1"

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; style-src 'self' 'unsafe-inline'; "
                         "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj).encode(), "application/json")

    def _read_body(self) -> bytes:
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def _serve_payguard(self, path: str) -> bool:
        """Serve built PAYGUARD SPA under /payguard/ with strict path containment."""
        if not (path == "/payguard" or path.startswith("/payguard/")):
            return False
        rel = "index.html" if path in ("/payguard", "/payguard/") else path[len("/payguard/") :]
        if not rel or rel.endswith("/"):
            rel = rel.rstrip("/") + "/index.html" if rel else "index.html"
        target = (PAYGUARD_STATIC / rel).resolve()
        root = PAYGUARD_STATIC.resolve()
        if not str(target).startswith(str(root)) or not target.is_file():
            self._json({"error": "not found"}, 404)
            return True
        ctype = "application/octet-stream"
        if target.suffix == ".html":
            ctype = "text/html; charset=utf-8"
        elif target.suffix == ".js":
            ctype = "text/javascript; charset=utf-8"
        elif target.suffix == ".css":
            ctype = "text/css; charset=utf-8"
        elif target.suffix == ".svg":
            ctype = "image/svg+xml"
        self._send(200, target.read_bytes(), ctype)
        return True

    def _gates(self) -> None:
        try:
            raw = Path(GATES_PATH).read_bytes()
        except FileNotFoundError:
            self._json([])  # no verification run yet: report nothing rather than invent gates
            return
        except OSError:
            self._json({"error": "verify.json is unreadable"}, 500)
            return
        try:
            data = json.loads(raw)
        except ValueError:
            self._json({"error": "verify.json is not valid JSON"}, 500)
            return
        self._json(data)

    def do_GET(self) -> None:  # noqa: N802
        host = self.headers.get("Host")
        if host is None or not ALLOWED_HOST_RE.match(host):
            self._json({"error": "forbidden host"}, 403)
            return
        path = self.path.split("?", 1)[0]
        if self._serve_payguard(path):
            return
        if path in STATIC_FILES:
            name, ctype = STATIC_FILES[path]
            self._send(200, (STATIC / name).read_bytes(), ctype)
        elif path == "/api/gates":
            self._gates()
        elif path == "/api/scenarios":
            self._json([{"id": k, "title": v["title"], "task": v["task"]} for k, v in SCENARIOS.items()])
        elif path == "/api/eval":
            self._json({"heldout": evalset.evaluate("heldout"), "dev": evalset.evaluate("dev")})
        elif path.startswith("/api/incident/"):
            sid = path.rsplit("/", 1)[-1]
            if sid not in SCENARIOS:
                self._json({"error": "unknown scenario"}, 404)
            else:
                self._json(incident.run_incident(sid))
        elif path == "/api/summary":
            self._json(engine.summary())
        elif path == "/api/dashboard/status":
            self._json(dashboard.dashboard_status())
        elif path == "/api/incidents":
            q = self.path.split("?", 1)[1] if "?" in self.path else ""
            limit = 50
            for part in q.split("&"):
                if part.startswith("limit="):
                    try:
                        limit = max(1, min(100, int(part.split("=", 1)[1])))
                    except ValueError:
                        pass
            self._json(dashboard.list_incidents(limit=limit))
        elif path.startswith("/api/incidents/"):
            parts = path.strip("/").split("/")
            # /api/incidents/{id} | trace | replays
            if len(parts) == 3:
                iid = parts[2]
                try:
                    sid = dashboard.resolve_scenario_id(iid)
                except KeyError:
                    self._json({"error": "unknown incident"}, 404)
                    return
                self._json(dashboard.incident_detail(sid))
            elif len(parts) == 4 and parts[3] == "trace":
                iid = parts[2]
                try:
                    sid = dashboard.resolve_scenario_id(iid)
                    rec = dashboard.incident_detail(sid)
                except KeyError:
                    self._json({"error": "unknown incident"}, 404)
                    return
                self._json(
                    {
                        "incident_id": rec["id"],
                        "nodes": rec["nodes"],
                        "edges": rec["edges"],
                        "motion": "action_blocked" if rec["live_action"].get("held") else "idle",
                    }
                )
            elif len(parts) == 4 and parts[3] == "replays":
                iid = parts[2]
                try:
                    sid = dashboard.resolve_scenario_id(iid)
                except KeyError:
                    self._json({"error": "unknown incident"}, 404)
                    return
                self._json(dashboard.replay_results(sid))
            else:
                self._json({"error": "not found"}, 404)
        elif path == "/api/metrics":
            self._json(dashboard.metrics())
        elif path == "/api/evidence/benchmarks":
            self._json(dashboard.evidence_benchmarks())
        elif path == "/api/autopatch/findings":
            q = self.path.split("?", 1)[1] if "?" in self.path else ""
            limit = 20
            for part in q.split("&"):
                if part.startswith("limit="):
                    try:
                        limit = max(1, min(100, int(part.split("=", 1)[1])))
                    except ValueError:
                        pass
            self._json(dashboard.autopatch_findings(limit=limit))
        elif path == "/api/autopatch/events":
            q = self.path.split("?", 1)[1] if "?" in self.path else ""
            limit = 50
            for part in q.split("&"):
                if part.startswith("limit="):
                    try:
                        limit = max(1, min(200, int(part.split("=", 1)[1])))
                    except ValueError:
                        pass
            self._json(dashboard.autopatch_timeline(limit=limit))
        elif path.startswith("/api/replay/") or path.startswith("/api/receipt/"):
            kind, sid = path.split("/")[2:4] if path.count("/") == 3 else ("", "")
            if sid not in SCENARIOS:
                self._json({"error": "unknown scenario"}, 404)
            else:
                self._json(engine.replay(sid) if kind == "replay" else engine.receipt(sid))
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        host = self.headers.get("Host")
        if host is None or not ALLOWED_HOST_RE.match(host):
            self._json({"error": "forbidden host"}, 403)
            return
        path = self.path.split("?", 1)[0]
        if path.startswith("/api/incidents/") and path.endswith("/replays"):
            iid = path.split("/")[3]
            try:
                sid = dashboard.resolve_scenario_id(iid)
            except KeyError:
                self._json({"error": "unknown incident"}, 404)
                return
            self._json(dashboard.run_replays(sid))
        elif path.startswith("/api/incidents/") and path.endswith("/approval-request"):
            iid = path.split("/")[3]
            try:
                sid = dashboard.resolve_scenario_id(iid)
            except KeyError:
                self._json({"error": "unknown incident"}, 404)
                return
            self._read_body()
            self._json(dashboard.approval_request(sid))
        else:
            self._json({"error": "not found"}, 404)

    def log_message(self, fmt: str, *args) -> None:
        pass


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"PHANTOMSHIFT listening on http://{host}:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
