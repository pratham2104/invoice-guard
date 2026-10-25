"""Stub Discord API (test double). Proves request shapes, operator-only approval and
timeout handling. Says nothing about the real Discord service."""

import json
import re
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from phantomshift import incident
from phantomshift.discord_channel import APPROVE, REJECT, DiscordChannel


class Stub:
    def __init__(self):
        self.posts, self.reactions, self.auth = [], {}, set()
        self.created, self.paths, self.existing = [], [], []
        stub = self

        class H(BaseHTTPRequestHandler):
            def _send(self, obj, code=200):
                out = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

            def do_POST(self):
                stub.auth.add(self.headers.get("Authorization"))
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if self.path.endswith("/channels"):
                    stub.created.append(body["name"])
                    return self._send({"id": f"id-{body['name']}"})
                stub.posts.append(body.get("content") or json.dumps(body.get("embeds")))
                stub.paths.append(self.path)
                self._send({"id": "m1"})

            def do_PUT(self):
                self.send_response(204); self.send_header("Content-Length", "0"); self.end_headers()

            def do_GET(self):
                if self.path.endswith("/channels"):
                    return self._send(stub.existing)
                m = re.search(r"/reactions/([^?]+)", self.path)
                emoji = urllib.parse.unquote(m.group(1))
                self._send([{"id": u} for u in stub.reactions.get(emoji, [])])

            def log_message(self, *a):
                pass

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.api = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def close(self):
        self.srv.shutdown(); self.srv.server_close()


class DiscordChannelTests(unittest.TestCase):
    def setUp(self):
        self.stub = Stub()
        self.addCleanup(self.stub.close)
        self.ch = DiscordChannel("tok", "c1", "op-9", self.stub.api)

    def test_not_labelled_as_hackathon_channel(self):
        self.assertFalse(self.ch.real)
        self.assertFalse(self.ch.openclaw_managed)
        self.assertTrue(self.ch.real_message)

    def test_operator_approval_activates_policy(self):
        self.stub.reactions[APPROVE] = ["op-9"]
        r = incident.run_incident("invoice_redirect", operator="op-9", channel=self.ch, wait_s=2)
        self.assertEqual(r["approval"]["state"], "activated")
        self.assertTrue(r["verification"]["verified"])
        self.assertTrue(r["approval"]["real_message"])
        self.assertFalse(r["approval"]["openclaw_managed"])
        self.assertTrue(any("SYNTHETIC" in p for p in self.stub.posts))
        self.assertEqual(self.stub.auth, {"Bot tok"})

    def test_operator_rejection_does_not_activate(self):
        self.stub.reactions[REJECT] = ["op-9"]
        r = incident.run_incident("invoice_redirect", operator="op-9", channel=self.ch, wait_s=2)
        self.assertNotEqual(r["approval"]["state"], "activated")
        self.assertIsNone(r["verification"])

    def test_other_users_reaction_ignored_then_times_out(self):
        self.stub.reactions[APPROVE] = ["someone-else"]
        r = incident.run_incident("invoice_redirect", operator="op-9", channel=self.ch, wait_s=0.2)
        self.assertNotEqual(r["approval"]["state"], "activated")
        self.assertIn("timeout", r["approval"]["state"])

    def test_ensure_channels_is_idempotent_and_routes_stages(self):
        self.stub.existing = [{"id": "cat1", "type": 4, "name": "PHANTOMSHIFT"},
                              {"id": "x1", "type": 0, "name": "approvals"}]
        ids = self.ch.ensure_channels("g1")
        self.assertNotIn("approvals", self.stub.created)
        self.assertNotIn("PHANTOMSHIFT", self.stub.created)
        self.assertEqual(set(ids), {"phantomshift-control", "live-attacks", "parallel-worlds", "approvals", "audit-evidence"})
        self.stub.reactions[APPROVE] = ["op-9"]
        incident.run_incident("invoice_redirect", operator="op-9", channel=self.ch, wait_s=2)
        sent_to = [p.split("/")[2] for p in self.stub.paths]
        self.assertIn("id-live-attacks", sent_to)
        self.assertIn("id-parallel-worlds", sent_to)
        self.assertIn("id-audit-evidence", sent_to)
        self.assertIn("x1", sent_to)  # approvals channel that already existed

    def test_both_reactions_from_operator_is_a_reject(self):
        self.stub.reactions[APPROVE] = ["op-9"]
        self.stub.reactions[REJECT] = ["op-9"]
        r = incident.run_incident("invoice_redirect", operator="op-9", channel=self.ch, wait_s=2)
        self.assertNotEqual(r["approval"]["state"], "activated")
        self.assertIsNone(r["verification"])

    def test_gate_uses_channel_operator_not_default_label(self):
        # CLI path: run_incident default operator is 'operator-1' but Discord authenticates 'op-9'
        self.stub.reactions[APPROVE] = ["op-9"]
        r = incident.run_incident("invoice_redirect", channel=self.ch, wait_s=2)
        self.assertEqual(r["approval"]["state"], "activated")

    def test_token_never_in_messages(self):
        self.stub.reactions[APPROVE] = ["op-9"]
        incident.run_incident("ticket_exfil", operator="op-9", channel=self.ch, wait_s=2)
        self.assertFalse(any("tok" == w for p in self.stub.posts for w in p.split()))


if __name__ == "__main__":
    unittest.main()
