# Risk-Weighted Counterfactual Repair (RWCR) Methodology

## 1. Architectural Philosophy: Path Separation

PHANTOMSHIFT AUTOPATCH strictly separates the synchronous enforcement path from the asynchronous discovery loop:

```
[OpenClaw Tool Proposal]
           │
           ▼
[Fast Enforcement Path] ──────(ALLOW)──────► [OpenShell Micro-Sandbox]
 (before_tool_call hook)
           │
      (DENY/HOLD)
           │
           ▼
[Durable SQLite Event Log / Outbox]
           │
           ▼
[Discovery & Research Loop]
 (Every 30m or on suspicious trigger)
           │
           ▼
[Counterfactual Policy Replay]
 (Baseline vs Lockdown vs Context-Bound)
           │
           ▼
[RWCR Triage & Prioritization]
           │
           ▼
[Proof-Carrying Discord Approval]
```

## 2. RWCR Heuristic Triage Formula

$$\text{priority} = 3 \cdot I + 2 \cdot E + 3 \cdot R + N + 2 \cdot Q - 2 \cdot D$$

All factors are integers strictly bounded between $0$ and $5$:
- **$I$ (Verified Impact / Blast Radius)**: Potential harm if malicious call reaches backend (5 = direct money movement or credential egress).
- **$E$ (Exposure)**: Accessibility of the untrusted entry point (e.g. public invoice vs internal config).
- **$R$ (Reproducibility)**: Determinism of attack reproduction in clean sandbox (5 = 100% reproducible across seeds).
- **$N$ (Novelty)**: Distinctiveness from existing known findings (prevents duplicate notification fatigue).
- **$Q$ (Evidence Quality)**: Completeness of causal hash-chain trace and tool payloads.
- **$D$ (Operational Disruption Risk)**: Likelihood that proposed policy change breaks legitimate agent workflows.

### Severity Tiers
- **Critical**: Forced on unauthorized financial transfers or security bypasses; or when $\text{priority} \ge 35$ or $I \ge 5$.
- **High**: $\text{priority} \ge 20$.
- **Medium**: $\text{priority} \ge 12$.
- **Low**: $\text{priority} < 12$.

### Non-Negotiable Disclaimers
1. **Triage Index, Not Expected Loss**: The score is a prioritization ranking for human review, not an actuarial probability or calibrated dollar risk.
2. **Simulated Transaction Exposure**: Any dollar values referenced (e.g. $24,800) represent synthetic test invoice values, never "fraud prevented" or "money saved".
