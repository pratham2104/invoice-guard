"""Regression tests for the adversarial-review fixes owned by agent B.

Sections: A policies, B llm, C inference gate, D UI server, E verify_hackathon evidence, F shell scripts.
Every test here fails on the pre-fix behaviour. No network beyond loopback, no real ssh/rsync/docker.
"""

import base64
import copy
import datetime as dt
import http.client
import http.server
import importlib.util
import json
import os
import shutil
import socket
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from phantomshift import llm, server  # noqa: E402
from phantomshift.eventstore import EventStore  # noqa: E402
from phantomshift.inference_gate import check_inference_config as gate  # noqa: E402
from phantomshift.policies import BASELINE, CANDIDATES, evaluate, validate_config  # noqa: E402

ALLOWLIST = next(c for c in CANDIDATES if c["name"] == "allowlist")
CONTEXT_BOUND = next(c for c in CANDIDATES if c["name"] == "context_bound")


def egress(tool, **args):
    return {"tool": tool, "args": args, "prov": {}, "labels": []}


# --------------------------------------------------------------------------- A. policies
class DestinationParsingTests(unittest.TestCase):
    def allowed(self, act):
        return evaluate(ALLOWLIST, act)["allow"]

    def test_multi_recipient_mail_is_denied(self):
        for to in ("attacker@evil.example,dana@customer.example",
                   "dana@customer.example,attacker@evil.example",
                   "attacker@evil.example;dana@customer.example",
                   "dana@customer.example attacker@evil.example",
                   "attacker@evil.example\ndana@customer.example",
                   "a@evil.example@customer.example",
                   "Dana <dana@customer.example>",
                   "dana@customer.example."):
            self.assertFalse(self.allowed(egress("send_email", to=to, body="x")), repr(to))

    def test_single_clean_recipient_still_allowed(self):
        for to in ("dana@customer.example", "Support-Lead@ACME.example", "x@eu.partner.example"):
            self.assertTrue(self.allowed(egress("send_email", to=to, body="x")), to)

    def test_url_parser_differential_is_denied(self):
        for url in ("http://evil.example\\@acme.example/",
                    "http://acme.example\\@evil.example/",
                    "http://acme.example@evil.example/",
                    "https://user:pw@acme.example/",
                    "https://acme.example/\n",
                    "https://acme.example/\x00",
                    "https://acme.example:notaport/",
                    "ftp://acme.example/x",
                    " https://acme.example/",
                    "//acme.example/x"):
            self.assertFalse(self.allowed(egress("http_post", url=url, body="x")), repr(url))

    def test_clean_urls_still_allowed(self):
        for url in ("https://hooks.acme.example/ci-status", "http://partner.example:8080/a?b=c", "https://ACME.example/"):
            self.assertTrue(self.allowed(egress("http_post", url=url, body="x")), url)

    def test_non_string_destination_is_denied(self):
        self.assertFalse(self.allowed(egress("send_email", to=["dana@customer.example"], body="x")))
        self.assertFalse(self.allowed(egress("http_post", url=None, body="x")))


class ValidateConfigTests(unittest.TestCase):
    def cfg(self, **kw):
        c = copy.deepcopy(CONTEXT_BOUND)
        c.update(kw)
        return c

    def test_never_raises_on_hostile_shapes(self):
        hostile = [
            self.cfg(deny_tools=[["x"]]),
            self.cfg(deny_tools=[{"a": 1}]),
            self.cfg(deny_tools=[None]),
            self.cfg(egress_label_rules={"a": ["deny"]}),
            self.cfg(egress_label_rules={("t",): "deny"}),
            self.cfg(egress_label_rules={"a": {"x": 1}}),
            self.cfg(bind_params={"pay_invoice": [["account"]]}),
            self.cfg(bind_params={"pay_invoice": [{"a": 1}]}),
            self.cfg(bind_params={"pay_invoice": "account"}),
            self.cfg(bind_params={None: ["account"]}),
            self.cfg(domain_allowlist=[["acme.example"]]),
            self.cfg(domain_allowlist=[None]),
            self.cfg(domain_allowlist="acme.example"),
            self.cfg(name=["x"]), self.cfg(label=None),
            {1: 2}, None, 5, [], "x",
        ]
        for c in hostile:
            try:
                problems = validate_config(c)
            except Exception as exc:  # noqa: BLE001
                self.fail(f"validate_config raised {type(exc).__name__} for {c!r}")
            self.assertTrue(problems, f"accepted hostile config {c!r}")

    def test_shipped_configs_validate(self):
        for c in [*CANDIDATES]:
            self.assertEqual(validate_config(c), [], c["name"])

    def test_name_and_label_must_be_non_empty_strings(self):
        self.assertTrue(validate_config(self.cfg(name="")))
        self.assertTrue(validate_config(self.cfg(label="   ")))
        self.assertTrue(validate_config(self.cfg(name=7)))

    def test_bind_param_names_are_allow_listed(self):
        self.assertTrue(validate_config(self.cfg(bind_params={"pay_invoice": ["account", "memo"]})))
        self.assertTrue(validate_config(self.cfg(bind_params={"pay_invoice": ["__class__"]})))
        self.assertEqual(validate_config(self.cfg(bind_params={"pay_invoice": ["account", "vendor_id"]})), [])

    def test_empty_bind_list_is_refused(self):
        self.assertTrue(validate_config(self.cfg(bind_params={"pay_invoice": []})))

    def test_candidate_may_not_be_weaker_than_the_active_policy(self):
        weaker = self.cfg(bind_params={"send_email": ["to"]}, egress_label_rules={"secret": "deny"})
        self.assertEqual(validate_config(weaker), [])  # fine against BASELINE
        problems = validate_config(weaker, against=CONTEXT_BOUND)
        self.assertTrue(any("weaker" in p for p in problems), problems)
        relaxed = self.cfg(egress_label_rules={"secret": "trusted_destination", "pii": "trusted_destination"})
        self.assertTrue(any("weaker" in p for p in validate_config(relaxed, against=CONTEXT_BOUND)))
        self.assertEqual(validate_config(CONTEXT_BOUND, against=CONTEXT_BOUND), [])
        self.assertEqual(validate_config(self.cfg(deny_tools=["http_post"]), against=CONTEXT_BOUND), [])

    def test_malformed_domain_entries_refused(self):
        for bad in ("com.", "com", "co.uk", "com.au", "acme.example.", "ACME.example", ".acme.example",
                    "acme..example", "-acme.example", "acme.example/x", "*.acme.example", "1.2.3.4", " acme.example",
                    "acme.example:80", "acme.e"):
            self.assertTrue(validate_config(self.cfg(domain_allowlist=[bad])), bad)
        self.assertEqual(validate_config(self.cfg(domain_allowlist=["acme.example", "eu.partner.co.uk"])), [])
        self.assertEqual(validate_config(self.cfg(domain_allowlist=[])), [])


# --------------------------------------------------------------------------- B. llm
class ProvenanceTests(unittest.TestCase):
    tp = staticmethod(llm.trace_provenance)

    def test_substring_of_task_id_is_not_user(self):
        prov = self.tp("invoice_redirect", {"account": "2291", "amount": "229"})
        self.assertNotIn(prov["account"], ("user", "registry"))
        self.assertNotIn(prov["amount"], ("user", "registry"))

    def test_normalised_lookalike_of_registry_is_not_registry(self):
        for v in ("0009 98774417", "000998774417!!<script>", "0009-98774417", "000998774417​"):
            self.assertNotEqual(self.tp("invoice_redirect", {"account": v})["account"], "registry", repr(v))

    def test_exact_values_keep_their_provenance(self):
        p = self.tp("invoice_redirect", {"vendor_id": "V-102", "amount": 24800, "account": "000998774417",
                                         "invoice_id": "INV-2291", "x": "000123459921"})
        self.assertEqual(p["vendor_id"], "registry")
        self.assertEqual(p["amount"], "registry")
        self.assertEqual(p["account"], "registry")
        self.assertEqual(p["invoice_id"], "user")
        self.assertEqual(p["x"], "untrusted")
        self.assertEqual(self.tp("invoice_redirect", {"account": " 000998774417 "})["account"], "registry")  # trim only
        self.assertEqual(self.tp("ticket_exfil", {"to": "dana@customer.example"})["to"], "registry")

    def test_partial_registry_and_case_variants_are_model(self):
        self.assertEqual(self.tp("ticket_exfil", {"to": "DANA@customer.example"})["to"], "model")
        self.assertEqual(self.tp("ticket_exfil", {"to": "dana@customer.example,evil@evil.example"})["to"], "model")
        self.assertEqual(self.tp("log_secret_post", {"url": "https://hooks.acme.example"})["url"], "model")
        self.assertEqual(self.tp("log_secret_post", {"url": "http"})["url"], "model")

    def test_bool_and_nan_never_trusted(self):
        p = self.tp("invoice_redirect", {"a": True, "b": float("nan"), "c": None, "d": ["V-102"]})
        for k in "abcd":
            self.assertEqual(p[k], "model", k)


class InferLabelsTests(unittest.TestCase):
    def labels(self, scenario, **args):
        return llm.infer_labels(scenario, args)

    def test_scans_every_string_argument(self):
        self.assertEqual(self.labels("log_secret_post", url="https://hooks.acme.example/x", note="the api key"), ["secret"])
        self.assertEqual(self.labels("log_secret_post", subject={"nested": ["contents of .env"]}), ["secret"])
        self.assertEqual(self.labels("ticket_exfil", to="a@b.example", subject="customers.csv"), ["pii"])

    def test_url_query_strings(self):
        self.assertEqual(self.labels("log_secret_post", url="https://hooks.acme.example/s?f=%2Eenv"), ["secret"])
        self.assertEqual(self.labels("log_secret_post", url="https://hooks.acme.example/s?data=AWS_SECRET_ACCESS_KEY"),
                         ["secret"])

    def test_case_spacing_and_zero_width_obfuscation(self):
        self.assertEqual(self.labels("log_secret_post", body="P a s s W o r d: hunter2"), ["secret"])
        self.assertEqual(self.labels("log_secret_post", body="pass​word"), ["secret"])
        self.assertEqual(self.labels("log_secret_post", body="A­PI KEY"), ["secret"])
        self.assertEqual(self.labels("ticket_exfil", body="C U S T O M E R   T A B L E"), ["pii"])
        self.assertEqual(self.labels("ticket_exfil", body="ｃｕｓｔｏｍｅｒ table"), ["pii"])

    def test_base64_substrings(self):
        enc = base64.b64encode(b"here is the AWS_SECRET_ACCESS_KEY value").decode()
        self.assertEqual(self.labels("log_secret_post", body=f"ref: {enc} end"), ["secret"])
        enc2 = base64.urlsafe_b64encode(b"customers.csv attached, all rows").decode().rstrip("=")
        self.assertEqual(self.labels("ticket_exfil", body=enc2), ["pii"])

    def test_benign_payloads_stay_unlabelled(self):
        self.assertEqual(self.labels("log_secret_post", url="https://hooks.acme.example/ci-status",
                                     body="build 8841 failed at step 7"), [])
        self.assertEqual(self.labels("ticket_exfil", to="dana@customer.example", body="Your export failed because ..."), [])
        self.assertEqual(self.labels("invoice_redirect", account="000998774417"), [])  # scenario without markers


class ParseActionTests(unittest.TestCase):
    pa = staticmethod(llm.parse_action)

    def test_non_finite_numbers_are_rejected(self):
        for amt in ("NaN", "Infinity", "-Infinity", "1e999"):
            txt = '{"tool":"pay_invoice","args":{"vendor_id":"V-102","amount":%s}}' % amt
            with self.assertRaises(ValueError, msg=amt):
                self.pa("invoice_redirect", txt)

    def test_first_object_wins_over_greedy_regex(self):
        a = self.pa("invoice_redirect", 'ok {"tool":"lookup_vendor","args":{"vendor_id":"V-102"}} and then {"tool":"x"} {note}')
        self.assertEqual(a["tool"], "lookup_vendor")
        b = self.pa("invoice_redirect", '{"tool":"send_email","args":{"to":"x"}} {"tool":"pay_invoice","args":{}}')
        self.assertEqual(b["tool"], "send_email")

    def test_trailing_brace_junk_is_ignored(self):
        a = self.pa("invoice_redirect", '{"tool":"lookup_vendor","args":{"vendor_id":"V-102"}} } trailing {')
        self.assertEqual(a["args"], {"vendor_id": "V-102"})

    def test_think_block_and_prose_are_skipped(self):
        txt = '<think>{"tool":"pay_invoice","args":{"amount":1}}</think> Sure: {"tool":"lookup_vendor","args":{}}'
        self.assertEqual(self.pa("invoice_redirect", txt)["tool"], "lookup_vendor")

    def test_duplicate_keys_and_bad_types_are_rejected(self):
        with self.assertRaises(ValueError):
            self.pa("invoice_redirect", '{"tool":"pay_invoice","args":{"amount":1,"amount":999999}}')
        with self.assertRaises(ValueError):
            self.pa("invoice_redirect", '{"tool":["x"],"args":{}}')
        with self.assertRaises(ValueError):
            self.pa("invoice_redirect", '{"tool":"x","args":[1]}')
        with self.assertRaises(ValueError):
            self.pa("invoice_redirect", "no json here")


class _Recorder(http.server.BaseHTTPRequestHandler):
    hits: list = []

    def do_POST(self):
        type(self).hits.append((self.path, self.rfile.read(int(self.headers.get("Content-Length", 0)))))
        body = json.dumps({"choices": [{"message": {"content": "{}"}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def _serve(handler):
    srv = http.server.HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


class ChatNetworkHygieneTests(unittest.TestCase):
    def test_proxy_environment_is_ignored(self):
        rec = type("Rec", (_Recorder,), {"hits": []})
        proxy = _serve(rec)
        self.addCleanup(proxy.server_close)
        self.addCleanup(proxy.shutdown)
        target = _serve(type("T", (_Recorder,), {"hits": []}))
        self.addCleanup(target.server_close)
        self.addCleanup(target.shutdown)
        env = {"http_proxy": f"http://127.0.0.1:{proxy.server_port}", "HTTP_PROXY": f"http://127.0.0.1:{proxy.server_port}"}
        with mock.patch.dict(os.environ, env):
            os.environ.pop("no_proxy", None)
            os.environ.pop("NO_PROXY", None)
            out = llm.chat(f"http://127.0.0.1:{target.server_port}/v1", "m", [{"role": "user", "content": "SECRET PROMPT"}], timeout=5)
        self.assertEqual(out, "{}")
        self.assertEqual(rec.hits, [], "prompt leaked to the proxy")

    def test_redirects_are_refused_and_not_followed(self):
        off_box = type("Off", (_Recorder,), {"hits": []})
        sink = _serve(off_box)
        self.addCleanup(sink.server_close)
        self.addCleanup(sink.shutdown)

        class Redirect(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                self.send_response(307)
                self.send_header("Location", f"http://127.0.0.1:{sink.server_port}/exfil")
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *a):
                pass

        red = _serve(Redirect)
        self.addCleanup(red.server_close)
        self.addCleanup(red.shutdown)
        with self.assertRaises(ValueError):
            llm.chat(f"http://127.0.0.1:{red.server_port}/v1", "m", [{"role": "user", "content": "x"}], timeout=5)
        self.assertEqual(off_box.hits, [], "redirect was followed")

    def test_require_loopback_rejects_parser_tricks(self):
        for u in ("http://evil.com\\@127.0.0.1/", "http://127.0.0.1\\@evil.com/", "http://user@127.0.0.1:1/",
                  "http://127.0.0.1:80@evil.com/", "ftp://127.0.0.1/", "http://127.0.0.1 /", "http://localhost.evil.com/",
                  "http://127.0.0.1:99999/"):
            with self.assertRaises(ValueError, msg=u):
                llm.require_loopback(u)
        llm.require_loopback("http://[::1]:8000/v1")
        llm.require_loopback("http://127.0.0.1:8000/v1")


# --------------------------------------------------------------------------- C. inference gate
class GateBypassTests(unittest.TestCase):
    LOCAL = {"llm": {"base_url": "http://127.0.0.1:8000/v1", "provider": "vllm", "model": "nvidia/Llama-3.1-Nemotron-Nano-4B-v1.1"}}

    def check(self, extra=None, env=None, mode="competition"):
        cfg = copy.deepcopy(self.LOCAL)
        cfg.update(extra or {})
        return gate(cfg, mode, env)

    def test_baseline_local_config_ok(self):
        self.assertTrue(self.check()["ok"])
        self.assertTrue(self.check(env={"HTTP_PROXY": "http://127.0.0.1:3128", "no_proxy": "example.com", "HOSTNAME": "gb10"})["ok"])
        self.assertTrue(self.check({"asset": "model.gguf", "cfg": "config.json"})["ok"])

    def test_schemeless_host_anywhere_is_rejected(self):
        for v in ("api.openai.com", "//api.openai.com/v1", "api.openai.com:443/v1", "8.8.8.8",
                  "fallback to api.openai.com if busy", "[2001:db8::1]:80", "host.openshell.internal:8000"):
            r = self.check({"fallback": v})
            self.assertFalse(r["ok"], v)
            self.assertIn("remote_endpoint", {x["code"] for x in r["violations"]}, v)

    def test_embedded_url_in_plain_config_string(self):
        self.assertFalse(self.check({"notes": "route via https://api.openai.com/v1 when busy"})["ok"])

    def test_env_plain_string_containing_url(self):
        self.assertFalse(self.check({"env": {"NOTE": "call https://api.openai.com/v1"}})["ok"])
        self.assertFalse(self.check(env={"NOTE": "x //api.openai.com/v1"})["ok"])

    def test_env_url_and_host_keys(self):
        for k, v in (("OPENAI_URL", "https://api.openai.com"), ("LLM_HOST", "api.openai.com"),
                     ("INFERENCE_SERVER", "10.1.2.3:8000"), ("openai_api_base", "https://x.example/v1")):
            self.assertFalse(self.check({"env": {k: v}})["ok"], k)
        self.assertTrue(self.check({"env": {"LLM_HOST": "127.0.0.1", "OPENAI_URL": "http://localhost:8000/v1"}})["ok"])

    def test_proxy_variables_must_be_loopback(self):
        for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
            r = self.check(env={k: "http://proxy.corp.example:3128"})
            self.assertFalse(r["ok"], k)
            self.assertFalse(self.check(env={k: "socks5://10.0.0.9:1080"})["ok"], k)
            self.assertTrue(self.check(env={k: "http://127.0.0.1:3128"})["ok"], k)
        self.assertTrue(self.check(env={"HTTP_PROXY": ""})["ok"])

    def test_prep_mode_also_rejects_remote_hosts(self):
        self.assertFalse(self.check({"fallback": "api.openai.com"}, mode="prep")["ok"])

    def test_nemoclaw_alias_is_not_treated_as_loopback_by_this_gate(self):
        # Documented in the module: only the runtime route check (verify_hackathon H03) accepts it.
        self.assertFalse(self.check({"llm2": {"base_url": "http://host.openshell.internal:8000/v1"}})["ok"])


# --------------------------------------------------------------------------- D. server
class ServerHardeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.srv.server_address[1]
        cls.thread = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.thread.join(5)

    def get(self, path, host="UNSET"):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.putrequest("GET", path, skip_host=True, skip_accept_encoding=True)
        if host != "UNSET":
            c.putheader("Host", host)
        c.endheaders()
        r = c.getresponse()
        body = r.read()
        c.close()
        return r.status, {k.lower(): v for k, v in r.getheaders()}, body

    def test_rebinding_hosts_get_403(self):
        for h in ("attacker.example", f"attacker.example:{self.port}", "127.0.0.1.evil.example", "localhost.evil.example",
                  "evil.example:127.0.0.1", "0.0.0.0", "127.0.0.2", "[::2]", "127.0.0.1:80@evil.example", "", "localhost."):
            code, hdr, _ = self.get("/api/summary", host=h)
            self.assertEqual(code, 403, repr(h))
            self.assertEqual(hdr["x-frame-options"], "DENY")

    def test_missing_host_header_is_refused(self):
        self.assertEqual(self.get("/api/scenarios", host="UNSET")[0], 403)

    def test_local_hosts_are_served(self):
        for h in ("127.0.0.1", f"127.0.0.1:{self.port}", "localhost", f"localhost:{self.port}", "[::1]", f"[::1]:{self.port}",
                  "LOCALHOST:8765"):
            code, _, _ = self.get("/api/scenarios", host=h)
            self.assertEqual(code, 200, h)

    def test_new_headers_on_every_kind_of_response(self):
        for path in ("/", "/app.js", "/api/gates", "/nope"):
            code, hdr, _ = self.get(path, host="localhost")
            self.assertEqual(hdr["x-frame-options"], "DENY", path)
            self.assertEqual(hdr["cross-origin-resource-policy"], "same-origin", path)
            self.assertIn("frame-ancestors 'none'", hdr["content-security-policy"], path)
            self.assertEqual(hdr["x-content-type-options"], "nosniff", path)


# --------------------------------------------------------------------------- E. verify_hackathon
def _load_verify():
    spec = importlib.util.spec_from_file_location("verify_hackathon_under_test", ROOT / "scripts" / "verify_hackathon.py")
    mod = importlib.util.module_from_spec(spec)
    with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"PHANTOMSHIFT_ARTIFACTS": d}):
        spec.loader.exec_module(mod)
    return mod


def _iso(delta_s=0):
    return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=delta_s)).isoformat(timespec="seconds")


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.v = _load_verify()
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.art = self.tmp / "runtime-verification"
        self.art.mkdir()
        self.db = self.tmp / "events.sqlite"
        for name, val in (("ART", self.art), ("EVENTS_DB", self.db)):
            p = mock.patch.object(self.v, name, val)
            p.start()
            self.addCleanup(p.stop)
        self.host = socket.gethostname()
        st = EventStore(self.db)
        st.append("QUEUED", "run-123", payload={"note": "demo", "nonce_seen": "nonce-abcdef123456"})
        st.close()

    def write(self, name, obj):
        (self.art / name).write_text(json.dumps(obj))

    def demo(self, **kw):
        d = {"is_live": True, "host": self.host, "timestamp": _iso(-60), "run_id": "run-123"}
        d.update(kw)
        return d

    def chan(self, **kw):
        d = {"is_live": True, "openclaw_managed": True, "type": "discord", "round_trip": "ack in channel",
             "host": self.host, "timestamp": _iso(-60), "nonce": "nonce-abcdef123456"}
        d.update(kw)
        return d

    TOOLS = {"nemoclaw": None}

    def test_demo_without_file_is_not_tested(self):
        ok, why = self.v.demo_evidence()
        self.assertFalse(ok)
        self.assertIn("no file", why)

    def test_demo_valid_evidence_passes(self):
        self.write("demo.json", self.demo())
        self.assertTrue(self.v.demo_evidence()[0])

    def test_demo_rejects_each_bad_field(self):
        cases = {
            "not live": self.demo(is_live=False),
            "string live": self.demo(is_live="true"),
            "foreign host": self.demo(host="someone-elses-laptop"),
            "no host": {k: v for k, v in self.demo().items() if k != "host"},
            "stale": self.demo(timestamp=_iso(-25 * 3600)),
            "future": self.demo(timestamp=_iso(3600)),
            "no timestamp": {k: v for k, v in self.demo().items() if k != "timestamp"},
            "garbage timestamp": self.demo(timestamp="yesterday-ish"),
            "bool timestamp": self.demo(timestamp=True),
            "unknown run": self.demo(run_id="run-nope"),
            "no run": self.demo(run_id=""),
            "not a dict": [1, 2],
        }
        for label, d in cases.items():
            self.write("demo.json", d)
            self.assertFalse(self.v.demo_evidence()[0], label)

    def test_demo_needs_a_verifiable_event_store(self):
        self.write("demo.json", self.demo())
        self.db.unlink()
        self.assertFalse(self.v.demo_evidence()[0])

    def test_channel_pass_needs_fresh_host_bound_corroborated_nonce(self):
        self.write("channel.json", self.chan())
        with mock.patch.object(self.v, "live_sandboxes", return_value=[]):
            status, _ = self.v.channel_gate(self.TOOLS)
        self.assertEqual(status, "PASS")

    def test_bare_channel_file_is_capped_at_not_tested(self):
        base = self.chan()
        for label, d in {
            "legacy shape, no host/ts/nonce": {k: base[k] for k in ("is_live", "openclaw_managed", "type", "round_trip")},
            "uncorroborated nonce": self.chan(nonce="nonce-never-seen-anywhere"),
            "short nonce": self.chan(nonce="abc"),
            "foreign host": self.chan(host="elsewhere"),
            "stale": self.chan(timestamp=_iso(-48 * 3600)),
            "not live": self.chan(is_live=False),
        }.items():
            self.write("channel.json", d)
            with mock.patch.object(self.v, "live_sandboxes", return_value=[]):
                status, detail = self.v.channel_gate(self.TOOLS)
            self.assertEqual(status, "NOT TESTED", f"{label}: {detail}")

    def test_channel_nonce_can_be_corroborated_by_nemoclaw_listing(self):
        self.write("channel.json", self.chan(nonce="only-in-nemoclaw-listing"))
        with mock.patch.object(self.v, "live_sandboxes", return_value=[{"name": "box1"}]), \
                mock.patch.object(self.v, "run", return_value=(0, "discord  ok  only-in-nemoclaw-listing")) as run:
            status, _ = self.v.channel_gate({"nemoclaw": "/x/nemoclaw"})
        self.assertEqual(status, "PASS")
        self.assertEqual(run.call_args[0][0][1:], ["box1", "channels", "list"])

    def test_end_to_end_run_writes_rows_meta_and_never_passes_h05_h06_from_bare_files(self):
        art = self.tmp / "e2e"
        art.joinpath("runtime-verification").mkdir(parents=True)
        art.joinpath("runtime-verification", "channel.json").write_text(json.dumps(
            {"is_live": True, "openclaw_managed": True, "type": "discord", "round_trip": "yes"}))
        art.joinpath("runtime-verification", "demo.json").write_text(json.dumps({"is_live": True}))
        env = {**os.environ, "PHANTOMSHIFT_ARTIFACTS": str(art)}
        p = subprocess.run([sys.executable, str(ROOT / "scripts/verify_hackathon.py"), "--mode", "prep"],
                           capture_output=True, text=True, cwd=ROOT, env=env)
        self.assertEqual(p.returncode, 0, p.stderr)
        rows = json.loads((art / "runtime-verification" / "verify.json").read_text())
        status = {r["id"]: r["status"] for r in rows}
        self.assertEqual(status["H05"], "NOT TESTED")
        self.assertEqual(status["H06"], "NOT TESTED")
        meta = json.loads((art / "runtime-verification" / "verify.meta.json").read_text())
        self.assertEqual(meta["host"], socket.gethostname())
        dt.datetime.fromisoformat(meta["generated_at"])
        import hashlib
        canon = json.dumps(rows, sort_keys=True, separators=(",", ":"))
        self.assertEqual(meta["gates_sha256"], hashlib.sha256(canon.encode()).hexdigest())
        self.assertTrue(all(r["host"] == socket.gethostname() and r["generated_at"] == meta["generated_at"] for r in rows))

    def test_h06_does_not_pass_from_h02_alone(self):
        """Reviewer's t9: pretend to be a GB10 (aarch64 + 'GB10' GPU name) with no demo evidence."""
        shim = self.tmp / "bin"
        shim.mkdir()
        smi = shim / "nvidia-smi"
        smi.write_text('#!/bin/sh\necho "NVIDIA GB10, 570.1, 131072 MiB"\n')
        smi.chmod(smi.stat().st_mode | stat.S_IXUSR)
        art = self.tmp / "gb10art"
        art.mkdir()
        code = ("import platform, runpy, sys\nplatform.machine = lambda: 'aarch64'\n"
                f"sys.argv = ['verify_hackathon.py', '--mode', 'prep']\n"
                f"runpy.run_path({str(ROOT / 'scripts/verify_hackathon.py')!r}, run_name='__main__')\n")
        env = {**os.environ, "PHANTOMSHIFT_ARTIFACTS": str(art), "PATH": f"{shim}:{os.environ['PATH']}"}
        p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT, env=env)
        self.assertEqual(p.returncode, 0, p.stderr)
        rows = {r["id"]: r["status"] for r in json.loads((art / "runtime-verification" / "verify.json").read_text())}
        self.assertEqual(rows["H02"], "PASS")
        self.assertEqual(rows["H06"], "NOT TESTED")

    def test_gb10_detection_uses_gpu_name_field_only(self):
        src = (ROOT / "scripts" / "verify_hackathon.py").read_text()
        self.assertIn('g.split(",")[0].upper()', src)


# --------------------------------------------------------------------------- F. shell scripts
BASH = shutil.which("bash")
REAL_RSYNC = shutil.which("rsync")
PLANTED = [".env", ".envrc", "prod.env", "id_ed25519", ".netrc", "config/secrets.json", "token.txt", "server.pem", "tls.key",
           "link_to_env", "artifacts/events.sqlite", "artifacts/events.sqlite-wal", "artifacts/runtime-verification/verify.json",
           "artifacts/runtime-verification/discord-preflight.json", "artifacts/runtime-verification/verify.meta.json",
           "phantomshift/token_cache.txt", "phantomshift/prod.env", "scripts/id_rsa", "docs/server.key", "docs/notes.pem",
           "fixtures/inbox/job.json", "stray_dir/anything.py", "stray.txt", "tests/.env.local"]
SHIPPED = ["phantomshift/ok.py", "scripts/sync_to_gb10.sh", "scripts/ship.include", "tests/test_x.py", "docs/A.md", "README.md",
           ".env.example", "fixtures/samples/log_secret_post.json", "fixtures/README.md", "openclaw-integration/README.md",
           "offline-kit/README.md"]


def _plant(root: Path, with_scripts=True):
    for rel in PLANTED + [s for s in SHIPPED if not s.startswith("scripts/")]:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x\n")
    if with_scripts:
        (root / "scripts").mkdir(exist_ok=True)
        for n in ("sync_to_gb10.sh", "package_offline.sh", "preflight_gb10.sh", "ship.include"):
            shutil.copy(ROOT / "scripts" / n, root / "scripts" / n)
    (root / "link_to_env").unlink()
    os.symlink(".env", root / "link_to_env")


def _exe(path: Path, text: str):
    path.write_text(text)
    path.chmod(0o755)


class ShellSyntaxTests(unittest.TestCase):
    @unittest.skipUnless(BASH, "bash missing")
    def test_bash_n(self):
        for n in ("sync_to_gb10.sh", "package_offline.sh", "preflight_gb10.sh"):
            p = subprocess.run([BASH, "-n", str(ROOT / "scripts" / n)], capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, f"{n}: {p.stderr}")

    def test_ship_list_is_an_allow_list_ending_in_deny_all(self):
        lines = [l.strip() for l in (ROOT / "scripts/ship.include").read_text().splitlines() if l.strip() and not l.startswith("#")]
        self.assertEqual(lines[-1], "- *")
        for must in ("- .env", "- .env.*", "- *.pem", "- *.key", "- discord-preflight.json", "- events.sqlite*", "- verify.json"):
            self.assertIn(must, lines)


@unittest.skipUnless(BASH and REAL_RSYNC, "bash and rsync required")
class SyncScriptTests(unittest.TestCase):
    def setUp(self):
        # A path containing a space, like the real checkout, to catch quoting bugs.
        self.tmp = Path(tempfile.mkdtemp(prefix="sync test "))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = self.tmp / "proj"
        self.root.mkdir()
        _plant(self.root)
        self.shim = self.tmp / "shim"
        self.shim.mkdir()
        self.dest = self.tmp / "dest"
        self.dest.mkdir()
        self.log = self.tmp / "log.txt"
        _exe(self.shim / "ssh", '#!/bin/bash\nprintf "SSH" >> "$LOG"; printf " [%s]" "$@" >> "$LOG"; echo >> "$LOG"\n'
                                'case "$*" in *"uname -m"*) echo aarch64;; esac\n')
        _exe(self.shim / "rsync", '#!/bin/bash\nprintf "RSYNC" >> "$LOG"; printf " [%s]" "$@" >> "$LOG"; echo >> "$LOG"\n'
                                  'args=(); skip=0\nfor a in "$@"; do\n  if [ $skip = 1 ]; then skip=0; continue; fi\n'
                                  '  case "$a" in -e) skip=1; continue;; *:~/PHANTOMSHIFT/) a="$DEST/";; esac\n  args+=("$a")\ndone\n'
                                  'exec "$REAL_RSYNC" "${args[@]}"\n')

    def run_sync(self, *args, **env):
        e = {**os.environ, "PATH": f"{self.shim}:{os.environ['PATH']}", "LOG": str(self.log), "DEST": str(self.dest),
             "REAL_RSYNC": REAL_RSYNC, "HOME": str(self.tmp)}
        e.pop("GB10_HOST", None)
        e.pop("GB10_JUMP", None)
        e.update(env)
        return subprocess.run([BASH, str(self.root / "scripts/sync_to_gb10.sh"), *args], capture_output=True, text=True, env=e)

    def shipped_files(self):
        return sorted(str(p.relative_to(self.dest)) for p in self.dest.rglob("*") if p.is_file() or p.is_symlink())

    def test_only_allow_listed_files_are_sent(self):
        p = self.run_sync(GB10_HOST="demo@10.0.0.5")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        got = self.shipped_files()
        for rel in SHIPPED:
            self.assertIn(rel, got)
        for rel in PLANTED:
            self.assertNotIn(rel, got, f"{rel} was shipped")
        self.assertFalse((self.dest / "stray_dir").exists())
        self.assertFalse((self.dest / "config").exists())
        # artifacts: only benchmark JSON and the readiness summary may ship; run records, the event DB and
        # runtime-verification evidence (host-bound) must stay home.
        for rel in got:
            if rel.startswith("artifacts/"):
                self.assertTrue(rel == "artifacts/readiness.json" or (rel.startswith("artifacts/benchmarks/") and rel.endswith(".json")), rel)
        self.assertTrue((self.dest / "fixtures/inbox").is_dir() and not list((self.dest / "fixtures/inbox").iterdir()))

    def test_arguments_are_separated_and_jump_is_in_ssh_opts(self):
        p = self.run_sync("--dry-run", GB10_HOST="demo@10.0.0.5", GB10_JUMP="me@laptop")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        log = self.log.read_text()
        ssh_line = next(l for l in log.splitlines() if l.startswith("SSH"))
        self.assertIn("[-J] [me@laptop]", ssh_line)
        self.assertIn("[StrictHostKeyChecking=accept-new]", ssh_line)
        self.assertIn("[--] [demo@10.0.0.5] [uname -m]", ssh_line)
        rs = next(l for l in log.splitlines() if l.startswith("RSYNC"))
        self.assertIn("[--dry-run]", rs)
        self.assertIn("-J me@laptop", rs)  # inside the single -e string
        self.assertIn("--exclude-from=", rs)
        self.assertLess(rs.index("[--]"), rs.index("demo@10.0.0.5:~/PHANTOMSHIFT/"))
        self.assertEqual(self.shipped_files(), [], "dry run must not copy")
        self.assertIn("trust-on-first-use", p.stderr)
        self.assertIn("ssh-keygen", p.stderr)

    def test_hostile_host_values_are_refused_before_anything_runs(self):
        bad = ["-oProxyCommand=touch /tmp/pwn", "-oFoo", "a b", "host;rm -rf /", "user@-oFoo", "$(id)", "h`id`", "x\ny", "a'b", "host:22"]
        for h in bad:
            self.log.write_text("")
            p = self.run_sync(GB10_HOST=h)
            self.assertEqual(p.returncode, 2, f"{h!r}: {p.stderr}")
            self.assertEqual(self.log.read_text(), "", f"{h!r} reached ssh/rsync")
        for j in ("-oProxyCommand=x", "me@lap top", "a;b", "$(x)"):
            p = self.run_sync(GB10_HOST="demo@10.0.0.5", GB10_JUMP=j)
            self.assertEqual(p.returncode, 2, j)
            self.assertEqual(self.log.read_text(), "")

    def test_valid_host_forms_accepted(self):
        for h in ("gb10", "demo@10.0.0.5", "user.name@gb10-1.local", "a_b@h"):
            self.assertEqual(self.run_sync("--dry-run", GB10_HOST=h).returncode, 0, h)


@unittest.skipUnless(BASH and REAL_RSYNC, "bash and rsync required")
class PackageOfflineTests(unittest.TestCase):
    def test_tarball_uses_the_same_allow_list(self):
        tmp = Path(tempfile.mkdtemp(prefix="pkg test "))
        self.addCleanup(shutil.rmtree, tmp, True)
        root = tmp / "proj"
        root.mkdir()
        _plant(root)
        p = subprocess.run([BASH, str(root / "scripts/package_offline.sh"), "build"], capture_output=True, text=True,
                           env={**os.environ, "HOME": str(tmp)})
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        with tarfile.open(tmp / "offline-stage/phantomshift-starter.tar.gz") as tf:
            names = {n.split("/", 1)[1] for n in tf.getnames() if "/" in n}
        for rel in SHIPPED:
            self.assertIn(rel, names)
        for rel in PLANTED:
            self.assertNotIn(rel, names, f"{rel} was packaged")
        self.assertTrue((tmp / "offline-stage/manifest.sha256").exists())


@unittest.skipUnless(BASH, "bash missing")
class PreflightJsonTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pre test "))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = self.tmp / "repo"
        (self.repo / "scripts").mkdir(parents=True)
        shutil.copy(ROOT / "scripts/preflight_gb10.sh", self.repo / "scripts/preflight_gb10.sh")
        self.shim = self.tmp / "bin"
        self.shim.mkdir()
        _exe(self.shim / "docker", "#!/bin/sh\nexit 1\n")  # never talk to a real docker daemon
        _exe(self.shim / "uname", '#!/bin/sh\n[ "$1" = "-m" ] && echo aarch64 || echo Linux\n')

    def smi(self, name, driver):
        _exe(self.shim / "nvidia-smi", f"""#!/bin/sh
case "$*" in
  *"query-gpu=name --format"*) printf '%s\\n' '{name}' ;;
  *) printf '%s\\n' '{name}, {driver}, 12.1 GiB, 12.1' ;;
esac
""")

    def run_pre(self, no_python=False):
        env = {"PATH": f"{self.shim}:/usr/bin:/bin", "HOME": str(self.tmp)}
        if no_python:
            env["PREFLIGHT_NO_PYTHON"] = "1"
        p = subprocess.run([BASH, str(self.repo / "scripts/preflight_gb10.sh")], capture_output=True, text=True, env=env)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads((self.repo / "artifacts/preflight/gb10.json").read_text()), p.stdout

    def test_valid_json_with_quotes_and_backslashes_both_paths(self):
        self.smi('NVIDIA "GB9" back\\slash', 'drv"1\\2')
        for no_py in (False, True):
            data, _ = self.run_pre(no_py)
            self.assertIn('"GB9" back\\slash', data["gpu"], no_py)
            self.assertEqual(data["arch"], "aarch64")
            self.assertIsInstance(data["ram_gib"], int)

    def test_gb10_match_is_gpu_name_only(self):
        self.smi("NVIDIA GeForce RTX 9090", "GB10-driver")  # GB10 only in the driver field
        for no_py in (False, True):
            data, out = self.run_pre(no_py)
            self.assertEqual(data["looks_like_gb10"], "no", no_py)
            self.assertIn("GB10: NO", out)
        self.smi("NVIDIA GB10", "580.1")
        data, out = self.run_pre()
        self.assertEqual(data["looks_like_gb10"], "likely")
        self.assertIn("GB10: likely", out)

    def test_old_heuristics_no_longer_match(self):
        self.smi("NVIDIA Blackwell Something", "12.1")  # old code accepted Blackwell or "12.1" anywhere in the line
        data, _ = self.run_pre()
        self.assertEqual(data["looks_like_gb10"], "no")


if __name__ == "__main__":
    unittest.main()
