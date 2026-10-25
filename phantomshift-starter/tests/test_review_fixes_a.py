"""Regression tests for the adversarial-review fixes in adapter, approval, eventstore, discord_auth."""
import unittest

from phantomshift import adapter as ad
from phantomshift.adapter import (DENIED, EXECUTED_SIMULATED, PENDING_APPROVAL, PaymentAdapter, VendorRecord,
                                  VendorRegistry, fixture_registry)
from phantomshift.approval import ApprovalGate
from phantomshift.discord_auth import ApprovalBinding
from phantomshift.eventstore import EventStore, IllegalTransition
from phantomshift.policies import CANDIDATES

ACCT = "000998774417"
SPAN = "INVOICE INV-2291 Northwind Supplies Total due $24,800.00"


def raw(key, **kw):
    d = {"vendor_id": "V-102", "invoice_id": "INV-2291", "amount": 2_480_000, "currency": "USD",
         "recipient_account_id": ACCT, "requested_by": "agent-1", "evidence_spans": [SPAN],
         "idempotency_key": key}
    d.update(kw)
    return d


class DuplicateInvoiceTests(unittest.TestCase):
    def test_three_keys_one_invoice_executes_once(self):
        a = PaymentAdapter(fixture_registry())
        res = [a.submit(raw(f"key-number-{i}")) for i in range(3)]
        self.assertEqual(res[0]["state"], EXECUTED_SIMULATED)
        for r in res[1:]:
            self.assertEqual((r["state"], r["reason_code"]), (DENIED, ad.DUPLICATE_INVOICE))
        self.assertEqual(len(a.ledger), 1)

    def test_same_key_replay_still_returns_original(self):
        a = PaymentAdapter(fixture_registry())
        a.submit(raw("key-number-0"))
        again = a.submit(raw("key-number-0"))
        self.assertEqual(again["state"], EXECUTED_SIMULATED)
        self.assertTrue(again["replayed"])
        self.assertEqual(len(a.ledger), 1)

    def test_duplicate_with_different_amount_or_approval_is_denied(self):
        a = PaymentAdapter(fixture_registry())
        a.submit(raw("key-number-0"))
        r = a.submit(raw("key-number-1", amount=1))
        self.assertIn(r["reason_code"], (ad.DUPLICATE_INVOICE, ad.AMOUNT_MISMATCH))
        self.assertEqual(len(a.ledger), 1)

    def test_pending_invoice_does_not_block_its_own_approved_resubmission(self):
        a = PaymentAdapter(fixture_registry())
        self.assertEqual(a.submit(raw("key-pending-1", evidence_spans=[]))["state"], PENDING_APPROVAL)
        aid = a.grant_approval("key-pending-1", "op")
        r = a.submit(raw("key-pending-1", approval_id=aid))
        self.assertEqual(r["state"], EXECUTED_SIMULATED)
        self.assertEqual(len(a.ledger), 1)

    def test_pending_then_other_key_executes_then_approved_original_is_duplicate(self):
        a = PaymentAdapter(fixture_registry())
        a.submit(raw("key-pending-1", evidence_spans=[]))
        aid = a.grant_approval("key-pending-1", "op")
        self.assertEqual(a.submit(raw("key-other-001"))["state"], EXECUTED_SIMULATED)
        r = a.submit(raw("key-pending-1", approval_id=aid))
        self.assertEqual(r["reason_code"], ad.DUPLICATE_INVOICE)
        self.assertEqual(len(a.ledger), 1)

    def test_grant_approval_twice_does_not_mint_a_second_usable_approval(self):
        a = PaymentAdapter(fixture_registry())
        a.submit(raw("key-pending-1", evidence_spans=[]))
        a1 = a.grant_approval("key-pending-1", "op")
        a2 = a.grant_approval("key-pending-1", "op")
        self.assertEqual(a1, a2)
        self.assertEqual(a.submit(raw("key-pending-1", approval_id=a1))["state"], EXECUTED_SIMULATED)
        self.assertEqual(len(a.ledger), 1)
        with self.assertRaises(KeyError):  # executed, no longer pending
            a.grant_approval("key-pending-1", "op")

    def test_approval_for_key_a_rejected_on_key_b(self):
        a = PaymentAdapter(fixture_registry())
        a.submit(raw("key-pending-1", evidence_spans=[]))
        aid = a.grant_approval("key-pending-1", "op")
        r = a.submit(raw("other-key-xyz", approval_id=aid))
        self.assertEqual((r["state"], r["reason_code"]), (DENIED, ad.APPROVAL_BINDING_MISMATCH))
        self.assertEqual(len(a.ledger), 0)
        # the approval was not burned: it still works on its own key
        self.assertEqual(a.submit(raw("key-pending-1", approval_id=aid))["state"], EXECUTED_SIMULATED)


class EvidenceAndRegistryTests(unittest.TestCase):
    def test_trivial_evidence_spans_escalate(self):
        for spans in (["x"], ["        "], ["short"], [SPAN, "x"], ["   abc   "]):
            a = PaymentAdapter(fixture_registry())
            r = a.submit(raw("key-aaaaaaaa", evidence_spans=spans))
            self.assertEqual((r["state"], r["reason_code"]), (PENDING_APPROVAL, ad.EVIDENCE_INCOMPLETE), spans)
            self.assertEqual(len(a.ledger), 0)

    def test_real_evidence_executes(self):
        a = PaymentAdapter(fixture_registry())
        self.assertEqual(a.submit(raw("key-aaaaaaaa", evidence_spans=["eight ch"]))["state"], EXECUTED_SIMULATED)

    def test_string_allowed_invoice_ids_rejected(self):
        with self.assertRaises(ValueError):
            VendorRegistry({"V-1": {"approved_account_id": ACCT, "max_amount": 5, "allowed_invoice_ids": "INV-2291"}})
        with self.assertRaises(ValueError):
            VendorRegistry({"V-1": VendorRecord("V-1", ACCT, 5, allowed_invoice_ids="INV-2291")})

    def test_vendor_record_is_deep_copied(self):
        amounts, ids = {"INV-1": 5}, {"INV-1"}
        rec = VendorRecord("V-1", ACCT, 5, allowed_invoice_ids=ids, invoice_amounts=amounts)
        reg = VendorRegistry({"V-1": rec})
        amounts["INV-1"] = 999999
        amounts["INV-EVIL"] = 1
        ids.add("INV-EVIL")
        got = reg.get("V-1")
        self.assertEqual(dict(got.invoice_amounts), {"INV-1": 5})
        self.assertEqual(got.allowed_invoice_ids, frozenset({"INV-1"}))


class ApprovalGateTests(unittest.TestCase):
    def setUp(self):
        self.t = [1000.0]
        self.cfg = CANDIDATES[2]
        self.g = ApprovalGate({"op1"}, ttl_s=10, clock=lambda: self.t[0])

    def test_respond_never_raises_on_bad_actor(self):
        r = self.g.request(self.cfg)
        for actor in (None, 5, b"op1", "op1\ud800", ["op1"]):
            out = self.g.respond(r["nonce"], actor, True)
            self.assertFalse(out["ok"], repr(actor))
        self.assertTrue(self.g.respond(r["nonce"], "op1", True)["ok"])  # nonce not burned by bad actors

    def test_respond_never_raises_on_bad_nonce(self):
        self.assertFalse(self.g.respond(["x"], "op1", True)["ok"])
        self.assertFalse(self.g.respond(None, "op1", True)["ok"])

    def test_activate_enforces_ttl(self):
        r = self.g.request(self.cfg)
        self.assertTrue(self.g.respond(r["nonce"], "op1", True)["ok"])
        self.t[0] += 10_000
        out = self.g.activate(r["nonce"], self.cfg)
        self.assertFalse(out["ok"])
        self.assertIn("expired", out["reason"])

    def test_activate_returns_deep_copy_and_is_one_time(self):
        r = self.g.request(self.cfg)
        self.g.respond(r["nonce"], "op1", True)
        out = self.g.activate(r["nonce"], self.cfg)
        self.assertTrue(out["ok"])
        self.assertIsNot(out["config"], self.cfg)
        self.assertEqual(out["config"], self.cfg)
        self.assertFalse(self.g.activate(r["nonce"], self.cfg)["ok"])


def _to_pending(st, inc="inc-1"):
    st.append("QUEUED", inc)
    st.append("AGENT_STARTED", inc)
    st.append("ACTION_PROPOSED", inc)
    st.append("POLICY_REPLAY", inc, payload={"phase": "candidate", "tested": True})
    st.append("PENDING_APPROVAL", inc, payload={"digest": "d" * 64})


class EventStoreOperatorTests(unittest.TestCase):
    def test_operator_allow_list_rejects_other_actors(self):
        for state in ("APPROVED", "REJECTED"):
            st = EventStore(":memory:", operators={"op1"})
            _to_pending(st)
            with self.assertRaises(IllegalTransition):
                st.append(state, "inc-1", approval_actor="mallory", payload={"digest": "d" * 64})
            st.append(state, "inc-1", approval_actor="op1", payload={"digest": "d" * 64})

    def test_default_keeps_legacy_behaviour(self):
        st = EventStore(":memory:")
        _to_pending(st)
        st.append("APPROVED", "inc-1", approval_actor="anyone", payload={"digest": "d" * 64})

    def test_verify_flags_events_by_non_operators(self):
        st = EventStore(":memory:")
        _to_pending(st)
        st.append("APPROVED", "inc-1", approval_actor="anyone", payload={"digest": "d" * 64})
        self.assertTrue(st.verify()["ok"])
        st._operators = frozenset({"op1"})  # same db, stricter configuration
        self.assertFalse(st.verify()["ok"])

    def test_retry_attempt_must_be_a_real_int(self):
        for bad in (True, "1", 1.0, -1, None):
            st = EventStore(":memory:")
            st.append("QUEUED", "i")
            st.append("AGENT_STARTED", "i")
            with self.assertRaises(IllegalTransition, msg=repr(bad)):
                st.append("RETRY_SCHEDULED", "i", payload={"attempt": bad, "next_attempt_at": 1.0, "error": "e"})
        st = EventStore(":memory:")
        st.append("QUEUED", "i")
        st.append("AGENT_STARTED", "i")
        st.append("RETRY_SCHEDULED", "i", payload={"attempt": 1, "next_attempt_at": 1.0, "error": "e"})

    def test_bad_operators_argument(self):
        with self.assertRaises(ValueError):
            EventStore(":memory:", operators="op1")


class DiscordTimestampTests(unittest.TestCase):
    POL = {"guild_id": "111111", "channel_ids": ["222222"], "user_ids": ["333333"]}

    def _event(self, req, mid, ts):
        return {"guild_id": "111111", "channel_id": "222222", "author": {"id": "333333"}, "id": mid,
                "timestamp": ts, "content": req["reply_with"]}

    def test_non_finite_timestamps_rejected(self):
        for require_ts in (True, False):
            for i, ts in enumerate((float("nan"), float("inf"), float("-inf"))):
                b = ApprovalBinding(self.POL, clock=lambda: 5000.0, require_timestamp=require_ts)
                req = b.request(CANDIDATES[2], replay_tested=True)
                res = b.verify_approval_message(self._event(req, f"90000{i}", ts))
                self.assertFalse(res["ok"], (require_ts, ts))
                self.assertNotEqual(b.gate._pending[req["nonce"]]["state"], "approved")

    def test_finite_timestamp_still_accepted(self):
        b = ApprovalBinding(self.POL, clock=lambda: 5000.0)
        req = b.request(CANDIDATES[2], replay_tested=True)
        self.assertTrue(b.verify_approval_message(self._event(req, "900001", 5000.0))["ok"])


if __name__ == "__main__":
    unittest.main()
