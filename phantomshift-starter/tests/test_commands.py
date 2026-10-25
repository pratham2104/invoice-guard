import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from phantomshift import commands
from phantomshift.discord_channel import DiscordChannel


class CommandTests(unittest.TestCase):
    def test_scan_holds_all_attacks_and_passes_legit(self):
        for sid in ("invoice_redirect", "ticket_exfil", "log_secret_post"):
            emb, _ = commands.dispatch(f"scan {sid}")
            fields = {f["name"]: f["value"] for f in emb["fields"]}
            self.assertEqual(fields["Attacks held"], "2/2", sid)
            self.assertEqual(fields["Legit passed authority check"], "2/2", sid)

    def test_simulate_selects_context_bound(self):
        emb, _ = commands.dispatch("/phantom simulate ticket_exfil")
        self.assertIn("context_bound", [f["value"] for f in emb["fields"]])
        self.assertIn("policy_only_replay", json.dumps(emb))

    def test_report_states_caveats(self):
        emb, _ = commands.dispatch("report")
        self.assertIn("Caveats", [f["name"] for f in emb["fields"]])

    def test_unknown_command_and_scenario(self):
        self.assertIsNone(commands.dispatch("rm -rf")[0])
        self.assertIsNone(commands.dispatch("scan nope")[0])
        self.assertIsNotNone(commands.dispatch("")[0])  # help

    def test_every_embed_is_labelled_synthetic(self):
        for c in ("scan", "simulate", "report", "help"):
            self.assertIn("SYNTHETIC FIXTURE", commands.dispatch(c)[0]["footer"]["text"])


class ListenerTests(unittest.TestCase):
    def test_only_operator_mentions_are_served(self):
        sent, state = [], {"served": False}
        msgs = [
            {"id": "11", "author": {"id": "intruder"}, "mentions": [{"id": "BOT"}], "content": "<@BOT> scan"},
            {"id": "12", "author": {"id": "op"}, "mentions": [], "content": "scan"},
            {"id": "13", "author": {"id": "op"}, "mentions": [{"id": "BOT"}], "content": "<@BOT> scan invoice_redirect"},
        ]

        class H(BaseHTTPRequestHandler):
            def _j(self, o):
                b = json.dumps(o).encode(); self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

            def do_GET(self):
                if self.path.startswith("/users/@me"):
                    return self._j({"id": "BOT"})
                if "limit=1" in self.path:
                    return self._j([{"id": "10"}])
                if not state["served"]:
                    state["served"] = True
                    return self._j(list(reversed(msgs)))
                self._j([])

            def do_POST(self):
                sent.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                self._j({"id": "99"})

            def log_message(self, *a):
                pass

        srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown); self.addCleanup(srv.server_close)
        ch = DiscordChannel("tok", "c1", "op", f"http://127.0.0.1:{srv.server_address[1]}", {"ctl": "c1"})
        n = ch.listen("ctl", commands.dispatch, seconds=0.5, poll_s=0.1)
        self.assertEqual(n, 1)
        self.assertEqual(sent[0]["message_reference"], {"message_id": "13"})
        self.assertIn("embeds", sent[0])


if __name__ == "__main__":
    unittest.main()
