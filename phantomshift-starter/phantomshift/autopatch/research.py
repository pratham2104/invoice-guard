"""Discovery path: reproduce fixtures, compare candidates, emit findings (no external scanning)."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from .. import engine
from ..adaptive_eval import run_adaptive_trial
from ..adapter import PaymentAdapter, fixture_registry
from ..enforcement_pipeline import malicious_payment_proposal
from ..approval import config_digest
from ..policies import BASELINE, CANDIDATES
from ..policies import diff_from_baseline
from ..tool_firewall import ToolFirewall
from .events import AutopatchStore, fingerprint_event
from .rwcr import rwcr_priority, rwcr_rationale
from .schemas import CRON_SECURITY_SCAN, TOOL_DENIED


def finding_fingerprint(scenario_id: str, boundary: str, policy_digest: str) -> str:
    return hashlib.sha256(f"{scenario_id}|{boundary}|{policy_digest}".encode()).hexdigest()[:32]


def run_research_cycle(store: AutopatchStore, *, scenario_id: str = "invoice_redirect") -> dict[str, Any]:
    """One bounded research pass: reproduce deny, replay policies, optional adaptive trial."""
    rep = engine.replay(scenario_id)
    fw = ToolFirewall(PaymentAdapter(fixture_registry(), mode="live"))
    attack = malicious_payment_proposal(scenario_id)
    exec_result = fw.execute_guarded_payment(attack)
    adaptive = run_adaptive_trial(
        fw,
        lambda turn, _last: {**attack, "idempotency_key": f"k-adapt-{turn}-" + "c" * 20} if turn < 3 else None,
        max_turns=3,
    )

    boundary = rep.get("broken_boundary") or "financial tool gate"
    pd = config_digest(BASELINE)
    fp = finding_fingerprint(scenario_id, boundary, pd)

    existing = store.get_finding_by_fingerprint(fp)
    if existing and existing.get("state") in ("AWAITING_APPROVAL", "VERIFIED"):
        return {"skipped": True, "reason": "duplicate finding already active", "fingerprint": fp}

    blocked = exec_result.get("block") or exec_result.get("state") == "DENIED"
    rwcr = rwcr_priority(
        impact=5 if blocked else 2,
        exposure=3,
        reproducibility=5 if blocked else 1,
        novelty=2 if not existing else 0,
        evidence_quality=4 if blocked else 2,
        disruption=2,
        force_critical=blocked and exec_result.get("ledger_unchanged") is False,
    )

    candidates = []
    for pol, row in [(BASELINE, rep["baseline"]), *[(p, next(c for c in rep["candidates"] if c["name"] == p["name"])) for p in CANDIDATES]]:
        candidates.append({
            "policy": pol["name"],
            "label": pol["label"],
            "attacks_blocked": row["attacks_blocked"],
            "attacks_total": row["attacks_total"],
            "legit_allowed": row["legit_allowed"],
            "legit_total": row["legit_total"],
            "verified": row.get("verified"),
            "digest": config_digest(pol),
        })

    selected = next((c for c in candidates if c["policy"] == "context_bound" and c.get("verified")), None)
    finding_id = f"find-{uuid.uuid4().hex[:10]}"
    record: dict[str, Any] = {
        "finding_id": finding_id,
        "fingerprint": fp,
        "state": "PROPOSED" if blocked else "INCONCLUSIVE",
        "scenario_id": scenario_id,
        "severity": rwcr["severity"],
        "priority_index": rwcr["priority_index"],
        "rwcr": rwcr,
        "rationale": rwcr_rationale(rwcr["factors"], boundary),
        "trust_boundary": boundary,
        "mechanism": "Unauthorized recipient derived from untrusted invoice text",
        "evidence": {
            "exec_result_state": exec_result.get("state"),
            "ledger_unchanged": exec_result.get("ledger_unchanged"),
            "adaptive": adaptive,
            "replay_mode": "policy_only_replay",
            "label": "fixture reproduction; not live OpenClaw proof",
        },
        "metrics": {
            "baseline_guard_latency_ms": exec_result.get("latency_ms"),
            "adaptive_denials": adaptive.get("denials"),
            "harmful_simulated_execution": adaptive.get("harmful_simulated_execution"),
        },
        "candidates": candidates,
        "selected_policy": selected["policy"] if selected else None,
        "proposed_diff": diff_from_baseline(next(p for p in CANDIDATES if p["name"] == "context_bound")) if selected else [],
        "exposure_classification": "simulated_transaction_exposure",
        "recommended_action": "Compare context_bound vs baseline; request operator approval for sandbox deploy",
    }

    store.upsert_finding(record)
    store.append_event(CRON_SECURITY_SCAN, {"finding_id": finding_id, "fingerprint": fp, "blocked": blocked})
    if blocked:
        store.enqueue_outbox(
            "approvals",
            f"finding-{fp}",
            {"finding_id": finding_id, "digest": selected["digest"] if selected else pd, "severity": rwcr["severity"]},
        )

    return {"finding_id": finding_id, "fingerprint": fp, "state": record["state"], "rwcr": rwcr, "blocked": blocked}
