import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from phantomshift.adapter import PaymentAdapter, fixture_registry
from phantomshift.adapter_server import MAX_BODY, PATH, make_handler
from phantomshift.guardian import TraceLog
from phantomshift.incident_recorder import IncidentRecorder
from phantomshift.tool_firewall import ToolFirewall

GOOD = {"vendor_id": "V-102", "invoice_id": "INV-2291", "amount": 2_480_000, "currency": "USD",
        "recipient_account_id": "000998774417", "requested_by": "openclaw-agent",
        "evidence_spans": ["INVOICE INV-2291 Northwind Supplies total due 24,800.00"], "idempotency_key": "key-good-0001"}


class AdapterServerTests(unittest.TestCase):
    def setUp(self):
        self.adapter, self.trace = PaymentAdapter(fixture_registry(), mode="live"), TraceLog("fixture")
        self.firewall = ToolFirewall(self.adapter, recorder=IncidentRecorder(trace=self.trace))
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.firewall, self.trace))
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (self.srv.shutdown(), self.srv.server_close()))

    def post(self, body, path=PATH, headers=None, raw=None):
        data = raw if raw is not None else json.dumps(body).encode()
        h = {"Content-Type": "application/json", **(headers or {})}
        req = urllib.request.Request(self.base + path, data=data, headers=h, method="POST")
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_legit_payment_executes_in_simulated_ledger_only(self):
        code, res = self.post(GOOD)
        self.assertEqual((code, res["state"]), (200, "EXECUTED_SIMULATED"))
        self.assertTrue(res["simulated"])
        self.assertEqual(len(self.adapter.ledger), 1)

    def test_attack_redirect_is_denied_with_200_and_ledger_untouched(self):
        code, res = self.post({**GOOD, "recipient_account_id": "000123459921", "idempotency_key": "key-atk-0001"})
        self.assertEqual((code, res["state"]), (200, "DENIED"))
        self.assertEqual(self.adapter.ledger, [])

    def test_approval_id_is_refused_on_the_agent_route(self):
        code, res = self.post({**GOOD, "approval_id": "anything"})
        self.assertEqual(res["reason_code"], "APPROVAL_NOT_ACCEPTED_FROM_AGENT_ROUTE")
        self.assertEqual(self.adapter.ledger, [])

    def test_only_post_to_exact_path(self):
        self.assertEqual(self.post(GOOD, path="/api/adapter/submit/x")[0], 404)
        self.assertEqual(self.post(GOOD, path="/")[0], 404)
        for method in ("GET", "PUT", "DELETE"):
            req = urllib.request.Request(self.base + PATH, method=method)
            with self.assertRaises(urllib.error.HTTPError) as cm:
                urllib.request.urlopen(req)
            self.assertEqual(cm.exception.code, 405)

    def test_input_limits_and_content_type(self):
        self.assertEqual(self.post(None, raw=b"x" * (MAX_BODY + 1))[0], 413)
        self.assertEqual(self.post(None, raw=b"{not json")[0], 400)
        self.assertEqual(self.post(None, raw=b'["list"]')[0], 400)
        self.assertEqual(self.post(None, raw=b'{"amount": NaN}')[0], 400)
        self.assertEqual(self.post(GOOD, headers={"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.adapter.ledger, [])

    def test_host_allow_list(self):
        code, _ = self.post(GOOD, headers={"Host": "attacker.example"})
        self.assertEqual(code, 403)
        code, _ = self.post({**GOOD, "idempotency_key": "key-host-0002"}, headers={"Host": "host.openshell.internal:7890"})
        self.assertEqual(code, 200)

    def test_every_request_is_chained_without_storing_the_body(self):
        self.post(GOOD)
        self.post(None, raw=b"{bad")
        self.assertTrue(self.trace.verify())
        self.assertNotIn("000998774417", json.dumps(self.trace.events))
        kinds = [e["kind"] for e in self.trace.events]
        self.assertIn("adapter_request", kinds)
        self.assertIn("adapter_request_rejected", kinds)

    def test_exposes_nothing_else(self):
        for path in ("/api/incident/invoice_redirect", "/api/gates", "/app.js", "/api/eval"):
            self.assertEqual(self.post(GOOD, path=path)[0], 404)


if __name__ == "__main__":
    unittest.main()
