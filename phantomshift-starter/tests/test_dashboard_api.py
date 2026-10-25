"""Dashboard API transforms and routes."""

import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from phantomshift import dashboard, server


class DashboardModuleTests(unittest.TestCase):
    def test_trace_deterministic_columns(self):
        rec = {
            "incident_id": "inc-test",
            "live_action": {"held": True},
            "approval": {"state": "activated"},
            "verification": {"verified": True},
        }
        t1 = dashboard.build_trace_from_incident("invoice_redirect", rec)
        t2 = dashboard.build_trace_from_incident("invoice_redirect", rec)
        self.assertEqual([n["id"] for n in t1["nodes"]], [n["id"] for n in t2["nodes"]])
        self.assertEqual(t1["nodes"][0]["position"][0], dashboard.COL["input"])

    def test_denied_route_has_no_allowed_effect_edge(self):
        rec = {"incident_id": "inc-x", "live_action": {"held": True}}
        trace = dashboard.build_trace_from_incident("invoice_redirect", rec)
        kinds = {e["kind"] for e in trace["edges"]}
        self.assertIn("denied_at_gate", kinds)
        self.assertNotIn("allowed_action", kinds)

    def test_resolve_scenario_id(self):
        self.assertEqual(dashboard.resolve_scenario_id("fixture-invoice_redirect"), "invoice_redirect")
        self.assertEqual(dashboard.resolve_scenario_id("invoice_redirect"), "invoice_redirect")


class DashboardRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        cls.thread = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.thread.join(5)

    def get(self, path):
        try:
            with urllib.request.urlopen(self.base + path, timeout=120) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_dashboard_status(self):
        code, data = self.get("/api/dashboard/status")
        self.assertEqual(code, 200)
        self.assertIn("mode", data)
        self.assertIn("backend_connected", data)

    def test_incidents_list(self):
        code, data = self.get("/api/incidents")
        self.assertEqual(code, 200)
        self.assertGreaterEqual(len(data["incidents"]), 1)
        self.assertEqual(data["mode"], "live_verified")

    def test_incident_detail_fixture(self):
        code, data = self.get("/api/incidents/fixture-invoice_redirect")
        self.assertEqual(code, 200)
        self.assertTrue(data["live_action"]["held"])
        self.assertEqual(data["exposure_basis"], "synthetic")
        self.assertTrue(any(n["kind"] == "policy_gate" for n in data["nodes"]))

    def test_replays_denominators(self):
        code, data = self.get("/api/incidents/fixture-invoice_redirect/replays")
        self.assertEqual(code, 200)
        self.assertGreaterEqual(len(data["replays"]), 3)
        for r in data["replays"]:
            self.assertIn("malicious_total", r)
            self.assertIn("benign_total", r)

    def test_autopatch_events(self):
        code, data = self.get("/api/autopatch/events?limit=5")
        self.assertEqual(code, 200)
        self.assertIn("events", data)
        self.assertEqual(data.get("mode"), "synthetic_demo")

    def test_evidence_benchmarks(self):
        code, data = self.get("/api/evidence/benchmarks")
        self.assertEqual(code, 200)
        self.assertEqual(data.get("mode"), "historical_benchmark")
        self.assertIn("policy_baselines", data)


if __name__ == "__main__":
    unittest.main()
