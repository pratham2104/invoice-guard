import os
import tempfile
import unittest
from pathlib import Path

os.environ["APG_DB"] = str(Path(tempfile.mkdtemp()) / "t.db")
os.environ["APG_FINGERPRINT_KEY"] = "test-key"

from apguard import cases, db, pipeline, rules, seed  # noqa: E402
from apguard.extractor import regex_extract  # noqa: E402
from apguard.parser import parse_eml  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.conn = db.connect(self.tmp / "t.db")
        self.inbox = self.tmp / "inbox"
        seed.seed(self.conn, self.inbox)
        self.addCleanup(self.conn.close)

    def run_one(self, name):
        return pipeline.process_eml(self.conn, self.inbox / name, use_llm=False)

    def rules_of(self, r):
        return {f.rule for f in r.verdict.findings}


class TestScenarios(Base):
    def test_normal_invoice_passes_clean(self):
        r = self.run_one("01_normal_invoice.eml")
        self.assertEqual(r.verdict.verdict, "PASS")
        self.assertEqual(r.verdict.findings, [])
        self.assertIsNone(r.case_id)

    def test_lookalike_domain_bank_change_held(self):
        r = self.run_one("02_lookalike_bank_change.eml")
        self.assertEqual(r.verdict.verdict, "HOLD")
        self.assertEqual(r.verdict.severity, "critical")
        self.assertTrue({"lookalike_domain", "bank_account_mismatch", "email_auth_failed",
                         "bank_change_with_risk_signals"} <= self.rules_of(r))
        self.assertEqual(r.verdict.vendor_name, "Acme Industrial Supply")

    def test_real_domain_new_contact_bank_change_held(self):
        r = self.run_one("03_real_domain_new_contact.eml")
        self.assertEqual(r.verdict.verdict, "HOLD")
        self.assertNotIn("lookalike_domain", self.rules_of(r))  # domain is genuine
        self.assertTrue({"new_contact", "bank_account_mismatch", "remit_address_changed",
                         "bank_change_with_risk_signals"} <= self.rules_of(r))

    def test_duplicate_invoice_held(self):
        r = self.run_one("04_duplicate_invoice.eml")
        self.assertEqual(r.verdict.verdict, "HOLD")
        self.assertIn("duplicate_invoice", self.rules_of(r))

    def test_over_po_held(self):
        r = self.run_one("05_over_po_amount.eml")
        self.assertEqual(r.verdict.verdict, "HOLD")
        self.assertIn("amount_over_po", self.rules_of(r))

    def test_prompt_injection_held_even_if_otherwise_clean(self):
        r = self.run_one("06_prompt_injection.eml")
        self.assertEqual(r.verdict.verdict, "HOLD")
        self.assertIn("prompt_injection", self.rules_of(r))
        # injection is the only serious signal: invoice itself matches PO
        self.assertNotIn("amount_over_po", self.rules_of(r))

    def test_reprocessing_is_idempotent(self):
        self.run_one("04_duplicate_invoice.eml")
        again = self.run_one("04_duplicate_invoice.eml")
        self.assertTrue(again.skipped)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) c FROM cases").fetchone()["c"], 1)

    def test_batch_totals(self):
        res = pipeline.process_dir(self.conn, self.inbox, use_llm=False)
        self.assertEqual(sum(1 for r in res if r.case_id), 5)
        self.assertEqual(sum(1 for r in res if r.verdict.verdict == "PASS"), 1)


class TestRules(Base):
    def test_lookalike_helpers(self):
        official = ["acmeindustrial.example"]
        self.assertIsNone(rules.lookalike("acmeindustrial.example", official))
        self.assertIsNone(rules.lookalike("mail.acmeindustrial.example", official))
        self.assertTrue(rules.lookalike("acmeindustrlal.example", official))
        self.assertTrue(rules.lookalike("acmeindustrial-pay.com", official))
        self.assertTrue(rules.lookalike("acmeindustrial.co", official))
        self.assertIsNone(rules.lookalike("randomvendor.org", official))

    def test_bank_fingerprint_not_raw(self):
        fps = [r["fingerprint"] for r in self.conn.execute("SELECT fingerprint FROM vendor_bank_accounts")]
        self.assertTrue(all("000123456789" not in fp for fp in fps))
        self.assertEqual(db.fingerprint("0001 2345-6789"), db.fingerprint("000123456789"))

    def test_unknown_sender_fails_closed(self):
        self.run_one("01_normal_invoice.eml")
        email = parse_eml(self.inbox / "01_normal_invoice.eml")
        email.sender_domain, email.sender_email = "nobody.example", "x@nobody.example"
        email.sender_name, email.subject, email.body = "X", "hi", "hello there"
        v = rules.evaluate(self.conn, email, regex_extract(email))
        self.assertEqual(v.verdict, "HOLD")
        self.assertIn("vendor_unknown", {f.rule for f in v.findings})

    def test_extraction_redacts_account(self):
        email = parse_eml(self.inbox / "02_lookalike_bank_change.eml")
        ex = regex_extract(email)
        self.assertEqual(ex.bank_account, "000999888777")
        self.assertTrue(ex.redacted()["bank_account"].endswith("8777"))
        self.assertNotIn("000999", ex.redacted()["bank_account"])
        # never persisted in the messages table
        pipeline.process_eml(self.conn, self.inbox / "02_lookalike_bank_change.eml", use_llm=False)
        blob = self.conn.execute("SELECT extraction_json||findings_json b FROM messages").fetchone()["b"]
        self.assertNotIn("000999888777", blob)

    def test_llm_failure_degrades_to_regex(self):
        from apguard import config, extractor
        config.LLM_BASE_URL = "http://127.0.0.1:9/v1"  # nothing listening
        config.LLM_TIMEOUT = 1
        try:
            ex = extractor.extract(parse_eml(self.inbox / "04_duplicate_invoice.eml"), use_llm=True)
        finally:
            config.LLM_BASE_URL = ""
        self.assertEqual(ex.invoice_number, "INV-7714")
        self.assertTrue(ex.llm_error)


class TestCaseControls(Base):
    def setUp(self):
        super().setUp()
        self.cid = self.run_one("03_real_domain_new_contact.eml").case_id

    def test_cannot_approve_without_verification(self):
        with self.assertRaises(cases.ControlError):
            cases.approve(self.conn, self.cid, "bob")

    def test_clerk_cannot_approve(self):
        cases.start_verification(self.conn, self.cid, "alice")
        cases.record_confirmation(self.conn, self.cid, "alice", True)
        with self.assertRaises(cases.ControlError):
            cases.approve(self.conn, self.cid, "alice")

    def test_segregation_of_duties(self):
        cases.start_verification(self.conn, self.cid, "bob")
        cases.record_confirmation(self.conn, self.cid, "bob", True)
        with self.assertRaises(cases.ControlError):
            cases.approve(self.conn, self.cid, "bob")  # same manager who verified

    def test_full_happy_path(self):
        cases.start_verification(self.conn, self.cid, "alice")
        cases.record_confirmation(self.conn, self.cid, "alice", True, "called Dana, confirmed")
        cases.approve(self.conn, self.cid, "bob")
        self.assertEqual(cases.get_case(self.conn, self.cid)["state"], "APPROVED")
        ok, bad = cases.verify_audit_chain(self.conn)
        self.assertTrue(ok)

    def test_vendor_denial_rejects(self):
        cases.start_verification(self.conn, self.cid, "alice")
        cases.record_confirmation(self.conn, self.cid, "alice", False, "vendor says not them")
        self.assertEqual(cases.get_case(self.conn, self.cid)["state"], "REJECTED")
        with self.assertRaises(cases.ControlError):
            cases.approve(self.conn, self.cid, "bob")

    def test_callback_uses_vendor_master_not_email(self):
        d = cases.draft_callback(self.conn, self.cid)
        self.assertEqual(d["contact"], "Dana Whitfield")
        self.assertNotEqual(d["contact"], "Jordan Miller")
        self.assertEqual(d["phone"], "+1-937-555-0114")
        self.assertNotIn("email_body", d)  # bank changes are never confirmed by email

    def test_audit_tamper_detected(self):
        cases.start_verification(self.conn, self.cid, "alice")
        self.assertTrue(cases.verify_audit_chain(self.conn)[0])
        self.conn.execute("UPDATE case_events SET actor='mallory' WHERE action='verification_started'")
        self.assertFalse(cases.verify_audit_chain(self.conn)[0])


class TestAgentInterface(unittest.TestCase):
    """The CLI surface OpenClaw drives."""

    def setUp(self):
        from apguard import config
        self.config = config
        tmp = Path(tempfile.mkdtemp())
        self._saved = (config.DB_PATH, config.INBOX_DIR, config.AGENT_MODE)
        config.DB_PATH, config.INBOX_DIR = tmp / "a.db", tmp / "inbox"
        self.addCleanup(self._restore)

    def _restore(self):
        self.config.DB_PATH, self.config.INBOX_DIR, self.config.AGENT_MODE = self._saved

    def cli(self, *argv):
        import contextlib, io
        from apguard.__main__ import main
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_process_json(self):
        import json
        self.cli("seed")
        code, out, _ = self.cli("process", "--json")
        data = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual([d["verdict"] for d in data].count("HOLD"), 5)
        self.assertIn("lookalike_domain", {f["rule"] for f in data[1]["findings"]})

    def test_agent_mode_blocks_human_actions(self):
        self.cli("seed")
        self.cli("process")
        self.config.AGENT_MODE = True
        for argv in (["approve", "CASE-0001", "--user", "bob"], ["seed"],
                     ["confirm", "CASE-0001", "--user", "alice"], ["reject", "CASE-0001", "--user", "bob"]):
            code, _, err = self.cli(*argv)
            self.assertEqual(code, 2, argv)
            self.assertIn("human-only", err)
        code, out, _ = self.cli("cases", "--json")
        self.assertEqual(code, 0)
        self.assertIn("CASE-0001", out)


if __name__ == "__main__":
    unittest.main()
