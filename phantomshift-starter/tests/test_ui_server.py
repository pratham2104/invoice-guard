"""UI server routes and static-asset hygiene. Binds loopback on an ephemeral port only."""

import json
import re
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from phantomshift import server

STATIC = Path(server.STATIC)


class UIServerTests(unittest.TestCase):
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
            with urllib.request.urlopen(self.base + path, timeout=10) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def test_static_routes(self):
        for path, ctype in (("/", "text/html"), ("/index.html", "text/html"),
                            ("/app.js", "text/javascript"), ("/style.css", "text/css")):
            code, hdr, body = self.get(path)
            self.assertEqual(code, 200, path)
            self.assertTrue(hdr["Content-Type"].startswith(ctype), path)
            self.assertTrue(body, path)

    def test_security_headers_on_every_kind_of_response(self):
        for path in ("/", "/app.js", "/style.css", "/api/gates", "/api/eval", "/nope"):
            _, hdr, _ = self.get(path)
            csp = hdr.get("Content-Security-Policy", "")
            self.assertIn("default-src 'self'", csp, path)
            self.assertNotIn("unsafe-eval", csp)
            self.assertNotRegex(csp, r"script-src[^;]*unsafe-inline")
            self.assertEqual(hdr.get("X-Content-Type-Options"), "nosniff", path)

    def test_unknown_paths_404(self):
        for path in ("/nope", "/static/app.js", "/../server.py", "/api/incident/nope",
                     "/api/gates/extra", "/style.css.map"):
            code, _, body = self.get(path)
            self.assertEqual(code, 404, path)
            self.assertIn("error", json.loads(body))

    def test_gates_empty_when_file_absent(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(server, "GATES_PATH", Path(d) / "missing.json"):
            code, _, body = self.get("/api/gates")
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body), [])

    def test_gates_serves_file_contents(self):
        gates = [{"id": "H01", "gate": "Example gate", "status": "NOT TESTED", "detail": "x"}]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "verify.json"
            p.write_text(json.dumps(gates))
            with mock.patch.object(server, "GATES_PATH", p):
                code, hdr, body = self.get("/api/gates")
        self.assertEqual(code, 200)
        self.assertTrue(hdr["Content-Type"].startswith("application/json"))
        self.assertEqual(json.loads(body), gates)

    def test_gates_invalid_json_is_an_error_not_fabricated(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "verify.json"
            p.write_text("{not json")
            with mock.patch.object(server, "GATES_PATH", p):
                code, _, body = self.get("/api/gates")
        self.assertEqual(code, 500)
        self.assertIn("error", json.loads(body))

    def test_gates_real_file_shape_if_present(self):
        # Reads the real artifact (never writes it): if present it must be a list of gate dicts.
        if not server.GATES_PATH.exists():
            self.skipTest("no verify.json in this checkout")
        code, _, body = self.get("/api/gates")
        self.assertEqual(code, 200)
        data = json.loads(body)
        self.assertIsInstance(data, list)
        for g in data:
            self.assertIn("status", g)

    def test_eval_shape(self):
        code, _, body = self.get("/api/eval")
        self.assertEqual(code, 200)
        res = json.loads(body)["heldout"]["results"]
        for part in ("parametric", "hard"):
            for pol in ("baseline", "lockdown", "allowlist", "context_bound"):
                cell = res[part][pol]["policy_only"]
                for k in ("attacks", "attacks_succeeded", "legit", "legit_completed"):
                    self.assertIn(k, cell)

    def test_incident_shape_for_every_scenario(self):
        code, _, body = self.get("/api/scenarios")
        self.assertEqual(code, 200)
        for s in json.loads(body):
            code, _, body = self.get("/api/incident/" + s["id"])
            self.assertEqual(code, 200)
            rec = json.loads(body)
            for k in ("run_id", "evidence", "replay_mode", "forks", "trace", "approval", "trace_chain_ok"):
                self.assertIn(k, rec)
            self.assertEqual(rec["replay_mode"], "policy_only_replay")
            self.assertEqual([f["name"] for f in rec["forks"]],
                             ["baseline", "lockdown", "allowlist", "context_bound"])
            for ev in rec["trace"]:
                for k in ("seq", "ts", "kind", "hash", "prev", "data"):
                    self.assertIn(k, ev)
            for f in rec["forks"]:
                for k in ("attacks", "legit", "harmful_executed", "attacks_total", "legit_completed", "legit_total"):
                    self.assertIn(k, f)


class StaticHygieneTests(unittest.TestCase):
    def read(self, name):
        return (STATIC / name).read_text(encoding="utf-8")

    def test_html_has_no_inline_script_or_handlers(self):
        html = self.read("index.html")
        scripts = re.findall(r"<script\b([^>]*)>(.*?)</script>", html, flags=re.S | re.I)
        self.assertTrue(scripts)
        for attrs, inner in scripts:
            self.assertIn("src=", attrs)
            self.assertEqual(inner.strip(), "")
        self.assertNotRegex(html, r"<style\b")  # styles come from /style.css
        self.assertNotRegex(html, r"\son[a-z]+\s*=", "inline event handler")
        self.assertNotRegex(html, r"javascript:", "javascript: URL")

    def test_no_external_urls_in_any_static_file(self):
        for name in ("index.html", "app.js", "style.css"):
            text = self.read(name)
            self.assertNotRegex(text, r"https?://", name)
            self.assertNotRegex(text, r"(?<![:\w])//[a-z0-9.-]+\.[a-z]{2,}/", name)
            self.assertNotRegex(text, r"@import", name)

    def test_js_never_uses_html_injection_sinks(self):
        js = self.read("app.js")
        for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"):
            self.assertNotIn(sink, js, sink)

    def test_page_names_the_four_surfaces_and_honesty_labels(self):
        html = self.read("index.html")
        for text in ("Control plane", "Attack graph", "Three futures", "Fix and receipt", "No live OpenClaw agent"):
            self.assertIn(text, html)
        js = self.read("app.js")
        for text in ("policy_only", "circular", "/api/gates", "/api/eval", "Download receipt JSON"):
            self.assertIn(text, js)


if __name__ == "__main__":
    unittest.main()
