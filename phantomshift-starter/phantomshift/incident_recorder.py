"""Record attempted, denied and completed tool operations (hash-chained trace)."""

from __future__ import annotations

import hashlib
import json
import time
import uuid

from .guardian import TraceLog


class IncidentRecorder:
    def __init__(self, incident_id: str | None = None, trace: TraceLog | None = None) -> None:
        self.incident_id = incident_id or f"inc-{uuid.uuid4().hex[:12]}"
        self.trace = trace or TraceLog("fixture")

    def record_tool_attempt(self, tool_name: str, params_redacted: dict, *, run_id: str | None = None) -> None:
        self.trace.add("tool_attempt", {"tool": tool_name, "params": params_redacted, "run_id": run_id})

    def record_denial(self, tool_name: str, reason_code: str, reason: str, *, run_id: str | None = None) -> None:
        self.trace.add("tool_denied", {"tool": tool_name, "reason_code": reason_code, "reason": reason, "run_id": run_id})

    def record_execution(self, tool_name: str, verdict: dict) -> None:
        self.trace.add(
            "tool_executed_simulated",
            {"tool": tool_name, "state": verdict.get("state"), "code": verdict.get("reason_code")},
        )

    def receipt_digest(self, observations: dict) -> str:
        body = {"incident_id": self.incident_id, "observations": observations, "ts": round(time.time(), 3)}
        return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()

    def export_trace(self) -> list[dict]:
        return list(self.trace.events)
