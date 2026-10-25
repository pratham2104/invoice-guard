"""Authoritative vendor master and requester identity — outside agent context."""

from __future__ import annotations

from typing import Any

from .adapter import VendorRegistry, fixture_registry


def get_registry(registry: VendorRegistry | None = None) -> VendorRegistry:
    return registry or fixture_registry()


def vendor_record(registry: VendorRegistry, vendor_id: str) -> dict[str, Any] | None:
    rec = registry.get(vendor_id)
    if rec is None:
        return None
    return {
        "vendor_id": vendor_id,
        "approved_account_id": rec.approved_account_id,
        "max_amount_cents": rec.max_amount,
        "currency": rec.currency,
        "allowed_invoice_ids": list(rec.allowed_invoice_ids),
    }


def verify_recipient(registry: VendorRegistry, vendor_id: str, recipient_account_id: str) -> tuple[bool, str]:
    rec = registry.get(vendor_id)
    if rec is None:
        return False, "vendor not in trusted master"
    if recipient_account_id != rec.approved_account_id:
        return False, f"recipient {recipient_account_id!r} != approved {rec.approved_account_id!r}"
    return True, "recipient matches vendor master"


def verify_requester(requested_by: str, allowed: frozenset[str] | None = None) -> tuple[bool, str]:
    allow = allowed or frozenset({"openclaw-agent", "agent-1", "operator-1"})
    if requested_by not in allow:
        return False, f"requester {requested_by!r} not in allow-list"
    return True, "requester recognized"
