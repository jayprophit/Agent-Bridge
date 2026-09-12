"""v0.5: version/config cleanup guards + validation + migration."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import versions
from config_validate import migrate_dict, validate_dict


class TestStaleLabels(unittest.TestCase):
    def test_no_stale_defaults(self):
        from config import BridgeConfig
        import tempfile as _t
        tmp = Path(_t.mkdtemp(prefix="v05_v_"))
        try:
            cfg = BridgeConfig(workspace=tmp)
            blob = json.dumps({"prefix": cfg.git.checkpoint_label_prefix,
                               "rt": versions.RUNTIME_VERSION})
            for frag in versions.STALE_LABEL_FRAGMENTS:
                self.assertNotIn(frag, blob)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_source_has_no_stale_producers(self):
        root = Path(".")
        hits = []
        for py in list(root.glob("*.py")) + list(root.glob("reference_agent_shell/*.py")):
            lines = py.read_text(encoding="utf-8").splitlines()
            in_frag_def = False
            for i, line in enumerate(lines, 1):
                if "STALE_LABEL_FRAGMENTS" in line:
                    in_frag_def = True
                if in_frag_def:
                    if line.strip().endswith(")"):
                        in_frag_def = False
                    continue  # the detector list itself is not a producer
                for frag in versions.STALE_LABEL_FRAGMENTS:
                    # legacy *readers* mention old labels in compat lists
                    low = line.lower()
                    if frag in line and "legacy" not in low \
                            and "stale" not in low:
                        hits.append(f"{py}:{i}")
        self.assertEqual(hits, [], f"stale producers: {hits}")

    def test_version_centralization(self):
        # v0.6 intentional bumps; single source of truth in versions.py
        self.assertEqual(versions.RUNTIME_VERSION, "0.6")
        self.assertEqual(versions.API_VERSION, "v1")
        self.assertEqual(versions.CONFIG_SCHEMA_VERSION, 2)
        self.assertEqual(versions.CLIENT_SDK_VERSION, "0.6")
        self.assertIn("0.3", versions.PROTOCOL_ACCEPTED)
        self.assertNotIn("bridge-v05", versions.CHECKPOINT_LABEL_PREFIX)


class TestValidation(unittest.TestCase):
    def test_good_config(self):
        d = json.loads(Path("bridge_config.json").read_text(encoding="utf-8"))
        ok, problems = validate_dict(d)
        self.assertTrue(ok, problems)
        self.assertEqual(d["config_schema"], 2)

    def test_rejects_bad_security(self):
        ok, _ = validate_dict({"mode": "turbo", "approval": "YOLO",
                               "api_key": "x"})
        self.assertFalse(ok)
        ok2, p2 = validate_dict({"runtime": {"host": "0.0.0.0"}})
        self.assertFalse(ok2)
        self.assertTrue(any("bind" in p for p in p2))
        ok3, _ = validate_dict({"runtime": {"quotas": {"max_actions_per_task": -1}}})
        self.assertFalse(ok3)

    def test_rejects_weakening_unknown(self):
        ok, _ = validate_dict({"collision": "SILENT"})
        self.assertFalse(ok)


class TestMigration(unittest.TestCase):
    def test_v04_shape_migrates(self):
        old = {"model": "m", "workspace": ".", "mode": "build",
               "git": {"checkpoint_label_prefix": "bridge-v04"}}
        nd, warnings = migrate_dict(old)
        self.assertEqual(nd["config_schema"], 2)
        self.assertEqual(nd["git"]["checkpoint_label_prefix"], "bridge-v06")
        self.assertTrue(any("ambiguous" in w for w in warnings))
        ok, problems = validate_dict(nd)
        self.assertTrue(ok, problems)

    def test_v05_shape_migrates(self):
        old = json.loads(Path("config/bridge_config_v05.json").read_text(encoding="utf-8"))
        nd, warnings = migrate_dict(old)
        ok, problems = validate_dict(nd)
        self.assertTrue(ok, problems)
        self.assertEqual(nd["git"]["checkpoint_label_prefix"], "bridge-v06")

    def test_bad_approval_refuses(self):
        with self.assertRaises(ValueError):
            migrate_dict({"approval": "TRUST_ME"})


if __name__ == "__main__":
    unittest.main()
