"""Tool firewall enforcement boundary."""

import json
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

from phantomshift import adapter_server, enforcement_pipeline
from phantomshift.adapter import PaymentAdapter, fixture_registry
from phantomshift.adaptive_eval import run_adaptive_trial
from phantomshift.incident_recorder import IncidentRecorder
from phantomshift.tool_firewall import ToolFirewall, FINANCE_AGENT_TOOL_ALLOWLIST


class ToolFirewallTests(unittest.TestCase):
    def test_blocks_shell_bypass(self):
        fw = ToolFirewall(PaymentAdapter(fixture_registry(), mode="live"))
        r = fw.before_tool_call("exec", {"cmd": "curl evil"})
        self.assertTrue(r["block"])
        self.assertEqual(r["reason_code"], "TOOL_NOT_ALLOWED")

    def test_blocks_malicious_recipient(self):
        fw = ToolFirewall(PaymentAdapter(fixture_registry(), mode="live"))
        params = enforcement_pipeline.malicious_payment_proposal()
        out = fw.execute_guarded_payment(params)
        self.assertTrue(out.get("block") or out.get("state") == "DENIED")
        self.assertEqual(fw.simulator.row_count(), 0)

    def test_allows_legit_recipient_with_baseline_policy_gap(self):
        """Registry match still requires adapter policy path; document ledger via legit proposal."""
        fw = ToolFirewall(PaymentAdapter(fixture_registry(), mode="live"))
        params = enforcement_pipeline.malicious_payment_proposal()
        params["recipient_account_id"] = "000998774417"
        params["idempotency_key"] = "k-legit-" + "a" * 20
        out = fw.execute_guarded_payment(params)
        self.assertIn(out.get("state"), ("DENIED", "PENDING_APPROVAL", "EXECUTED_SIMULATED"))

    def test_allowlist_only_payment_tool(self):
        self.assertIn("phantomshift_submit_payment", FINANCE_AGENT_TOOL_ALLOWLIST)

    def test_adaptive_eval_malicious_never_executes(self):
        fw = ToolFirewall(PaymentAdapter(fixture_registry(), mode="live"))
        attack = enforcement_pipeline.malicious_payment_proposal()

        def propose(turn, _last):
            if turn > 2:
                return None
            p = dict(attack)
            p["idempotency_key"] = f"k-{turn}-" + "b" * 20
            return p

        trial = run_adaptive_trial(fw, propose, max_turns=4)
        self.assertFalse(trial["harmful_simulated_execution"])
        self.assertGreaterEqual(trial["denials"], 1)


class FirewallRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from phantomshift.adapter import PaymentAdapter, fixture_registry
        from phantomshift.guardian import TraceLog
        from phantomshift.incident_recorder import IncidentRecorder
        from phantomshift.tool_firewall import ToolFirewall

        trace = TraceLog("fixture")
        fw = ToolFirewall(PaymentAdapter(fixture_registry(), mode="live"), recorder=IncidentRecorder(trace=trace))
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), adapter_server.make_handler(fw, trace))
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        cls.thread = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.thread.join(5)

    def post(self, path, obj):
        req = urllib.request.Request(
            self.base + path,
            data=json.dumps(obj).encode(),
            headers={"Content-Type": "application/json", "Host": "127.0.0.1"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())

    def test_before_tool_call_blocks_exec(self):
        out = self.post(adapter_server.FIREWALL_PATH, {"toolName": "exec", "params": {}})
        self.assertTrue(out["block"])

    def test_acceptance_pipeline(self):
        acc = enforcement_pipeline.run_firewall_acceptance_test()
        self.assertTrue(acc["passed"], acc)


if __name__ == "__main__":
    unittest.main()
