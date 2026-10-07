"""FreeCAD adapter: discovery, bounded execution, failure behavior, and one
end-to-end native-artifact proof.

The end-to-end test runs the REAL installed application (skipped honestly
when it is absent): a parametric bracket is created, saved as native .FCStd,
reopened, and its dimensions verified. Every other test pins a refusal or a
failure mode so the adapter cannot silently become unrestricted control.
"""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

import freecad_adapter
from freecad_adapter import discover, run_script


class DiscoveryTests(unittest.TestCase):
    def test_reports_missing_application_honestly(self):
        missing = discover(search_dirs=(Path(tempfile.mkdtemp(prefix="noapp_")),))
        self.assertFalse(missing.found)
        self.assertIsNone(missing.executable)
        self.assertTrue(missing.reason)

    def test_finds_the_real_installation(self):
        found = discover()
        if not found.found:
            self.skipTest(f"FreeCAD not installed: {found.reason}")
        self.assertTrue(Path(found.executable).is_file())
        self.assertIsNotNone(found.version)
        self.assertIn("freecad", found.version.lower())


BRACKET_SCRIPT = '''import FreeCAD, Part
doc = FreeCAD.newDocument("Bracket")
base = Part.makeBox(60.0, 40.0, 10.0)
rib = Part.makeBox(10.0, 40.0, 30.0)
rib.translate(FreeCAD.Vector(0, 0, 10.0))
shape = base.fuse(rib)
obj = doc.addObject("Part::Feature", "Bracket")
obj.Shape = shape
doc.recompute()
doc.saveAs(r"{workdir}/bracket.FCStd")
print("SAVED x=%.1f y=%.1f z=%.1f" % (shape.BoundBox.XLength, shape.BoundBox.YLength, shape.BoundBox.ZLength))
'''

VERIFY_SCRIPT = '''import FreeCAD
doc = FreeCAD.open(r"{workdir}/bracket.FCStd")
doc.recompute()
bb = doc.getObject("Bracket").Shape.BoundBox
print("VERIFY x=%.1f y=%.1f z=%.1f solids=%d" % (
    bb.XLength, bb.YLength, bb.ZLength, len(doc.getObject("Bracket").Shape.Solids)))
assert abs(bb.XLength - 60.0) < 0.01 and abs(bb.YLength - 40.0) < 0.01 and abs(bb.ZLength - 40.0) < 0.01
print("VERIFY PASS")
'''


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="freecad_"))
        found = discover()
        if not found.found:
            self.skipTest(f"FreeCAD not installed: {found.reason}")
        self.exe = found.executable

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, name: str, content: str) -> Path:
        path = self.tmp / name
        path.write_text(content.replace("{workdir}", self.tmp.as_posix()), encoding="utf-8")
        return path

    def test_bracket_is_created_saved_reopened_and_verified(self):
        create = run_script(self.exe, self._write("bracket.py", BRACKET_SCRIPT), self.tmp, timeout_s=300.0)
        self.assertTrue(create.ok, create.stderr_tail)
        self.assertIn("SAVED", create.stdout_tail)
        self.assertTrue((self.tmp / "bracket.FCStd").exists())
        check = run_script(self.exe, self._write("verify.py", VERIFY_SCRIPT), self.tmp, timeout_s=300.0)
        self.assertTrue(check.ok, check.stderr_tail)
        self.assertIn("VERIFY PASS", check.stdout_tail)
        self.assertIn("x=60.0 y=40.0 z=40.0", check.stdout_tail)

    def test_script_outside_workdir_is_refused(self):
        outside = Path(tempfile.mkdtemp(prefix="outside_")) / "evil.py"
        outside.write_text("print('nope')", encoding="utf-8")
        try:
            result = run_script(self.exe, outside, self.tmp)
            self.assertFalse(result.ok)
            self.assertIn("outside", result.stderr_tail)
        finally:
            shutil.rmtree(outside.parent, ignore_errors=True)

    def test_non_python_file_is_refused(self):
        sistine = self.tmp / "chapel.txt"
        sistine.write_text("print('nope')", encoding="utf-8")
        result = run_script(self.exe, sistine, self.tmp)
        self.assertFalse(result.ok)
        self.assertIn("not a Python script", result.stderr_tail)

    def test_missing_script_is_reported_not_executed(self):
        result = run_script(self.exe, self.tmp / "ghost.py", self.tmp)
        self.assertFalse(result.ok)
        self.assertIn("missing script", result.stderr_tail)

    def test_timeout_is_reported_not_hung(self):
        sleeper = self._write("sleep.py", "import time\ntime.sleep(60)\nprint('woke')\n")
        result = run_script(self.exe, sleeper, self.tmp, timeout_s=5.0)
        self.assertFalse(result.ok)
        self.assertTrue(result.timed_out)

    def test_failing_script_error_is_captured_not_hidden(self):
        # FreeCADCmd exits 0 even when the script raises, so the adapter must
        # surface the error text: exit codes alone cannot prove anything here.
        bogus = self._write("bogus.py", "import nonexistent_module_xyz\n")
        result = run_script(self.exe, bogus, self.tmp, timeout_s=120.0)
        combined = result.stdout_tail + result.stderr_tail
        self.assertIn("nonexistent_module_xyz", combined)


if __name__ == "__main__":
    unittest.main()
