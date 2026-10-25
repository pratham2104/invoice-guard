"""Agent-facing listener: firewall, AUTOPATCH hooks, guarded payment submit."""

from __future__ import annotations

import hashlib
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING

from .adapter import PaymentAdapter, fixture_registry
from .guardian import TraceLog
from .incident_recorder import IncidentRecorder
from .tool_firewall import ToolFirewall

if TYPE_CHECKING:
    from .autopatch.context import AutopatchRuntime

MAX_BODY = 64 * 1024
SUBMIT_PATH = "/api/adapter/submit"
PATH = SUBMIT_PATH
FIREWALL_PATH = "/api/firewall/before_tool_call"
AFTER_PATH = "/api/firewall/after_tool_call"
POST_PATHS = frozenset({SUBMIT_PATH, FIREWALL_PATH, AFTER_PATH})
DEFAULT_HOSTS = ("127.0.0.1", "localhost", "[::1]", "host.openshell.internal")
LABEL = "agent-facing route; simulated ledger; fixture evidence"


def _host_ok(host: str | None, allowed: tuple[str, ...]) -> bool:
    if not host:
        return False
    name = re.sub(r":[0-9]{1,5}$", "", host.strip().lower())
    return name in {h.lower() for h in allowed}


def make_handler(
    firewall: ToolFirewall,
    trace: TraceLog,
    allowed_hosts: tuple[str, ...] = DEFAULT_HOSTS,
    autopatch: AutopatchRuntime | None = None,
):
    from .autopatch.schemas import TOOL_DENIED
    from .autopatch.triage import triage_event

    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        server_version = "phantomshift-adapter/0.3"
        protocol_version = "HTTP/1.0"

        def _send(self, code: int, obj: dict) -> None:
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _reject(self, code: int, why: str) -> None:
            with lock:
                trace.add("adapter_request_rejected", {"http": code, "why": why, "path": self.path[:64]})
            self._send(code, {"state": "ERROR", "reason_code": "HTTP_" + str(code), "reason": why, "label": LABEL})

        def _read_json(self) -> dict | None:
            if "chunked" in (self.headers.get("Transfer-Encoding") or "").lower():
                self._reject(411, "Content-Length required")
                return None
            if (self.headers.get("Content-Type") or "").split(";")[0].strip().lower() != "application/json":
                self._reject(415, "application/json required")
                return None
            try:
                n = int(self.headers.get("Content-Length", ""))
            except ValueError:
                self._reject(411, "Content-Length required")
                return None
            if n < 0 or n > MAX_BODY:
                self._reject(413, "body too large")
                return None
            raw = self.rfile.read(n)
            try:
                obj = json.loads(raw, parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c)))
            except ValueError:
                self._reject(400, "body is not valid JSON")
                return None
            if not isinstance(obj, dict):
                self._reject(400, "JSON object required")
                return None
            return obj

        def do_POST(self) -> None:  # noqa: N802
            if not _host_ok(self.headers.get("Host"), allowed_hosts):
                return self._reject(403, "forbidden host")
            if self.path not in POST_PATHS:
                return self._reject(404, "not found")
            obj = self._read_json()
            if obj is None:
                return
            digest = hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()

            if self.path == FIREWALL_PATH:
                tool = str(obj.get("toolName") or obj.get("tool_name") or "")
                params = obj.get("params") if isinstance(obj.get("params"), dict) else {}
                run_id = obj.get("runId") or obj.get("run_id")
                session_id = obj.get("sessionId") or obj.get("session_id")
                if autopatch:
                    res = autopatch.gate.evaluate(tool, params, run_id=run_id, session_id=session_id)
                    autopatch.recorder.record_before(tool, params, res)
                    oc = res.get("openclaw") or {}
                    res = {**res, "block": oc.get("block", res.get("block")), "blockReason": oc.get("blockReason")}
                    if res.get("decision") == "DENY":
                        ev = autopatch.store.append_event(TOOL_DENIED, {"tool": tool, "run_id": run_id, "reason": res.get("reason")})
                        triage_event(autopatch.store, TOOL_DENIED, {"tool": tool, "fingerprint": ev["fingerprint"]})
                else:
                    res = firewall.before_tool_call(tool, params, run_id=run_id)
                res = {**res, "label": LABEL, "route": "before_tool_call enforcement"}
                with lock:
                    trace.add("firewall_hook", {"sha256": digest, "tool": tool, "block": res.get("block")})
                return self._send(200, res)

            if self.path == AFTER_PATH:
                tool = str(obj.get("toolName") or obj.get("tool_name") or "")
                run_id = obj.get("runId") or obj.get("run_id")
                ok = bool(obj.get("ok", True))
                if autopatch:
                    autopatch.recorder.record_after(
                        tool,
                        run_id=run_id,
                        ok=ok,
                        result_state=obj.get("result_state"),
                        latency_ms=obj.get("latency_ms"),
                        error=obj.get("error"),
                    )
                self._send(200, {"recorded": True, "tool": tool, "run_id": run_id})
                return

            if "approval_id" in obj:
                res = {
                    "state": "DENIED",
                    "reason_code": "APPROVAL_NOT_ACCEPTED_FROM_AGENT_ROUTE",
                    "reason": "approvals are granted server-side by a human, never accepted from the agent",
                    "executed_simulated": False,
                    "simulated": True,
                    "evidence": "fixture",
                    "mode": "live",
                }
            else:
                res = firewall.execute_guarded_payment(obj)
            res = {**res, "route": LABEL}
            with lock:
                trace.add("adapter_request", {"sha256": digest, "state": res.get("state"), "code": res.get("reason_code")})
            self._send(200, res)

        def _no(self) -> None:
            self._reject(405, "POST only")

        do_GET = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _no  # noqa: N815

        def log_message(self, fmt: str, *args) -> None:
            pass

    return Handler


def serve(
    host: str = "127.0.0.1",
    port: int = 7890,
    allowed_hosts: tuple[str, ...] = DEFAULT_HOSTS,
    *,
    enable_autopatch: bool = True,
    autopatch_db: str = "artifacts/autopatch.sqlite",
) -> None:
    trace = TraceLog("fixture")
    adapter = PaymentAdapter(fixture_registry(), mode="live")
    firewall = ToolFirewall(adapter, recorder=IncidentRecorder(trace=trace))
    ap = None
    if enable_autopatch:
        from .autopatch.context import AutopatchRuntime

        ap = AutopatchRuntime.open(autopatch_db)
    httpd = ThreadingHTTPServer((host, port), make_handler(firewall, trace, allowed_hosts, ap))
    print(
        f"adapter+firewall on http://{host}:{port}{SUBMIT_PATH}, {FIREWALL_PATH}, {AFTER_PATH} "
        f"(autopatch={'on' if ap else 'off'}). Bind private IP for sandbox; never 0.0.0.0."
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        print(f"trace chain ok={trace.verify()} events={len(trace.events)}")
