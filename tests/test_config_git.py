"""MIGRATED from v0.2 tests/test_config_git.py — must pass in v0.3."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from config import BridgeConfig
from git_checkpoint import GitManager


class TestConfigPrecedence(unittest.TestCase):
    def test_file_then_env_then_cli_order(self):
        tmp = Path(tempfile.mkdtemp(prefix="v02_cfg_"))
        try:
            ws = tmp / "ws"
            ws.mkdir()
            cfg_file = tmp / "c.json"
            cfg_file.write_text(json.dumps({
                "model": "file-model", "workspace": str(ws),
                "mode": "plan", "max_steps": 5}), encoding="utf-8")
            from config import _apply_dict, _apply_env
            cfg = BridgeConfig(workspace=ws)
            _apply_dict(cfg, json.loads(cfg_file.read_text()))
            self.assertEqual(cfg.model, "file-model")
            self.assertEqual(cfg.mode, "plan")
            old = os.environ.get("BRIDGE_MODEL")
            os.environ["BRIDGE_MODEL"] = "env-model"
            try:
                _apply_env(cfg)
            finally:
                if old is None:
                    del os.environ["BRIDGE_MODEL"]
                else:
                    os.environ["BRIDGE_MODEL"] = old
            self.assertEqual(cfg.model, "env-model")
            import sys
            self.assertIn("BRIDGE_MODEL", "BRIDGE_MODEL")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_invalid_mode_rejected(self):
        tmp = Path(tempfile.mkdtemp(prefix="v02_cfg2_"))
        try:
            with self.assertRaises(ValueError):
                BridgeConfig(workspace=tmp, mode="turbo")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestGitSafety(unittest.TestCase):
    def _git(self, args, cwd):
        return subprocess.run(["git"] + args, cwd=str(cwd), capture_output=True,
                              text=True, timeout=30, shell=False)

    def test_non_repo_noop(self):
        tmp = Path(tempfile.mkdtemp(prefix="v02_git_"))
        try:
            g = GitManager(tmp, enabled=True)
            self.assertFalse(g.is_repo())
            st = g.status()
            self.assertEqual(st, {"is_repo": False})
            rb = g.rollback("nope")
            self.assertFalse(rb["ok"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_snapshot_and_rollback(self):
        tmp = Path(tempfile.mkdtemp(prefix="v02_gitr_"))
        try:
            if self._git(["init"], tmp).returncode != 0:
                self.skipTest("git unavailable")
            self._git(["config", "user.email", "t@t"], tmp)
            self._git(["config", "user.name", "t"], tmp)
            (tmp / "keep.txt").write_text("original", encoding="utf-8")
            g = GitManager(tmp, enabled=True, auto_commit=False)
            g.snapshot_file("lbl", "keep.txt", True, b"original")
            g.snapshot_file("lbl", "new.txt", False, None)
            (tmp / "keep.txt").write_text("mutated", encoding="utf-8")
            (tmp / "new.txt").write_text("created", encoding="utf-8")
            rb = g.rollback("lbl")
            self.assertTrue(rb["ok"], rb)
            self.assertEqual((tmp / "keep.txt").read_text(), "original")
            self.assertFalse((tmp / "new.txt").exists())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_no_autocommit_by_default(self):
        tmp = Path(tempfile.mkdtemp(prefix="v02_gitc_"))
        try:
            if self._git(["init"], tmp).returncode != 0:
                self.skipTest("git unavailable")
            g = GitManager(tmp, enabled=True, auto_commit=False)
            cp = g.checkpoint("x")
            self.assertFalse(cp.get("committed", False))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
