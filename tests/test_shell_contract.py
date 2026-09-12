"""v0.5: shell contract, display safety, prefs isolation."""
import ast
import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from reference_agent_shell import views
from reference_agent_shell.prefs import Prefs

ALLOWED_SHELL_IMPORTS = {"client", "reference_agent_shell", "argparse",
                         "json", "sys", "time", "pathlib", "typing"}
# NOTE: `runtime` (AgentRuntime) and `client` are PUBLIC APIs and allowed.
# Only bridge internals are banned.
BANNED = {"executor", "policy", "protocol", "checkpoints",
          "memory", "cache", "events", "state", "bridge", "providers",
          "reviewer", "routing", "oracle"}


class TestShellContract(unittest.TestCase):
    def test_shell_imports_public_only(self):
        for name in ("shell.py", "views.py", "prefs.py", "mock_runtime.py",
                     "__init__.py"):
            tree = ast.parse((Path("reference_agent_shell") / name).read_text(
                encoding="utf-8"))
            imported: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(a.name.split(".")[0] for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
            for banned in BANNED:
                self.assertNotIn(banned, imported, f"{name} imports {banned}")

    def test_genesis_sim_v2_public_only(self):
        tree = ast.parse(Path("genesis_client_simulator_v2.py").read_text(
            encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        for banned in BANNED | {"runtime"}:
            self.assertNotIn(banned, imported)
        self.assertIn("client", imported)


class TestDisplaySafety(unittest.TestCase):
    def test_control_chars_stripped(self):
        self.assertNotIn("\x1b", views.safe("\x1b[31mRED\x00INJECT"))
        self.assertNotIn("\x00", views.safe("a\x00b"))

    def test_oversized_bounded(self):
        self.assertLessEqual(len(views.safe("x" * 100000, limit=500)), 700)

    def test_html_escaping(self):
        self.assertIn("&lt;script&gt;", views.safe_html("<script>alert(1)</script>"))

    def test_malicious_event_rendered_inert(self):
        e = {"event": "approval.requested",
             "action": {"action": "write", "path": "\x1b[2J../../evil\nname"},
             "context": {"risk": "RISKY\"><img src=x>",
                         "reason": "x" * 5000}}
        line = views.event_line(e)
        self.assertNotIn("\x1b", line)
        self.assertLess(len(line), 3000)

    def test_malicious_diff_inert(self):
        evil = {"ok": True, "diff": "<script>\x00" + "A" * 9000}
        self.assertIn("&lt;script&gt;", views.safe_html(evil["diff"]))
        self.assertLess(len(views.safe(evil["diff"], 4000)), 4600)


class TestPrefsIsolation(unittest.TestCase):
    def test_prefs_ignore_policy_keys(self):
        tmp = Path(tempfile.mkdtemp(prefix="v05_prefs_"))
        try:
            p = tmp / "p.json"
            p.write_text(json.dumps({"default_mode": "plan",
                                     "approval": "READ_ONLY",
                                     "allowed_workspace_roots": ["/"],
                                     "token": "steal"}))
            prefs = Prefs(p)
            self.assertEqual(prefs.data["default_mode"], "plan")
            self.assertNotIn("approval", prefs.data)
            self.assertNotIn("allowed_workspace_roots", prefs.data)
            self.assertNotIn("token", prefs.data)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_prefs_only_known_keys_saved(self):
        prefs = Prefs(Path(tempfile.mkdtemp(prefix="v05_p2_")) / "p.json")
        self.assertEqual(set(prefs.data), {"default_mode", "default_model_profile",
                                           "approval_preference", "event_verbosity",
                                           "display", "workspace_root",
                                           "last_workspace"})


if __name__ == "__main__":
    unittest.main()
