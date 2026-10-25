"""Risk-Weighted Counterfactual Repair triage score (heuristic, not calibrated probability)."""

from __future__ import annotations

from typing import Any


def rwcr_priority(
    *,
    impact: int,
    exposure: int,
    reproducibility: int,
    novelty: int,
    evidence_quality: int,
    disruption: int,
    force_critical: bool = False,
) -> dict[str, Any]:
    """Each factor 0..5. Returns score and components."""
    for name, v in (
        ("impact", impact),
        ("exposure", exposure),
        ("reproducibility", reproducibility),
        ("novelty", novelty),
        ("evidence_quality", evidence_quality),
        ("disruption", disruption),
    ):
        if not 0 <= v <= 5:
            raise ValueError(f"{name} must be 0..5")
    score = 3 * impact + 2 * exposure + 3 * reproducibility + novelty + 2 * evidence_quality - 2 * disruption
    severity = "critical" if force_critical or impact >= 5 else "high" if score >= 20 else "medium" if score >= 12 else "low"
    return {
        "priority_index": score,
        "severity": severity,
        "factors": {
            "I_impact": impact,
            "E_exposure": exposure,
            "R_reproducibility": reproducibility,
            "N_novelty": novelty,
            "Q_evidence": evidence_quality,
            "D_disruption": disruption,
        },
        "formula": "3*I + 2*E + 3*R + N + 2*Q - 2*D",
        "disclaimer": "Heuristic triage index, not expected loss or probability.",
    }


def rwcr_rationale(factors: dict[str, int], mechanism: str) -> str:
    parts = [f"Mechanism: {mechanism}."]
    for k, v in factors.items():
        parts.append(f"{k}={v}/5")
    return " ".join(parts)
