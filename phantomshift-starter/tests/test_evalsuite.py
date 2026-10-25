import copy
import hashlib
import json
import re
import unittest
from pathlib import Path

from phantomshift import evalsuite as es
from phantomshift.adapter import fixture_registry

PINNED = "5a053cdacefabdbe2b36a03aae18cac45bbfef1b3207e9cfef0411c0ec257c98"
CATEGORIES = {
    "direct_payout_attack", "indirect_injection", "altered_recipient", "mismatched_invoice", "authorised_payment",
    "idempotency_replay", "missing_authorisation", "parser_failure", "oversized_unsupported", "benign_suspicious",
    "forbidden_egress", "wrong_unknown_approver",
}


class ManifestTests(unittest.TestCase):
    def test_ids_unique_and_well_formed(self):
        ids = [c["id"] for c in es.MANIFEST["cases"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(re.fullmatch(r"E\d{3}", i) for i in ids))
        self.assertTrue(30 <= len(ids) <= 40)
        for c in es.MANIFEST["cases"]:
            self.assertIn(c["label"], es.LABELS)
            self.assertIn(c["expected"]["outcome"], ("allowed", "denied", "pending"))
            self.assertIn(c["kind"], ("payment", "egress", "approver"))

    def test_hash_is_frozen_and_stable(self):
        self.assertEqual(es.MANIFEST_SHA256, PINNED)
        self.assertEqual(es.manifest_sha256(), PINNED)
        self.assertEqual(es.manifest_sha256(es._manifest_dict()), PINNED)  # rebuilt from scratch, same hash

    def test_hash_detects_edits(self):
        edited = copy.deepcopy(es.MANIFEST)
        edited["cases"][0]["expected"]["outcome"] = "allowed"
        self.assertNotEqual(es.manifest_sha256(edited), PINNED)
        self.assertFalse(es.run_suite("heldout", edited)["manifest_frozen_ok"])

    def test_split_rule_reproducible(self):
        for c in es.MANIFEST["cases"]:
            h = hashlib.sha256(("phantomshift-evalsuite-v1:" + c["id"]).encode()).digest()[0]
            self.assertEqual(c["split"], "heldout" if h < 128 else "dev")
            self.assertEqual(es.split_for_id(c["id"]), c["split"])
        splits = {c["split"] for c in es.MANIFEST["cases"]}
        self.assertEqual(splits, {"dev", "heldout"})

    def test_every_category_and_label_present(self):
        self.assertEqual({c["category"] for c in es.MANIFEST["cases"]}, CATEGORIES)
        self.assertEqual({c["label"] for c in es.MANIFEST["cases"]}, set(es.LABELS))

    def test_suite_registry_matches_the_real_fixture_for_v102(self):
        real = fixture_registry().get("V-102")
        spec = es.MANIFEST["registries"]["suite"]["V-102"]
        self.assertEqual(spec["approved_account_id"], real.approved_account_id)
        self.assertEqual(spec["max_amount"], real.max_amount)
        self.assertEqual(frozenset(spec["allowed_invoice_ids"]), real.allowed_invoice_ids)
        self.assertEqual(spec["invoice_amounts"], dict(real.invoice_amounts))

    def test_committed_results_match_pinned_manifest(self):
        path = Path(es.__file__).resolve().parent.parent / "artifacts" / "benchmarks" / "results_v2.json"
        if not path.exists():
            self.skipTest("results_v2.json not generated yet")
        data = json.loads(path.read_text())
        for split, res in data["results"].items():
            self.assertEqual(res["manifest_sha256"], PINNED, split)
            self.assertTrue(res["limitations"])


class StatsTests(unittest.TestCase):
    def test_wilson_known_values(self):
        self.assertEqual(es.wilson_interval(0, 10), [0.0, 0.2775])
        self.assertEqual(es.wilson_interval(5, 10), [0.2366, 0.7634])
        self.assertEqual(es.wilson_interval(10, 10), [0.7225, 1.0])
        lo, hi = es.wilson_interval(81, 100)
        # hand computed: centre 0.7985, half 0.0763
        self.assertAlmostEqual(lo, 0.7222, places=3)
        self.assertAlmostEqual(hi, 0.8749, places=3)
        self.assertIsNone(es.wilson_interval(0, 0))
        with self.assertRaises(ValueError):
            es.wilson_interval(3, 2)

    def test_rate_carries_denominator(self):
        r = es.rate(1, 4)
        self.assertEqual((r["k"], r["n"], r["rate"]), (1, 4, 0.25))
        self.assertIsNone(es.rate(0, 0)["rate"])

    def test_percentile_nearest_rank(self):
        v = [5, 1, 3, 2, 4]
        self.assertEqual(es.percentile(v, 0.5), 3)
        self.assertEqual(es.percentile(v, 0.95), 5)
        self.assertIsNone(es.percentile([], 0.5))


class RunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.all = es.run_suite("all")

    def test_deterministic_across_two_runs_ignoring_latency(self):
        again = es.run_suite("all")
        self.assertEqual(es.strip_timing(self.all), es.strip_timing(again))

    def test_stacks_are_separate_and_labelled(self):
        stacks = self.all["stacks"]
        self.assertEqual(set(stacks), {"policy_only", "live_stack"})
        self.assertIn("POLICY-ONLY", stacks["policy_only"]["scope"])
        self.assertIn("FULL LIVE STACK", stacks["live_stack"]["scope"])
        self.assertEqual(set(stacks["policy_only"]["policies"]), {"baseline", "lockdown", "context_bound"})
        n_payment_egress = sum(c["kind"] != "approver" for c in es.MANIFEST["cases"])
        self.assertEqual(stacks["policy_only"]["applicable_cases"], n_payment_egress)
        for d in stacks["live_stack"]["variants"].values():
            self.assertEqual(d["summary"]["n_cases"], len(es.MANIFEST["cases"]))

    def test_denominators_match_manifest_counts(self):
        labels = self.all["case_counts"]["label"]
        for d in self.all["stacks"]["live_stack"]["variants"].values():
            s = d["summary"]
            self.assertEqual(s["attack_success_rate"]["n"], labels["attack"])
            self.assertEqual(s["benign_completion_rate"]["n"], labels["benign"])
            self.assertEqual(s["false_positive_deny_rate"]["n"], labels["benign"])
            self.assertEqual(s["escalation_correct_rate"]["n"], labels["escalate"])
            self.assertEqual(s["attack_success_rate_substantive"]["n"], labels["attack"] - self.all["case_counts"]["non_action"])

    def test_splits_partition_the_manifest(self):
        n = es.run_suite("dev")["n_cases"] + es.run_suite("heldout")["n_cases"]
        self.assertEqual(n, len(es.MANIFEST["cases"]))

    def test_benign_suspicious_allowed_under_context_bound(self):
        ids = {c["id"] for c in es.MANIFEST["cases"] if c["category"] == "benign_suspicious"}
        self.assertTrue(len(ids) >= 3)
        pol = {r["id"]: r for r in self.all["stacks"]["policy_only"]["policies"]["context_bound"]["cases"]}
        live = {r["id"]: r for r in self.all["stacks"]["live_stack"]["variants"]["authority_plus_context_bound"]["cases"]}
        for i in ids:
            self.assertEqual(pol[i]["observed"]["outcome"], "allowed", i)
            self.assertEqual(live[i]["observed"]["outcome"], "allowed", i)
            self.assertEqual(live[i]["observed"]["ledger_rows"], 1, i)

    def test_idempotent_replay_does_not_double_execute(self):
        live = {r["id"]: r for r in self.all["stacks"]["live_stack"]["variants"]["authority_only"]["cases"]}
        replay = [c["id"] for c in es.MANIFEST["cases"] if c["category"] == "idempotency_replay"]
        self.assertTrue(replay)
        for i in replay:
            self.assertTrue(live[i]["passed"], i)
            self.assertEqual(live[i]["observed"]["ledger_rows"], 1, i)

    def test_known_failures_are_recorded_not_hidden(self):
        # A case whose expectation is wrong for the code under test must surface, never be dropped.
        m = copy.deepcopy(es.MANIFEST)
        bad = next(c for c in m["cases"] if c["id"] == "E001")  # attacker-account payment
        bad["expected"]["outcome"] = "allowed"
        bad["label"] = "benign"
        res = es.run_suite("all", m)
        self.assertFalse(res["manifest_frozen_ok"])
        ids = {(k["id"], k["stack"]) for k in res["known_failures"]}
        self.assertIn(("E001", "live_stack"), ids)
        entry = next(k for k in res["known_failures"] if k["id"] == "E001" and k["stack"] == "live_stack")
        self.assertEqual(entry["observed_outcome"], "denied")
        self.assertEqual(entry["expected"]["outcome"], "allowed")
        live = res["stacks"]["live_stack"]["variants"]["authority_only"]["summary"]
        self.assertIn("E001", live["failed_case_ids"])

    def test_runner_exception_is_recorded_as_error(self):
        m = copy.deepcopy(es.MANIFEST)
        m["cases"][0]["kind"] = "payment"
        m["cases"][0]["spec"] = {"registry": "does-not-exist", "steps": []}
        res = es.run_suite("all", m)
        rec = next(r for r in res["stacks"]["live_stack"]["variants"]["authority_only"]["cases"] if r["id"] == "E001")
        self.assertEqual(rec["observed"]["outcome"], "error")
        self.assertFalse(rec["passed"])
        self.assertTrue(any(k["id"] == "E001" for k in res["known_failures"]))

    def test_known_failures_only_from_designated_arms(self):
        for k in self.all["known_failures"]:
            self.assertTrue(k["stack"] == "live_stack" or k["variant"] == "context_bound")

    def test_limitations_listed(self):
        text = " ".join(self.all["limitations"]).lower()
        for needle in ("same-author", "small n", "in-process latency", "no model", "circular"):
            self.assertIn(needle, text)

    def test_attack_success_requires_an_effect(self):
        rec = {"label": "attack", "non_action": False, "passed": True, "category": "x", "latency_ms": 0.0,
               "id": "T", "observed": {"outcome": "allowed", "effects": 0}}
        s = es.summarize([rec])
        self.assertEqual(s["attack_success_rate"]["k"], 0)


if __name__ == "__main__":
    unittest.main()
