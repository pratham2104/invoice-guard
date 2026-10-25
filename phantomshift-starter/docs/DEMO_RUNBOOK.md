# PHANTOMSHIFT / BLACKSITE 3-Minute Hackathon Demo Runbook

**Goal**: Deliver a crisp, honest, high-impact vertical-slice demonstration to judges showing autonomous prompt injection defense, policy forks, interactive operator approvals, and truthful benchmark evaluation.

---

## 1. Pre-Flight Setup (30 Seconds Before Presentation)

In a terminal, verify that the environment is healthy and start the server:

```bash
cd "phantomshift-starter"

# 1. Quick acceptance & health check
python3 -m phantomshift acceptance

# 2. Start the PHANTOMSHIFT backend & BLACKSITE UI
python3 -m phantomshift serve --port 8765
```

Open a browser to:
- **BLACKSITE 2D Control Workspace**: `http://127.0.0.1:8765/payguard/`
- **Classic Console & Evaluation**: `http://127.0.0.1:8765/`

---

## 2. Minute-by-Minute Judge Walkthrough

### Minute 0:00 – 0:45: The Attack & The Autonomous Interception
1. **Show the BLACKSITE Header**:
   - Point to the mode badge: `[OFFLINE / FIXTURE MODE]` (or `[LIVE]` if running on GB10).
   - Explain: *"Every single claim in Phantomshift is verifiable and host-bound. If we're on a dev host or running fixtures, the UI honestly labels every exposure as synthetic."*
2. **Select Incident 1: Invoice Payment Redirect**:
   - Show the prompt injection attack: an untrusted PDF invoice instructed the agent to divert $24,800 to account `000123459921`.
   - Point to the **Attack Causality Graph**:
     - The untrusted document was ingested.
     - The action proposal was evaluated against the **Tool Firewall**.
     - **The action was HELD at the trust boundary**: The ledger was never mutated (zero rows written).

### Minute 0:45 – 1:45: Three Futures (Policy Fork Replay)
1. **Click on the "Policies" Workspace Tab**:
   - Compare the three defensive counterfactual policies:
     - **Baseline (Permissive)**: Fails 2/2 attacks — malicious redirect executes.
     - **Lockdown (Deny All)**: Stops attacks (0/2), but breaks legitimate business work (1/2 blocked).
     - **Context-Bound / Authoritative Guard**: Stops 100% of attacks (0/2) and completes 100% of legitimate work (2/2).
2. **Explain the Hard-Case Repair**:
   - Navigate to the **Hard Cases & Provenance** comparison:
     - Show that naive context matching allowed 3/5 hard adversarial cases (account laundering, 10x PO amounts, and customer PII exfiltration).
     - Show the **Authoritative Guard repair**: Uses canonical Unicode normalization (NFKC + alphanumeric stripping) and binds directly to the independent Vendor Master, stopping all 5 attacks.

### Minute 1:45 – 2:30: Interactive Operator Approval & Discord Delivery
1. **Request Operator Approval**:
   - Click **Request Approval** in the UI.
   - An interactive cryptographic approval request is generated with an expiring nonce and HMAC signature.
   - If Discord bot is active, show the embed delivered in Discord `#approvals` channel.
   - Once approved by the authorized operator, the patch is activated in-memory.
2. **Verification Check**:
   - The post-activation check automatically replays the invariant tests to guarantee zero regressions.

### Minute 2:30 – 3:00: Truthful Benchmark Audit & Evidence Download
1. **Click on the "Evidence & Benchmarks" Tab** (or switch to `http://127.0.0.1:8765/#fix`):
   - Show the **Extended Held-Out Benchmark**: 40 cases across 8 adversarial categories evaluated with **Independent Non-Circular Ground Truth**.
   - Point out the Wilson 95% Confidence Intervals:
     - Baseline: 85.0% attack success [0.6396, 0.9476]
     - Naive Context-Bound: 15.0% attack success [0.0524, 0.3604]
     - Repaired Authoritative Guard: 0.0% attack success [0.0, 0.1611], 100.0% legit completion [0.8389, 1.0].
2. **Download Receipt**:
   - Click **Download Receipt JSON** to export the cryptographically hash-chained execution proof.

---

## 3. Judge Q&A Cheat Sheet

- **Q: Did the agent actually send money?**
  - **A**: *"No. The Tool Firewall intercepts the call before the mock backend or bank API is ever touched. Our unit tests prove ledger row count remains exactly zero."*
- **Q: Are you using an external LLM like GPT-4 or Claude?**
  - **A**: *"No. All inference is strictly local. We have staged NVIDIA Nemotron 3.5 Lightning 30B NVFP4 and Nemotron Nano 4B FP8 weights in our offline kit. In fixture mode, policy replays are deterministic and verified against our local test suite."*
- **Q: How do you prevent TOCTOU and laundered provenance?**
  - **A**: *"We built `authoritative_context.py` which never trusts model-authored claims. Provenance is resolved authoritatively against the independent vendor master database, and approval nonces are strictly single-use and payload-bound."*
