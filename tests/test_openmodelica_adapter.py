"""OpenModelica adapter: discovery, bounded execution, failure behavior, and
one end-to-end native-artifact proof.

The end-to-end test runs the REAL installed simulator (skipped honestly
when it is absent): an exponential-decay model is compiled and simulated,
and the transcript value x(2) is checked against e^-2 physics. Every other
test pins a refusal or a failure mode so the adapter cannot silently become
unrestricted control.

Measured 2026-10-07: first compile ~117s; budgets below ~300s risk false
timeouts, so the proof allows 600s.
"""
from __future__ import annotations

import math
import re
import shutil
import tempfile
import unittest
from pathlib import Path

import openmodelica_adapter
from openmodelica_adapter import discover, run_mos

DECAY_MO = """model Decay
  Real x(start = 1.0);
equation
  der(x) = -x;
end Decay;
"""

# Marker is printed LAST so it survives the adapter's tail window.
RUN_MOS = """loadFile("Decay.mo");
simulate(Decay, stopTime=2.0);
print("SIMDONE x2=" + String(val(x, 2.0)) + "\\n");
"""

EXPECTED = math.exp(-2.0)  # 0.135335...


def _value_of(stdout: str) -> float:
    match = re.search(r"SIMDONE x2=([0-9.eE+\-]+)", stdout)
    if not match:
        raise AssertionError(f"marker absent from transcript tail: {stdout[-500:]!r}")
    return float(match.group(1))


class DiscoveryTests(unittest.TestCase):
    def test_reports_missing_application_honestly(self):
        missing = discover(search_dirs=(Path(tempfile.mkdtemp(prefix="noapp_")),))
        self.assertFalse(missing.found)
        self.assertIsNone(missing.executable)
        self.assertTrue(missing.reason)

    def test_finds_the_real_installation(self):
        found = discover()
        if not found.found:
            self.skipTest(f"OpenModelica not installed: {found.reason}")
        self.assertTrue(Path(found.executable).is_file())
        self.assertIsNotNone(found.version)
        self.assertIn("1.", found.version)


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="om_"))
        found = discover()
        if not found.found:
            self.skipTest(f"OpenModelica not installed: {found.reason}")
        self.exe = found.executable

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, name: str, content: str) -> Path:
        path = self.tmp / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_decay_model_simulates_to_expected_physics(self):
        self._write("Decay.mo", DECAY_MO)
        script = self._write("run.mos", RUN_MOS)
        result = run_mos(self.exe, script, self.tmp, timeout_s=600.0)
        self.assertTrue(result.ok, result.stderr_tail[-500:])
        self.assertFalse(result.timed_out)
        value = _value_of(result.stdout_tail)
        self.assertAlmostEqual(value, EXPECTED, places=3)
        self.assertTrue((self.tmp / "Decay_res.mat").exists())

    def test_script_outside_workdir_is_refused(self):
        outside = Path(tempfile.mkdtemp(prefix="outside_")) / "evil.mos"
        outside.write_text(RUN_MOS, encoding="utf-8")
        try:
            result = run_mos(self.exe, outside, self.tmp)
            self.assertFalse(result.ok)
            self.assertIn("outside", result.stderr_tail)
        finally:
            shutil.rmtree(outside.parent, ignore_errors=True)

    def test_non_mos_file_is_refused(self):
        txt = self.tmp / "notes.txt"
        txt.write_text("not a script", encoding="utf-8")
        result = run_mos(self.exe, txt, self.tmp)
        self.assertFalse(result.ok)
        self.assertIn("not a Modelica script", result.stderr_tail)

    def test_missing_script_is_reported_not_executed(self):
        result = run_mos(self.exe, self.tmp / "ghost.mos", self.tmp)
        self.assertFalse(result.ok)
        self.assertIn("missing script", result.stderr_tail)


if __name__ == "__main__":
    unittest.main()
