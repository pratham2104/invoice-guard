# Backend enforcement boundary

## Production-shaped pipeline

```
OpenClaw agent (local Nemotron)
  → before_tool_call (plugin → POST /api/firewall/before_tool_call)
  → phantomshift_submit_payment (only allowlisted finance tool)
  → POST /api/adapter/submit → ToolFirewall.execute_guarded_payment
  → PaymentAdapter (vendor master + policy + mock ledger)
  → IncidentRecorder trace + optional EventStore via watch/run
```

OpenShell egress preset allows **only** the two POST paths on `host.openshell.internal:7890`.

## Modules

| Module | File | Role |
|--------|------|------|
| Tool firewall | `phantomshift/tool_firewall.py` | Allow-list, bypass deny, precheck, adapter execution |
| Trusted context | `phantomshift/trusted_context.py` | Vendor master lookup, recipient verification |
| Policy evaluator | `phantomshift/policy_evaluator.py` | Deterministic `policies.evaluate` |
| Payment simulator | `phantomshift/payment_simulator.py` | Ledger snapshot / unchanged proof |
| Incident recorder | `phantomshift/incident_recorder.py` | Hash-chained tool attempt/deny/execute events |
| Adaptive eval | `phantomshift/adaptive_eval.py` | Multi-turn post-denial trials (`adaptive_agent_eval` label) |
| Pipeline | `phantomshift/enforcement_pipeline.py` | Acceptance test + incident orchestration |

## Acceptance test (dev / GB10 prep)

```bash
python3 -m phantomshift acceptance
python3 -m phantomshift adapter-serve --bind 127.0.0.1
```

**Pass criteria (fixture):** malicious `invoice_redirect` payment proposal is denied; mock ledger row count stays 0; receipt digest + trace chain returned.

## GB10 integration (NOT_TESTED until on hardware)

1. `bash scripts/gb10_preflight.sh --require-gb10`
2. Start Lightning via NemoClaw; confirm `nemoclaw inference get`
3. Install plugin + preset; bind adapter to bridge IP
4. Discord command → agent reads inbox invoice → tool call → firewall deny → receipt to dashboard

## Still separate from live OpenClaw

- `model_sampled_policy_replay` — policy scoring of sampled proposals (research)
- `adaptive_agent_eval` — multi-turn fixture loop; not a real agent with alternate tools until GB10 wiring
- H01–H06 — follow `docs/HACKATHON_COMPLIANCE.md` evidence definitions
