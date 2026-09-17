"""Workspace API tests: unit + live HTTP routes (safe temp workspace)."""
import json
import os
import tempfile
import threading
import unittest
import urllib.parse
import urllib.request
from pathlib import Path

from workspace_api import WorkspaceAPI


def _get(port, path, query=""):
    url = f"http://127.0.0.1:{port}{path}"
    if query:
        url += "?" + query
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def _post(port, path, body):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


import urllib.error  # noqa: E402


class WorkspaceUnitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="v10_ws_"))
        (self.tmp / "sub").mkdir()
        (self.tmp / "a.txt").write_text("hello alpha\n", encoding="utf-8")
        (self.tmp / "sub" / "b.py").write_text("x = 1\n", encoding="utf-8")
        self.api = WorkspaceAPI([self.tmp])

    def test_list_read_search(self):
        listed = self.api.list(str(self.tmp))
        self.assertTrue(listed["ok"])
        names = {e["name"] for e in listed["entries"]}
        self.assertIn("a.txt", names)
        self.assertIn("sub", names)
        read = self.api.read(str(self.tmp), "a.txt")
        self.assertTrue(read["ok"])
        self.assertIn("alpha", read["content"])
        found = self.api.search(str(self.tmp), "alpha")
        self.assertTrue(found["ok"])
        self.assertTrue(any(h["path"] == "a.txt" for h in found["hits"]))

    def test_write_roundtrip_atomic(self):
        res = self.api.write(str(self.tmp), "new/n.txt", "data-1\n")
        self.assertTrue(res["ok"])
        self.assertTrue(res["verified"])
        self.assertEqual((self.tmp / "new" / "n.txt").read_text(), "data-1\n")
        self.assertFalse((self.tmp / "new" / "n.txt.bridge-tmp").exists())

    def test_escape_blocked(self):
        with self.assertRaises(PermissionError):
            self.api.list(str(self.tmp), "../outside")
        with self.assertRaises(PermissionError):
            self.api.read("/definitely/not/allowed", "a.txt")

    def test_bad_pattern(self):
        res = self.api.search(str(self.tmp), "([unclosed")
        self.assertFalse(res["ok"])

    def test_git_not_a_repo(self):
        res = self.api.git(str(self.tmp), "status")
        self.assertFalse(res["ok"])
        res = self.api.git(str(self.tmp), "push")
        self.assertFalse(res["ok"])


class WorkspaceRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from runtime import AgentRuntime, RuntimeConfig
        from service import serve
        cls.tmp = Path(tempfile.mkdtemp(prefix="v10_wsapi_"))
        (cls.tmp / "proj").mkdir()
        (cls.tmp / "proj" / "hello.txt").write_text("hi\n", encoding="utf-8")
        cls.rt = AgentRuntime(RuntimeConfig(
            allowed_workspace_roots=[str(cls.tmp)]))
        cls.srv = serve(cls.rt, "127.0.0.1", 0)
        cls.port = cls.srv.server_address[1]
        cls.th = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.th.start()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.srv.shutdown()
            cls.srv.server_close()
        except Exception:
            pass
        import shutil
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _q(self, **kw):
        root = str(self.tmp / "proj")
        params = {"root": root}
        params.update(kw)
        return urllib.parse.urlencode(params)

    def test_files_and_file(self):
        code, listed = _get(self.port, "/v1/workspace/files", self._q())
        self.assertEqual(code, 200)
        self.assertTrue(listed["ok"])
        self.assertTrue(any(e["name"] == "hello.txt"
                            for e in listed["entries"]))
        code, read = _get(self.port, "/v1/workspace/file",
                          self._q(path="hello.txt"))
        self.assertEqual(code, 200)
        self.assertIn("hi", read["content"])

    def test_write_then_read(self):
        code, res = _post(self.port, "/v1/workspace/file",
                          {"root": str(self.tmp / "proj"),
                           "path": "w.txt", "content": "written\n"})
        self.assertEqual(code, 200)
        self.assertTrue(res["verified"])
        code, read = _get(self.port, "/v1/workspace/file",
                          self._q(path="w.txt"))
        self.assertIn("written", read["content"])

    def test_escape_rejected(self):
        code, res = _get(self.port, "/v1/workspace/file",
                         self._q(path="../secret"))
        self.assertEqual(code, 403)

    def test_search_and_git(self):
        code, res = _get(self.port, "/v1/workspace/search",
                         self._q(pattern="hi", glob="*.txt"))
        self.assertEqual(code, 200)
        self.assertTrue(res["hits"])
        code, res = _get(self.port, "/v1/git",
                         self._q(op="status"))
        self.assertEqual(code, 200)
        # temp proj is not a git repo: honest negative, still 200 envelope
        self.assertIn("ok", res)


if __name__ == "__main__":
    unittest.main()
