"""after_tool_call recorder — bounded events, no LLM in hook."""

from __future__ import annotations

import time
from typing import Any

from .events import AutopatchStore
from .schemas import TOOL_COMPLETED, TOOL_DENIED, TOOL_PROPOSED


class HookRecorder:
    def __init__(self, store: AutopatchStore) -> None:
        self.store = store

    def record_before(self, tool_name: str, params: dict, gate_result: dict) -> None:
        dec = gate_result.get("decision", "DENY")
        base = {
            "tool": tool_name,
            "run_id": gate_result.get("run_id"),
            "session_id": gate_result.get("session_id"),
            "latency_ms": gate_result.get("latency_ms"),
            "incident_id": gate_result.get("incident_id"),
            "ts": time.time(),
        }
        self.store.append_event(TOOL_PROPOSED, {**base, "decision": dec, "params_redacted": True})
        if dec == "DENY":
            self.store.append_event(
                TOOL_DENIED,
                {**base, "reason_code": gate_result.get("reason_code"), "reason": gate_result.get("reason")},
            )

    def record_after(
        self,
        tool_name: str,
        *,
        run_id: str | None,
        ok: bool,
        result_state: str | None,
        latency_ms: float | None = None,
        error: str | None = None,
    ) -> None:
        self.store.append_event(
            TOOL_COMPLETED,
            {
                "tool": tool_name,
                "run_id": run_id,
                "ok": ok,
                "result_state": result_state,
                "latency_ms": latency_ms,
                "error": error,
                "ts": time.time(),
            },
        )
