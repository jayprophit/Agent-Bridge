"""Real desktop E2E: built IDE app + live Agent Bridge service.

Serves the production-built IDE bundle, points it at a live loopback
Agent Bridge service (ephemeral ports), drives headless Edge with
test-only --disable-web-security (production CORS policy untouched),
and asserts LIVE runtime data renders. Skips cleanly when the IDE
bundle or a browser is unavailable.
"""
import json
import os
import tempfile
import threading
import time
import unittest
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

IDE_DIST = r"C:\Users\jpowe\Desktop\IDE-Workspace\workspace\app\dist"


def _has_browser():
    try:
        from browser_cdp import find_browser
        find_browser()
        return True
    except Exception:
        return False


class DesktopE2E(unittest.TestCase):
    def test_live_runtime_in_ide(self):
        if not os.path.isdir(IDE_DIST) or not os.path.exists(
                os.path.join(IDE_DIST, "index.html")):
            self.skipTest("IDE production bundle not built")
        if not _has_browser():
            self.skipTest("no headless browser available")
        from browser_cdp import BrowserSession
        from runtime import AgentRuntime, RuntimeConfig
        from service import serve
        from tests.helpers import FakeProvider

        tmp = tempfile.mkdtemp(prefix="v10_e2e_")
        session_id = ""
        try:
            provs = {}

            def factory(role):
                if role not in provs:
                    provs[role] = FakeProvider(
                        ['{"action":"write","path":"e2e.txt","content":"hi"}',
                         '{"action":"finish","message":"e2e demo"}'])
                return provs[role]

            rt = AgentRuntime(
                RuntimeConfig(allowed_workspace_roots=[tmp]),
                provider_factory=factory)
            srv = serve(rt, "127.0.0.1", 0)
            port = srv.server_address[1]
            sth = threading.Thread(target=srv.serve_forever, daemon=True)
            sth.start()

            handler = partial(SimpleHTTPRequestHandler, directory=IDE_DIST)
            web = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            web.daemon_threads = True
            wth = threading.Thread(target=web.serve_forever, daemon=True)
            wth.start()
            web_port = web.server_address[1]

            # Seed one completed task on the SERVED runtime so the UI
            # has live task data.
            ws = os.path.join(tmp, "proj")
            os.makedirs(ws, exist_ok=True)
            s = rt.create_session(ws, mode="build")
            session_id = s.session_id
            res = s.run_task("e2e demo task", timeout=120)
            self.assertEqual(res.get("status"), "COMPLETED")
            _ = session_id

            b = BrowserSession(headless=True, extra_chrome_args=[
                "--disable-web-security"])
            try:
                launched = b.launch()
                self.assertTrue(launched.get("ok", True), launched)
                opened = b.open_url(f"http://127.0.0.1:{web_port}/index.html")
                self.assertTrue(opened.get("ok", True), opened)
                b.wait_for("[data-testid=backend-state]")
                b._eval(
                    f"window.__BRIDGE_BASE__='http://127.0.0.1:{port}'")
                deadline = time.time() + 30
                text = ""
                while time.time() < deadline:
                    text = b.dom_text().get("text", "")
                    if "backend: connected" in text:
                        break
                    time.sleep(1.0)
                self.assertIn("backend: connected", text)
                self.assertIn("nomic-embed-text", text)
                # Real terminal flow: run a command, see real output.
                b.wait_for("[data-testid=terminal-input]")
                b.type_text("[data-testid=terminal-input]", "python --version")
                b.click("[data-testid=terminal-send]")
                deadline = time.time() + 60
                tout = ""
                while time.time() < deadline:
                    tout = b.dom_text().get("text", "")
                    if "Python 3" in tout:
                        break
                    time.sleep(1.0)
                self.assertIn("Python 3", tout)
                self.assertIn("USER TERMINAL COMMAND", tout)
                # Denied command surfaces policy, not silence.
                b.type_text("[data-testid=terminal-input]", "format F:")
                b.click("[data-testid=terminal-send]")
                deadline = time.time() + 60
                tden = ""
                while time.time() < deadline:
                    tden = b.dom_text().get("text", "")
                    if "POLICY_DENIED" in tden:
                        break
                    time.sleep(1.0)
                self.assertIn("POLICY_DENIED", tden)
            finally:
                try:
                    b.stop()
                except Exception:
                    pass
            srv.shutdown()
            web.shutdown()
            web.server_close()
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
