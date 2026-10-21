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

    def test_models_agree_with_the_live_inventory(self):
        """The runtime snapshot and /v1/models must not disagree.

        /v1/runtime said "no models" while /v1/models said ten, because
        the snapshot only ever carried what a tracker had recorded. A
        consumer of the runtime route was told the machine had no models
        when it had ten. The snapshot is a projection of live state, so
        it has to report the live inventory.
        """
        class WithModels(FakeRuntime):
            def model_inventory(self):
                return {"ok": True, "source": "ollama@127.0.0.1",
                        "models": [{"name": "m-one"}, {"name": "m-two"}]}

        snap = build_runtime_snapshot(WithModels())
        self.assertEqual([m["name"] for m in snap["models"]],
                         ["m-one", "m-two"])

    def test_recorded_models_win_over_the_inventory(self):
        class WithModels(FakeRuntime):
            def model_inventory(self):
                return {"models": [{"name": "live"}]}

        tracker = RuntimeStateTracker()
        tracker.record_models([{"name": "recorded"}], active="recorded")
        snap = build_runtime_snapshot(WithModels(), tracker)
        self.assertEqual([m["name"] for m in snap["models"]], ["recorded"])
        self.assertEqual(snap["active_model"], "recorded")

    def test_no_model_selected_is_not_no_model_available(self):
        """Having models is not the same as having one selected.

        `active_model` stays empty until something is actually chosen,
        so an interface cannot claim a live connection it does not have.
        """
        class WithModels(FakeRuntime):
            def model_inventory(self):
                return {"models": [{"name": "m-one"}]}

        snap = build_runtime_snapshot(WithModels())
        self.assertEqual(len(snap["models"]), 1)
        self.assertEqual(snap["active_model"], "")

    def test_inventory_failure_does_not_break_the_snapshot(self):
        class Angry(FakeRuntime):
            def model_inventory(self):
                raise OSError("ollama unreachable")

        snap = build_runtime_snapshot(Angry())
        self.assertEqual(snap["models"], [])
        self.assertEqual(snap["health"], "HEALTHY")

    def test_runtime_without_an_inventory_still_builds(self):
        snap = build_runtime_snapshot(FakeRuntime())
        self.assertEqual(snap["models"], [])


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
                srv.server_close()
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
