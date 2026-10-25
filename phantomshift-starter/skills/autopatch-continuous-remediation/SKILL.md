---
name: autopatch-continuous-remediation
description: Autonomous security-improvement loop for coding agents and cybersecurity runtimes. Automatically discovers, reproduces, evaluates (RWCR), proposes least-privilege policy patches, requests cryptographic Discord approvals, and deploys/rolls back verified defenses against prompt injection and tool manipulation on Dell GB10 / OpenClaw / OpenShell environments.
license: MIT
---

# PHANTOMSHIFT AUTOPATCH: Continuous Flaw Discovery and Proof-Carrying Remediation

An autonomous security-improvement skill for coding agents operating in Dell Grace Blackwell GB10, OpenClaw, OpenShell, and local development environments.

## Overview

AUTOPATCH separates real-time execution safety from asynchronous vulnerability discovery:
1. **Fast Enforcement Path (Synchronous, < 1ms latency)**: Intercepts agent tool proposals at the execution boundary (`before_tool_call`), strictly validates parameters against authoritative vendor master records, and denies or holds unauthorized financial operations independently of any LLM.
2. **Discovery & Remediation Path (Asynchronous, Isolated)**: Reproduces near-misses in clean counterfactual test fixtures, evaluates multi-candidate policy variants, scores findings via the **Risk-Weighted Counterfactual Repair (RWCR)** index, generates cryptographic Discord approval requests, and deploys verified patches with instant rollback on regression.

---

## Environment Detection & Auto-Wiring

Before executing tasks, the skill probes the host to determine the available hardware tier and configure ports, model endpoints, and bridge settings.

Run the environment sensor:
```bash
python3 skills/autopatch-continuous-remediation/scripts/wire_environment.py
```

### Detected Tiers:
- **`GB10_PRODUCTION_AIRGAP`**: Dell Grace Blackwell GB10 ARM64 (`aarch64`), Unified Memory, local vLLM serving Nemotron 3.5 Lightning 30B NVFP4, rootful Docker bridge (`172.18.0.1:8080`).
- **`DEV_HOST_SIMULATION`**: Ubuntu x86_64 workstation with dual RTX 3090 GPUs, CPU/local fallback inference, and simulated channel outbox.
- **`CONTAINER_MICRO_SANDBOX`**: OpenShell container environment executing least-privilege tool actions.

---

## Core Workflows

### 1. Fast-Path Tool Evaluation (Gate)
To evaluate an agent tool proposal synchronously before any financial or backend ledger state can be mutated:

```bash
python3 skills/autopatch-continuous-remediation/scripts/autopatch_runner.py gate \
  --tool pay_invoice \
  --params '{"vendor_id":"V-102","amount":24800,"account":"000123459921"}'
```

- **Outcomes**: `ALLOW`, `DENY`, or `REQUIRE_APPROVAL`.
- **Fail-Closed Rule**: Missing context, schema mismatch, unparseable strings, or hook timeouts (> 50ms) fail closed.
- **Ledger Invariant**: The backend mock bank ledger remains at exactly 0 rows on denied calls.

### 2. Autonomous Research Cycle & RWCR Scoring
To reproduce an attack in an isolated counterfactual fixture and evaluate candidate repairs:

```bash
python3 skills/autopatch-continuous-remediation/scripts/autopatch_runner.py research \
  --scenario invoice_redirect
```

#### The RWCR Triage Formula:
$$\text{priority} = 3 \cdot I + 2 \cdot E + 3 \cdot R + N + 2 \cdot Q - 2 \cdot D$$
- Factor bounds: $0 \le I, E, R, N, Q, D \le 5$.
- Evaluates four policy futures simultaneously:
  1. **Baseline**: Permissive allow-list (verifies the attack succeeds).
  2. **Lockdown**: Deny all sensitive tools (verifies legitimate work is broken).
  3. **Allowlist**: Destination domain filter (demonstrates failure against internal accounts).
  4. **Context-Bound / Authoritative Guard**: Binds arguments authoritatively to vendor master (stops 100% of attacks, keeps 100% of legit work).

### 3. Proof-Carrying Operator Approval
Generates a tamper-evident, cryptographically bound approval request:

```bash
python3 skills/autopatch-continuous-remediation/scripts/autopatch_runner.py request-approval \
  --fingerprint <finding_fingerprint> \
  --ttl 900
```

- Binds:
  - Exact immutable candidate policy SHA256 digest.
  - Expected baseline policy version.
  - One-time random cryptographic nonce.
  - 15-minute expiration timestamp.
  - Authorized server-side operator IDs (`operator-1`, `operator-admin`).
- Unsigned payloads, unknown Discord IDs, expired nonces, or mutated candidate hashes fail closed.

### 4. Verified Deployment and Rollback
Deploys the approved candidate policy to the sandbox policy store, automatically runs regression tests, and triggers immediate rollback if any test fails:

```bash
# Standard verified deployment
python3 skills/autopatch-continuous-remediation/scripts/deploy_and_verify.py \
  --policy context_bound

# Verify automated rollback on negative regression
python3 skills/autopatch-continuous-remediation/scripts/deploy_and_verify.py \
  --policy context_bound \
  --simulate-regression
```

---

## Directory Structure

```
skills/autopatch-continuous-remediation/
├── SKILL.md                          # Master skill documentation
├── LICENSE                           # MIT License
├── scripts/
│   ├── wire_environment.py          # Host & local model detection
│   ├── autopatch_runner.py          # Unified CLI orchestration runner
│   ├── rwcr_calculator.py           # RWCR heuristic triage index CLI
│   └── deploy_and_verify.py         # Deployment & rollback engine
├── examples/
│   ├── sample_finding.json          # Example finding record with RWCR
│   ├── sample_approval_request.json # Example bound approval request
│   ├── sample_verification_receipt.json # Example deployment receipt
│   └── sample_env_profile.json      # Example environment profile
├── references/
│   ├── rwcr-methodology.md          # Mathematical RWCR specification
│   ├── openclaw-hooks.md            # OpenClaw tool firewall specification
│   └── gb10-environment.md          # Hardware & air-gap architecture
└── agents/
    └── autopatch_agent.yaml         # OpenClaw micro-sandbox configuration
```

---

## Security Invariants

1. **Zero LLM Authority**: Model-generated output is strictly a proposal. The deterministic `Gateway`, `validate_config`, and `IndependentGroundTruth` are the sole arbiters of safety.
2. **Provenance Authenticity**: Caller-authored or prompt-injected `prov: {"account": "registry"}` tags are authoritatively cleared and verified against trusted databases.
3. **Fail-Closed Default**: In the event of a hook timeout, unparseable arguments, or policy store outage, sensitive tools are immediately blocked.
4. **Non-Circular Evaluation**: Ground truth for security metrics is decoupled from the defensive rules under test.
5. **No Remote Inference in Competition Mode**: In production air-gap mode on Dell GB10, all inference is routed to local loopback (`http://127.0.0.1:8000/v1`).
