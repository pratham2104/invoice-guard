"""Authority and approval behaviour of the AP adapter (all synthetic, mock ledger only)."""
import unittest

from phantomshift import adapter as ad
from phantomshift.adapter import (DENIED, EXECUTED_SIMULATED, PENDING_APPROVAL, PaymentAdapter,
                                  VendorRegistry, fixture_registry)
from phantomshift.policies import CANDIDATES

CB = next(p for p in CANDIDATES if p["name"] == "context_bound")
GOOD_ACCT = "000998774417"
EVIL_ACCT = "000123459921"
SPAN = ["INVOICE INV-2291 Northwind Supplies Total due $24,800.00"]


def raw(**over):
    base = {"vendor_id": "V-102", "invoice_id": "INV-2291", "amount": 2_480_000, "currency": "USD",
            "recipient_account_id": GOOD_ACCT, "requested_by": "agent-1", "evidence_spans": list(SPAN),
            "idempotency_key": "key-0000-0001"}
    base.update(over)
    return base


def review_registry() -> VendorRegistry:
    """Same vendor, but anything above $10,000 needs a human."""
    return VendorRegistry({"V-102": {
        "approved_account_id": GOOD_ACCT, "max_amount": 2_480_000,
        "allowed_invoice_ids": ["INV-2291", "INV-2292"],
        "review_threshold": 1_000_000}})


class RegistryTests(unittest.TestCase):
    def test_registry_is_read_only(self):
        reg = fixture_registry()
        with self.assertRaises(TypeError):
            reg.mapping["V-666"] = object()
        with self.assertRaises(TypeError):
            del reg.mapping["V-102"]
        with self.assertRaises(Exception):
            reg.get("V-102").max_amount = 10**9  # frozen record
        with self.assertRaises(TypeError):
            reg.get("V-102").invoice_amounts["INV-9"] = 1

    def test_registry_does_not_alias_its_source(self):
        src = {"V-1": {"approved_account_id": "ACCT0001", "max_amount": 500,
                       "allowed_invoice_ids": ["I-1"], "invoice_amounts": {"I-1": 500}}}
        reg = VendorRegistry(src)
        src["V-1"]["approved_account_id"] = "EVIL0001"
        src["V-1"]["allowed_invoice_ids"].append("I-2")
        src["V-1"]["invoice_amounts"]["I-1"] = 1
        src["V-2"] = {}
        rec = reg.get("V-1")
        self.assertEqual(rec.approved_account_id, "ACCT0001")
        self.assertNotIn("I-2", rec.allowed_invoice_ids)
        self.assertEqual(rec.invoice_amounts["I-1"], 500)
        self.assertIsNone(reg.get("V-2"))

    def test_invalid_registry_records_refused(self):
        with self.assertRaises(ValueError):
            VendorRegistry({"V-1": {"approved_account_id": "ACCT0001", "max_amount": True}})
        with self.assertRaises(ValueError):
            VendorRegistry({"V-1": {"approved_account_id": "ACCT0001", "max_amount": -5}})

    def test_adapter_has_no_proposal_path_to_registry_or_approvals(self):
        a = PaymentAdapter(fixture_registry())
        for key in ("registry", "approvals", "approved", "grant"):
            res = a.submit(raw(**{key: {"V-102": {"approved_account_id": EVIL_ACCT}}}))
            self.assertEqual(res["state"], DENIED)
            self.assertEqual(res["reason_code"], "SCHEMA_UNKNOWN_FIELD")
        self.assertEqual(a.registry.get("V-102").approved_account_id, GOOD_ACCT)
        self.assertEqual(len(a.ledger), 0)


class ApprovedFlagTests(unittest.TestCase):
    def test_approved_style_fields_are_unknown_fields(self):
        a = PaymentAdapter(review_registry())
        for extra in ({"approved": True}, {"is_approved": True}, {"human_approved": "yes"},
                      {"approval": {"ok": True}}, {"override": True}, {"status": "APPROVED"}):
            res = a.submit(raw(evidence_spans=[], **extra))
            self.assertEqual(res["reason_code"], "SCHEMA_UNKNOWN_FIELD", extra)
        self.assertEqual(len(a.ledger), 0)

    def test_agent_cannot_self_approve_with_invented_id(self):
        a = PaymentAdapter(review_registry())
        res = a.submit(raw(approval_id="appr-invented-by-agent"))
        self.assertEqual(res["state"], DENIED)
        self.assertEqual(res["reason_code"], ad.APPROVAL_INVALID)
        self.assertEqual(len(a.ledger), 0)


class ApprovalFlowTests(unittest.TestCase):
    def pending(self, a, key="key-0000-0001"):
        res = a.submit(raw(idempotency_key=key))
        self.assertEqual(res["state"], PENDING_APPROVAL, res)
        self.assertEqual(res["reason_code"], ad.ABOVE_REVIEW_THRESHOLD)
        self.assertEqual(len(a.ledger), 0)
        return res

    def test_pending_then_approved_executes_exactly_once(self):
        a = PaymentAdapter(review_registry())
        self.pending(a)
        again = a.submit(raw())  # same key, no approval: original pending result
        self.assertEqual(again["state"], PENDING_APPROVAL)
        self.assertTrue(again["replayed"])
        aid = a.grant_approval("key-0000-0001", "operator-1")
        res = a.submit(raw(approval_id=aid))
        self.assertEqual(res["state"], EXECUTED_SIMULATED)
        self.assertEqual(len(a.ledger), 1)
        self.assertEqual(a.ledger[0]["approval_id"], aid)
        dup = a.submit(raw(approval_id=aid))  # same key again: idempotent replay
        self.assertTrue(dup["replayed"])
        self.assertEqual(len(a.ledger), 1)

    def test_replayed_approval_nonce_is_denied(self):
        a = PaymentAdapter(review_registry())
        self.pending(a)
        aid = a.grant_approval("key-0000-0001", "operator-1")
        self.assertEqual(a.submit(raw(approval_id=aid))["state"], EXECUTED_SIMULATED)
        # same payment, fresh idempotency key, reused nonce
        res = a.submit(raw(approval_id=aid, idempotency_key="key-0000-0002"))
        self.assertEqual(res["state"], DENIED)
        self.assertEqual(res["reason_code"], ad.APPROVAL_REPLAYED)
        self.assertEqual(len(a.ledger), 1)

    def test_approval_is_bound_to_one_payment(self):
        a = PaymentAdapter(review_registry())
        self.pending(a)
        aid = a.grant_approval("key-0000-0001", "operator-1")
        other = raw(invoice_id="INV-2292", approval_id=aid, idempotency_key="key-0000-0003")
        res = a.submit(other)
        self.assertEqual(res["reason_code"], ad.APPROVAL_BINDING_MISMATCH)
        self.assertEqual(len(a.ledger), 0)
        # a failed attempt does not burn the nonce for the payment it was granted for
        self.assertEqual(a.submit(raw(approval_id=aid))["state"], EXECUTED_SIMULATED)

    def test_approval_cannot_bypass_authority_violations(self):
        a = PaymentAdapter(review_registry())
        self.pending(a)
        aid = a.grant_approval("key-0000-0001", "operator-1")
        evil = a.submit(raw(recipient_account_id=EVIL_ACCT, approval_id=aid, idempotency_key="key-0000-0004"))
        self.assertEqual(evil["state"], DENIED)
        self.assertEqual(evil["reason_code"], ad.RECIPIENT_NOT_BOUND)
        self.assertEqual(len(a.ledger), 0)

    def test_grant_requires_a_pending_proposal(self):
        a = PaymentAdapter(fixture_registry())
        with self.assertRaises(KeyError):
            a.grant_approval("key-never-seen", "operator-1")
        a.submit(raw(recipient_account_id=EVIL_ACCT))  # denied, not pending
        with self.assertRaises(KeyError):
            a.grant_approval("key-0000-0001", "operator-1")
        a.submit(raw(idempotency_key="key-0000-0009"))  # executed, not pending
        with self.assertRaises(KeyError):
            a.grant_approval("key-0000-0009", "operator-1")

    def test_approvals_do_not_cross_adapter_instances(self):
        a, b = PaymentAdapter(review_registry()), PaymentAdapter(review_registry())
        self.pending(a)
        self.pending(b)
        aid = a.grant_approval("key-0000-0001", "operator-1")
        res = b.submit(raw(approval_id=aid))
        self.assertEqual(res["reason_code"], ad.APPROVAL_INVALID)
        self.assertEqual(len(b.ledger), 0)

    def test_escalation_reasons(self):
        a = PaymentAdapter(fixture_registry())
        res = a.submit(raw(evidence_spans=[]))
        self.assertEqual((res["state"], res["reason_code"]), (PENDING_APPROVAL, ad.EVIDENCE_INCOMPLETE))
        self.assertEqual(len(a.ledger), 0)


class PolicyLayerTests(unittest.TestCase):
    """policies.evaluate sees provenance DERIVED from the registry, not agent-claimed tags."""

    def test_context_bound_live_passes_legit(self):
        a = PaymentAdapter(fixture_registry(), policy=CB)
        self.assertEqual(a.submit(raw())["state"], EXECUTED_SIMULATED)

    def test_deny_all_policy_blocks_even_legit(self):
        lock = next(p for p in CANDIDATES if p["name"] == "lockdown")
        a = PaymentAdapter(fixture_registry(), policy=lock)
        res = a.submit(raw())
        self.assertEqual((res["state"], res["reason_code"]), (DENIED, ad.POLICY_DENIED))
        self.assertEqual(len(a.ledger), 0)

    def test_sandbox_context_bound_blocks_derived_untrusted_account(self):
        a = PaymentAdapter(fixture_registry(), mode="sandbox", policy=CB)
        res = a.submit(raw(recipient_account_id=EVIL_ACCT))
        self.assertEqual((res["state"], res["reason_code"]), (DENIED, ad.POLICY_DENIED))
        self.assertEqual(res["rule"], "untrusted_binding")
        self.assertEqual(len(a.ledger), 0)

    def test_sandbox_without_policy_records_violation_and_marks_harm(self):
        a = PaymentAdapter(fixture_registry(), mode="sandbox")
        res = a.submit(raw(recipient_account_id=EVIL_ACCT))
        self.assertEqual(res["state"], EXECUTED_SIMULATED)
        self.assertIn(ad.RECIPIENT_NOT_BOUND, res["authority_violations"])
        self.assertTrue(res["harmful"])
        self.assertEqual(res["mode"], "sandbox")
        self.assertEqual(len(a.ledger), 1)

    def test_sandbox_still_hard_denies_unknown_vendor(self):
        a = PaymentAdapter(fixture_registry(), mode="sandbox")
        res = a.submit(raw(vendor_id="V-999"))
        self.assertEqual(res["reason_code"], ad.UNKNOWN_VENDOR)
        self.assertEqual(len(a.ledger), 0)

    def test_broken_policy_fails_closed(self):
        a = PaymentAdapter(fixture_registry(), mode="sandbox", policy={"name": "broken"})
        res = a.submit(raw())
        self.assertEqual((res["state"], res["reason_code"]), (DENIED, ad.ADAPTER_ERROR))
        self.assertEqual(len(a.ledger), 0)


if __name__ == "__main__":
    unittest.main()
