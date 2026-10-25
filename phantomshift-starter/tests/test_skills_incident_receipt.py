"""Tests for skills/agent-incident-receipt. Scripts are loaded by path and also run as subprocesses."""

import copy
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "agent-incident-receipt"
SCRIPT = SKILL / "scripts" / "incident_receipt.py"
EX = SKILL / "examples"

spec = importlib.util.spec_from_file_location("incident_receipt_under_test", SCRIPT)
ir = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ir
_old_flag = sys.dont_write_bytecode
sys.dont_write_bytecode = True  # do not leave __pycache__ inside the skill package
spec.loader.exec_module(ir)
sys.dont_write_bytecode = _old_flag

# Fake credentials assembled at runtime so no real-looking secret sits in the source.
FAKE_OPENAI = "sk-" + "Ab1Cd2Ef" * 4
FAKE_PROJ = "sk-proj-" + "Qq7Ww8Ee" * 4
FAKE_DISCORD = "N" + "x" * 24 + "." + "y" * 6 + "." + "z" * 30
FAKE_AWS = "AKIA" + "B7C8D9E0F1G2H3J4"
FAKE_AWS_SECRET = "wJalrXUtnFEMI" + "/K7MDENG/bPxRfiCY" + "EXAMPLEKEY"  # 40 characters
FAKE_BEARER = "Bearer " + "Tt5Uu6Vv7Ww8" * 3
FAKE_PEM = "-----BEGIN " + "RSA " + "PRIVATE KEY-----\n" + "MIIBOgIBAAJBAKfakefakefake\n" + "abcdefghijklmnop\n" + "-----END " + "RSA " + "PRIVATE KEY-----"
FAKE_GH = "ghp_" + "a1B2c3D4e5" * 4
FAKE_EMAIL = "someone.private@example.org"
ALL_FAKES = [FAKE_OPENAI, FAKE_PROJ, FAKE_DISCORD, FAKE_AWS, FAKE_AWS_SECRET, FAKE_BEARER.split()[1], "MIIBOgIBAAJBAKfakefakefake",
             "abcdefghijklmnop", FAKE_GH]


def run_cli(*args, stdin=None):
    return subprocess.run([sys.executable, str(SCRIPT), *args], input=stdin, capture_output=True, text=True, timeout=60)


def incident(**over):
    base = {
        "incident_id": "INC-T-1",
        "observations": [{"seq": 1, "text": "benign observation"}],
        "policy_before": {"name": "baseline", "deny_tools": []},
        "policy_after": {"name": "context_bound", "deny_tools": [], "bind_params": {"pay_invoice": ["account"]}},
        "approval": {"actor": "operator-1", "state": "approved"},
        "test_results": {"replay": "6/6"},
    }
    base.update(over)
    return base


assert len(FAKE_AWS_SECRET) == 40


class PackageShapeTests(unittest.TestCase):
    def test_skill_package_format(self):
        text = (SKILL / "SKILL.md").read_text()
        m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
        self.assertIsNotNone(m)
        self.assertRegex(m.group(1), r"(?m)^name: agent-incident-receipt$")
        self.assertRegex(m.group(1), r"(?m)^description: .{40,}")
        self.assertIn("MIT License", (SKILL / "LICENSE").read_text())
        for p in SKILL.rglob("*"):
            self.assertFalse(p.is_symlink(), p)
            self.assertFalse(p.name.startswith("."), p)
            self.assertRegex(str(p.relative_to(SKILL)), r"^[A-Za-z0-9._\-/]+$")
        for section in ("When to use", "Inputs", "Outputs", "Safety rules", "CLI usage", "Limits"):
            self.assertIn(section, text)

    def test_hash_is_not_a_signature_statement_is_everywhere(self):
        skill_md = (SKILL / "SKILL.md").read_text()
        self.assertIn("NOT a digital signature", skill_md)
        self.assertIn("NOT an immutable log", skill_md)
        self.assertIn("NOT a digital signature", ir.NOTICE)
        self.assertIn("NOT an immutable log", ir.NOTICE)
        receipt = ir.build_receipt(incident())
        self.assertIn("NOT a digital signature", receipt["notice"])
        self.assertIn("NOT an immutable log", receipt["notice"])
        self.assertIn("NOT a signature", receipt["provenance_label"])
        self.assertIn("NOT a digital signature", ir.verify_receipt(receipt)["notice"])

    def test_script_is_standalone_and_has_no_risky_constructs(self):
        src = SCRIPT.read_text()
        self.assertNotIn("phantomshift", src)
        for needle in ("subprocess", "urllib.request", "socket", "os.environ", "eval(", "exec(", "import time", "import random"):
            self.assertNotIn(needle, src)


class RedactionTests(unittest.TestCase):
    def red(self, text, emails=False):
        counts = {}
        return ir.redact_text(text, counts, emails), counts

    def test_each_token_shape_is_redacted(self):
        cases = {
            "openai_like_key": [FAKE_OPENAI, FAKE_PROJ],
            "discord_token": [FAKE_DISCORD],
            "aws_access_key": [FAKE_AWS],
            "bearer_token": [FAKE_BEARER],
            "private_key": [FAKE_PEM],
            "github_token": [FAKE_GH],
        }
        for kind, samples in cases.items():
            for sample in samples:
                out, counts = self.red(f"before {sample} after")
                self.assertIn(f"[REDACTED:{kind}]", out, kind)
                self.assertEqual(counts.get(kind), 1, (kind, counts))
                secret = sample.split()[-1] if kind == "bearer_token" else sample
                self.assertNotIn(secret, out)
                self.assertTrue(out.startswith("before ") and out.endswith(" after"))

    def test_aws_secret_assignment_and_generic_assignment(self):
        out, counts = self.red(f"aws_secret_access_key = {FAKE_AWS_SECRET}")
        self.assertNotIn(FAKE_AWS_SECRET, out)
        self.assertEqual(counts, {"aws_secret_key": 1})
        k_val = "".join(["abc", "def", "gh12345"])
        k_label = "".join(["api", "_", "key: "])
        out, counts = self.red(f'password="hunter2hunter2" and {k_label}{k_val}')
        self.assertNotIn("hunter2hunter2", out)
        self.assertNotIn(k_val, out)
        self.assertEqual(counts["secret_assignment"], 2)
        self.assertIn("password=", out)  # the key name stays, the value goes

    def test_assignment_does_not_double_count_an_already_redacted_value(self):
        out, counts = self.red(f"token={FAKE_OPENAI}")
        self.assertEqual(counts, {"openai_like_key": 1})

    def test_unterminated_private_key_block_is_redacted_to_the_end(self):
        out, counts = self.red("x -----BEGIN " + "PRIVATE KEY-----\nMIIEvQIBADANBgkq" + "A" * 50)
        self.assertEqual(counts, {"private_key": 1})
        self.assertNotIn("MIIEvQ", out)
        self.assertTrue(out.startswith("x "))

    def test_emails_are_optional(self):
        out, counts = self.red(f"mail {FAKE_EMAIL}")
        self.assertIn(FAKE_EMAIL, out)
        out, counts = self.red(f"mail {FAKE_EMAIL}", emails=True)
        self.assertNotIn(FAKE_EMAIL, out)
        self.assertEqual(counts, {"email": 1})

    def test_ordinary_text_is_untouched(self):
        text = "Pay invoice INV-2291 to account 000998774417; the task is sk-learn related. Total $24,800."
        out, counts = self.red(text)
        self.assertEqual((out, counts), (text, {}))

    def test_keys_and_nested_values_are_redacted(self):
        counts = {}
        out = ir.redact_value({FAKE_OPENAI: [{"a": FAKE_DISCORD}], "n": 5, "t": True, "z": None}, counts)
        blob = json.dumps(out)
        self.assertNotIn(FAKE_OPENAI, blob)
        self.assertNotIn(FAKE_DISCORD, blob)
        self.assertEqual((out["n"], out["t"], out["z"]), (5, True, None))
        self.assertEqual(sum(counts.values()), 2)

    def test_colliding_redacted_keys_do_not_drop_data(self):
        out = ir.redact_value({FAKE_OPENAI: 1, "sk-" + "Zz9Yy8Xx" * 4: 2}, {})
        self.assertEqual(sorted(out.values()), [1, 2])


class BuildAndVerifyTests(unittest.TestCase):
    def planted(self):
        return incident(
            observations=[{"seq": 1, "text": f"keys {FAKE_OPENAI} {FAKE_DISCORD} {FAKE_AWS} {FAKE_BEARER}"},
                          {"seq": 2, "text": FAKE_PEM}, {"seq": 3, "text": f"aws_secret_access_key={FAKE_AWS_SECRET}"}, FAKE_GH],
            approval={"actor": "op", "note": f"approved via {FAKE_PROJ}"},
            test_results={"log": f"Authorization: {FAKE_BEARER}", "contact": FAKE_EMAIL},
        )

    def test_receipt_redacts_a_planted_fake_token_and_verify_detects_tampering(self):
        receipt = ir.build_receipt(self.planted(), redact_emails=True)
        blob = json.dumps(receipt)
        for secret in ALL_FAKES + [FAKE_EMAIL]:
            self.assertNotIn(secret, blob)
        self.assertGreaterEqual(receipt["redaction"]["total"], 8)
        for kind in ("openai_like_key", "discord_token", "aws_access_key", "bearer_token", "private_key"):
            self.assertIn(kind, receipt["redaction"]["redactions_by_kind"])
        ok = ir.verify_receipt(receipt)
        self.assertTrue(ok["ok"], ok)
        self.assertEqual(ok["unredacted_secret_shapes"], 0)
        self.assertEqual(ok["claimed_digest"], ok["recomputed_digest"])
        # tamper with each part in turn
        for mutate, expected in (
            (lambda r: r["sections"]["observations"].append({"seq": 9}), "section:observations"),
            (lambda r: r["sections"]["policy_diff"].update(added={}), "section:policy_diff"),
            (lambda r: r["sections"]["approval"].update(actor="attacker"), "section:approval"),
            (lambda r: r["sections"]["test_results"].update(replay="0/6"), "section:test_results"),
            (lambda r: r["redaction"].update(total=0), "digest"),
            (lambda r: r.update(incident_id="INC-OTHER"), "digest"),
            (lambda r: r.update(digest="0" * 64), "digest"),
            (lambda r: r["section_digests"].update(approval="0" * 64), "section:approval"),
        ):
            bad = copy.deepcopy(receipt)
            mutate(bad)
            res = ir.verify_receipt(bad)
            self.assertFalse(res["ok"], expected)
            self.assertIn(expected, res["mismatches"])

    def test_digest_is_deterministic_and_key_order_independent(self):
        a = ir.build_receipt(incident())
        b = ir.build_receipt(dict(reversed(list(incident().items()))))
        self.assertEqual(a["digest"], b["digest"])
        self.assertEqual(ir.build_receipt(incident())["digest"], a["digest"])
        self.assertNotEqual(ir.build_receipt(incident(observations=[{"seq": 2}]))["digest"], a["digest"])

    def test_digest_is_over_redacted_content(self):
        a = ir.build_receipt(incident(observations=[{"t": FAKE_OPENAI}]))
        b = ir.build_receipt(incident(observations=[{"t": "sk-" + "Zz9Yy8Xx" * 4}]))
        self.assertEqual(a["digest"], b["digest"], "two different secrets collapse to the same redacted receipt")

    def test_a_hash_is_not_a_signature_an_editor_can_recompute_it(self):
        receipt = ir.build_receipt(incident())
        forged = copy.deepcopy(receipt)
        forged["sections"]["approval"]["actor"] = "attacker"
        self.assertFalse(ir.verify_receipt(forged)["ok"])
        # an attacker with write access recomputes every digest and verify cannot tell
        forged["section_digests"], forged["digest"] = ir._digests(forged)
        self.assertTrue(ir.verify_receipt(forged)["ok"])
        self.assertIn("anchor", forged["notice"])

    def test_verify_warns_about_secret_shapes_inserted_later(self):
        receipt = ir.build_receipt(incident())
        receipt["sections"]["observations"][0]["text"] = FAKE_OPENAI
        res = ir.verify_receipt(receipt)
        self.assertFalse(res["ok"])
        self.assertEqual(res["unredacted_secret_shapes"], 1)
        self.assertNotIn(FAKE_OPENAI, json.dumps(res))

    def test_policy_diff_forms(self):
        r = ir.build_receipt(incident())
        diff = r["sections"]["policy_diff"]
        self.assertEqual(diff["changed"]["name"], {"from": "baseline", "to": "context_bound"})
        self.assertEqual(diff["added"], {"bind_params": {"pay_invoice": ["account"]}})
        explicit = {k: v for k, v in incident().items() if k not in ("policy_before", "policy_after")}
        explicit["policy_diff"] = {"note": "manual"}
        self.assertEqual(ir.build_receipt(explicit)["sections"]["policy_diff"], {"note": "manual"})
        both = dict(incident(), policy_diff={})
        with self.assertRaises(ir.ReceiptError):
            ir.build_receipt(both)

    def test_approval_may_be_null_but_is_never_invented(self):
        r = ir.build_receipt(incident(approval=None))
        self.assertIsNone(r["sections"]["approval"])
        self.assertTrue(ir.verify_receipt(r)["ok"])
        with self.assertRaises(ir.ReceiptError):
            ir.build_receipt({k: v for k, v in incident().items() if k != "approval"})

    def test_input_validation(self):
        bad = [None, [], incident(incident_id="has space"), incident(incident_id=""), incident(observations="text"),
               incident(surprise=1), incident(test_results="ok"), incident(approval="yes"),
               {k: v for k, v in incident().items() if k not in ("policy_before", "policy_after")},
               incident(observations=[float("nan")])]
        for doc in bad:
            with self.assertRaises(ir.ReceiptError, msg=repr(doc)[:60]):
                ir.build_receipt(doc)

    def test_verify_rejects_malformed_receipts(self):
        for bad in (None, [], {}, {"receipt_version": "other"}, dict(ir.build_receipt(incident()), sections={}),
                    dict(ir.build_receipt(incident()), section_digests=[])):
            res = ir.verify_receipt(bad)
            self.assertFalse(res["ok"])
            self.assertTrue(res["mismatches"])


class CliTests(unittest.TestCase):
    def test_example_round_trip_and_tamper(self):
        raw = (EX / "incident.json").read_text()
        for fake in ("FAKEFAKEFAKEFAKEFAKE0000", "MFAKEFAKEFAKEFAKEFAKEFAKE.FAKE00.", "sk-EXAMPLEEXAMPLE", "AKIAFAKEFAKEFAKEFAKE", "ops@evil.example"):
            self.assertIn(fake, raw, "the example input plants fake secrets on purpose")
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "receipt.json"
            p = run_cli("build", "--input", str(EX / "incident.json"), "--redact-emails", "--out", str(out))
            self.assertEqual(p.returncode, 0, p.stderr)
            receipt = json.loads(p.stdout)
            self.assertEqual(json.loads(out.read_text()), receipt)
            for fake in ("FAKEFAKEFAKEFAKEFAKE0000", "MFAKEFAKEFAKEFAKEFAKEFAKE", "EXAMPLEEXAMPLE", "AKIAFAKEFAKE", "ops@evil.example"):
                self.assertNotIn(fake, p.stdout)
            for kind in ("discord_token", "openai_like_key", "aws_access_key", "bearer_token", "email"):
                self.assertIn(f"[REDACTED:{kind}]", p.stdout)
            self.assertIn("NOT a digital signature", p.stdout)
            v = run_cli("verify", "--receipt", str(out))
            self.assertEqual(v.returncode, 0, v.stdout)
            self.assertTrue(json.loads(v.stdout)["ok"])
            self.assertIn("NOT an immutable log", v.stdout)
            tampered = json.loads(out.read_text())
            tampered["sections"]["test_results"]["replay"]["harmful_blocked"] = "0/6"
            out.write_text(json.dumps(tampered))
            v = run_cli("verify", "--receipt", str(out))
            self.assertEqual(v.returncode, 1)
            res = json.loads(v.stdout)
            self.assertFalse(res["ok"])
            self.assertIn("section:test_results", res["mismatches"])
            self.assertIn("digest", res["mismatches"])

    def test_emails_not_redacted_by_default(self):
        p = run_cli("build", "--input", str(EX / "incident.json"))
        self.assertIn("ops@evil.example", p.stdout)
        self.assertNotIn("FAKEFAKEFAKEFAKEFAKE0000", p.stdout)

    def test_stdin_and_digest_stability_across_processes(self):
        raw = (EX / "incident.json").read_text()
        d1 = json.loads(run_cli("build", "--input", "-", stdin=raw).stdout)["digest"]
        d2 = json.loads(run_cli("build", "--input", str(EX / "incident.json")).stdout)["digest"]
        self.assertEqual(d1, d2)

    def test_bad_input_exit_2(self):
        for stdin in ("nope", '{"incident_id": "a", "incident_id": "b"}', '{"x": NaN}', "{}"):
            p = run_cli("build", "--input", "-", stdin=stdin)
            self.assertEqual(p.returncode, 2, stdin)
            self.assertIn("error", json.loads(p.stdout))
        self.assertEqual(run_cli("verify", "--receipt", str(EX / "missing.json")).returncode, 2)

    def test_verify_malformed_receipt_exit_1(self):
        p = run_cli("verify", "--receipt", "-", stdin="{}")
        self.assertEqual(p.returncode, 1)


if __name__ == "__main__":
    unittest.main()
