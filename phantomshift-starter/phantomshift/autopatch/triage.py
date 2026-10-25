"""Immediate deterministic triage on high-risk events."""

from __future__ import annotations

from .events import AutopatchStore
from .schemas import TOOL_DENIED, SANDBOX_EGRESS_DENIED


def triage_event(store: AutopatchStore, event_type: str, payload: dict) -> dict:
    if event_type in (TOOL_DENIED, SANDBOX_EGRESS_DENIED):
        fp = payload.get("fingerprint") or store.append_event(event_type, payload)["fingerprint"]
        job = store.schedule_research(fp, {"trigger": event_type, "payload": payload}, delay_s=0.0)
        return {"action": "schedule_research", "job_id": job, "immediate": True}
    return {"action": "none"}
