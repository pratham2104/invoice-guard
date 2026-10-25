#!/usr/bin/env python3
"""Master orchestration CLI for PHANTOMSHIFT AUTOPATCH.

Runs the complete autonomous security-improvement loop:
1. Wires to the detected host environment (GB10 ARM64, dev workstation, or container sandbox).
2. Synchronous fast-path tool evaluation (ALLOW, DENY, REQUIRE_APPROVAL).
3. Isolated counterfactual research cycle with RWCR triage scoring.
4. Cryptographically bound, single-use operator approval requests.
5. Atomic candidate policy deployment with automatic verification and rollback.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from phantomshift.autopatch.approval_broker import FindingApprovalBroker
from phantomshift.autopatch.context import AutopatchRuntime
from phantomshift.autopatch.deploy import PolicyDeployService
from phantomshift.autopatch.events import AutopatchStore
from phantomshift.autopatch.research import run_research_cycle
from phantomshift.autopatch.rwcr import rwcr_priority
from phantomshift.policies import CANDIDATES


def get_runtime(db_path: str = "artifacts/autopatch.sqlite") -> AutopatchRuntime:
    return AutopatchRuntime.open(db_path)


def handle_wire(args: argparse.Namespace) -> int:
    from wire_environment import wire_environment
    prof = wire_environment(ROOT)
    print(json.dumps(prof, indent=2))
    return 0


def handle_gate(args: argparse.Namespace) -> int:
    rt = get_runtime(args.db)
    tool_name = args.tool
    try:
        params = json.loads(args.params) if args.params else {}
    except Exception as exc:
        print(json.dumps({"decision": "DENY", "reason": f"invalid JSON params: {exc}"}, indent=2))
        return 1

    dec = rt.gate.evaluate(tool_name, params, run_id=args.run_id, session_id=args.session_id)
    print(json.dumps(dec, indent=2))
    return 0 if dec.get("decision") == "ALLOW" else 1


def handle_research(args: argparse.Namespace) -> int:
    rt = get_runtime(args.db)
    res = run_research_cycle(rt.store, scenario_id=args.scenario)
    print(json.dumps(res, indent=2))
    return 0


def handle_approval_request(args: argparse.Namespace) -> int:
    rt = get_runtime(args.db)
    broker = FindingApprovalBroker({"operator-1", "operator-admin"}, ttl_s=float(args.ttl))
    finding = rt.store.get_finding_by_fingerprint(args.fingerprint) if args.fingerprint else None

    cb = next(p for p in CANDIDATES if p["name"] == "context_bound")
    req = broker.request_for_finding(
        finding_id=finding["finding_id"] if finding else "find-manual",
        policy_cfg=cb,
        expected_policy_version="baseline",
    )
    print(json.dumps(req, indent=2))
    return 0


def handle_deploy(args: argparse.Namespace) -> int:
    from deploy_and_verify import execute_deploy_pipeline
    cb = next(p for p in CANDIDATES if p["name"] == args.policy)
    res = execute_deploy_pipeline(
        cb,
        expected_version=args.expected_version,
        finding_id=args.finding_id,
        store_dir=args.store_dir,
        force_regression=args.simulate_regression,
    )
    print(json.dumps(res, indent=2))
    return 0 if res.get("ok") else 1


def handle_status(args: argparse.Namespace) -> int:
    store = AutopatchStore(args.db)
    findings = store.list_findings(limit=10)
    events = store.list_events(limit=10)
    out = {
        "active_findings": findings,
        "recent_events": events,
        "total_findings": len(findings),
        "total_events": len(events),
    }
    print(json.dumps(out, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="PHANTOMSHIFT AUTOPATCH Master Runner")
    parser.add_argument("--db", type=str, default="artifacts/autopatch.sqlite", help="Path to SQLite store")

    sub = parser.add_subparsers(dest="cmd", required=True)

    # wire
    sub.add_parser("wire", help="Probe and wire environment")

    # gate
    g = sub.add_parser("gate", help="Synchronously evaluate a tool call")
    g.add_argument("--tool", required=True, help="Tool name")
    g.add_argument("--params", default="{}", help="Tool parameters JSON")
    g.add_argument("--run-id", default=None)
    g.add_argument("--session-id", default=None)

    # research
    r = sub.add_parser("research", help="Run counterfactual reproduction and RWCR triage")
    r.add_argument("--scenario", default="invoice_redirect")

    # request-approval
    ap = sub.add_parser("request-approval", help="Create bound operator approval request")
    ap.add_argument("--fingerprint", default=None)
    ap.add_argument("--ttl", default=900, help="TTL in seconds (default: 900s / 15m)")

    # deploy
    dp = sub.add_parser("deploy", help="Deploy verified candidate policy")
    dp.add_argument("--policy", choices=["context_bound", "lockdown", "allowlist", "baseline"], default="context_bound")
    dp.add_argument("--finding-id", default="find-runner")
    dp.add_argument("--expected-version", default="baseline")
    dp.add_argument("--store-dir", default="artifacts/autopatch/policies")
    dp.add_argument("--simulate-regression", action="store_true")

    # status
    sub.add_parser("status", help="Show AUTOPATCH store status")

    args = parser.parse_args()

    dispatch = {
        "wire": handle_wire,
        "gate": handle_gate,
        "research": handle_research,
        "request-approval": handle_approval_request,
        "deploy": handle_deploy,
        "status": handle_status,
    }

    return dispatch[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
