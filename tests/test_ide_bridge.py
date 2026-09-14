"""IDE runtime bridge tests: tracker, snapshot, live /v1/runtime."""
import json
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

from ide_bridge import (RuntimeSnapshot, RuntimeStateTracker, TaskEntry,
                        build_runtime_snapshot)


class TestTracker(unittest.TestCase):
    def test_record_snapshot_progress(self):
        tr = RuntimeStateTracker()
        tr.record_task(TaskEntry(task_id="a", objective="x",
                                 status="VERIFIED_COMPLETE"))
        tr.record_task(TaskEntry(task_id="b", objective="y", status="RUNNING"))
        tr.record_queue(["b"])
        tr.record_models([{"model": "m"}], active="m")
        tr.record_workers([{"worker": "w", "state": "BUSY"}])
        tr.record_approval({"id": "ap1"})
        tr.record_result({"task": "a", "ok": True})
        tr.record_evidence("e-1")
        tr.record_resources({"ram_free_gb": 6})
        tr.set_health("HEALTHY")
        tr.record_error("none")
        snap = tr.snapshot().to_dict()
        self.assertEqual(snap["progress_pct"], 50.0)
        self.assertEqual(snap["queue_depth"], 1)
        self.assertEqual(snap["active_model"], "m")
        self.assertEqual(snap["health"], "HEALTHY")
        self.assertIn("e-1", snap["evidence_refs"])

    def test_save_load_roundtrip(self):
        tmp = Path(tempfile.mkdtemp(prefix="v10_ide_"))
        try:
            tr = RuntimeStateTracker(tmp / "snap.json")
            tr.record_task(TaskEntry(task_id="a", status="COMPLETE"))
            self.assertTrue(tr.save())
            tr2 = RuntimeStateTracker(tmp / "snap.json")
            self.assertTrue(tr2.load())
            self.assertEqual(tr2.tasks["a"].status, "COMPLETE")
            self.assertFalse(RuntimeStateTracker(tmp / "nope.json").load())
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_evidence_dedup(self):
        tr = RuntimeStateTracker()
        tr.record_evidence("e-1")
        tr.record_evidence("e-1")
        self.assertEqual(tr.evidence_refs, ["e-1"])


class FakeSession:
    def __init__(self):
        self.tasks = {"t1": {"status": "RUNNING"}}


class FakeRuntime:
    def list_sessions(self):
        return [{"session_id": "s-1"}]

    def get_session(self, sid):
        return FakeSession()

    def health(self):
        return {"status": "HEALTHY"}


class TestSnapshot(unittest.TestCase):
    def test_build_from_runtime(self):
        snap = build_runtime_snapshot(FakeRuntime())
        by_id = {t["task_id"]: t for t in snap["tasks"]}
        self.assertEqual(by_id["t1"]["status"], "RUNNING")
        self.assertEqual(snap["health"], "HEALTHY")

    def test_broken_runtime_degrades(self):
        class Broken:
            def list_sessions(self):
                raise OSError("down")

            def health(self):
                raise OSError("down")
        snap = build_runtime_snapshot(Broken())
        self.assertEqual(snap["tasks"], [])
        self.assertEqual(snap["health"], "UNKNOWN")


class TestLiveRoute(unittest.TestCase):
    def test_runtime_route_live(self):
        from runtime import AgentRuntime, RuntimeConfig
        from service import serve
        tmp = Path(tempfile.mkdtemp(prefix="v10_rt_"))
        try:
            rt = AgentRuntime(RuntimeConfig(
                allowed_workspace_roots=[str(tmp)]))
            srv = serve(rt, "127.0.0.1", 0)
            port = srv.server_address[1]
            th = threading.Thread(target=srv.serve_forever, daemon=True)
            th.start()
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/v1/runtime",
                        timeout=15) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                self.assertIn("tasks", body)
                self.assertIn("queue_depth", body)
                self.assertIn("health", body)
                self.assertIn("timestamp", body)
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/v1/schema",
                        timeout=15) as resp:
                    schema = json.loads(resp.read().decode("utf-8"))
                paths = [r["path"] for r in schema["routes"]]
                self.assertIn("/v1/runtime", paths)
            finally:
                srv.shutdown()
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
