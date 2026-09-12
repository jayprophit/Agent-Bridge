"""v0.8.1 maintenance conformance: think control, verified completion,
test-runner discovery, safe-edit repair, local dirs, product version.

No network, no Ollama, no browser. Adapter network calls are faked at
the _ollama_request boundary; bridge runs use FakeProvider + tmp dirs.
"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class ThinkControlTests(unittest.TestCase):
    def _provider(self, reply):
        from models.providers.ollama_provider import OllamaProvider
        p = OllamaProvider()
        seen = {}
        fake = {"message": {"content": reply.get("content", ""),
                            "thinking": reply.get("thinking", "")},
                "done": True, "eval_count": 3, "eval_duration": 100000000}
        def _req(method, path, payload=None):
            seen.update(payload or {})
            return fake
        p._ollama_request = _req
        return p, seen

    def test_capability_advertised(self):
        from models.providers.ollama_provider import OllamaProvider
        caps = OllamaProvider().capabilities()
        self.assertTrue(caps.get("supports_think_control"))

    def test_think_omitted_by_default(self):
        p, seen = self._provider({"content": "hi"})
        out = p.generate("m", [{"role": "user", "content": "hi"}])
        self.assertTrue(out["ok"])
        self.assertNotIn("think", seen)

    def test_think_false_forwarded(self):
        p, seen = self._provider({"content": '{"action":"finish"}'})
        out = p.generate("qwen3:1.7b", [{"role": "user", "content": "x"}],
                         think=False)
        self.assertTrue(out["ok"])
        self.assertIs(seen.get("think"), False)
        self.assertFalse(out["think_requested"])

    def test_thinking_chars_visible_not_hidden(self):
        p, _ = self._provider({"content": "", "thinking": "hmm " * 40})
        out = p.generate("qwen3:1.7b", [{"role": "user", "content": "x"}])
        self.assertEqual(out["content"], "")
        self.assertGreater(out["metadata"]["thinking_chars"], 0)


class VerifiedCompletionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ab_v081_"))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, **kw):
        from bridge import run_bridge
        from config import BridgeConfig
        from tests.helpers import FakeProvider
        args = dict(workspace=self.tmp, mode="build", approval="AUTO_SAFE",
                    max_steps=6, non_interactive=True, enable_reviewer=False)
        args.update(kw)
        cfg = BridgeConfig(**args)
        return run_bridge(cfg, "t", provider=FakeProvider(
            ['{"action":"finish","message":"done"}']))

    def test_default_stays_verified_complete(self):
        out = self._run()
        self.assertTrue(out.get("finished"))
        self.assertEqual(out.get("completion"), "VERIFIED_COMPLETE")

    def test_missing_artifact_is_claimed_not_verified(self):
        out = self._run(expected_artifacts=["proof.txt"])
        self.assertTrue(out.get("finished"))
        self.assertEqual(out.get("completion"), "MODEL_CLAIMED_COMPLETE")
        self.assertTrue(any("proof.txt" in m
                            for m in out["verification"]["missing"]))

    def test_present_artifact_verifies(self):
        (self.tmp / "proof.txt").write_text("evidence", encoding="utf-8")
        out = self._run(expected_artifacts=["proof.txt"])
        self.assertEqual(out.get("completion"), "VERIFIED_COMPLETE")

    def test_invalid_json_detected(self):
        (self.tmp / "data.json").write_text("{not json", encoding="utf-8")
        out = self._run(expected_artifacts=["data.json"])
        self.assertEqual(out.get("completion"), "MODEL_CLAIMED_COMPLETE")

    def test_verify_command_must_exit_zero(self):
        (self.tmp / "test_ok.py").write_text(
            "import unittest\nclass T(unittest.TestCase):\n"
            " def test_x(self):\n  self.assertTrue(True)\n",
            encoding="utf-8")
        out = self._run(expected_artifacts=["test_ok.py"],
                        verify_command="python -m unittest test_ok -v")
        self.assertEqual(out.get("completion"), "VERIFIED_COMPLETE")


class RunnerDetectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ab_runner_"))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_pytest_config_without_pytest_is_dependency(self):
        from tools.cat_core import detect_test_runner
        (self.tmp / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
        with mock.patch("shutil.which", return_value=None):
            det = detect_test_runner(self.tmp)
        self.assertEqual(det["runner"], "pytest")
        self.assertIn("dependency", det)

    def test_unittest_discovery_preferred(self):
        from tools.cat_core import detect_test_runner
        (self.tmp / "test_a.py").write_text("x = 1\n", encoding="utf-8")
        det = detect_test_runner(self.tmp)
        self.assertEqual(det["runner"], "unittest")
        self.assertIn("unittest", det["command"])

    def test_stdlib_fallback(self):
        from tools.cat_core import detect_test_runner
        with mock.patch("shutil.which", return_value=None):
            det = detect_test_runner(self.tmp)
        self.assertEqual(det["command"], "python -m unittest")

    def test_adapter_reports_missing_runner(self):
        from executor import Executor
        from tools.cat_core import TestAdapter
        (self.tmp / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
        ex = Executor(workspace=self.tmp)
        ad = TestAdapter({"executor": ex}, "test.run")
        with mock.patch("shutil.which", return_value=None):
            res = ad.execute({})
        self.assertFalse(res.get("ok"))
        self.assertIn("pytest", res.get("error", ""))


class SafeEditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ab_edit_"))
        from executor import Executor
        self.ex = Executor(workspace=self.tmp)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, content="line1\nline2\n"):
        self.assertTrue(self.ex.dispatch(
            {"action": "write", "path": "f.txt",
             "content": content})["ok"])

    def test_hash_match_proceeds_and_returns_new_hash(self):
        self._write()
        h1 = self.ex.dispatch({"action": "read", "path": "f.txt"})
        self.assertTrue(h1["ok"])
        import hashlib
        h = hashlib.sha256(b"line1\nline2\n").hexdigest()[:16]
        res = self.ex.dispatch(
            {"action": "edit", "path": "f.txt", "old": "line2",
             "new": "LINE2", "expected_hash": h})
        self.assertTrue(res.get("ok"), res)
        self.assertIn("current_hash", res)

    def test_stale_hash_conflicts_without_mutation(self):
        self._write()
        before = (self.tmp / "f.txt").read_bytes()
        res = self.ex.dispatch(
            {"action": "edit", "path": "f.txt", "old": "line2",
             "new": "LINE2", "expected_hash": "deadbeefdeadbeef"})
        self.assertFalse(res.get("ok"))
        self.assertEqual(res.get("kind"), "EDIT_CONFLICT")
        self.assertIn("preview", res)
        self.assertIn("current_hash", res)
        self.assertEqual((self.tmp / "f.txt").read_bytes(), before)

    def test_miss_returns_hash_and_preview(self):
        self._write()
        res = self.ex.dispatch(
            {"action": "edit", "path": "f.txt", "old": "nope",
             "new": "x"})
        self.assertFalse(res.get("ok"))
        self.assertEqual(res.get("kind"), "EDIT_MISS")
        self.assertIn("current_hash", res)

    def test_reconcile_retry_flow(self):
        self._write()
        first = self.ex.dispatch(
            {"action": "edit", "path": "f.txt", "old": "line2",
             "new": "LINE2", "expected_hash": "stale0000000000"})
        self.assertEqual(first.get("kind"), "EDIT_CONFLICT")
        retry = self.ex.dispatch(
            {"action": "edit", "path": "f.txt", "old": "line2",
             "new": "LINE2",
             "expected_hash": first["current_hash"]})
        self.assertTrue(retry.get("ok"), retry)


class LocalDirsTests(unittest.TestCase):
    def test_explicit_env_repo_order(self):
        import tempfile as _t
        import localdirs
        d1 = _t.mkdtemp(prefix="ab_loc1_")
        d2 = _t.mkdtemp(prefix="ab_loc2_")
        try:
            self.assertEqual(localdirs.local_root(explicit=d1), d1)
            with mock.patch.dict(os.environ, {"AGENT_BRIDGE_LOCAL": d2}):
                self.assertEqual(localdirs.local_root(), d2)
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("AGENT_BRIDGE_LOCAL", None)
                os.environ.pop("AGENT_BRIDGE_ROOT", None)
                root = localdirs.local_root(root=os.path.abspath("."))
                self.assertTrue(root.endswith("local"))
        finally:
            import shutil
            shutil.rmtree(d1, ignore_errors=True)
            shutil.rmtree(d2, ignore_errors=True)

    def test_unknown_area_rejected_and_create_works(self):
        import localdirs
        with self.assertRaises(ValueError):
            localdirs.local_subdir("nope")
        import tempfile as _t
        d = _t.mkdtemp(prefix="ab_loc3_")
        try:
            p = localdirs.local_subdir("temp", explicit=d, create=True)
            self.assertTrue(os.path.isdir(p))
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)


class ProductVersionTests(unittest.TestCase):
    def test_product_version(self):
        import versions
        self.assertEqual(versions.PRODUCT_VERSION, "0.8.1")
        self.assertEqual(versions.RUNTIME_VERSION, "0.6")


if __name__ == "__main__":
    unittest.main()
