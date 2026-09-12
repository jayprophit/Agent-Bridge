"""v0.6: owner tools — net/proc/installs/gitops/sysinfo (+browser live E2E file)."""
import json
import shutil
import socket
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import installs
import net
import proc
import sysinfo
from executor import Executor


class LocalHTTP:
    """Deterministic local fixture (no external dependency for unit tests)."""

    def __init__(self):
        outer = self
        pages = {"/": ("<html><head><title>Fixture Home</title></head><body>"
                       "<h1>Hi</h1><a href='/p2'>NEXT</a>"
                       "<a href='/file.txt'>file</a></body></html>"),
                 "/p2": ("<html><head><title>Page Two</title></head><body>"
                         "<p>second</p></body></html>"),
                 "/file.txt": "hello-download"}

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
                self.send_header("Content-Type",
                                 "text/html" if self.path != "/file.txt"
                                 else "text/plain")
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


class TestNet(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = LocalHTTP()

    @classmethod
    def tearDownClass(cls):
        cls.http.close()

    def test_get_real(self):
        r = net.http_get(self.http.base + "/")
        self.assertTrue(r["ok"])
        self.assertEqual(r["status"], 200)
        self.assertIn("Fixture", r["text"])
        self.assertGreater(r["duration_s"], 0)

    def test_404_honest(self):
        r = net.http_get(self.http.base + "/nope")
        self.assertFalse(r["ok"])
        self.assertEqual(r["status"], 404)

    def test_timeout_behavior(self):
        # non-routable address with a short timeout must fail fast-ish,
        # never hang, and report honestly
        import time as _t
        t0 = _t.monotonic()
        with self.assertRaises(net.NetError):
            net.http_get("http://10.255.255.1/nope", timeout_s=3)
        self.assertLess(_t.monotonic() - t0, 30)

    def test_download_verified(self):
        tmp = Path(tempfile.mkdtemp(prefix="v06_dl_"))
        try:
            r = net.download(self.http.base + "/file.txt", tmp)
            self.assertTrue(r["ok"], r)
            self.assertTrue(Path(r["destination"]).exists())
            self.assertEqual(Path(r["destination"]).read_bytes(), b"hello-download")
            self.assertEqual(r["size"], 14)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_secret_header_refused(self):
        with self.assertRaises(net.NetError):
            net.http_get(self.http.base + "/",
                         headers={"Authorization": "Bearer x"})

    def test_bad_scheme_refused(self):
        with self.assertRaises(net.NetError):
            net.http_get("ftp://example.com/x")

    def test_safe_filename(self):
        self.assertNotIn("/", net.safe_filename("http://h/a%20b/../x?y=1"))


class TestProc(unittest.TestCase):
    def test_list_real(self):
        r = proc.list_processes()
        self.assertTrue(r["ok"])
        self.assertGreater(r["count"], 2)
        self.assertIn("pid", r["processes"][0])

    def test_launch_evidence(self):
        r = proc.launch("python --version")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["exit_code"], 0)
        self.assertIn("Python", r["stdout"] + r["stderr"])

    def test_spawn_status_kill(self):
        s = proc.spawn("python -c \"import time; time.sleep(60)\"")
        self.assertTrue(s["ok"])
        self.assertIsInstance(s["pid"], int)
        try:
            self.assertTrue(proc.proc_status(s["pid"])["alive"])
        finally:
            k = proc.terminate(s["pid"])
            self.assertTrue(k["ok"], k)
        w = proc.wait_for(s["pid"], timeout_s=15)
        self.assertTrue(w["exited"])

    def test_dead_pid(self):
        self.assertFalse(proc.proc_status(999999).get("alive", True))


class TestInstalls(unittest.TestCase):
    def test_probe_no_mutation(self):
        r = installs.probe()
        self.assertTrue(r["ok"])
        self.assertTrue(r["managers"]["pip"]["present"])
        # probe must not install anything: no new packages asserted here,
        # presence flags only
        self.assertIn("path", r["managers"]["pip"])

    def test_pip_download_proof(self):
        tmp = Path(tempfile.mkdtemp(prefix="v06_pip_"))
        try:
            r = installs.pip_download("six", str(tmp), timeout_s=180)
            self.assertTrue(r["ok"], r)
            names = [p.name for p in tmp.iterdir()]
            self.assertTrue(any("six" in n for n in names), names)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_refuses_non_pm(self):
        r = installs.run_install("rm -rf /tmp/x")
        self.assertFalse(r["ok"])


class TestSysinfo(unittest.TestCase):
    def test_inventory_no_secrets(self):
        import re
        inv = sysinfo.inventory()
        self.assertIn(inv["admin"], ("ADMIN_ACTIVE", "ADMIN_NOT_ACTIVE",
                                    "ADMIN_UNKNOWN"))
        self.assertTrue(inv["drives"])
        self.assertTrue(inv["tools"]["python"]["present"])
        self.assertTrue(inv["tools"]["git"]["present"])
        blob = json.dumps(inv)
        # no secret VALUES (key assignments, tokens, private blocks)
        self.assertIsNone(re.search(r"(?i)(api[_-]?key|password|passwd)\s*[:=]", blob))
        self.assertNotIn("PRIVATE KEY", blob)


class TestGitops(unittest.TestCase):
    def _repo(self):
        tmp = Path(tempfile.mkdtemp(prefix="v06_git_"))
        subprocess.run(["git", "init"], cwd=str(tmp), capture_output=True,
                       timeout=30)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=str(tmp),
                       capture_output=True, timeout=15)
        subprocess.run(["git", "config", "user.name", "t"], cwd=str(tmp),
                       capture_output=True, timeout=15)
        (tmp / "a.txt").write_text("v1\n")
        return tmp

    def test_status_diff_add_commit(self):
        import gitops
        tmp = self._repo()
        try:
            self.assertTrue(gitops.operate(tmp, "status")["ok"])
            self.assertTrue(gitops.operate(tmp, "add", ["a.txt"])["ok"])
            c = gitops.operate(tmp, "commit", message="v06 test commit")
            self.assertTrue(c["ok"], c)
            self.assertTrue(c["before_head"] != c["after_head"] or c["after_head"])
            self.assertEqual(c["branch"] in ("master", "main"), True)
            (tmp / "a.txt").write_text("v2\n")
            d = gitops.operate(tmp, "diff")
            self.assertTrue(d["ok"])
            self.assertIn("a.txt", d["stdout"])
            b = gitops.operate(tmp, "branch")
            self.assertTrue(b["ok"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_not_a_repo(self):
        import gitops
        tmp = Path(tempfile.mkdtemp(prefix="v06_nogit_"))
        try:
            r = gitops.operate(tmp, "status")
            self.assertFalse(r["ok"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestOwnerGating(unittest.TestCase):
    def test_tools_refused_outside_owner(self):
        tmp = Path(tempfile.mkdtemp(prefix="v06_gate_"))
        try:
            ex = Executor(tmp)  # safe profile
            for act in ({"action": "net", "op": "get", "url": "http://x/"},
                        {"action": "proc", "op": "list"},
                        {"action": "browser", "op": "status"},
                        {"action": "git", "op": "status"}):
                r = ex.dispatch(act)
                self.assertFalse(r["ok"], act)
                self.assertIn("OWNER", r["error"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
