"""CuraEngine adapter: discovery, bounded execution, failure behavior, and one
end-to-end native-artifact proof.

The end-to-end test runs the REAL installed slicer (skipped honestly when it
is absent): a generated 10mm box STL is sliced with the shipped fdmprinter +
fdmextruder definitions, and the g-code is independently verified (layer
count, extrusion moves). Every other test pins a refusal or a failure mode
so the adapter cannot silently become unrestricted control.
"""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

import cura_adapter
from cura_adapter import discover, slice_stl, verify_gcode


class DiscoveryTests(unittest.TestCase):
    def test_reports_missing_application_honestly(self):
        missing = discover(search_dirs=(Path(tempfile.mkdtemp(prefix="noapp_")),))
        self.assertFalse(missing.found)
        self.assertIsNone(missing.executable)
        self.assertTrue(missing.reason)

    def test_finds_the_real_installation(self):
        found = discover()
        if not found.found:
            self.skipTest(f"CuraEngine not installed: {found.reason}")
        self.assertTrue(Path(found.executable).is_file())
        self.assertIsNotNone(found.version)
        self.assertIn("5.", found.version)


def _box_stl(size: float = 10.0) -> str:
    """Minimal ASCII STL of a cube (12 facets). Generated, never fixtures."""
    s = size
    v = [(0, 0, 0), (s, 0, 0), (s, s, 0), (0, s, 0),
         (0, 0, s), (s, 0, s), (s, s, s), (0, s, s)]
    faces = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7),
             (0, 1, 5), (0, 5, 4), (2, 3, 7), (2, 7, 6),
             (0, 4, 7), (0, 7, 3), (1, 2, 6), (1, 6, 5)]
    out = ["solid box"]
    for a, b, c in faces:
        out.append(" facet normal 0 0 0")
        out.append("  outer loop")
        for p in (v[a], v[b], v[c]):
            out.append(f"   vertex {p[0]} {p[1]} {p[2]}")
        out.append("  endloop")
        out.append(" endfacet")
    out.append("endsolid box")
    return "\n".join(out)


def _definitions(exe: str) -> tuple[Path, Path]:
    share = Path(exe).parent / "share" / "cura" / "resources" / "definitions"
    return share / "fdmprinter.def.json", share / "fdmextruder.def.json"


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cura_"))
        found = discover()
        if not found.found:
            self.skipTest(f"CuraEngine not installed: {found.reason}")
        self.exe = found.executable
        self.printer, self.extruder = _definitions(found.executable)
        if not (self.printer.is_file() and self.extruder.is_file()):
            self.skipTest("shipped printer definitions not found")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_box_is_sliced_and_gcode_verifies(self):
        stl = self.tmp / "box.stl"
        stl.write_text(_box_stl(), encoding="utf-8")
        out = self.tmp / "box.gcode"
        result = slice_stl(self.exe, stl, out, self.tmp,
                           self.printer, self.extruder, timeout_s=300.0)
        self.assertTrue(result.ok, result.stderr_tail)
        self.assertTrue(out.exists())
        self.assertGreater(out.stat().st_size, 10000)
        self.assertGreater(result.layers or 0, 10)
        self.assertGreater(result.g1_moves or 0, 100)

    def test_stl_outside_workdir_is_refused(self):
        outside = Path(tempfile.mkdtemp(prefix="outside_")) / "evil.stl"
        outside.write_text(_box_stl(), encoding="utf-8")
        try:
            result = slice_stl(self.exe, outside, self.tmp / "o.gcode",
                               self.tmp, self.printer, self.extruder)
            self.assertFalse(result.ok)
            self.assertIn("outside", result.stderr_tail)
        finally:
            shutil.rmtree(outside.parent, ignore_errors=True)

    def test_non_stl_file_is_refused(self):
        txt = self.tmp / "notes.txt"
        txt.write_text("not a mesh", encoding="utf-8")
        result = slice_stl(self.exe, txt, self.tmp / "o.gcode",
                           self.tmp, self.printer, self.extruder)
        self.assertFalse(result.ok)
        self.assertIn("not a .stl", result.stderr_tail)

    def test_missing_stl_is_reported_not_executed(self):
        result = slice_stl(self.exe, self.tmp / "ghost.stl",
                           self.tmp / "o.gcode", self.tmp,
                           self.printer, self.extruder)
        self.assertFalse(result.ok)
        self.assertIn("missing input", result.stderr_tail)

    def test_empty_gcode_fails_verification(self):
        empty = self.tmp / "empty.gcode"
        empty.write_text("", encoding="utf-8")
        report = verify_gcode(empty)
        self.assertFalse(report.ok)

    def test_missing_gcode_fails_verification(self):
        report = verify_gcode(self.tmp / "ghost.gcode")
        self.assertFalse(report.ok)


if __name__ == "__main__":
    unittest.main()
