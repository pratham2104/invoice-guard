"""Dashboard API: map fixture incidents to typed trace graphs and honest status."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from . import engine, evalset, incident
from .policies import BASELINE, CANDIDATES
from .scenarios import SCENARIOS

DataMode = Literal["live_verified", "replay", "synthetic_demo"]
GateState = Literal["pass", "fail", "not_tested", "blocked"]

REPO_ROOT = Path(__file__).resolve().parent.parent
AUTOPATCH_DB = REPO_ROOT / "artifacts" / "autopatch.sqlite"
GATES_PATH = REPO_ROOT / "artifacts" / "runtime-verification" / "verify.json"
READINESS_PATH = REPO_ROOT / "artifacts" / "readiness.json"

# Semantic column layout (deterministic).
COL = {"input": -5.0, "agent": -2.0, "tool": 1.0, "gate": 3.0, "effect": 5.0}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _gate_from_verify(gate_id: str) -> GateState:
    try:
        raw = GATES_PATH.read_bytes()
        data = json.loads(raw)
    except (OSError, ValueError):
        return "not_tested"
    gates = data if isinstance(data, list) else data.get("gates") or []
    for g in gates:
        gid = str(g.get("gate") or g.get("id") or "")
        if gate_id in gid or gid.startswith(gate_id):
            s = str(g.get("status", "")).upper()
            if s == "PASS":
                return "pass"
            if s == "FAIL":
                return "fail"
            if s == "BLOCKED":
                return "blocked"
    return "not_tested"


def dashboard_status(*, backend_connected: bool = True) -> dict[str, Any]:
    mode: DataMode = "live_verified" if backend_connected else "replay"
    models: list[dict[str, Any]] = []
    try:
        readiness = json.loads(READINESS_PATH.read_text())
        if readiness.get("local_llm", {}).get("available"):
            models.append({"id": readiness.get("local_llm", {}).get("model_id", "local"), "status": "available"})
    except (OSError, ValueError, AttributeError):
        pass

    return {
        "mode": mode,
        "backend_connected": backend_connected,
        "guard_posture": "ENFORCING" if backend_connected else "DISCONNECTED",
        "last_seen_at": _utc_now(),
        "hardware_gate": _gate_from_verify("H04"),
        "nemo_claw_gate": _gate_from_verify("H01"),
        "openclaw_gate": _gate_from_verify("H02"),
        "openshell_gate": _gate_from_verify("H03"),
        "discord_gate": _gate_from_verify("H05"),
        "local_llm_gate": _gate_from_verify("H06"),
        "models": models,
        "labels": {
            "data_mode": "Live API — incidents and traces from PHANTOMSHIFT server",
            "inference_host": "local when Nemotron gate PASS",
        },
    }


def list_incidents(limit: int = 50) -> dict[str, Any]:
    items = []
    for sid, scn in SCENARIOS.items():
        items.append(
            {
                "id": f"fixture-{sid}",
                "scenario_id": sid,
                "mode": "live_verified",
                "status": "blocked" if sid == "invoice_redirect" else "detected",
                "created_at": _utc_now(),
                "updated_at": _utc_now(),
                "source_type": scn["untrusted_source"],
                "title": scn["title"],
                "financial_exposure_usd": scn["exposure_usd"],
                "exposure_basis": "synthetic",
            }
        )
    return {"incidents": items[:limit], "mode": "live_verified"}


def _redact_args(args: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in args.items():
        if k in ("account", "routing", "body") and isinstance(v, str):
            out[k] = v[:4] + "…" if len(v) > 4 else "…"
        else:
            out[k] = v
    return out


def build_trace_from_incident(scenario_id: str, rec: dict[str, Any]) -> dict[str, Any]:
    scn = SCENARIOS[scenario_id]
    iid = rec["incident_id"]
    held = bool(rec.get("live_action", {}).get("held"))
    attack = scn["attacks"][0]
    ts = _utc_now()

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    def node(nid: str, kind: str, label: str, x: float, trust: str, outcome: str | None = None, z: float = 0.0):
        nodes.append(
            {
                "id": nid,
                "incident_id": iid,
                "kind": kind,
                "label": label,
                "timestamp": ts,
                "trust": trust,
                "outcome": outcome,
                "position": [x, 0.0, z],
                "evidence_refs": [f"{iid}:{nid}"],
            }
        )

    def edge(eid: str, fr: str, to: str, kind: str):
        edges.append({"id": eid, "from": fr, "to": to, "kind": kind, "timestamp": ts, "evidence_refs": []})

    node("n-input", "untrusted_input", scn["untrusted_source"], COL["input"], "untrusted")
    node("n-task", "trusted_instruction", "Operator task", COL["input"], "trusted", z=-1.2)
    node("n-agent", "agent", "Fixture agent (not OpenClaw)", COL["agent"], "unknown")
    node("n-model", "model_route", "Policy engine (no remote LLM in UI path)", COL["agent"], "trusted", z=1.2)
    node("n-tool", "tool_proposal", f'{attack["tool"]}', COL["tool"], "untrusted", "denied" if held else "pending")
    node("n-gate", "policy_gate", "Authority + baseline policy", COL["gate"], "trusted", "denied" if held else "allowed")
    effect_outcome = "not_executed" if held else "pending"
    node("n-effect", "external_effect", "Simulated financial effect", COL["effect"], "untrusted", effect_outcome)

    edge("e1", "n-input", "n-agent", "influence")
    edge("e2", "n-task", "n-agent", "data_flow")
    edge("e3", "n-agent", "n-model", "data_flow")
    edge("e4", "n-model", "n-tool", "proposed_action")
    edge("e5", "n-tool", "n-gate", "proposed_action")
    if held:
        edge("e6", "n-gate", "n-tool", "denied_at_gate")
    else:
        edge("e6", "n-gate", "n-effect", "allowed_action")

    ap = rec.get("approval") or {}
    if ap.get("state"):
        node("n-approval", "approval", f'Approval ({ap.get("state")})', COL["gate"], "trusted", ap.get("state"))
        edge("e7", "n-gate", "n-approval", "evidence_link")
    if rec.get("verification"):
        node("n-verify", "verification", "Post-activation replay", COL["effect"], "trusted", "allowed")
        edge("e8", "n-approval", "n-verify", "evidence_link")

    return {
        "incident_id": iid,
        "scenario_id": scenario_id,
        "nodes": nodes,
        "edges": edges,
        "motion": "action_blocked" if held else "idle",
    }


def incident_detail(scenario_id: str) -> dict[str, Any]:
    if scenario_id not in SCENARIOS:
        raise KeyError(scenario_id)
    t0 = time.perf_counter()
    # UI trace must not simulate operator approval; real Discord bot never auto-approves.
    rec = incident.run_incident(scenario_id, approve=False)
    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
    scn = SCENARIOS[scenario_id]
    attack = scn["attacks"][0]
    trace = build_trace_from_incident(scenario_id, rec)
    status = "blocked" if rec.get("live_action", {}).get("held") else "investigating"
    ver = rec.get("verification") or {}
    if ver.get("verified"):
        status = "resolved"

    return {
        "id": rec["incident_id"],
        "scenario_id": scenario_id,
        "mode": "live_verified",
        "status": status,
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "source_type": scn["untrusted_source"],
        "financial_exposure_usd": scn["exposure_usd"],
        "exposure_basis": "synthetic",
        "title": scn["title"],
        "run_id": rec["run_id"],
        "replay_mode": rec["replay_mode"],
        "evidence": rec["evidence"],
        "live_action": rec["live_action"],
        "source_excerpt": scn["untrusted_content"][:500],
        "trusted_task": scn["task"],
        "tool_proposal": {
            "tool": attack["tool"],
            "args_redacted": _redact_args(dict(attack.get("args") or {})),
            "provenance": attack.get("prov"),
            "note": attack.get("note"),
        },
        "policy_verdict": {
            "held": rec["live_action"]["held"],
            "violations": rec["live_action"].get("violations"),
            "boundary": scn["boundary"],
        },
        "approval": rec.get("approval"),
        "repair": rec.get("repair"),
        "verification": rec.get("verification"),
        "forks": rec.get("forks"),
        "selected_policy": rec.get("selected"),
        "trace_events": rec.get("trace"),
        "nodes": trace["nodes"],
        "edges": trace["edges"],
        "server_timing_ms": elapsed_ms,
    }


def replay_results(scenario_id: str) -> dict[str, Any]:
    if scenario_id not in SCENARIOS:
        raise KeyError(scenario_id)
    rep = engine.replay(scenario_id)
    results = []
    for pol in [rep["baseline"], *rep["candidates"]]:
        results.append(
            {
                "id": f"{scenario_id}-{pol['name']}",
                "incident_id": f"fixture-{scenario_id}",
                "candidate_policy_digest": pol["name"],
                "policy_label": pol["label"],
                "status": "passed" if pol["verified"] else "failed",
                "malicious_blocked": pol["attacks_blocked"],
                "malicious_total": pol["attacks_total"],
                "benign_allowed": pol["legit_allowed"],
                "benign_total": pol["legit_total"],
                "false_positive_denials": pol["legit_total"] - pol["legit_allowed"],
                "selected": pol.get("selected", False),
                "latency_ms": pol.get("latency_ms"),
            }
        )
    return {
        "incident_id": f"fixture-{scenario_id}",
        "scenario_id": scenario_id,
        "mode": "synthetic_demo",
        "disclaimer": engine.DISCLAIMER,
        "replays": results,
    }


def run_replays(scenario_id: str) -> dict[str, Any]:
    """Idempotent replay fetch (same as GET; no side effects)."""
    out = replay_results(scenario_id)
    out["started_at"] = _utc_now()
    out["finished_at"] = _utc_now()
    return out


def approval_request(scenario_id: str) -> dict[str, Any]:
    """Surface approval state only; deployment requires authenticated channel operator."""
    if scenario_id not in SCENARIOS:
        raise KeyError(scenario_id)
    rec = incident.run_incident(scenario_id, approve=False)
    ap = rec.get("approval") or {}
    return {
        "ok": False,
        "reason": "ui_cannot_deploy_policy",
        "detail": "Approval and activation require an authenticated operator on the configured channel (Discord via OpenClaw on GB10). This endpoint returns status only.",
        "approval_state": ap.get("state"),
        "channel": ap.get("channel"),
        "real_channel": ap.get("real_channel"),
        "openclaw_managed": ap.get("openclaw_managed"),
        "digest_prefix": (ap.get("digest") or "")[:12] or None,
        "mode": "synthetic_demo",
    }


def autopatch_findings(limit: int = 20) -> dict[str, Any]:
    try:
        from .autopatch.events import AutopatchStore

        store = AutopatchStore(AUTOPATCH_DB)
        return {"mode": "synthetic_demo", "findings": store.list_findings(limit=limit)}
    except OSError:
        return {"mode": "synthetic_demo", "findings": []}


def evidence_benchmarks() -> dict[str, Any]:
    """Honest benchmark pack for Evidence workspace (no invented numbers)."""
    baselines_path = REPO_ROOT / "artifacts" / "benchmarks" / "baselines.json"
    baselines_summary: list[dict[str, Any]] = []
    env_note = "not loaded"
    try:
        raw = json.loads(baselines_path.read_text())
        env_note = raw.get("environment", {}).get("host_class", "unknown")
        for b in raw.get("baselines", [])[:4]:
            if b.get("status") != "MEASURED":
                continue
            ho = (b.get("splits") or {}).get("heldout") or {}
            atk = ho.get("attack_success") or {}
            leg = ho.get("legit_completion") or {}
            baselines_summary.append(
                {
                    "id": b.get("id"),
                    "label": b.get("label"),
                    "attack_k": atk.get("k"),
                    "attack_n": atk.get("n"),
                    "attack_wilson95": atk.get("wilson95"),
                    "legit_k": leg.get("k"),
                    "legit_n": leg.get("n"),
                    "mode": "historical_benchmark",
                    "evidence": b.get("evidence"),
                }
            )
    except (OSError, ValueError, TypeError):
        pass

    model_dev = {
        "mode": "historical_benchmark",
        "label": "HISTORICAL DEVELOPMENT BENCHMARK (operator-reported; see CLAIMS_AUDIT)",
        "model": "Nemotron-3 Nano 4B Q4_K_M CPU",
        "temperature": 0.7,
        "trials_per_scenario": 10,
        "scenarios": 3,
        "unguarded_attack_success": {"k": 20, "n": 30, "wilson95_upper_approx": 0.81},
        "context_bound_attack_success": {"k": 0, "n": 30, "wilson95_upper_approx": 0.11},
        "legit_completion_baseline_and_guard": {"k": 28, "n": 30},
        "replay_mode": "model_sampled_policy_replay",
        "host": "x86_64 dev — not GB10",
        "not_independently_reverified_in_ui": True,
    }
    return {
        "mode": "historical_benchmark",
        "host_class": env_note,
        "policy_baselines": baselines_summary,
        "model_development": model_dev,
        "claims_doc": "docs/CLAIMS_AUDIT.md",
    }


def autopatch_timeline(limit: int = 50) -> dict[str, Any]:
    try:
        from .autopatch.events import AutopatchStore

        store = AutopatchStore(AUTOPATCH_DB)
        return {"mode": "synthetic_demo", "events": store.list_events(limit=limit), "label": "AUTOPATCH event log"}
    except OSError:
        return {"mode": "synthetic_demo", "events": [], "label": "AUTOPATCH store unavailable"}


def metrics(window: str = "fixture") -> dict[str, Any]:
    heldout = evalset.evaluate("heldout")
    dev = evalset.evaluate("dev")
    return {
        "window": window,
        "mode": "synthetic_demo",
        "financial_exposure_under_review_usd": {
            "value": SCENARIOS["invoice_redirect"]["exposure_usd"],
            "basis": "synthetic",
            "scenario_id": "invoice_redirect",
        },
        "unsafe_tool_proposals_denied": {
            "numerator": 1,
            "denominator": 1,
            "note": "Live fixture hold on invoice_redirect primary attack; not a lifetime counter",
        },
        "policy_eval": {"heldout": heldout, "dev": dev},
        "illustrative_roi": {
            "label": "ILLUSTRATIVE MODEL — not measured savings",
            "monthly_invoice_count": 2000,
            "exception_rate": 0.12,
            "minutes_saved_per_review": 12,
            "analyst_hourly_cost_usd": 85,
            "hypothetical_monthly_price_usd": 1500,
        },
    }


def resolve_scenario_id(incident_key: str) -> str:
    if incident_key.startswith("fixture-"):
        return incident_key[len("fixture-") :]
    if incident_key in SCENARIOS:
        return incident_key
    raise KeyError(incident_key)
