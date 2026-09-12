"""v0.6: real browser automation (headless Edge/Chrome on this machine)."""
import shutil
import socket
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import browser_cdp
from browser_cdp import BrowserSession, vision_provider


class Fixture:
    PAGES = {
        "/": ("<html><head><title>Fixture Home</title></head><body>"
              "<h1>Welcome</h1><a id='next' href='/p2'>NEXT PAGE</a>"
              "<a href='/p3'>three</a></body></html>"),
        "/p2": ("<html><head><title>Second</title></head><body>"
                "<ul><li class='it'>alpha</li><li class='it'>beta</li></ul>"
                "<a id='next' href='/p3'>NEXT PAGE</a></body></html>"),
        "/p3": ("<html><head><title>Third</title></head><body>"
                "<p>final</p></body></html>"),
        "/tall": ("<html><head><title>Tall</title></head><body>"
                  "<div style='height:5000px'>tall content</div></body></html>"),
    }

    def __init__(self):
        pages = self.PAGES

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                body = pages.get(self.path)
                if body is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                data = body.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.srv.daemon_threads = True
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    @property
    def base(self):
        return f"http://127.0.0.1:{self.port}"

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


class TestBrowserReal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fix = Fixture()

    @classmethod
    def tearDownClass(cls):
        cls.fix.close()

    def _sess(self):
        s = BrowserSession()
        s.launch()
        self.addCleanup(lambda: s.stop())
        return s

    def test_launch_navigate_title_text(self):
        s = self._sess()
        r = s.open_url(self.fix.base + "/")
        self.assertTrue(r["ok"], r)
        self.assertEqual(s.title(), "Fixture Home")
        t = s.dom_text()
        self.assertTrue(t["ok"])
        self.assertIn("Welcome", t["text"])
        self.assertEqual(s.current_url(), self.fix.base + "/")

    def test_links_click_pagination(self):
        s = self._sess()
        s.open_url(self.fix.base + "/")
        links = s.links()
        self.assertTrue(links["ok"])
        self.assertTrue(any("NEXT" in (l.get("text") or "") for l in links["links"]))
        s.click("#next")
        s.wait_for("li.it", timeout_s=15)
        self.assertEqual(s.title(), "Second")
        pg = s.paginate("#next", max_pages=5)
        self.assertTrue(pg["ok"])
        self.assertGreaterEqual(pg["pages"], 1)
        self.assertEqual(s.title(), "Third")

    def test_scroll_screenshot_cookies(self):
        s = self._sess()
        s.open_url(self.fix.base + "/")
        sc = s.scroll(400)
        self.assertTrue(sc["ok"])
        tmp = Path(tempfile.mkdtemp(prefix="v06_shot_"))
        try:
            shot = s.screenshot(tmp / "s.png")
            self.assertTrue(shot["ok"], shot)
            self.assertGreater(shot["bytes"], 1000)
            ck = s.cookies()
            self.assertTrue(ck["ok"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_back_forward_reload(self):
        s = self._sess()
        s.open_url(self.fix.base + "/")
        s.click("#next")
        s.wait_for("li.it", timeout_s=15)
        self.assertTrue(s.back()["ok"])
        self.assertEqual(s.title(), "Fixture Home")
        self.assertTrue(s.forward()["ok"])
        self.assertTrue(s.reload()["ok"])

    def test_infinite_scroll_terminates(self):
        s = self._sess()
        s.open_url(self.fix.base + "/tall")
        r = s.infinite_scroll(max_rounds=6)
        self.assertTrue(r["ok"])
        self.assertLessEqual(r["rounds"], 6)
        self.assertIn("rounds_done", r["checkpoint"])


class TestVisionHonesty(unittest.TestCase):
    def test_unavailable_by_default(self):
        v = vision_provider()
        r = v.describe("whatever.png", "what is this?")
        self.assertFalse(r["ok"])
        self.assertFalse(r["available"])

    def test_unknown_kind_refused(self):
        with self.assertRaises(browser_cdp.BrowserError):
            vision_provider("gpt-xyz")


if __name__ == "__main__":
    unittest.main()
