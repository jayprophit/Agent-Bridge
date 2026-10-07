"""Application registry: one record per installed app, queried by capability.

Tests prove the registry mechanics and pin the workstation seed: every
VERIFIED entry must name a bridge adapter, capability queries return the
measured state (not aspirations), and the seed round-trips through disk.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app_registry import (
    APPLICATION_IDS,
    ApplicationRecord,
    ApplicationRegistry,
    AppRegistryError,
    seed_workstation_registry,
)


class RegistryMechanicsTests(unittest.TestCase):
    def test_duplicate_app_id_is_refused(self):
        reg = ApplicationRegistry()
        reg.register(ApplicationRecord(app_id="x", name="X", version="1",
                                       executable="x", install_path="x",
                                       license="?", verification_status="ABSENT"))
        with self.assertRaises(AppRegistryError):
            reg.register(ApplicationRecord(app_id="x", name="X2", version="2",
                                           executable="x", install_path="x",
                                           license="?", verification_status="ABSENT"))

    def test_unknown_app_id_is_an_error_not_none(self):
        with self.assertRaises(AppRegistryError):
            ApplicationRegistry().get("nope")

    def test_verified_requires_a_bridge_adapter(self):
        with self.assertRaises(ValueError):
            ApplicationRecord(app_id="x", name="X", version="1",
                              executable="x", install_path="x", license="?",
                              verification_status="VERIFIED")

    def test_bad_status_is_rejected(self):
        with self.assertRaises(ValueError):
            ApplicationRecord(app_id="x", name="X", version="1",
                              executable="x", install_path="x", license="?",
                              verification_status="SUPERB")


class WorkstationSeedTests(unittest.TestCase):
    def setUp(self):
        self.reg = seed_workstation_registry()

    def test_seed_contains_the_measured_toolchain(self):
        ids = sorted(a.app_id for a in (self.reg.get(i) for i in APPLICATION_IDS))
        self.assertEqual(ids, sorted(APPLICATION_IDS))
        self.assertEqual(len(self.reg.to_dict()["applications"]), len(APPLICATION_IDS))

    def test_verified_entries_all_have_adapters(self):
        for app in [self.reg.get(i) for i in APPLICATION_IDS]:
            if app.verification_status == "VERIFIED":
                self.assertTrue(app.bridge_adapter, app.app_id)
                self.assertTrue(app.last_verified, app.app_id)

    def test_capability_map_answers_honestly(self):
        self.assertIn("freecad", self.reg.verified_for("PARAMETRIC_CAD"))
        self.assertIn("blender", self.reg.verified_for("MESH_MODELING"))
        # slicing VERIFIED 2026-10-07: CuraEngine standalone slice proven
        # (298 layers, 13832 G1 moves) via cura_adapter.py; Orca interactive
        self.assertEqual(self.reg.verified_for("3D_PRINT_SLICING"), ["cura"])
        self.assertEqual(
            self.reg.capability_map()["3D_PRINT_SLICING"], ["cura", "orcaslicer"])

    def test_records_store_placeholders_not_personal_paths(self):
        from app_registry import expand_record_paths
        import os
        kicad = self.reg.get("kicad")
        self.assertNotIn("C:/Users", kicad.executable + kicad.install_path)
        expanded = expand_record_paths(kicad)
        self.assertNotIn("%LOCALAPPDATA%", expanded.executable)
        self.assertTrue(os.path.isabs(expanded.executable))

    def test_seed_round_trips_through_disk(self):
        with tempfile.TemporaryDirectory(prefix="appreg_") as tmp:
            path = Path(tmp) / "apps.json"
            self.reg.save(path)
            back = ApplicationRegistry.load(path)
            ids = sorted(a.app_id for a in (back.get(i) for i in APPLICATION_IDS))
            self.assertEqual(ids, sorted(APPLICATION_IDS))
            self.assertEqual(back.get("kicad").version, "10.0.6")


if __name__ == "__main__":
    unittest.main()
