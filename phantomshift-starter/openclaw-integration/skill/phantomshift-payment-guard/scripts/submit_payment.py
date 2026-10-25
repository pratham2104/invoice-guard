#!/usr/bin/env python3
"""Fallback client: read one JSON proposal on stdin, POST it to the PHANTOMSHIFT adapter, print the reply.

Stdlib only. The URL is a constant on purpose (the model must not choose it). Requires the egress preset
policy/phantomshift-adapter-preset.yaml to list this interpreter's path in `binaries`.
Fails closed: any problem prints a JSON object with state ERROR and exits 1. Never prints a payment state
it did not receive from the adapter.
"""
import json
import sys
import urllib.error
import urllib.request

ADAPTER_URL = "http://host.openshell.internal:7890/api/adapter/submit"  # keep in sync with the preset
TIMEOUT_S = 10
MAX_BYTES = 64 * 1024
ALLOWED = {
    "vendor_id", "invoice_id", "amount", "currency", "recipient_account_id",
    "evidence_spans", "idempotency_key",
}


def fail(code: str, reason: str) -> None:
    print(json.dumps({"state": "ERROR", "reason_code": code, "reason": reason}))
    sys.exit(1)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):  # refuse every redirect
        return None


def main() -> None:
    try:
        obj = json.loads(sys.stdin.read(MAX_BYTES + 1))
    except Exception:
        fail("BAD_INPUT", "stdin is not valid JSON")
    if not isinstance(obj, dict):
        fail("BAD_INPUT", "proposal must be a JSON object")
    body = {k: obj[k] for k in ALLOWED if k in obj}      # drop approval_id, requested_by, anything else
    body["requested_by"] = "openclaw-agent"
    req = urllib.request.Request(
        ADAPTER_URL, data=json.dumps(body).encode(), method="POST",
        headers={"content-type": "application/json", "accept": "application/json"})
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=TIMEOUT_S) as r:
            raw = r.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as e:
        raw = e.read(MAX_BYTES + 1)
    except Exception as e:  # noqa: BLE001
        fail("ADAPTER_UNREACHABLE", type(e).__name__)
    if len(raw) > MAX_BYTES:
        fail("RESPONSE_TOO_LARGE", "adapter reply too large")
    try:
        verdict = json.loads(raw)
    except Exception:
        fail("BAD_RESPONSE", "adapter reply is not JSON")
    if not isinstance(verdict, dict) or not isinstance(verdict.get("state"), str):
        fail("BAD_RESPONSE", "adapter reply has no state")
    print(json.dumps(verdict))


if __name__ == "__main__":
    main()
