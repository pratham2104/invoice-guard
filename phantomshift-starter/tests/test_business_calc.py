import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("phantomshift_business_calc", ROOT / "scripts" / "business_calc.py")
bc = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = bc  # dataclasses needs the module registered
_spec.loader.exec_module(bc)


class Defaults(unittest.TestCase):
    def test_default_numbers(self):
        a = bc.Assumptions()
        self.assertEqual(bc.minutes_saved(a), 11)
        self.assertAlmostEqual(bc.time_value(a), 9350.0)
        self.assertAlmostEqual(bc.net_monthly(a), 6850.0)
        self.assertAlmostEqual(bc.annualised(a), 82200.0)

    def test_breakeven(self):
        a = bc.Assumptions()
        be = bc.breakeven_minutes_saved(a)
        self.assertAlmostEqual(be, 2500 / 850)
        self.assertAlmostEqual(bc.net_monthly(bc.Assumptions(minutes_before=be, minutes_after=0)), 0.0, places=6)

    def test_no_negative_time_value_when_slower(self):
        a = bc.Assumptions(minutes_before=5, minutes_after=9)
        self.assertEqual(bc.time_value(a), 0.0)
        self.assertEqual(bc.net_monthly(a), -2500.0)

    def test_validation(self):
        for bad in (-1, float("nan"), float("inf"), True, "3"):
            with self.assertRaises(ValueError):
                bc.time_value(bc.Assumptions(cases_per_day=bad))
        self.assertIsNone(bc.breakeven_minutes_saved(bc.Assumptions(cases_per_day=0)))


class Sensitivity(unittest.TestCase):
    def test_grid_matches_formula(self):
        a = bc.Assumptions()
        rows = bc.sensitivity(a, [11.0, 5.0], [30.0, 10.0])
        self.assertAlmostEqual(rows[0][0], 6850.0)  # 11 minutes saved, 30 cases/day == default
        self.assertAlmostEqual(rows[1][1], 10 * 5 / 60 * 20 * 85 - 2500)
        self.assertLess(rows[1][1], 0)  # low volume and low savings: negative net is shown, not hidden

    def test_table_renders_negative(self):
        t = bc.format_table(bc.Assumptions(), [2.0], [10.0])
        self.assertIn("-$", t)


class Cli(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "scripts" / "business_calc.py"), *args],
                              capture_output=True, text=True, timeout=30)

    def test_default_output_labelled(self):
        r = self.run_cli()
        self.assertEqual(r.returncode, 0)
        self.assertIn("ILLUSTRATIVE, NOT MEASURED", r.stdout)
        for s in ("$9,350.00", "$6,850.00", "$82,200.00"):
            self.assertIn(s, r.stdout)

    def test_json(self):
        r = self.run_cli("--json", "--sensitivity")
        d = json.loads(r.stdout)
        self.assertEqual(d["annualised_net"], 82200.0)
        self.assertEqual(d["label"], "ILLUSTRATIVE, NOT MEASURED")
        self.assertIn("| minutes saved", d["sensitivity_table_markdown"])

    def test_bad_input_exit_2(self):
        self.assertEqual(self.run_cli("--cases-per-day", "-5").returncode, 2)


class DocConsistency(unittest.TestCase):
    def test_doc_quotes_default_numbers_and_disclaimers(self):
        p = ROOT / "docs" / "BUSINESS_MODEL.md"
        if not p.exists():
            self.skipTest("docs/BUSINESS_MODEL.md not present")
        text = p.read_text()
        for s in ("$9,350", "$6,850", "$82,200", "ILLUSTRATIVE", "measured from observed investigation durations",
                  "never", "hypothesis", bc.format_table(bc.Assumptions(), bc.DEFAULT_SAVED, bc.DEFAULT_VOLUMES)):
            self.assertIn(s, text)


if __name__ == "__main__":
    unittest.main()
