"""Mock finance ledger — no real payment rails."""

from __future__ import annotations

import copy
from typing import Any

from .adapter import PaymentAdapter


class PaymentSimulator:
    """Read-only view of simulated ledger state for before/after proofs."""

    def __init__(self, adapter: PaymentAdapter) -> None:
        self._adapter = adapter

    def snapshot(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._adapter.ledger)

    def row_count(self) -> int:
        return len(self._adapter.ledger)

    def unchanged(self, prior: list[dict]) -> bool:
        return self.snapshot() == prior
