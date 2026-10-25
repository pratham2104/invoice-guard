"""One end-to-end incident on fixtures: hold -> fork -> select -> propose -> approve -> verify.

Evidence label is always 'fixture'. Forks are POLICY-ONLY replays of captured proposals,
not model-driven counterfactual runs.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from . import discord_views
from .approval import ApprovalGate, SimulatedChannel, config_digest
from .guardian import Authority, Gateway, TraceLog
from .mockapi import MockBusiness
from .policies import BASELINE, CANDIDATES, diff_from_baseline
from .scenarios import SCENARIOS

REPLAY_MODE = "policy_only_replay"


def _run_via_adapter(policy: dict, act: dict, mode: str, evidence: tuple) -> dict:
    """pay_invoice through the strict PaymentAdapter in a fresh registry + ledger.
    Outcome is read from the adapter's ledger, not from the policy's return value."""
    from .adapter import PaymentAdapter, fixture_registry, proposal_from_fixture_action
    ad = PaymentAdapter(fixture_registry(), mode="sandbox" if mode == "sandbox" else "live", policy=policy)
    t0 = time.perf_counter()
    res = ad.submit(proposal_from_fixture_action(act, "INV-2291", "k" + uuid.uuid4().hex[:24], evidence_spans=evidence))
    ms = (time.perf_counter() - t0) * 1000
    executed = len(ad.ledger) > 0
    return {"executed": executed, "harmful": executed and bool(res["authority_violations"]),
            "rule": res.get("rule") or ("" if executed else res["reason_code"]),
            "violations": list(res["authority_violations"]), "latency_ms": ms,
            "state": res["state"], "via": "payment_adapter"}


def run_action(authority: Authority, policy: dict, act: dict, mode: str,
               use_adapter: bool = False, evidence: tuple = (),
               authoritative: bool = False) -> dict:
    """One action in a fresh disposable environment; outcome is read from backend state."""
    if use_adapter and act.get("tool") == "pay_invoice" and isinstance(act.get("args"), dict):
        return _run_via_adapter(policy, act, mode, evidence)
    biz = MockBusiness()
    t0 = time.perf_counter()
    res = Gateway(authority, policy, biz, mode=mode, authoritative=authoritative).submit(act)
    ms = (time.perf_counter() - t0) * 1000
    executed = len(biz.calls) > 0
    return {"executed": executed, "harmful": executed and bool(res["violations"]),
            "rule": res["rule"], "violations": res["violations"], "latency_ms": ms}


def fork(authority: Authority, policy: dict, scn: dict, mode: str = "sandbox", use_adapter: bool = False) -> dict:
    ev = (scn["untrusted_content"],) if use_adapter else ()
    atk = [{"note": a["note"], **run_action(authority, policy, a, mode, use_adapter, ev)} for a in scn["attacks"]]
    leg = [{"note": a["note"], **run_action(authority, policy, a, mode, use_adapter, ev)} for a in scn["legit"]]
    harmed = sum(r["harmful"] for r in atk)
    done = sum(r["executed"] for r in leg)
    return {"name": policy["name"], "label": policy["label"], "attacks": atk, "legit": leg,
            "harmful_executed": harmed, "attacks_total": len(atk),
            "legit_completed": done, "legit_total": len(leg),
            "verified": harmed == 0 and done == len(leg)}


def run_incident(scenario_id: str, operator: str = "operator-1", approve: bool = True,
                 channel=None, wait_s: float = 90.0, store=None, incident_id: str | None = None,
                 run_id: str | None = None, meta: dict | None = None) -> dict:
    scn = SCENARIOS[scenario_id]
    authority = Authority.for_scenario(scenario_id)
    trace = TraceLog("fixture")
    run_id = run_id or uuid.uuid4().hex[:12]
    incident_id = incident_id or f"inc-{run_id}"
    meta = {"run_id": run_id, **(meta or {})}

    def ev(state: str, payload: dict | None = None, **kw) -> None:
        """Append to the durable event store when one is attached (state machine enforced there)."""
        if store is not None:
            store.append(state, incident_id, payload=payload or {}, **{**meta, **kw})

    if store is not None and store.current_state(incident_id) is None:
        ev("QUEUED", {"scenario": scenario_id, "source": "direct run"})
        ev("AGENT_STARTED", {"agent": "fixture pipeline (not an OpenClaw agent)"})
    trace.add("untrusted_content_ingested", {"source": scn["untrusted_source"], "task": scn["task"]})

    live = Gateway(authority, BASELINE, MockBusiness(), trace, mode="live")
    held = live.submit(scn["attacks"][0])
    proposal_id = uuid.uuid4().hex[:12]
    ev("ACTION_PROPOSED", {"tool": scn["attacks"][0]["tool"], "args": scn["attacks"][0]["args"]}, tool_proposal_id=proposal_id)
    if held["held"]:
        ev("DENIED", {"violations": held["violations"]}, tool_proposal_id=proposal_id)
    trace.add("incident_opened", {"boundary": scn["boundary"], "held": held["held"]})
    post = getattr(channel, "post", None)
    if post:
        post("live-attacks", embed=discord_views.attack_embed(scn, scenario_id, held))

    forks = [fork(authority, p, scn, use_adapter=True) for p in [BASELINE, *CANDIDATES]]
    trace.add("forks_replayed", {"mode": REPLAY_MODE, "results": {f["name"]: [f["harmful_executed"], f["legit_completed"]] for f in forks}})
    if post:
        post("parallel-worlds", embed=discord_views.forks_embed(
            {"title": scn["title"], "forks": forks, "replay_mode": REPLAY_MODE,
             "selected": next((f["name"] for f in forks if f["name"] != "baseline" and f["verified"]), None)}))
    good = [f for f in forks if f["name"] != "baseline" and f["verified"]]
    chosen = max(good, key=lambda f: -len(diff_from_baseline(next(p for p in CANDIDATES if p["name"] == f["name"])))) if good else None
    ev("POLICY_REPLAY", {"phase": "candidate", "tested": True, "mode": REPLAY_MODE,
                         "results": {f["name"]: [f["harmful_executed"], f["legit_completed"], f["verified"]] for f in forks}},
       policy_version=chosen["name"] if chosen else None)

    out: dict[str, Any] = {
        "run_id": run_id, "incident_id": incident_id, "scenario": scenario_id, "title": scn["title"],
        "evidence": "fixture", "replay_mode": REPLAY_MODE,
        "live_action": {"held": held["held"], "violations": held["violations"]},
        "forks": forks, "selected": chosen["name"] if chosen else None,
        "synthetic_exposure_usd": scn["exposure_usd"],
    }
    if not chosen:
        trace.add("no_verified_repair", {})
        ev("FAILED", {"reason": "no candidate policy blocked the attack while preserving legitimate work"})
        out.update(approval={"state": "none"}, verification=None)
    else:
        cfg = next(p for p in CANDIDATES if p["name"] == chosen["name"])
        # the gate's operator is whoever the channel authenticates (a Discord user id), not the default label
        operator = getattr(channel, "operator_id", None) or operator
        gate = ApprovalGate({operator})
        channel = channel or SimulatedChannel()
        req = gate.request(cfg)
        text = (f"PHANTOMSHIFT [{scenario_id}] SYNTHETIC FIXTURE. Attack held before execution.\n"
                f"Candidate policy `{cfg['name']}` verified in replay (policy-only): "
                f"attacks executed {chosen['harmful_executed']}/{chosen['attacks_total']}, "
                f"legit completed {chosen['legit_completed']}/{chosen['legit_total']}.\n"
                f"Digest {req['digest'][:12]}. React {chr(0x2705)} to approve or {chr(0x274c)} to reject (operator only).")
        mid = channel.send(text)
        ev("PENDING_APPROVAL", {"digest": req["digest"], "channel": channel.name}, message_id=str(mid),
           policy_version=cfg["name"])
        trace.add("approval_requested", {"digest": req["digest"], "channel": channel.name,
                                         "real_message": getattr(channel, "real_message", False),
                                         "openclaw_managed": getattr(channel, "openclaw_managed", False)})
        if hasattr(channel, "await_decision"):
            decision = channel.await_decision(mid, wait_s)
            if decision is None:
                resp = {"ok": False, "reason": "no operator response before timeout"}
            else:
                resp = gate.respond(req["nonce"], decision[0], decision[1])
        else:
            # Simulated channel only (fixture CLI). Live Discord uses await_decision above; bot never approves alone.
            resp = gate.respond(req["nonce"], operator, approve)
        trace.add("approval_response", {"ok": resp["ok"], "state": resp.get("state", resp.get("reason"))})
        if not resp["ok"]:
            ev("EXPIRED", {"reason": resp.get("reason", "no valid operator response")})
        elif resp.get("state") == "rejected":
            ev("REJECTED", {"digest": req["digest"]}, approval_actor=operator)
        else:
            ev("APPROVED", {"digest": req["digest"]}, approval_actor=operator)
        act = gate.activate(req["nonce"], cfg)
        verification = None
        if act["ok"]:
            after = fork(authority, act["config"], scn, mode="live", use_adapter=True)
            verification = {k: after[k] for k in ("harmful_executed", "attacks_total", "legit_completed", "legit_total", "verified")}
            trace.add("verification", verification)
            ev("POLICY_REPLAY", {"phase": "verification", "verified": bool(verification["verified"]), "digest": req["digest"]})
            if verification["verified"]:
                ev("VERIFIED", verification)
            else:
                ev("FAILED", {"reason": "post-activation verification failed"})
        out.update(
            approval={"state": "activated" if act["ok"] else resp.get("state", resp.get("reason", "rejected")),
                      "channel": channel.name, "real_channel": channel.real,
                      "real_message": getattr(channel, "real_message", False),
                      "openclaw_managed": getattr(channel, "openclaw_managed", False),
                      "digest": req["digest"], "messages": channel.outbox},
            repair={"policy": cfg["name"], "config_diff": diff_from_baseline(cfg), "digest": config_digest(cfg)},
            verification=verification)
    out["trace"] = trace.events
    out["trace_chain_ok"] = trace.verify()
    if store is not None:
        v = store.verify()
        out["event_store"] = {"incident_id": incident_id, "ok": v["ok"], "events": v["events"], "head": v["head"],
                              "final_state": store.current_state(incident_id),
                              "note": "local hash chain; head must be anchored elsewhere to detect full rewrites"}
    if post:
        post("audit-evidence", embed=discord_views.audit_embed(out))
    return out
