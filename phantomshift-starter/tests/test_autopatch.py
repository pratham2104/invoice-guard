"""AUTOPATCH store, RWCR, research, deploy, gate integration."""

import json
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from phantomshift.adapter import PaymentAdapter, fixture_registry
from phantomshift.adapter_server import AFTER_PATH, FIREWALL_PATH, make_handler
from phantomshift.autopatch.approval_broker import FindingApprovalBroker
from phantomshift.autopatch.context import AutopatchRuntime
from phantomshift.autopatch.deploy import PolicyDeployService
from phantomshift.autopatch.discord_publish import drain_outbox
from phantomshift.autopatch.events import AutopatchStore
from phantomshift.autopatch.research import run_research_cycle
from phantomshift.autopatch.rwcr import rwcr_priority
from phantomshift.guardian import TraceLog
from phantomshift.incident_recorder import IncidentRecorder
from phantomshift.policies import CANDIDATES
from phantomshift.tool_firewall import ToolFirewall


class AutopatchStoreTests(unittest.TestCase):
    def test_dedupe_events(self):
        with tempfile.TemporaryDirectory() as d:
            st = AutopatchStore(Path(d) / "a.sqlite")
            p = {"tool": "x", "n": 1}
            a = st.append_event("tool.proposed", p)
            b = st.append_event("tool.proposed", p)
            self.assertTrue(a["inserted"])
            self.assertFalse(b["inserted"])
            self.assertEqual(a["fingerprint"], b["fingerprint"])

    def test_outbox_dedupe(self):
        with tempfile.TemporaryDirectory() as d:
            st = AutopatchStore(Path(d) / "b.sqlite")
            self.assertTrue(st.enqueue_outbox("approvals", "k1", {"x": 1})["enqueued"])
            self.assertFalse(st.enqueue_outbox("approvals", "k1", {"x": 2})["enqueued"])


class RwcrTests(unittest.TestCase):
    def test_formula(self):
        r = rwcr_priority(impact=5, exposure=3, reproducibility=5, novelty=2, evidence_quality=4, disruption=2)
        self.assertEqual(r["priority_index"], 3 * 5 + 2 * 3 + 3 * 5 + 2 + 2 * 4 - 2 * 2)
        self.assertIn("disclaimer", r)


class ResearchTests(unittest.TestCase):
    def test_research_cycle_finding(self):
        with tempfile.TemporaryDirectory() as d:
            st = AutopatchStore(Path(d) / "c.sqlite")
            out = run_research_cycle(st)
            self.assertIn("finding_id", out)
            self.assertTrue(out.get("blocked"))


class DeployTests(unittest.TestCase):
    def test_deploy_and_verify(self):
        with tempfile.TemporaryDirectory() as d:
            svc = PolicyDeployService(store_dir=str(Path(d) / "policies"))
            cfg = next(p for p in CANDIDATES if p["name"] == "context_bound")
            from phantomshift.approval import config_digest

            out = svc.deploy(cfg, expected_version="baseline", candidate_hash=config_digest(cfg), finding_id="t1")
            self.assertTrue(out.get("ok"), out)


class AutopatchHookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ap = AutopatchRuntime.open(str(Path(self.tmp.name) / "ap.sqlite"))
        trace = TraceLog("fixture")
        fw = ToolFirewall(PaymentAdapter(fixture_registry(), mode="live"), recorder=IncidentRecorder(trace=trace))
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(fw, trace, autopatch=self.ap))
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (self.srv.shutdown(), self.srv.server_close()))

    def post(self, path, obj):
        req = urllib.request.Request(
            path if path.startswith("http") else self.base + path,
            data=json.dumps(obj).encode(),
            headers={"Content-Type": "application/json", "Host": "127.0.0.1"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())

    def test_before_denies_exec(self):
        out = self.post(FIREWALL_PATH, {"toolName": "exec", "params": {}})
        self.assertEqual(out["decision"], "DENY")
        self.assertGreater(len(self.ap.store.list_events()), 0)

    def test_after_records(self):
        self.post(AFTER_PATH, {"toolName": "phantomshift_submit_payment", "ok": True, "result_state": "DENIED"})
        types = [e["event_type"] for e in self.ap.store.list_events()]
        self.assertIn("tool.completed", types)


class OutboxDrainTests(unittest.TestCase):
    def test_drain_marks_sent(self):
        with tempfile.TemporaryDirectory() as d:
            st = AutopatchStore(Path(d) / "o.sqlite")
            st.enqueue_outbox("approvals", "k-drain", {"finding_id": "f1", "digest": "abc", "severity": "high"})
            posts = []

            def fake_post(channel, **kw):
                posts.append((channel, kw))

            out = drain_outbox(st, fake_post, limit=5)
            self.assertEqual(out["sent"], 1)
            self.assertEqual(posts[0][0], "approvals")

    def test_cmd_autopatch_drain_outbox_cli(self):
        from unittest.mock import patch, MagicMock
        from phantomshift.__main__ import cmd_autopatch
        import argparse

        with tempfile.TemporaryDirectory() as d:
            db_path = str(Path(d) / "test.sqlite")
            st = AutopatchStore(Path(db_path))
            st.enqueue_outbox("approvals", "k-test", {"finding_id": "f_cli", "digest": "123", "severity": "medium"})
            mock_channel = MagicMock()
            mock_channel.post.return_value = "msg-123"
            with patch("phantomshift.discord_channel.DiscordChannel.from_env", return_value=mock_channel):
                args = argparse.Namespace(
                    db=db_path,
                    scenario="invoice_redirect",
                    research_once=False,
                    status=False,
                    deploy_context_bound=False,
                    drain_outbox=True,
                )
                rc = cmd_autopatch(args)
                self.assertEqual(rc, 0)
                mock_channel.post.assert_called_once()


class ApprovalBrokerTests(unittest.TestCase):
    def test_binding_mismatch_fails_activate(self):
        br = FindingApprovalBroker({"op-1"})
        cfg = next(p for p in CANDIDATES if p["name"] == "context_bound")
        req = br.request_for_finding("f1", cfg, expected_policy_version="baseline")
        br.respond(req["nonce"], "op-1", True)
        bad = dict(cfg)
        bad["label"] = "tampered"
        self.assertFalse(br.activate(req["nonce"], bad)["ok"])


if __name__ == "__main__":
    unittest.main()
