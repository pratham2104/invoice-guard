"""Tests for skills/counterfactual-policy-replay. Scripts are loaded by path and also run as subprocesses."""

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
SKILL = ROOT / "skills" / "counterfactual-policy-replay"
SCRIPT = SKILL / "scripts" / "policy_replay.py"
EX = SKILL / "examples"

spec = importlib.util.spec_from_file_location("policy_replay_under_test", SCRIPT)
pr = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = pr
_old_flag = sys.dont_write_bytecode
sys.dont_write_bytecode = True  # do not leave __pycache__ inside the skill package
spec.loader.exec_module(pr)
sys.dont_write_bytecode = _old_flag

FIXTURES = json.loads((EX / "fixtures.json").read_text())
POLICIES = json.loads((EX / "policies.json").read_text())


def cell(m, key):
    c = m[key]
    return c["numerator"], c["denominator"]


def by_name(result):
    return {m["policy"]: m for m in result["matrix"]}


def run_cli(*args, stdin=None):
    return subprocess.run([sys.executable, str(SCRIPT), *args], input=stdin, capture_output=True, text=True, timeout=60)


def fx(id, kind, tool="send_email", args=None, prov=None, labels=()):
    return {"id": id, "kind": kind, "expected": "allow" if kind == "benign" else "deny",
            "action": {"tool": tool, "args": args or {"to": "dana@customer.example", "body": "x"},
                       "prov": prov if prov is not None else {"to": "registry"}, "labels": list(labels)}}


def pol_set(*extra):
    base = [{"name": "p_all", "type": "allow_all"},
            {"name": "p_lock", "type": "deny_all_sensitive", "sensitive_tools": ["send_email"]},
            {"name": "p_allow", "type": "allowlist", "egress_params": {"send_email": "to"}, "allowed_domains": ["customer.example"]}]
    return {"policies": base + list(extra)}


class PackageShapeTests(unittest.TestCase):
    def test_skill_package_format(self):
        text = (SKILL / "SKILL.md").read_text()
        m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
        self.assertIsNotNone(m)
        self.assertRegex(m.group(1), r"(?m)^name: counterfactual-policy-replay$")
        self.assertRegex(m.group(1), r"(?m)^description: .{40,}")
        self.assertIn("MIT License", (SKILL / "LICENSE").read_text())
        for p in SKILL.rglob("*"):
            self.assertFalse(p.is_symlink(), p)
            self.assertFalse(p.name.startswith("."), p)
            self.assertRegex(str(p.relative_to(SKILL)), r"^[A-Za-z0-9._\-/]+$")
        for section in ("When to use", "Inputs", "Outputs", "Safety rules", "CLI usage", "Limits"):
            self.assertIn(section, text)

    def test_script_is_standalone_and_has_no_risky_constructs(self):
        src = SCRIPT.read_text()
        self.assertNotIn("phantomshift", src)
        for needle in ("subprocess", "urllib.request", "socket", "os.environ", "eval(", "exec(", "import random", "import time"):
            self.assertNotIn(needle, src)

    def test_examples_have_at_least_three_policies_and_both_kinds(self):
        self.assertGreaterEqual(len(POLICIES["policies"]), 3)
        self.assertEqual({p["type"] for p in POLICIES["policies"]} >= {"deny_all_sensitive", "allowlist", "context_bound"}, True)
        kinds = {f["kind"] for f in FIXTURES["fixtures"]}
        self.assertEqual(kinds, {"benign", "malicious"})


class MatrixTests(unittest.TestCase):
    def setUp(self):
        self.result = pr.replay(FIXTURES, POLICIES, require_lock=True)
        self.m = by_name(self.result)

    def test_matrix_numerators_and_denominators(self):
        self.assertEqual(self.result["fixture_counts"], {"malicious": 6, "benign": 6})
        expect = {"baseline": ((0, 6), (6, 6), (0, 6)), "lockdown": ((6, 6), (2, 6), (4, 6)),
                  "allowlist": ((2, 6), (6, 6), (0, 6)), "context_bound": ((6, 6), (6, 6), (0, 6))}
        for name, (blocked, kept, denied) in expect.items():
            self.assertEqual(cell(self.m[name], "harmful_blocked"), blocked, name)
            self.assertEqual(cell(self.m[name], "legit_preserved"), kept, name)
            self.assertEqual(cell(self.m[name], "false_denials"), denied, name)
            self.assertEqual(cell(self.m[name], "harmful_executed")[0] + blocked[0], 6)

    def test_only_context_bound_is_a_successful_remediation(self):
        self.assertEqual(self.result["successful_policies"], ["context_bound"])
        self.assertEqual(self.m["context_bound"]["remediation_label"], pr.LABEL_OK)
        self.assertEqual(self.m["lockdown"]["remediation_label"], pr.LABEL_FALSE_DENIALS)
        self.assertEqual(self.m["allowlist"]["remediation_label"], pr.LABEL_MISSES)
        self.assertEqual(self.m["baseline"]["remediation_label"], pr.LABEL_MISSES)

    def test_policy_that_fails_any_legitimate_fixture_is_never_successful(self):
        # blocks every attack but false-denies exactly one legitimate fixture
        fixtures = {"fixtures": [fx("m1", "malicious", args={"to": "evil@evil.example", "body": "x"}, prov={"to": "untrusted"}),
                                 fx("b1", "benign"), fx("b2", "benign", args={"to": "lead@acme.example", "body": "x"})]}
        strict = {"name": "strict", "type": "allowlist", "egress_params": {"send_email": "to"}, "allowed_domains": ["customer.example"]}
        res = pr.replay(fixtures, pol_set(strict))
        m = by_name(res)["strict"]
        self.assertEqual(cell(m, "harmful_blocked"), (1, 1))
        self.assertEqual(cell(m, "false_denials"), (1, 2))
        self.assertFalse(m["successful_remediation"])
        self.assertEqual(m["remediation_label"], pr.LABEL_FALSE_DENIALS)
        self.assertNotIn("strict", res["successful_policies"])

    def test_false_denials_dominate_misses(self):
        fixtures = {"fixtures": [fx("m1", "malicious", args={"to": "evil@customer.example", "body": "x"}, prov={"to": "untrusted"}),
                                 fx("b1", "benign", args={"to": "lead@acme.example", "body": "x"})]}
        res = pr.replay(fixtures, pol_set())
        m = by_name(res)["p_allow"]  # misses the attack (allow-listed domain) AND false-denies the benign
        self.assertEqual(m["remediation_label"], pr.LABEL_FALSE_DENIALS)
        self.assertEqual(len(m["reasons"]), 2)

    def test_inconclusive_without_both_kinds(self):
        for kinds in (("benign", "benign"), ("malicious", "malicious")):
            fixtures = {"fixtures": [fx(f"f{i}", k) for i, k in enumerate(kinds)]}
            res = pr.replay(fixtures, pol_set())
            self.assertTrue(all(m["remediation_label"] == pr.LABEL_INCONCLUSIVE and not m["successful_remediation"]
                                for m in res["matrix"]))

    def test_label_cannot_be_injected_from_inputs(self):
        for mutate in (lambda p: p["policies"][1].update(remediation_label=pr.LABEL_OK),
                       lambda p: p["policies"][1].update(successful_remediation=True)):
            pol = copy.deepcopy(POLICIES)
            mutate(pol)
            with self.assertRaises(pr.ReplayInputError):
                pr.replay(FIXTURES, pol)
        fix = copy.deepcopy(FIXTURES)
        fix["fixtures"][0]["successful_remediation"] = True
        with self.assertRaises(pr.ReplayInputError):
            pr.replay(fix, POLICIES)

    def test_per_fixture_rows_cover_everything(self):
        for m in self.result["matrix"]:
            self.assertEqual([r["fixture"] for r in m["per_fixture"]], [f["id"] for f in FIXTURES["fixtures"]])
            self.assertEqual(len(m["policy_sha256"]), 64)

    def test_caveat_is_present(self):
        self.assertIn("not evidence of real-world prevention", self.result["caveat"])


class DeterminismAndFreshStateTests(unittest.TestCase):
    def test_repeated_runs_are_identical(self):
        a = pr.replay(FIXTURES, POLICIES)
        b = pr.replay(copy.deepcopy(FIXTURES), copy.deepcopy(POLICIES))
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))
        self.assertEqual(a["result_sha256"], b["result_sha256"])
        self.assertTrue(a["fresh_state_per_evaluation"])

    def test_cli_output_is_byte_identical_across_runs(self):
        args = ("--fixtures", str(EX / "fixtures.json"), "--policies", str(EX / "policies.json"))
        p1, p2 = run_cli(*args), run_cli(*args)
        self.assertEqual(p1.returncode, 0, p1.stderr)
        self.assertEqual(p1.stdout, p2.stdout)

    def test_fixture_and_policy_order_do_not_change_per_policy_numbers(self):
        base = by_name(pr.replay(FIXTURES, POLICIES))
        fx2 = copy.deepcopy(FIXTURES)
        fx2["fixtures"].reverse()
        fx2.pop("locked_sha256")
        pol2 = copy.deepcopy(POLICIES)
        pol2["policies"].reverse()
        other = by_name(pr.replay(fx2, pol2))
        for name, m in base.items():
            for key in ("harmful_blocked", "legit_preserved", "false_denials"):
                self.assertEqual(cell(m, key), cell(other[name], key), (name, key))
            self.assertEqual(m["remediation_label"], other[name]["remediation_label"])

    def test_inputs_are_not_mutated_and_no_state_leaks_between_runs(self):
        fixtures, policies = copy.deepcopy(FIXTURES), copy.deepcopy(POLICIES)
        pr.replay(fixtures, policies)
        self.assertEqual((fixtures, policies), (FIXTURES, POLICIES))

    def test_run_one_uses_a_fresh_ledger_each_time(self):
        pol = POLICIES["policies"][0]
        row1 = pr.run_one(pol, FIXTURES["fixtures"][0])
        row2 = pr.run_one(pol, FIXTURES["fixtures"][0])
        self.assertEqual(row1, row2)
        self.assertTrue(row1["executed"])

    def test_evaluator_error_fails_closed(self):
        row = pr.run_one({"name": "broken", "type": "allowlist"}, FIXTURES["fixtures"][2])  # missing egress_params
        self.assertFalse(row["executed"])
        self.assertTrue(row["rule"].startswith("evaluator_error"))


class InputValidationTests(unittest.TestCase):
    def test_locked_fixture_set_detects_change(self):
        tampered = copy.deepcopy(FIXTURES)
        tampered["fixtures"][0]["action"]["args"]["account"] = "000998774417"
        with self.assertRaises(pr.ReplayInputError):
            pr.replay(tampered, POLICIES)

    def test_lock_digest_matches_documented_command(self):
        p = run_cli("--fixtures", str(EX / "fixtures.json"), "--policies", str(EX / "policies.json"), "--print-fixtures-digest")
        self.assertEqual(json.loads(p.stdout)["fixtures_sha256"], FIXTURES["locked_sha256"])

    def test_require_lock(self):
        unlocked = {k: v for k, v in FIXTURES.items() if k != "locked_sha256"}
        pr.replay(unlocked, POLICIES)
        with self.assertRaises(pr.ReplayInputError):
            pr.replay(unlocked, POLICIES, require_lock=True)

    def test_needs_three_policies(self):
        with self.assertRaises(pr.ReplayInputError):
            pr.replay(FIXTURES, {"policies": POLICIES["policies"][:2]})

    def test_rejects_malformed_policies(self):
        bad = [{"name": "x", "type": "magic"}, {"name": "x", "type": "allowlist"},
               {"name": "x", "type": "deny_all_sensitive", "sensitive_tools": "send_email"},
               {"name": "x", "type": "context_bound", "bind_params": {"t": []}},
               {"name": "x", "type": "context_bound", "bind_params": {"t": ["a"]}, "egress_label_rules": {"pii": "allow"}},
               {"name": "bad name", "type": "allow_all"}, {"name": "x", "type": "allow_all", "extra": 1}]
        for p in bad:
            with self.assertRaises(pr.ReplayInputError, msg=str(p)):
                pr.replay(FIXTURES, pol_set(p))
        with self.assertRaises(pr.ReplayInputError):
            pr.replay(FIXTURES, pol_set({"name": "p_all", "type": "allow_all"}))  # duplicate name

    def test_rejects_malformed_fixtures(self):
        good = fx("f", "benign")
        bad = [dict(good, expected="deny"), dict(good, kind="neutral"), dict(good, id="a b"),
               {k: v for k, v in good.items() if k != "action"}, dict(good, action={"tool": "t"}),
               dict(good, action=dict(good["action"], labels="pii")), dict(good, surprise=1)]
        for f in bad:
            with self.assertRaises(pr.ReplayInputError, msg=str(f)):
                pr.replay({"fixtures": [f]}, pol_set())
        with self.assertRaises(pr.ReplayInputError):
            pr.replay({"fixtures": [good, copy.deepcopy(good)]}, pol_set())
        with self.assertRaises(pr.ReplayInputError):
            pr.replay({"fixtures": []}, pol_set())


class PolicySemanticsTests(unittest.TestCase):
    def decide(self, policy, **kw):
        return pr.decide(policy, fx("x", "benign", **kw)["action"])[0]

    def test_allowlist_rejects_ambiguous_destinations(self):
        p = {"name": "a", "type": "allowlist", "egress_params": {"send_email": "to", "http_post": "url"}, "allowed_domains": ["acme.example"]}
        self.assertTrue(self.decide(p, args={"to": "x@acme.example", "body": "b"}))
        self.assertTrue(self.decide(p, args={"to": "x@sub.acme.example", "body": "b"}))
        for to in ("x@acme.example,y@evil.example", "x@evil.example", "x@acme.example.evil.example", "", 5, None):
            self.assertFalse(self.decide(p, args={"to": to, "body": "b"}), repr(to))
        self.assertFalse(self.decide(p, tool="http_post", args={"url": "https://acme.example@evil.example/", "body": "b"}))
        self.assertTrue(self.decide(p, tool="http_post", args={"url": "https://hooks.acme.example/x", "body": "b"}))

    def test_context_bound_missing_provenance_is_untrusted(self):
        p = {"name": "c", "type": "context_bound", "bind_params": {"send_email": ["to"]}, "trusted_sources": ["user", "registry"]}
        self.assertFalse(self.decide(p, prov={}))
        self.assertFalse(self.decide(p, prov={"to": "model"}))
        self.assertTrue(self.decide(p, prov={"to": "user"}))

    def test_context_bound_label_rules(self):
        p = {"name": "c", "type": "context_bound", "bind_params": {"send_email": ["to"]},
             "egress_params": {"send_email": "to"}, "egress_label_rules": {"secret": "deny", "pii": "trusted_destination"}}
        self.assertFalse(self.decide(p, prov={"to": "registry"}, labels=["secret"]))
        self.assertTrue(self.decide(p, prov={"to": "registry"}, labels=["pii"]))
        p2 = dict(p, bind_params={"send_email": ["body"]})
        self.assertFalse(self.decide(p2, prov={"to": "untrusted", "body": "user"}, labels=["pii"]))


class CliTests(unittest.TestCase):
    ARGS = ("--fixtures", str(EX / "fixtures.json"), "--policies", str(EX / "policies.json"))

    def test_example_run(self):
        p = run_cli(*self.ARGS)
        self.assertEqual(p.returncode, 0, p.stderr)
        res = json.loads(p.stdout)
        self.assertEqual(res["successful_policies"], ["context_bound"])
        self.assertEqual(cell(by_name(res)["lockdown"], "legit_preserved"), (2, 6))

    def test_require_success_exit_codes(self):
        self.assertEqual(run_cli(*self.ARGS, "--require-success", "context_bound", "--require-lock").returncode, 0)
        for name in ("lockdown", "allowlist", "baseline", "nonexistent"):
            self.assertEqual(run_cli(*self.ARGS, "--require-success", name).returncode, 1, name)

    def test_out_file(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "r.json"
            p = run_cli(*self.ARGS, "--out", str(out))
            self.assertEqual(json.loads(out.read_text()), json.loads(p.stdout))

    def test_tampered_fixtures_exit_2(self):
        with tempfile.TemporaryDirectory() as d:
            doc = copy.deepcopy(FIXTURES)
            doc["fixtures"][3]["action"]["args"]["to"] = "someone@customer.example"
            path = Path(d) / "f.json"
            path.write_text(json.dumps(doc))
            p = run_cli("--fixtures", str(path), "--policies", str(EX / "policies.json"))
            self.assertEqual(p.returncode, 2)
            self.assertIn("changed since it was locked", json.loads(p.stdout)["error"])

    def test_bad_json_exit_2(self):
        for stdin in ("nope", '{"fixtures": [{"id": "a", "id": "b"}]}', '{"fixtures": NaN}'):
            p = run_cli("--fixtures", "-", "--policies", str(EX / "policies.json"), stdin=stdin)
            self.assertEqual(p.returncode, 2, stdin)


if __name__ == "__main__":
    unittest.main()
