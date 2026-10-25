#!/usr/bin/env python3
"""Risk-Weighted Counterfactual Repair (RWCR) triage index calculator.

Computes a bounded, heuristic ranking index for autonomous security findings:
  priority = 3*I + 2*E + 3*R + N + 2*Q - 2*D

Where all factors are rated 0..5:
  I: Verified impact / blast radius
  E: Exposure
  R: Reproducibility
  N: Novelty
  Q: Evidence quality
  D: Operational disruption risk

DISCLAIMER: This is a triage index, not a calibrated probability or monetary expected loss.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any


def calculate_rwcr(
    *,
    impact: int,
    exposure: int,
    reproducibility: int,
    novelty: int,
    evidence_quality: int,
    disruption: int,
    mechanism: str = "unspecified trust boundary bypass",
    force_critical: bool = False,
) -> dict[str, Any]:
    factors = {
        "I_impact": impact,
        "E_exposure": exposure,
        "R_reproducibility": reproducibility,
        "N_novelty": novelty,
        "Q_evidence": evidence_quality,
        "D_disruption": disruption,
    }
    for name, val in factors.items():
        if not isinstance(val, int) or not 0 <= val <= 5:
            raise ValueError(f"Factor {name} must be an integer between 0 and 5 inclusive, got {val!r}")

    score = 3 * impact + 2 * exposure + 3 * reproducibility + novelty + 2 * evidence_quality - 2 * disruption

    # Severity tiering
    if force_critical or impact >= 5:
        severity = "critical"
    elif score >= 20:
        severity = "high"
    elif score >= 12:
        severity = "medium"
    else:
        severity = "low"

    rationale_parts = [f"Mechanism: {mechanism}."]
    rationale_parts.extend(f"{k}={v}/5" for k, v in factors.items())
    rationale = " ".join(rationale_parts)

    return {
        "priority_index": score,
        "severity": severity,
        "factors": factors,
        "formula": "3*I + 2*E + 3*R + N + 2*Q - 2*D",
        "rationale": rationale,
        "disclaimer": "Heuristic triage index, not expected loss or probability.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Calculate RWCR security triage index")
    parser.add_argument("--impact", "-i", type=int, default=5, help="Verified impact / blast radius (0-5)")
    parser.add_argument("--exposure", "-e", type=int, default=3, help="Exposure (0-5)")
    parser.add_argument("--reproducibility", "-r", type=int, default=5, help="Reproducibility (0-5)")
    parser.add_argument("--novelty", "-n", type=int, default=2, help="Novelty (0-5)")
    parser.add_argument("--evidence-quality", "-q", type=int, default=4, help="Evidence quality (0-5)")
    parser.add_argument("--disruption", "-d", type=int, default=2, help="Disruption risk (0-5)")
    parser.add_argument("--mechanism", "-m", type=str, default="unauthorized financial tool manipulation", help="Mechanism description")
    parser.add_argument("--force-critical", action="store_true", help="Force critical severity")
    parser.add_argument("--from-json", type=str, default="", help="Read factors from JSON file or '-' for stdin")
    args = parser.parse_args()

    if args.from_json:
        if args.from_json == "-":
            data = json.load(sys.stdin)
        else:
            with open(args.from_json) as f:
                data = json.load(f)
        out = calculate_rwcr(
            impact=data.get("impact", data.get("I_impact", 5)),
            exposure=data.get("exposure", data.get("E_exposure", 3)),
            reproducibility=data.get("reproducibility", data.get("R_reproducibility", 5)),
            novelty=data.get("novelty", data.get("N_novelty", 2)),
            evidence_quality=data.get("evidence_quality", data.get("Q_evidence", 4)),
            disruption=data.get("disruption", data.get("D_disruption", 2)),
            mechanism=data.get("mechanism", args.mechanism),
            force_critical=data.get("force_critical", args.force_critical),
        )
    else:
        out = calculate_rwcr(
            impact=args.impact,
            exposure=args.exposure,
            reproducibility=args.reproducibility,
            novelty=args.novelty,
            evidence_quality=args.evidence_quality,
            disruption=args.disruption,
            mechanism=args.mechanism,
            force_critical=args.force_critical,
        )

    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
