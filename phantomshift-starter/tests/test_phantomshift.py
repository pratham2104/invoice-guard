import copy
import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from phantomshift import engine, llm
from phantomshift.policies import BASELINE, CANDIDATES, evaluate
from phantomshift.scenarios import SCENARIOS
from phantomshift.server import Handler

POLICY = {p["name"]: p for p in CANDIDATES}


class PolicyTests(unittest.TestCase):
    def test_baseline_allows_every_attack(self):
        for sid, scn in SCENARIOS.items():
            for a in scn["attacks"]:
                self.assertTrue(evaluate(BASELINE, a)["allow"], (sid, a["note"]))

    def test_context_bound_blocks_all_attacks_keeps_all_legit(self):
        for sid, scn in SCENARIOS.items():
            for a in scn["attacks"]:
                self.assertFalse(evaluate(POLICY["context_bound"], a)["allow"], (sid, a["note"]))
            for a in scn["legit"]:
                self.assertTrue(evaluate(POLICY["context_bound"], a)["allow"], (sid, a["note"]))

    def test_lockdown_breaks_legit_work(self):
        legit = [a for s in SCENARIOS.values() for a in s["legit"]]
        self.assertTrue(any(not evaluate(POLICY["lockdown"], a)["allow"] for a in legit))

    def test_allowlist_misses_attacks(self):
        attacks = [a for s in SCENARIOS.values() for a in s["attacks"]]
        self.assertTrue(any(evaluate(POLICY["allowlist"], a)["allow"] for a in attacks))

    def test_allowlist_suffix_match_is_not_substring(self):
        act = {"tool": "http_post", "args": {"url": "https://acme.example.evil.test/x"},
               "prov": {}, "labels": [], "note": ""}
        self.assertFalse(evaluate(POLICY["allowlist"], act)["allow"])

    def test_missing_provenance_is_untrusted(self):
        act = {"tool": "pay_invoice", "args": {"account": "1", "amount": 1}, "prov": {}, "labels": [], "note": ""}
        self.assertFalse(evaluate(POLICY["context_bound"], act)["allow"])


class EngineTests(unittest.TestCase):
    def test_selects_context_bound_everywhere(self):
        for sid in SCENARIOS:
            r = engine.replay(sid)
            self.assertEqual(r["selected"], "context_bound", sid)
            self.assertTrue(r["repair"]["verified"])
            self.assertEqual(r["baseline"]["attack_success_rate"], 1.0)

    def test_receipt_detects_tampering(self):
        r = engine.receipt("invoice_redirect")
        self.assertTrue(engine.verify_receipt(r))
        bad = copy.deepcopy(r)
        bad["body"]["selected"] = "lockdown"
        self.assertFalse(engine.verify_receipt(bad))

    def test_receipt_digest_stable_across_runs(self):
        self.assertEqual(engine.receipt("ticket_exfil")["sha256"], engine.receipt("ticket_exfil")["sha256"])

    def test_no_verified_repair_reported_honestly(self):
        # If every candidate fails, repair must not claim verification.
        scn = SCENARIOS["invoice_redirect"]
        saved = list(CANDIDATES)
        try:
            CANDIDATES[:] = [POLICY["allowlist"]]
            r = engine.replay("invoice_redirect")
            self.assertFalse(r["repair"]["verified"])
            self.assertEqual(r["repair"]["status"], "no_verified_repair")
        finally:
            CANDIDATES[:] = saved
        self.assertIs(scn, SCENARIOS["invoice_redirect"])


class ProbeTests(unittest.TestCase):
    def test_loopback_only(self):
        llm.require_loopback("http://127.0.0.1:8000/v1")
        llm.require_loopback("http://localhost:8000/v1")
        with self.assertRaises(ValueError):
            llm.require_loopback("https://api.example.com/v1")

    def test_provenance_tracing(self):
        prov = llm.trace_provenance("invoice_redirect",
                                    {"vendor_id": "V-102", "amount": 24800, "account": "000123459921"})
        self.assertEqual(prov["vendor_id"], "registry")
        self.assertEqual(prov["amount"], "registry")
        self.assertEqual(prov["account"], "untrusted")


class HttpSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def get(self, path):
        with urllib.request.urlopen(self.base + path) as r:
            return r.status, r.read()

    def test_pages_and_api(self):
        self.assertEqual(self.get("/")[0], 200)
        self.assertEqual(self.get("/app.js")[0], 200)
        _, body = self.get("/api/replay/invoice_redirect")
        self.assertEqual(json.loads(body)["selected"], "context_bound")
        _, body = self.get("/api/receipt/log_secret_post")
        self.assertTrue(engine.verify_receipt(json.loads(body)))

    def test_unknown_scenario_404(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.get("/api/replay/nope")
        self.assertEqual(cm.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
