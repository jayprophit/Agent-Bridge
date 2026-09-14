"""Genesis runtime tests: persistence/rotation live, delegation mocked."""
import tempfile
import unittest
from pathlib import Path

from genesis_runtime import LocalGenesisRuntime


class FakeBridge:
    def __init__(self):
        self.tasks = {}
        self.n = 0

    def submit(self, handoff):
        self.n += 1
        tid = f"w-{self.n}"
        self.tasks[tid] = {"status": "COMPLETED", "handoff": handoff}
        return tid

    def poll(self, task_id):
        return dict(self.tasks.get(task_id, {"status": "UNKNOWN"}))


class GenesisRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="v10_gen_"))
        self.rt = LocalGenesisRuntime(
            self.tmp / "genesis.json",
            bridge_factory=FakeBridge,
            model_ping=lambda m: True)

    def test_identify_and_session(self):
        ident = self.rt.identify("g-1")
        self.assertEqual(ident["genesis_id"], "g-1")
        s = self.rt.start_session("demo objective")
        self.assertEqual(s.genesis_id, "g-1")
        kinds = [e["kind"] for e in self.rt.events]
        self.assertIn("session.started", kinds)
        self.assertIn("objective.received", kinds)

    def test_rotation_keeps_identity(self):
        self.rt.identify("g-1")
        r1 = self.rt.rotate_model("granite3.3:2b")
        self.assertTrue(r1["ok"])
        r2 = self.rt.rotate_model("qwen2.5-coder:3b-instruct-q4_K_M")
        self.assertTrue(r2["ok"])
        self.assertEqual(self.rt.identity.genesis_id, "g-1")
        self.assertIn("granite3.3:2b", self.rt.identity.model_history)

    def test_dead_model_refused(self):
        rt = LocalGenesisRuntime(
            self.tmp / "gen2.json", bridge_factory=FakeBridge,
            model_ping=lambda m: False)
        rt.identify("g-1")
        out = rt.rotate_model("ghost-xyz")
        self.assertFalse(out["ok"])
        kinds = [e["kind"] for e in rt.events]
        self.assertIn("model.unavailable", kinds)

    def test_delegate_observe_integrate(self):
        self.rt.identify("g-1")
        s = self.rt.start_session("build x")
        tid = self.rt.delegate({"genesis_session": s.session_id,
                                "objective": "build x"})
        obs = self.rt.observe(tid)
        self.assertEqual(obs["status"], "COMPLETED")
        done = self.rt.integrate(tid)
        self.assertTrue(done["ok"])
        kinds = [e["kind"] for e in self.rt.events]
        for k in ("task.created", "worker.assigned", "verification.passed",
                  "task.completed"):
            self.assertIn(k, kinds)

    def test_persistence_roundtrip(self):
        self.rt.identify("g-7")
        self.rt.rotate_model("granite3.3:2b")
        s = self.rt.start_session("persist me")
        path = self.rt.save()
        rt2 = LocalGenesisRuntime(
            path, bridge_factory=FakeBridge, model_ping=lambda m: True)
        self.assertTrue(path)
        self.assertEqual(rt2.identity.genesis_id, "g-7")
        self.assertEqual(rt2.identity.active_model, "granite3.3:2b")
        self.assertIn(s.session_id, rt2.sessions)


class GenesisLiveRotationTests(unittest.TestCase):
    def test_live_rotation_granite_to_qwen(self):
        tmp = Path(tempfile.mkdtemp(prefix="v10_genlive_"))
        try:
            rt = LocalGenesisRuntime(tmp / "genesis.json")
            rt.identify("g-live")
            first = rt.rotate_model("granite3.3:2b")
            self.assertTrue(first["ok"], first)
            second = rt.rotate_model("qwen3:0.6b")
            self.assertTrue(second["ok"], second)
            self.assertEqual(rt.identity.genesis_id, "g-live")
            kinds = [e["kind"] for e in rt.events]
            self.assertIn("model.ready", kinds)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
