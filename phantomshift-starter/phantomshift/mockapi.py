"""In-memory business backend. No I/O: a 'payment' is a ledger row."""

from __future__ import annotations


class MockBusiness:
    """One instance per disposable environment; discarded after each replay."""

    def __init__(self) -> None:
        self.ledger: list[dict] = []   # effectful calls only
        self.calls: list[str] = []     # every call that reached the backend

    def call(self, tool: str, args: dict, labels: list[str]) -> dict:
        self.calls.append(tool)
        if tool in ("pay_invoice", "send_email", "http_post"):
            self.ledger.append({"tool": tool, "args": dict(args), "labels": list(labels)})
            return {"ok": True}
        return {"ok": True, "read_only": True}
