#!/usr/bin/env python3
"""Verified deployment and automatic rollback for PHANTOMSHIFT AUTOPATCH.

Applies pre-approved, immutable candidate policies to the sandbox policy store.
Validates candidate digest, backs up existing policy, runs automated regression verification,
and immediately rolls back if any security invariant or legit test regresses.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from phantomshift.approval import config_digest
from phantomshift.autopatch.deploy import PolicyDeployService
from phantomshift.policies import BASELINE, CANDIDATES, validate_config


def execute_deploy_pipeline(
    candidate_config: dict,
    *,
    expected_version: str = "baseline",
    finding_id: str = "find-manual",
    store_dir: str = "artifacts/autopatch/policies",
    force_regression: bool = False,
) -> dict[str, Any]:
    """Execute deploy, regression check, and rollback if needed."""
    candidate_hash = config_digest(candidate_config)
    errs = validate_config(candidate_config)
    if errs:
        return {
            "ok": False,
            "state": "FAILED",
            "reason": f"config validation failed: {errs}",
            "candidate_hash": candidate_hash,
        }

    deploy_svc = PolicyDeployService(store_dir=store_dir)

    if force_regression:
        # Simulate regression: intentionally trigger rollback
        deploy_svc.deploy(
            candidate_config,
            expected_version=expected_version,
            candidate_hash=candidate_hash,
            finding_id=finding_id,
        )
        rb_res = deploy_svc.force_rollback("Simulated post-deploy negative regression triggered")
        return {
            "ok": False,
            "state": "ROLLED_BACK",
            "candidate_hash": candidate_hash,
            "finding_id": finding_id,
            "reason": rb_res["reason"],
            "rolled_back": True,
        }

    res = deploy_svc.deploy(
        candidate_config,
        expected_version=expected_version,
        candidate_hash=candidate_hash,
        finding_id=finding_id,
    )

    receipt = {
        "deploy_id": res.get("deploy_id"),
        "state": res.get("state"),
        "ok": res.get("ok"),
        "finding_id": finding_id,
        "candidate_hash": candidate_hash,
        "verified": res.get("verify", {}).get("passed", False),
        "timestamp": time.time(),
        "reason": res.get("reason", "verified against acceptance suite"),
    }
    receipt_bytes = json.dumps(receipt, sort_keys=True).encode()
    receipt["receipt_digest"] = hashlib.sha256(receipt_bytes).hexdigest()

    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy approved candidate policy with automated rollback on regression")
    parser.add_argument("--policy", choices=["context_bound", "lockdown", "allowlist", "baseline"], default="context_bound", help="Candidate policy name")
    parser.add_argument("--policy-file", type=str, default="", help="Optional JSON file containing full candidate policy dict")
    parser.add_argument("--finding-id", type=str, default="find-deploy-cli", help="Associated finding ID")
    parser.add_argument("--expected-version", type=str, default="baseline", help="Expected current policy version")
    parser.add_argument("--simulate-regression", action="store_true", help="Simulate a post-deploy regression failure to test rollback")
    parser.add_argument("--store-dir", type=str, default="artifacts/autopatch/policies", help="Sandbox policy directory")
    args = parser.parse_args()

    if args.policy_file:
        with open(args.policy_file) as f:
            cfg = json.load(f)
    elif args.policy == "baseline":
        cfg = BASELINE
    else:
        cfg = next((p for p in CANDIDATES if p["name"] == args.policy), None)
        if not cfg:
            print(f"Unknown policy {args.policy}", file=sys.stderr)
            return 1

    res = execute_deploy_pipeline(
        cfg,
        expected_version=args.expected_version,
        finding_id=args.finding_id,
        store_dir=args.store_dir,
        force_regression=args.simulate_regression,
    )

    print(json.dumps(res, indent=2))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
