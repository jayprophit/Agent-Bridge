"""Output routing: canonical E: areas, Desktop guard (file-placement rule)."""
import os
import unittest
from pathlib import Path

import output_locations
from output_locations import OutputLocationResolver, area, assert_not_desktop, is_desktop_path, resolve


class AreaTests(unittest.TestCase):
    def test_known_workstreams(self):
        self.assertEqual(area("CONVERSATION_ANALYSIS"),
                         Path("E:/OpenCode-Data/conversation-analysis"))
        self.assertEqual(area("REPOSITORY_GOVERNANCE"),
                         Path("E:/OpenCode-Data/Repository-Governance"))
        self.assertEqual(area("APP_ECOSYSTEM"),
                         Path("E:/OpenCode-Data/Aetherius-App-Ecosystem"))
        self.assertEqual(area("POIETEK_AUDIO_RESEARCH"),
                         Path("E:/OpenCode-Data/Poietek-Audio-Research"))
        self.assertEqual(area("SIMULATION_GAME_VIDEO"),
                         Path("E:/OpenCode-Data/Simulation-Game-Video-Research"))
        self.assertEqual(area("LOGS"), Path("E:/OpenCode-Data/logs"))
        self.assertEqual(area("TEMP"), Path("E:/OpenCode-Data/temp"))

    def test_unknown_workstream_rejected(self):
        with self.assertRaises(ValueError):
            area("NOPE")

    def test_env_override(self):
        os.environ["OPENCODE_DATA_ROOT"] = "F:/Alt-Data"
        try:
            self.assertEqual(area("LOGS"), Path("F:/Alt-Data/logs"))
        finally:
            del os.environ["OPENCODE_DATA_ROOT"]

    def test_resolve_subpath(self):
        self.assertEqual(resolve("LOGS", "run1", "out.json"),
                         Path("E:/OpenCode-Data/logs/run1/out.json"))


class GuardTests(unittest.TestCase):
    def test_desktop_detected(self):
        self.assertTrue(is_desktop_path(r"C:\Users\jpowe\Desktop\out.json"))
        self.assertTrue(is_desktop_path("C:/Users/jpowe/Desktop"))
        self.assertFalse(is_desktop_path("E:/OpenCode-Data/logs/out.json"))

    def test_desktop_project_dir_still_desktop(self):
        # Canonical repo dirs live on Desktop; the guard flags any Desktop
        # path, so callers must pass explicit owner approval for those.
        self.assertTrue(is_desktop_path(r"C:\Users\jpowe\Desktop\Agent-Bridge\bridge.py"))

    def test_guard_blocks_by_default(self):
        os.environ.pop("OWNER_EXPLICIT_DESKTOP_REQUEST", None)
        with self.assertRaises(ValueError):
            assert_not_desktop(r"C:\Users\jpowe\Desktop\out.json")

    def test_guard_allows_explicit_owner_request(self):
        os.environ["OWNER_EXPLICIT_DESKTOP_REQUEST"] = "TRUE"
        try:
            p = assert_not_desktop(r"C:\Users\jpowe\Desktop\Start-Aetherius-IDE.ps1")
            self.assertEqual(p, Path(r"C:\Users\jpowe\Desktop\Start-Aetherius-IDE.ps1"))
        finally:
            del os.environ["OWNER_EXPLICIT_DESKTOP_REQUEST"]

    def test_guard_passes_canonical(self):
        p = assert_not_desktop("E:/OpenCode-Data/logs/out.json")
        self.assertEqual(p, Path("E:/OpenCode-Data/logs/out.json"))

    def test_default_rule_is_deny(self):
        self.assertFalse(output_locations.ALLOW_DESKTOP_PROGRAMME_OUTPUT)


class ResolverTests(unittest.TestCase):
    def test_conceptual_api(self):
        r = OutputLocationResolver()
        self.assertEqual(r.resolve("CONVERSATION_ANALYSIS", "x.json"),
                         Path("E:/OpenCode-Data/conversation-analysis/x.json"))
        self.assertEqual(r.resolve("LOGS", "a.log", persistence="LOG"),
                         Path("E:/OpenCode-Data/logs/logs/a.log"))

    def test_unknown_persistence_rejected(self):
        with self.assertRaises(ValueError):
            OutputLocationResolver().resolve("LOGS", "a", persistence="NOPE")


if __name__ == "__main__":
    unittest.main()
