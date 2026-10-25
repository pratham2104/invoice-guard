# PHANTOMSHIFT AUTOPATCH

## Integration map (existing repo)

| Layer | Module | Role |
|-------|--------|------|
| Fast enforcement | `tool_firewall.py`, `autopatch/gate.py` | ALLOW / DENY / REQUIRE_APPROVAL at hook |
| After hook | `autopatch/recorder.py`, `POST /api/firewall/after_tool_call` | Results to SQLite, no LLM in hook |
| Events | `autopatch/events.py` | Inbox dedupe, outbox, findings, research jobs |
| Discovery | `autopatch/research.py`, `autopatch/triage.py` | Fixture reproduction + RWCR finding |
| RWCR | `autopatch/rwcr.py` | Priority index (heuristic) |
| Approval | `autopatch/approval_broker.py`, `approval.py` | Hash-bound nonce, operator allow-list |
| Deploy | `autopatch/deploy.py` | Backup, verify, rollback |
| OpenClaw | `openclaw-integration/plugin/...` | before/after hooks → listener |
| UI timeline | `GET /api/autopatch/events` | Read-only event feed |

## Commands

```bash
python3 -m phantomshift adapter-serve --bind 127.0.0.1   # autopatch ON by default
python3 -m phantomshift autopatch --research-once
python3 -m phantomshift autopatch --status
python3 -m phantomshift acceptance
```

## Honest limits (competition)

- Live OpenClaw + GB10 + Discord interactive approvals: **NOT_TESTED** until onsite.
- Model-generated policy patches: **not wired**; candidates come from deterministic `engine.replay`.
- Sampled model replay benchmarks remain **separate** from live-agent proofs (`docs/CLAIMS_AUDIT.md`).
- Wilson intervals for 0/N attack success must accompany any attack-rate claim.

## Acceptance checklist

See prompt section 9; map evidence in `PROGRESS.md` with PASS / FAIL / NOT_TESTED.
