"""Blender adapter: discovery, bounded execution, failure behavior, and one
end-to-end native-artifact proof through the REAL installed Blender 5.2.2.

Skipped honestly when Blender is absent. The end-to-end test asserts on
artifacts and transcripts only: this Blender exits 0 on script errors and
crashed on shutdown after a successful render, so any assertion on exit codes
would prove nothing.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from blender_adapter import discover, run_script

SCENE_SCRIPT = '''import bpy, json
for name in ("Cube", "Cylinder", "Plane", "Camera", "Light"):
    obj = bpy.data.objects.get(name)
    if obj is not None:
        bpy.data.objects.remove(obj, do_unlink=True)
bpy.ops.mesh.primitive_cube_add(size=2.0, location=(0, 0, 1))
bpy.context.active_object.name = "Cube"
bpy.ops.mesh.primitive_cylinder_add(radius=1.0, depth=3.0, location=(4, 0, 1.5))
bpy.context.active_object.name = "Cylinder"
bpy.ops.mesh.primitive_plane_add(size=10.0, location=(0, 0, 0))
bpy.context.active_object.name = "Plane"
bpy.ops.object.camera_add(location=(8, -8, 6), rotation=(1.1, 0, 0.785))
bpy.context.active_object.name = "Camera"
bpy.ops.object.light_add(type="POINT", location=(2, 2, 8))
bpy.context.active_object.name = "Light"
bpy.ops.wm.save_as_mainfile(filepath=r"{workdir}/scene.blend")
names = sorted(o.name for o in bpy.data.objects)
open(r"{workdir}/SCENE_DONE.txt", "w").write("saved objects=" + ",".join(names))
'''

VERIFY_SCRIPT = '''import bpy, json
bpy.ops.wm.open_mainfile(filepath=r"{workdir}/scene.blend")
expected = {"Cube": "MESH", "Cylinder": "MESH", "Plane": "MESH",
            "Camera": "CAMERA", "Light": "LIGHT"}
problems = []
for name, want_type in expected.items():
    o = bpy.data.objects.get(name)
    if o is None:
        problems.append(f"missing {name}")
    elif o.type != want_type:
        problems.append(f"{name} type {o.type}")
report = {"objects_found": len(bpy.data.objects), "problems": problems,
          "pass": not problems}
open(r"{workdir}/VERIFY.json", "w").write(json.dumps(report))
'''

INVALID_SCRIPT = '''import bpy
bpy.ops.mesh.primitive_cube_add(size=2.0)
this_function_does_not_exist_xyz()
'''


class DiscoveryTests(unittest.TestCase):
    def test_launcher_absence_is_reported_not_simulated(self):
        import blender_adapter
        original = blender_adapter.LAUNCHER_NAMES
        blender_adapter.LAUNCHER_NAMES = ("definitely-not-blender-xyz.exe",)
        try:
            missing = discover()
        finally:
            blender_adapter.LAUNCHER_NAMES = original
        self.assertFalse(missing.found)
        self.assertIsNone(missing.launcher)
        self.assertTrue(missing.reason)

    def test_real_launcher_is_found(self):
        found = discover()
        if not found.found:
            self.skipTest(f"Blender not installed: {found.reason}")
        self.assertTrue(found.launcher)


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="blender_"))
        found = discover()
        if not found.found:
            self.skipTest(f"Blender not installed: {found.reason}")
        self.exe = found.launcher

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, name: str, content: str) -> Path:
        path = self.tmp / name
        path.write_text(content.replace("{workdir}", self.tmp.as_posix()), encoding="utf-8")
        return path

    def test_scene_is_created_saved_reopened_and_verified(self):
        create = run_script(self.exe, self._write("scene.py", SCENE_SCRIPT), self.tmp, timeout_s=300.0)
        self.assertTrue((self.tmp / "scene.blend").exists(), create.note)
        self.assertTrue((self.tmp / "SCENE_DONE.txt").exists(), create.note)
        check = run_script(self.exe, self._write("verify.py", VERIFY_SCRIPT), self.tmp, timeout_s=300.0)
        report = json.loads((self.tmp / "VERIFY.json").read_text(encoding="utf-8"))
        self.assertTrue(report["pass"], report)
        self.assertEqual(report["objects_found"], 5)

    def test_script_outside_workdir_is_refused(self):
        outside = Path(tempfile.mkdtemp(prefix="outside_")) / "evil.py"
        outside.write_text("print('nope')", encoding="utf-8")
        try:
            result = run_script(self.exe, outside, self.tmp)
            self.assertFalse(result.ok)
            self.assertIn("outside", result.note)
        finally:
            shutil.rmtree(outside.parent, ignore_errors=True)

    def test_non_python_file_is_refused(self):
        sistine = self.tmp / "chapel.txt"
        sistine.write_text("print('nope')", encoding="utf-8")
        result = run_script(self.exe, sistine, self.tmp)
        self.assertFalse(result.ok)

    def test_missing_script_is_reported_not_executed(self):
        result = run_script(self.exe, self.tmp / "ghost.py", self.tmp)
        self.assertFalse(result.ok)
        self.assertIn("missing script", result.note)

    def test_timeout_kills_the_application(self):
        sleeper = self._write("sleep.py",
                              "import time\ntime.sleep(120)\n"
                              "open(r\"" + self.tmp.as_posix() + "/WOKE.txt\", \"w\").write('woke')\n")
        result = run_script(self.exe, sleeper, self.tmp, timeout_s=25.0)
        self.assertFalse(result.ok)
        self.assertTrue(result.timed_out)
        self.assertTrue(result.killed)
        self.assertFalse((self.tmp / "WOKE.txt").exists())

    def test_invalid_script_leaves_no_artifact(self):
        # The script raises before saving. Blender still exits 0, so the only
        # honest assertion is on the world: no native artifact was produced.
        before = {p.name for p in self.tmp.iterdir()}
        run_script(self.exe, self._write("bogus.py", INVALID_SCRIPT), self.tmp,
                   timeout_s=180.0)
        after = {p.name for p in self.tmp.iterdir()}
        new_blend = [n for n in (after - before) if n.endswith(".blend")]
        self.assertEqual(new_blend, [])


if __name__ == "__main__":
    unittest.main()
