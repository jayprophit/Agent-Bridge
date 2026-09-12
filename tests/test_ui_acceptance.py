"""Reference UI acceptance (v0.8, real headless Edge over local HTTP).

Serves ui/ on loopback, drives it through browser_cdp: Chat/Work session
continuity, docking, Three.js GLB load + avatar animation states,
screenshot evidence. No external hosts, no downloaded assets at runtime
(three.js is vendored).
"""
import os
import re
import tempfile
import threading
import time
import unittest
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

UI_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui")


def _serve():
    handler = partial(SimpleHTTPRequestHandler, directory=UI_DIR)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    srv.daemon_threads = True
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def _session_id(dom_text):
    m = re.search(r"session:\s*([A-Za-z0-9-]+)", dom_text)
    return m.group(1) if m else ""


class ChatWorkContinuityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv, cls.base = _serve()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        from browser_cdp import BrowserSession
        self.browser = BrowserSession(headless=True)
        res = self.browser.launch()
        assert res.get("ok", True), res
        opened = self.browser.open_url(self.base + "/index.html")
        self.assertTrue(opened.get("ok", True), opened)
        self.browser.wait_for("#session-id")

    def tearDown(self):
        try:
            self.browser.stop()
        except Exception:
            pass

    def test_session_survives_chat_work_switch(self):
        b = self.browser
        chat_id = _session_id(b.dom_text().get("text", ""))
        self.assertTrue(chat_id.startswith("session-"), chat_id)
        b.click("#btn-work")
        time.sleep(1.0)
        work_id = _session_id(b.dom_text().get("text", ""))
        self.assertEqual(work_id, chat_id)
        b.click("#btn-chat")
        time.sleep(1.0)
        back_id = _session_id(b.dom_text().get("text", ""))
        self.assertEqual(back_id, chat_id)

    def test_docking_left_right(self):
        b = self.browser
        b.click("#btn-dock")
        time.sleep(0.5)
        self.assertIn("Dock: left", b.dom_text().get("text", ""))
        b.click("#btn-dock")
        time.sleep(0.5)
        self.assertIn("Dock: right", b.dom_text().get("text", ""))

    def test_avatar_canvas_present(self):
        text = self.browser.dom_text().get("text", "")
        self.assertIn("IDLE", text)


class ThreeAvatarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv, cls.base = _serve()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        from browser_cdp import BrowserSession
        self.browser = BrowserSession(headless=True)
        res = self.browser.launch()
        assert res.get("ok", True), res

    def tearDown(self):
        try:
            self.browser.stop()
        except Exception:
            pass

    def _probe_text(self, url, timeout_s=90):
        b = self.browser
        opened = b.open_url(url, timeout_s=timeout_s)
        self.assertTrue(opened.get("ok", True), opened)
        deadline = time.time() + timeout_s
        text = ""
        while time.time() < deadline:
            text = b.dom_text().get("text", "")
            if "probe: ready" in text or "probe: FAILED" in text:
                break
            time.sleep(1.0)
        return text

    def test_glb_loads_in_three(self):
        text = self._probe_text(self.base + "/three.html")
        self.assertIn("probe: ready", text)
        for node in ("Head", "Jaw", "EyeL", "EyeR"):
            self.assertIn(node, text)

    def test_avatar_animation_states(self):
        text = self._probe_text(self.base + "/three.html?demo=think,speak,tool")
        self.assertIn("probe: ready", text)
        for event in ("THINKING", "EMOTION", "SPEAKING", "VISEME",
                      "SUCCESS", "TOOL_RUNNING"):
            self.assertIn(event, text)

    def test_screenshot_has_pixels(self):
        self._probe_text(self.base + "/three.html?demo=speak")
        with tempfile.TemporaryDirectory(prefix="ab_ui_shot_") as d:
            dest = os.path.join(d, "avatar.png")
            res = self.browser.screenshot(dest)
            self.assertTrue(res.get("ok", True), res)
            self.assertTrue(os.path.exists(dest))
            self.assertGreater(os.path.getsize(dest), 10 * 1024)


if __name__ == "__main__":
    unittest.main()
