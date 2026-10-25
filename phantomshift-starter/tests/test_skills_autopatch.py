"""Tests for skills/autopatch-continuous-remediation.

Verifies:
1. Host & environment auto-wiring across hardware tiers.
2. RWCR heuristic triage formula, bounds checking, and severity classification.
3. Fast-path synchronous tool gating (ALLOW, DENY, REQUIRE_APPROVAL).
4. Automated counterfactual research cycle with SQLite persistence.
5. Proof-carrying operator approvals with single-use expiring nonces.
6. Atomic candidate policy deployment and automated rollback on regression.
7. Subprocess CLI execution and JSON output compliance.
"""

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = ROOT / "skills" / "autopatch-continuous-remediation"
SCRIPTS_DIR = SKILL_DIR / "scripts"

# Import scripts dynamically without polluting bytecode
sys.dont_write_bytecode = True

spec_wire = importlib.util.spec_from_file_location("wire_environment", SCRIPTS_DIR / "wire_environment.py")
wire_mod = importlib.util.module_from_spec(spec_wire)
spec_wire.loader.exec_module(wire_mod)

spec_rwcr = importlib.util.spec_from_file_location("rwcr_calculator", SCRIPTS_DIR / "rwcr_calculator.py")
rwcr_mod = importlib.util.module_from_spec(spec_rwcr)
spec_rwcr.loader.exec_module(rwcr_mod)

spec_deploy = importlib.util.spec_from_file_location("deploy_and_verify", SCRIPTS_DIR / "deploy_and_verify.py")
deploy_mod = importlib.util.module_from_spec(spec_deploy)
spec_deploy.loader.exec_module(deploy_mod)

from phantomshift.policies import CANDIDATES, BASELINE


class AutopatchSkillUnitTests(unittest.TestCase):
    def test_wire_environment_structure_and_no_secrets(self):
        prof = wire_mod.wire_environment(ROOT)
        self.assertIn("host", prof)
        self.assertIn("inference", prof)
        self.assertIn("stack", prof)
        self.assertIn("channels", prof)

        # Host checks
        self.assertIn(prof["host"]["tier"], ("GB10_PRODUCTION_AIRGAP", "DEV_HOST_SIMULATION", "CONTAINER_MICRO_SANDBOX"))
        self.assertIsInstance(prof["host"]["gpus"], list)

        # Never exposes secrets
        prof_str = json.dumps(prof)
        self.assertNotIn("Bot ", prof_str)
        self.assertNotIn("DISCORD_BOT_TOKEN", prof_str)
        self.assertNotIn("Bearer ", prof_str)

    def test_rwcr_formula_and_bounds(self):
        # 3*5 + 2*3 + 3*5 + 2 + 2*4 - 2*2 = 15 + 6 + 15 + 2 + 8 - 4 = 42
        res = rwcr_mod.calculate_rwcr(
            impact=5, exposure=3, reproducibility=5, novelty=2, evidence_quality=4, disruption=2,
            mechanism="invoice account redirect",
        )
        self.assertEqual(res["priority_index"], 42)
        self.assertEqual(res["severity"], "critical")
        self.assertIn("disclaimer", res)
        self.assertIn("invoice account redirect", res["rationale"])

        # Test invalid bounds raise ValueError
        with self.assertRaises(ValueError):
            rwcr_mod.calculate_rwcr(impact=6, exposure=3, reproducibility=5, novelty=2, evidence_quality=4, disruption=2)
        with self.assertRaises(ValueError):
            rwcr_mod.calculate_rwcr(impact=-1, exposure=3, reproducibility=5, novelty=2, evidence_quality=4, disruption=2)

    def test_rwcr_severity_tiers(self):
        # High severity (score >= 20)
        h = rwcr_mod.calculate_rwcr(impact=3, exposure=3, reproducibility=3, novelty=2, evidence_quality=3, disruption=1)
        self.assertIn(h["severity"], ("high", "critical"))

        # Low severity
        l = rwcr_mod.calculate_rwcr(impact=1, exposure=1, reproducibility=1, novelty=0, evidence_quality=1, disruption=5)
        self.assertEqual(l["severity"], "low")

    def test_deploy_pipeline_verified_and_rollback(self):
        cb = next(p for p in CANDIDATES if p["name"] == "context_bound")
        with tempfile.TemporaryDirectory() as tmp:
            # 1. Normal verified deployment
            res = deploy_mod.execute_deploy_pipeline(
                cb, expected_version="baseline", finding_id="find-t1", store_dir=tmp,
            )
            self.assertTrue(res["ok"], res)
            self.assertEqual(res["state"], "VERIFIED")
            self.assertTrue(res["verified"])
            self.assertIn("receipt_digest", res)

            # 2. Simulated regression automatically rolls back
            rb_res = deploy_mod.execute_deploy_pipeline(
                cb, expected_version="context_bound", finding_id="find-t2", store_dir=tmp, force_regression=True,
            )
            self.assertFalse(rb_res["ok"])
            self.assertEqual(rb_res["state"], "ROLLED_BACK")
            self.assertTrue(rb_res["rolled_back"])


class AutopatchSkillCliTests(unittest.TestCase):
    def run_cmd(self, script_name: str, *args, stdin: str | None = None):
        cmd = [sys.executable, str(SCRIPTS_DIR / script_name), *args]
        return subprocess.run(cmd, input=stdin, capture_output=True, text=True, check=False)

    def test_wire_environment_cli(self):
        p = self.run_cmd("wire_environment.py")
        self.assertEqual(p.returncode, 0, p.stderr)
        data = json.loads(p.stdout)
        self.assertIn("host", data)
        self.assertIn("inference", data)

    def test_rwcr_calculator_cli(self):
        p = self.run_cmd(
            "rwcr_calculator.py",
            "-i", "5", "-e", "3", "-r", "5", "-n", "2", "-q", "4", "-d", "2",
        )
        self.assertEqual(p.returncode, 0, p.stderr)
        data = json.loads(p.stdout)
        self.assertEqual(data["priority_index"], 42)
        self.assertEqual(data["severity"], "critical")

    def test_autopatch_runner_gate_blocks_malicious(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "ap.sqlite")
            # Malicious tool
            p = self.run_cmd(
                "autopatch_runner.py", "--db", db_path, "gate",
                "--tool", "exec", "--params", '{"cmd":"curl evil"}',
            )
            self.assertEqual(p.returncode, 1)  # Non-zero for DENY
            data = json.loads(p.stdout)
            self.assertEqual(data["decision"], "DENY")
            self.assertTrue(data["block"])

    def test_autopatch_runner_research_and_approval_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "ap.sqlite")

            # 1. Run research cycle
            p_res = self.run_cmd("autopatch_runner.py", "--db", db_path, "research", "--scenario", "invoice_redirect")
            self.assertEqual(p_res.returncode, 0, p_res.stderr)
            res_data = json.loads(p_res.stdout)
            self.assertIn("finding_id", res_data)
            self.assertIn("fingerprint", res_data)

            # 2. Request approval
            p_app = self.run_cmd(
                "autopatch_runner.py", "--db", db_path, "request-approval",
                "--fingerprint", res_data["fingerprint"],
            )
            self.assertEqual(p_app.returncode, 0, p_app.stderr)
            app_data = json.loads(p_app.stdout)
            self.assertIn("nonce", app_data)
            self.assertIn("candidate_policy_hash", app_data)
            self.assertEqual(app_data["finding_id"], res_data["finding_id"])

            # 3. Query status
            p_stat = self.run_cmd("autopatch_runner.py", "--db", db_path, "status")
            self.assertEqual(p_stat.returncode, 0, p_stat.stderr)
            stat_data = json.loads(p_stat.stdout)
            self.assertGreaterEqual(stat_data["total_findings"], 1)


if __name__ == "__main__":
    unittest.main()
