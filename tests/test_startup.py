"""Startup/packaging acceptance: CLI boots, service serves, health answers."""
import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


class StartupTests(unittest.TestCase):
    def test_cli_help_boots(self):
        r = subprocess.run([sys.executable, str(REPO / "cli.py"), "--help"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0)
        self.assertIn("serve", r.stdout)

    def test_serve_boots_and_health(self):
        from runtime import AgentRuntime, RuntimeConfig
        from service import serve
        tmp = Path(tempfile.mkdtemp(prefix="v10_boot_"))
        try:
            rt = AgentRuntime(RuntimeConfig(
                allowed_workspace_roots=[str(tmp)]))
            srv = serve(rt, "127.0.0.1", 0)
            th = threading.Thread(target=srv.serve_forever, daemon=True)
            th.start()
            try:
                port = srv.server_address[1]
                deadline = time.time() + 30
                body = None
                while time.time() < deadline:
                    try:
                        with urllib.request.urlopen(
                                f"http://127.0.0.1:{port}/health",
                                timeout=5) as resp:
                            body = json.loads(resp.read().decode("utf-8"))
                        break
                    except OSError:
                        time.sleep(0.5)
                self.assertIsNotNone(body, "health never answered")
            finally:
                srv.shutdown()
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
