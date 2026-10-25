"""Unit tests for SlackChannel and slack_views (mock HTTP double)."""

from __future__ import annotations

import json
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from phantomshift import incident
from phantomshift.slack_channel import APPROVE_EMOJI, REJECT_EMOJI, SlackChannel
from phantomshift.slack_views import (
    slack_attack_blocks,
    slack_audit_blocks,
    slack_autopatch_finding_blocks,
    slack_forks_blocks,
    slack_status_blocks,
)


class SlackStub:
    def __init__(self):
        self.posts = []
        self.reactions = {}
        self.auth = set()
        stub = self

        class H(BaseHTTPRequestHandler):
            def _send(self, obj, code=200):
                out = json.dumps(obj).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

            def do_POST(self):
                stub.auth.add(self.headers.get("Authorization"))
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if self.path.endswith("auth.test"):
                    return self._send({"ok": True, "user_id": "U_BOT", "user": "invoiceguard", "team": "Chetas"})
                if self.path.endswith("conversations.open"):
                    return self._send({"ok": True, "channel": {"id": "D_TEST"}})
                if self.path.endswith("chat.postMessage"):
                    stub.posts.append(body)
                    return self._send({"ok": True, "ts": "1700000000.000100"})
                if self.path.endswith("reactions.add"):
                    emoji = body.get("name")
                    stub.reactions.setdefault(emoji, []).append("U_BOT")
                    return self._send({"ok": True})
                self._send({"ok": True})

            def do_GET(self):
                stub.auth.add(self.headers.get("Authorization"))
                if "reactions.get" in self.path:
                    parsed = urllib.parse.urlparse(self.path)
                    qs = urllib.parse.parse_qs(parsed.query)
                    # Return recorded reactions
                    rx = []
                    for emoji, users in stub.reactions.items():
                        rx.append({"name": emoji, "users": users, "count": len(users)})
                    return self._send({"ok": True, "message": {"reactions": rx}})
                if "conversations.history" in self.path:
                    return self._send({
                        "ok": True,
                        "messages": [
                            {"user": "U_OP", "text": "help", "ts": "1700000000.000200"}
                        ],
                    })
                self._send({"ok": True})

            def log_message(self, *a):
                pass

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.api = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


class SlackChannelTests(unittest.TestCase):
    def setUp(self):
        self.stub = SlackStub()
        self.addCleanup(self.stub.close)
        self.ch = SlackChannel("test-token", "D_TEST", "U_OP", api=self.stub.api)

    def test_channel_attributes(self):
        self.assertTrue(self.ch.real_message)
        self.assertTrue(self.ch.openclaw_managed)
        self.assertTrue(self.ch.real)
        self.assertEqual(self.ch.channel_type, "slack")

    def test_post_message(self):
        ts = self.ch.post("approvals", content="Test alert")
        self.assertEqual(ts, "1700000000.000100")
        self.assertTrue(any("Test alert" in p.get("text", "") for p in self.stub.posts))

    def test_post_with_embed_conversion(self):
        embed = {
            "title": "Incident Alert",
            "description": "Payment held",
            "fields": [{"name": "Amount", "value": "$100", "inline": True}],
        }
        ts = self.ch.post("approvals", embed=embed)
        self.assertEqual(ts, "1700000000.000100")
        self.assertTrue(len(self.stub.posts) > 0)
        last_post = self.stub.posts[-1]
        self.assertIn("attachments", last_post)
        self.assertEqual(last_post["attachments"][0]["title"], "Incident Alert")

    def test_send_and_await_approval(self):
        self.stub.reactions[APPROVE_EMOJI] = ["U_OP"]
        mid = self.ch.send("Please approve this patch")
        self.assertEqual(mid, "1700000000.000100")
        decision = self.ch.await_decision(mid, timeout_s=2.0)
        self.assertEqual(decision, ("U_OP", True))

    def test_send_and_await_rejection(self):
        self.stub.reactions[REJECT_EMOJI] = ["U_OP"]
        mid = self.ch.send("Please approve this patch")
        decision = self.ch.await_decision(mid, timeout_s=2.0)
        self.assertEqual(decision, ("U_OP", False))

    def test_fail_closed_both_reactions(self):
        self.stub.reactions[APPROVE_EMOJI] = ["U_OP"]
        self.stub.reactions[REJECT_EMOJI] = ["U_OP"]
        mid = self.ch.send("Please approve this patch")
        decision = self.ch.await_decision(mid, timeout_s=2.0)
        # Fail closed: reject if both
        self.assertEqual(decision, ("U_OP", False))

    def test_unauthorized_user_reaction_ignored(self):
        self.stub.reactions[APPROVE_EMOJI] = ["U_ATTACKER"]
        mid = self.ch.send("Please approve this patch")
        decision = self.ch.await_decision(mid, timeout_s=0.2)
        self.assertIsNone(decision)

    def test_listen_commands(self):
        def mock_handle(text):
            return None, f"Executed: {text}"

        replies = self.ch.listen("approvals", mock_handle, seconds=0.5, poll_s=0.1)
        self.assertEqual(replies, 1)


class SlackViewsTests(unittest.TestCase):
    def test_attack_blocks(self):
        scn = {
            "title": "Invoice Redirect",
            "task": "Pay invoice",
            "untrusted_source": "email",
            "boundary": "financial",
            "attacks": [{"tool": "pay_invoice", "args": {"amt": 100}}],
            "exposure_usd": 100,
        }
        blocks = slack_attack_blocks(scn, {"violations": ["Account mismatch"]})
        self.assertTrue(isinstance(blocks, list))
        self.assertIn("HELD", blocks[0]["text"]["text"])

    def test_autopatch_blocks(self):
        blocks = slack_autopatch_finding_blocks({"finding_id": "find-123", "severity": "critical", "priority_index": 40})
        self.assertTrue(isinstance(blocks, list))
        self.assertIn("find-123", json.dumps(blocks))

    def test_status_blocks(self):
        gates = [{"id": "H01", "gate": "Trigger", "status": "PASS", "detail": "ok"}]
        blocks = slack_status_blocks(gates, "Ran 546 tests in 75s OK")
        self.assertTrue(isinstance(blocks, list))
        self.assertIn("H01", json.dumps(blocks))


if __name__ == "__main__":
    unittest.main()
