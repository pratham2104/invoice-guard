"""Counterfactual replay: run every candidate policy against the same actions."""

from __future__ import annotations

import hashlib
import json
import statistics
import time
from typing import Any

from .policies import BASELINE, CANDIDATES, diff_from_baseline, evaluate
from .scenarios import SCENARIOS

DISCLAIMER = (
    "Synthetic fixtures. Results show how each policy judges the scripted actions in this "
    "scenario, not real-world attack prevention. No payment, mail or network request is made."
)
LATENCY_RUNS = 200


def _latency_ms(policy: dict, acts: list[dict]) -> dict:
    samples = []
    for _ in range(LATENCY_RUNS):
        for act in acts:
            t0 = time.perf_counter()
            evaluate(policy, act)
            samples.append((time.perf_counter() - t0) * 1000)
    samples.sort()
    return {"p50": round(statistics.median(samples), 4),
            "p95": round(samples[int(len(samples) * 0.95) - 1], 4)}


def _run_policy(policy: dict, scn: dict) -> dict:
    attacks = [{"note": a["note"], "action": a, "decision": evaluate(policy, a)} for a in scn["attacks"]]
    legit = [{"note": a["note"], "action": a, "decision": evaluate(policy, a)} for a in scn["legit"]]
    blocked = sum(1 for r in attacks if not r["decision"]["allow"])
    allowed = sum(1 for r in legit if r["decision"]["allow"])
    return {
        "name": policy["name"],
        "label": policy["label"],
        "attacks": attacks,
        "legit": legit,
        "attacks_blocked": blocked,
        "attacks_total": len(attacks),
        "legit_allowed": allowed,
        "legit_total": len(legit),
        "attack_success_rate": round(1 - blocked / len(attacks), 3),
        "false_deny_rate": round(1 - allowed / len(legit), 3),
        "latency_ms": _latency_ms(policy, scn["attacks"] + scn["legit"]),
        "verified": blocked == len(attacks) and allowed == len(legit),
        "config_diff": diff_from_baseline(policy),
    }


def _rank_key(r: dict) -> tuple:
    # Never trade away legitimate work first, then block as much as possible,
    # then prefer the smaller change.
    return (r["legit_allowed"] == r["legit_total"], r["attacks_blocked"], -len(r["config_diff"]))


def replay(scenario_id: str) -> dict:
    scn = SCENARIOS[scenario_id]
    baseline = _run_policy(BASELINE, scn)
    candidates = [_run_policy(p, scn) for p in CANDIDATES]
    best = max(candidates, key=_rank_key)
    for r in candidates:
        r["selected"] = r is best
    return {
        "scenario": scenario_id,
        "title": scn["title"],
        "task": scn["task"],
        "untrusted_source": scn["untrusted_source"],
        "untrusted_content": scn["untrusted_content"],
        "exposure_usd": scn["exposure_usd"],
        "broken_boundary": scn["boundary"],
        "baseline": baseline,
        "candidates": candidates,
        "selected": best["name"],
        "repair": {
            "policy": best["name"],
            "config_diff": best["config_diff"],
            "verified": best["verified"],
            "status": "pending_admin_approval" if best["verified"] else "no_verified_repair",
        },
        "disclaimer": DISCLAIMER,
    }


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def receipt(scenario_id: str) -> dict:
    """Replay result plus a content digest so later tampering is detectable."""
    body = replay(scenario_id)
    # Latency varies run to run; keep it as evidence but outside the digest.
    stable = json.loads(json.dumps(body))
    for r in [stable["baseline"], *stable["candidates"]]:
        r.pop("latency_ms", None)
    return {"body": body, "sha256": hashlib.sha256(_canonical(stable)).hexdigest()}


def verify_receipt(rcpt: dict) -> bool:
    stable = json.loads(json.dumps(rcpt["body"]))
    for r in [stable["baseline"], *stable["candidates"]]:
        r.pop("latency_ms", None)
    return hashlib.sha256(_canonical(stable)).hexdigest() == rcpt["sha256"]


def summary() -> dict:
    """Aggregate across all scenarios for the selected policy and for baseline."""
    rows = [replay(s) for s in SCENARIOS]
    def agg(get):
        blocked = sum(get(r)["attacks_blocked"] for r in rows)
        atk = sum(get(r)["attacks_total"] for r in rows)
        ok = sum(get(r)["legit_allowed"] for r in rows)
        leg = sum(get(r)["legit_total"] for r in rows)
        return {"attacks_blocked": blocked, "attacks_total": atk, "legit_allowed": ok, "legit_total": leg}
    out = {"baseline": agg(lambda r: r["baseline"])}
    for p in CANDIDATES:
        out[p["name"]] = agg(lambda r, n=p["name"]: next(c for c in r["candidates"] if c["name"] == n))
    out["disclaimer"] = DISCLAIMER
    return out
