"""Runtime wiring for adapter listener + AUTOPATCH."""

from __future__ import annotations

from dataclasses import dataclass

from .events import AutopatchStore
from .gate import EnforcementGate
from .recorder import HookRecorder


@dataclass
class AutopatchRuntime:
    store: AutopatchStore
    gate: EnforcementGate
    recorder: HookRecorder

    @classmethod
    def open(cls, db_path: str = "artifacts/autopatch.sqlite") -> "AutopatchRuntime":
        from ..adapter import PaymentAdapter, fixture_registry
        from ..incident_recorder import IncidentRecorder
        from ..tool_firewall import ToolFirewall

        store = AutopatchStore(db_path)
        adapter = PaymentAdapter(fixture_registry(), mode="live")
        fw = ToolFirewall(adapter, recorder=IncidentRecorder())
        gate = EnforcementGate(fw)
        return cls(store=store, gate=gate, recorder=HookRecorder(store))
