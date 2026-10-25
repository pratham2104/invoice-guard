import copy
import subprocess
import sys
import unittest
from pathlib import Path

from phantomshift import evalset, incident
from phantomshift.approval import ApprovalGate, SimulatedChannel, config_digest
from phantomshift.guardian import Authority, Gateway, TraceLog
from phantomshift.mockapi import MockBusiness
from phantomshift.policies import BASELINE, CANDIDATES, validate_config
from phantomshift.scenarios import SCENARIOS

CB = next(p for p in CANDIDATES if p["name"] == "context_bound")
ROOT = Path(__file__).resolve().parent.parent


class GatewayTests(unittest.TestCase):
    def gw(self, sid="invoice_redirect", policy=BASELINE, mode="live"):
        biz = MockBusiness()
        return Gateway(Authority.for_scenario(sid), policy, biz, mode=mode), biz

    def test_live_mode_holds_attack_before_backend_sees_it(self):
        for sid, scn in SCENARIOS.items():
            for a in scn["attacks"]:
                gw, biz = self.gw(sid)
                res = gw.submit(a)
                self.assertTrue(res["held"], (sid, a["note"]))
                self.assertEqual(biz.calls, [], "backend must not observe a held action")

    def test_legit_reaches_backend_under_context_bound(self):
        for sid, scn in SCENARIOS.items():
            for a in scn["legit"]:
                gw, biz = self.gw(sid, CB)
                self.assertTrue(gw.submit(a)["executed"], (sid, a["note"]))
                self.assertEqual(len(biz.calls), 1)

    def test_fails_closed_on_internal_error(self):
        broken = {"name": "broken"}  # missing keys -> KeyError inside evaluate
        gw, biz = self.gw("invoice_redirect", broken, mode="sandbox")
        res = gw.submit(SCENARIOS["invoice_redirect"]["legit"][0])
        self.assertFalse(res["executed"])
        self.assertEqual(res["rule"], "gateway_error")
        self.assertEqual(biz.calls, [])
        self.assertEqual(gw.trace.events[-1]["kind"], "action_denied")

    def test_unknown_tool_and_malformed_denied(self):
        gw, biz = self.gw()
        self.assertFalse(gw.submit({"tool": "delete_vendor", "args": {}})["executed"])
        self.assertFalse(gw.submit({"tool": "pay_invoice", "args": "x"})["executed"])
        self.assertFalse(gw.submit("nonsense")["executed"])
        self.assertEqual(biz.calls, [])

    def test_authority_is_read_only(self):
        auth = Authority.for_scenario("invoice_redirect")
        with self.assertRaises(TypeError):
            auth.rules["pay_invoice"]["account"] = ("attacker",)
        with self.assertRaises(TypeError):
            auth.rules["new_tool"] = {}

    def test_trace_chain_detects_tampering(self):
        t = TraceLog()
        t.add("a", {"x": 1}); t.add("b", {"y": 2})
        self.assertTrue(t.verify())
        t.events[0]["data"]["x"] = 999
        self.assertFalse(t.verify())


class AmountCapTests(unittest.TestCase):
    def test_bad_amounts_are_held_not_executed(self):
        base = SCENARIOS["invoice_redirect"]["legit"][0]
        for bad in (float("nan"), -5_000_000, True, None, 24801, 0, 24800.0, "24800"):
            act = {**base, "args": {**base["args"], "amount": bad}}
            biz = MockBusiness()
            res = Gateway(Authority.for_scenario("invoice_redirect"), BASELINE, biz, mode="live").submit(act)
            self.assertTrue(res["held"], bad)
            self.assertEqual(biz.calls, [], bad)
        gone = {**base, "args": {k: v for k, v in base["args"].items() if k != "amount"}}
        self.assertTrue(Gateway(Authority.for_scenario("invoice_redirect"), BASELINE, MockBusiness(), mode="live").submit(gone)["held"])

    def test_exact_cap_and_normal_amount_pass_authority(self):
        base = SCENARIOS["invoice_redirect"]["legit"][0]
        for ok in (1, 24800):
            act = {**base, "args": {**base["args"], "amount": ok}}
            self.assertEqual(Authority.for_scenario("invoice_redirect").violations(act), [])


class ApprovalTests(unittest.TestCase):
    def setUp(self):
        self.now = [1000.0]
        self.gate = ApprovalGate({"op-1"}, ttl_s=60, clock=lambda: self.now[0])

    def test_happy_path_activates(self):
        req = self.gate.request(CB)
        self.assertTrue(self.gate.respond(req["nonce"], "op-1", True)["ok"])
        self.assertTrue(self.gate.activate(req["nonce"], CB)["ok"])

    def test_unknown_actor_rejected(self):
        req = self.gate.request(CB)
        self.assertFalse(self.gate.respond(req["nonce"], "agent", True)["ok"])
        self.assertFalse(self.gate.activate(req["nonce"], CB)["ok"])

    def test_expired_nonce_rejected(self):
        req = self.gate.request(CB)
        self.now[0] += 61
        self.assertEqual(self.gate.respond(req["nonce"], "op-1", True)["reason"], "nonce expired")

    def test_nonce_cannot_be_reused(self):
        req = self.gate.request(CB)
        self.gate.respond(req["nonce"], "op-1", True)
        self.assertFalse(self.gate.respond(req["nonce"], "op-1", True)["ok"])
        self.assertTrue(self.gate.activate(req["nonce"], CB)["ok"])
        self.assertFalse(self.gate.activate(req["nonce"], CB)["ok"], "activation is single use")

    def test_approval_bound_to_exact_config(self):
        req = self.gate.request(CB)
        self.gate.respond(req["nonce"], "op-1", True)
        widened = copy.deepcopy(CB)
        widened["deny_tools"] = []
        widened["bind_params"] = {}
        self.assertFalse(self.gate.activate(req["nonce"], widened)["ok"])

    def test_rejection_does_not_activate(self):
        req = self.gate.request(CB)
        self.gate.respond(req["nonce"], "op-1", False)
        self.assertFalse(self.gate.activate(req["nonce"], CB)["ok"])

    def test_invalid_config_refused_even_if_approved(self):
        bad = copy.deepcopy(CB)
        bad["deny_tools"] = ["rm_rf"]
        req = self.gate.request(bad)
        self.gate.respond(req["nonce"], "op-1", True)
        res = self.gate.activate(req["nonce"], bad)
        self.assertFalse(res["ok"])
        self.assertIn("invalid config", res["reason"])

    def test_validate_config(self):
        self.assertEqual(validate_config(CB), [])
        self.assertTrue(validate_config({"name": "x"}))
        self.assertTrue(validate_config("nope"))

    def test_simulated_channel_is_not_real(self):
        self.assertFalse(SimulatedChannel.real)
        self.assertEqual(config_digest(CB), config_digest(copy.deepcopy(CB)))


class IncidentTests(unittest.TestCase):
    def test_every_scenario_ends_verified_and_labelled(self):
        for sid in SCENARIOS:
            r = incident.run_incident(sid)
            self.assertEqual(r["selected"], "context_bound", sid)
            self.assertEqual(r["approval"]["state"], "activated")
            self.assertTrue(r["verification"]["verified"])
            self.assertTrue(r["live_action"]["held"])
            self.assertTrue(r["trace_chain_ok"])
            self.assertEqual(r["evidence"], "fixture")
            self.assertEqual(r["replay_mode"], "policy_only_replay")
            self.assertFalse(r["approval"]["real_channel"])

    def test_lockdown_never_selected_it_fails_legit_work(self):
        r = incident.run_incident("invoice_redirect")
        lock = next(f for f in r["forks"] if f["name"] == "lockdown")
        self.assertFalse(lock["verified"])
        self.assertLess(lock["legit_completed"], lock["legit_total"])


class EvalTests(unittest.TestCase):
    def test_deterministic_for_seed(self):
        a, b = evalset.parametric(5), evalset.parametric(5)
        self.assertEqual(a, b)
        self.assertNotEqual(evalset.parametric(5), evalset.parametric(6))

    def test_hard_cases_expose_policy_only_gaps(self):
        r = evalset.evaluate("heldout")["results"]["hard"]
        self.assertGreater(r["context_bound"]["policy_only"]["attacks_succeeded"], 0)
        self.assertGreater(r["context_bound"]["policy_only"]["legit"] - r["context_bound"]["policy_only"]["legit_completed"], 0)

    def test_circular_column_is_flagged(self):
        self.assertIn("CIRCULAR", evalset.evaluate("dev")["note"])


class VerifyScriptTests(unittest.TestCase):
    def test_competition_mode_fails_off_gb10(self):
        import os, tempfile
        env = {**os.environ, "PHANTOMSHIFT_ARTIFACTS": tempfile.mkdtemp()}
        p = subprocess.run([sys.executable, str(ROOT / "scripts/verify_hackathon.py"), "--mode", "competition"],
                           capture_output=True, text=True, cwd=ROOT, env=env)
        # Holds on any non-GB10 machine; on the GB10 this test must be revisited.
        self.assertEqual(p.returncode, 1)
        self.assertIn("H02", p.stdout)



class VerifyPrepModeTests(unittest.TestCase):
    def test_prep_mode_exits_zero_and_marks_gb10_gates_not_tested(self):
        import os, tempfile
        env = {**os.environ, "PHANTOMSHIFT_ARTIFACTS": tempfile.mkdtemp()}
        p = subprocess.run([sys.executable, str(ROOT / "scripts/verify_hackathon.py"), "--mode", "prep"],
                           capture_output=True, text=True, cwd=ROOT, env=env)
        self.assertEqual(p.returncode, 0)
        h02 = next(l for l in p.stdout.splitlines() if l.startswith("H02"))
        self.assertIn("NOT TESTED", h02)
        self.assertNotIn("PASS", h02)


if __name__ == "__main__":
    unittest.main()
