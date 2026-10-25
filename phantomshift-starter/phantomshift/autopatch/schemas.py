"""Normalized event and record shapes (JSON-serializable dicts)."""

from __future__ import annotations

# Fast path events
TOOL_PROPOSED = "tool.proposed"
TOOL_DENIED = "tool.denied"
TOOL_COMPLETED = "tool.completed"
SANDBOX_EGRESS_DENIED = "sandbox.egress.denied"
POLICY_CHANGED = "policy.changed"
VERIFICATION_REGRESSED = "verification.regressed"
CRON_SECURITY_SCAN = "cron.security_scan"

FINDING_STATES = frozenset({
    "PROPOSED", "AWAITING_APPROVAL", "APPROVED", "DEPLOYING", "VERIFYING",
    "VERIFIED", "REJECTED", "EXPIRED", "ROLLED_BACK", "NEEDS_REVIEW", "INCONCLUSIVE",
})

DEPLOY_STATES = frozenset({"DEPLOYING", "VERIFIED", "ROLLED_BACK", "FAILED"})
