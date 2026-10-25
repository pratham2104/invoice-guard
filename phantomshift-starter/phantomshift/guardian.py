"""Authority record, hash-chained trace and the gateway every tool call must pass.

The gateway is the only path to MockBusiness. It fails closed: schema error,
policy exception or any internal error means deny plus a trace event.
"""

from __future__ import annotations

import copy
import hashlib
import json
import time
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from .mockapi import MockBusiness
from .policies import evaluate
from .scenarios import AUTHORITY, KNOWN_TOOLS


@dataclass(frozen=True)
class Authority:
    rules: Any  # read-only mapping tool -> constraints

    @classmethod
    def for_scenario(cls, scenario_id: str) -> "Authority":
        frozen = {t: MappingProxyType({k: tuple(v) if isinstance(v, list) else v for k, v in r.items()})
                  for t, r in AUTHORITY[scenario_id].items()}
        return cls(MappingProxyType(frozen))

    def violations(self, act: dict) -> list[str]:
        out = []
        for param, bound in self.rules.get(act["tool"], {}).items():
            if param == "max_amount":
                amt = act["args"].get("amount")
                # strict: a real positive int within the cap. NaN, negatives, bools, floats and a missing amount all fail closed.
                if type(amt) is not int or amt <= 0 or amt > bound:
                    out.append(f"amount {amt!r} is not a positive integer within the authorised maximum {bound}")
            elif param == "forbid_labels":
                bad = sorted(set(act.get("labels", [])) & set(bound))
                if bad:
                    out.append(f"payload labelled {bad} may not leave via {act['tool']}")
            elif act["args"].get(param) not in bound:
                out.append(f"{act['tool']}.{param}={act['args'].get(param)!r} is not an authorised value")
        return out


class TraceLog:
    """Hash-chained event list. A local checksum chain, not a signature or external anchor."""

    def __init__(self, evidence: str = "fixture") -> None:
        self.evidence = evidence
        self.events: list[dict] = []

    def add(self, kind: str, data: dict) -> dict:
        prev = self.events[-1]["hash"] if self.events else "0" * 64
        ev = {"seq": len(self.events), "ts": round(time.time(), 3), "kind": kind,
              "evidence": self.evidence, "data": data, "prev": prev}
        ev["hash"] = hashlib.sha256(json.dumps(ev, sort_keys=True, default=str).encode()).hexdigest()
        self.events.append(ev)
        return ev

    def verify(self) -> bool:
        prev = "0" * 64
        for ev in self.events:
            body = {k: v for k, v in ev.items() if k != "hash"}
            if ev["prev"] != prev or hashlib.sha256(
                    json.dumps(body, sort_keys=True, default=str).encode()).hexdigest() != ev["hash"]:
                return False
            prev = ev["hash"]
        return True


def _schema_problem(act: Any) -> str:
    if not isinstance(act, dict) or not isinstance(act.get("args"), dict):
        return "malformed action"
    if act.get("tool") not in KNOWN_TOOLS:
        return f"unknown tool {act.get('tool')!r}"
    if not isinstance(act.get("prov", {}), dict) or not isinstance(act.get("labels", []), list):
        return "malformed provenance or labels"
    return ""


class Gateway:
    """mode 'live': any authority violation HOLDS the action (never reaches the backend).
    mode 'sandbox': the candidate policy alone decides, so each fork's outcome is observed."""

    def __init__(self, authority: Authority, policy: dict, business: MockBusiness,
                 trace: TraceLog | None = None, mode: str = "live",
                 authoritative: bool = False) -> None:
        self.authority, self.policy, self.business = authority, policy, business
        self.trace = trace or TraceLog()
        self.mode = mode
        self.authoritative = authoritative

    def submit(self, act: dict) -> dict:
        try:
            if self.authoritative:
                from .authoritative_context import canonicalize_action, derive_authoritative_provenance
                canon_act, canon_problem = canonicalize_action(act)
                if canon_problem:
                    return self._deny("schema", canon_problem, act if isinstance(act, dict) else {})
                act = canon_act
                act["prov"] = derive_authoritative_provenance(act, self.authority)
            else:
                problem = _schema_problem(act)
                if problem:
                    return self._deny("schema", problem, act if isinstance(act, dict) else {})
                act = copy.deepcopy(act)
                act = {"prov": {}, "labels": [], **act}
            violations = self.authority.violations(act)
            if violations and self.mode == "live":
                self.trace.add("action_held", {"tool": act["tool"], "args": act["args"], "violations": violations})
                return {"executed": False, "held": True, "violations": violations, "rule": "authority_mismatch"}
            d = evaluate(self.policy, act)
            if not d["allow"]:
                return self._deny(d["rule"], d["reason"], act, violations)
            self.business.call(act["tool"], act["args"], act["labels"])
            self.trace.add("action_executed", {"tool": act["tool"], "args": act["args"], "violations": violations})
            return {"executed": True, "held": False, "violations": violations, "rule": ""}
        except Exception as exc:  # fail closed
            return self._deny("gateway_error", f"{type(exc).__name__}: {exc}", act if isinstance(act, dict) else {})

    def _deny(self, rule: str, reason: str, act: dict, violations: list[str] | None = None) -> dict:
        self.trace.add("action_denied", {"tool": act.get("tool"), "rule": rule, "reason": reason})
        return {"executed": False, "held": False, "violations": violations or [], "rule": rule, "reason": reason}

