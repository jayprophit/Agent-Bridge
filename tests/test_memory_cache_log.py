"""MIGRATED from v0.2 tests/test_memory_cache_log.py — must pass in v0.3."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from bridge import run_bridge
from cache import BridgeCache
from config import BridgeConfig
from eventlog import EventLogger
from executor import Executor
from memory import SessionMemory
from tests.helpers import FakeProvider


class TestMemory(unittest.TestCase):
    def test_record_and_persist(self):
        tmp = Path(tempfile.mkdtemp(prefix="v02_mem_"))
        try:
            mp = tmp / "mem.json"
            m = SessionMemory(mp)
            m.set_task("demo", "fake")
            m.record("completed", {"step": 1, "action": {"action": "list"}})
            m.record("tests_run", {"command": "python -m pytest", "passed": True})
            self.assertTrue(mp.exists())
            m2 = SessionMemory(mp)
            self.assertEqual(m2.data["task"], "demo")
            self.assertEqual(len(m2.data["completed"]), 1)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestCache(unittest.TestCase):
    def test_invalidation(self):
        tmp = Path(tempfile.mkdtemp(prefix="v02_cache_"))
        try:
            cache = BridgeCache(workspace=tmp, enabled=True)
            ex = Executor(tmp, cache=cache)
            ex.do_write("a.txt", "v1")
            r1 = ex.do_read("a.txt")
            self.assertIn("v1", r1["content"])
            cache.put_read("a.txt", tmp / "a.txt", r1)
            ex.do_write("a.txt", "v2")
            self.assertNotIn("a.txt", cache._reads)
            r2 = ex.do_read("a.txt")
            self.assertIn("v2", r2["content"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_disabled(self):
        c = BridgeCache(enabled=False)
        self.assertIsNone(c.get_read("x"))
        self.assertEqual(c.stats()["entries"], 0)


class TestJsonlLogging(unittest.TestCase):
    def test_jsonl_events(self):
        tmp = Path(tempfile.mkdtemp(prefix="v02_log_"))
        try:
            jl = tmp / "events.jsonl"
            cfg = BridgeConfig(workspace=tmp, mode="build", approval="AUTO_SAFE",
                               max_steps=4, non_interactive=True,
                               enable_reviewer=False)
            cfg.logging.jsonl_log = str(jl)
            fake = FakeProvider(['{"action":"list","path":"."}',
                                 '{"action":"finish","message":"ok"}'])
            out = run_bridge(cfg, "log test", provider=fake)
            self.assertTrue(out["finished"])
            self.assertTrue(jl.exists())
            lines = [json.loads(l) for l in jl.read_text().splitlines() if l.strip()]
            self.assertTrue(any("session_id" in l and "step" in l for l in lines))
            self.assertTrue(all("api_key" not in l for l in lines))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_human_log_file(self):
        tmp = Path(tempfile.mkdtemp(prefix="v02_hlog_"))
        try:
            hl = tmp / "run.log"
            log = EventLogger(hl, None, "m", "build", session_id="abc")
            log.human("hello")
            self.assertIn("hello", hl.read_text())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
