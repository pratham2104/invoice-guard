"""scripts/gb10_preflight.sh: syntax, host-class reporting on this (x86) host, size-only manifest check, secrets hygiene.

The wrapper CALLS scripts/preflight_gb10.sh, which rewrites artifacts/preflight/gb10.json by design; these tests
snapshot and restore that file so running them leaves the repo as found."""

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "gb10_preflight.sh"
BASE_JSON = ROOT / "artifacts" / "preflight" / "gb10.json"
HOST_IS_X86 = os.uname().machine not in ("aarch64", "arm64")


def run(*args, env=None, timeout=120):
    e = {**os.environ, **(env or {})}
    return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True, timeout=timeout, env=e)


class Base(unittest.TestCase):
    def setUp(self):
        self._snap = BASE_JSON.read_bytes() if BASE_JSON.exists() else None

    def tearDown(self):
        if self._snap is not None:
            BASE_JSON.write_bytes(self._snap)
        elif BASE_JSON.exists():
            BASE_JSON.unlink()


class Syntax(unittest.TestCase):
    def test_bash_n(self):
        r = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_executable_and_calls_base_script_rather_than_copying_it(self):
        self.assertTrue(os.access(SCRIPT, os.X_OK))
        text = SCRIPT.read_text()
        self.assertIn('scripts/preflight_gb10.sh', text)
        self.assertNotIn("--format=csv,noheader | head -1", text)  # the base script's probes are not duplicated

    def test_help_and_bad_option(self):
        self.assertEqual(run("--help").returncode, 0)
        self.assertEqual(run("--bogus").returncode, 2)


class OnThisHost(Base):
    @classmethod
    def setUpClass(cls):
        if BASE_JSON.exists():
            snap = BASE_JSON.read_bytes()
        else:
            snap = None
        cls.r = run()
        if snap is not None:
            BASE_JSON.write_bytes(snap)
        cls.out = cls.r.stdout

    def test_table_and_exit_code_consistent(self):
        self.assertIn("STATUS", self.out)
        self.assertRegex(self.out, r"RESULT: \d+ PASS, \d+ WARN, \d+ FAIL")
        fails = len(re.findall(r"^FAIL ", self.out, re.M))
        self.assertEqual(self.r.returncode, 1 if fails else 0)

    def test_base_script_output_is_embedded(self):
        self.assertIn("base preflight (scripts/preflight_gb10.sh", self.out)
        self.assertIn("---- verdict ----", self.out)

    @unittest.skipUnless(HOST_IS_X86, "x86-only assertion")
    def test_reports_not_a_gb10(self):
        self.assertRegex(self.out, r"WARN\s+host class\s+NOT a GB10")

    @unittest.skipUnless(HOST_IS_X86, "x86-only assertion")
    def test_require_gb10_makes_it_fail(self):
        r = run("--require-gb10")
        self.assertRegex(r.stdout, r"FAIL\s+host class")
        self.assertEqual(r.returncode, 1)

    @unittest.skipUnless(HOST_IS_X86 and (Path.home() / ".docker").exists() and not Path("/var/run/docker.sock").exists(),
                         "this dev host runs rootless Docker (no /var/run/docker.sock)")
    def test_rootless_warning_on_this_host(self):
        self.assertIn("WARNING: ROOTLESS DOCKER DETECTED", self.out)
        self.assertIn("docs/GB10_RUNBOOK.md", self.out)
        self.assertIn("NemoClaw onboarding FAILED", self.out)

    def test_ports_and_discord_rows_present(self):
        for p in (8000, 8080, 7890, 18789):
            self.assertRegex(self.out, rf"(PASS|WARN|FAIL)\s+port {p}\s")
        for v in ("DISCORD_BOT_TOKEN", "DISCORD_SERVER_ID", "DISCORD_USER_ID"):
            self.assertRegex(self.out, rf"(PASS|WARN)\s+env {v}\s")


class DiscordValuesNeverPrinted(Base):
    def test_sentinel_values_absent_from_output(self):
        env = {"DISCORD_BOT_TOKEN": "SENTINEL-TOKEN-xyz123", "DISCORD_SERVER_ID": "SENTINEL-SERVER-987",
               "DISCORD_USER_ID": "SENTINEL-USER-555"}
        r = run("--no-base", env=env)
        for v in env.values():
            self.assertNotIn(v, r.stdout + r.stderr)
        for k in env:
            self.assertRegex(r.stdout, rf"PASS\s+env {k}\s+set")


class ManifestSizes(Base):
    def make_kit(self, d: Path):
        (d / "sub").mkdir()
        (d / "a.bin").write_bytes(b"x" * 10)
        (d / "sub" / "b.bin").write_bytes(b"y" * 20)
        sums = subprocess.run(["sha256sum", "./a.bin", "./sub/b.bin"], cwd=d, capture_output=True, text=True).stdout
        (d / "manifest.sha256").write_text(sums)

    def test_existence_only_without_sizes_file(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            self.make_kit(d)
            r = run("--no-base", "--manifest", str(d / "manifest.sha256"))
            self.assertRegex(r.stdout, r"WARN\s+staged files\s+all 2 exist \(existence only")

    def test_emit_sizes_then_match_then_mismatch_then_missing(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            self.make_kit(d)
            m = str(d / "manifest.sha256")
            emitted = run("--manifest", m, "--emit-sizes")
            self.assertEqual(emitted.returncode, 0)
            self.assertEqual(sorted(emitted.stdout.split("\n")[:2]), ["10  ./a.bin", "20  ./sub/b.bin"])
            (d / "manifest.sizes").write_text(emitted.stdout)
            self.assertRegex(run("--no-base", "--manifest", m).stdout, r"PASS\s+staged files\s+all 2 exist and sizes match")
            (d / "a.bin").write_bytes(b"x" * 11)  # same name, wrong size; no hashing is done, so only size catches it
            r = run("--no-base", "--manifest", m)
            self.assertRegex(r.stdout, r"FAIL\s+staged files\s+1 size mismatch")
            self.assertEqual(r.returncode, 1)
            (d / "a.bin").unlink()
            self.assertRegex(run("--no-base", "--manifest", m).stdout, r"FAIL\s+staged files\s+1 of 2 missing")

    def test_verify_hashes_flag_runs_sha256sum_and_default_does_not(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            self.make_kit(d)
            m = str(d / "manifest.sha256")
            self.assertRegex(run("--no-base", "--manifest", m).stdout, r"WARN\s+staged hashes\s+not verified")
            self.assertRegex(run("--no-base", "--manifest", m, "--verify-hashes").stdout, r"PASS\s+staged hashes\s+sha256sum -c OK")
            (d / "a.bin").write_bytes(b"z" * 10)  # same size, different content: only the hash check can see it
            r = run("--no-base", "--manifest", m, "--verify-hashes")
            self.assertRegex(r.stdout, r"FAIL\s+staged hashes")
            self.assertRegex(r.stdout, r"WARN\s+staged files\s+all 2 exist \(existence only")


class BasePreflightUntouched(Base):
    def test_artifact_restored_by_these_tests(self):
        # sanity: the snapshot/restore mechanism works (guards the "do not edit existing files" rule)
        before = BASE_JSON.read_bytes()
        run()
        BASE_JSON.write_bytes(before)
        self.assertEqual(BASE_JSON.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
