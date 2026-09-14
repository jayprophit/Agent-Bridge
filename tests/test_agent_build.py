"""v0.9.0 agent router + build pipeline tests (mocked)."""
import unittest

from agent_router import AgentRouter, WorkerEconomics, WorkerSpec, integrate_results
from build_pipeline import BuildPipeline, Readiness, benchmark


def _w(wid, caps, kind="native", rel=0.9, cost=1.0):
    return WorkerSpec(worker_id=wid, kind=kind, capabilities=list(caps),
                      reliability=rel, cost_per_task=cost)


class TestAgentRouter(unittest.TestCase):
    def test_auto_routes_capable(self):
        r = AgentRouter([_w("w1", ["code"]), _w("w2", ["media"])])
        self.assertEqual(r.route({"capabilities": ["code"]})["worker"], "w1")

    def test_no_capable_worker(self):
        r = AgentRouter([_w("w1", ["code"])])
        self.assertIn("error", r.route({"capabilities": ["quantum"]}))

    def test_override(self):
        r = AgentRouter([_w("w1", ["code"])])
        self.assertTrue(r.route({}, override="w1")["override"])
        self.assertIn("error", r.route({}, override="nope"))

    def test_native_only_excludes_third_party(self):
        r = AgentRouter([_w("t1", ["code"], kind="third-party")])
        self.assertIn("error", r.route({"capabilities": ["code"],
                                        "native_only": True}))

    def test_fan_out_and_integrate(self):
        r = AgentRouter([_w("w1", ["a"]), _w("w2", ["b"])])
        out = r.fan_out({"parallel_subtasks": [{"x": 1}, {"x": 2}]})
        self.assertTrue(out["plan"]["use_workers"])
        self.assertEqual(len(out["assignments"]), 2)
        integ = integrate_results([
            {"status": "COMPLETE", "artifacts": ["a.py"], "evidence": ["e1"]},
            {"status": "COMPLETE", "artifacts": ["b.py"], "evidence": ["e2"]}])
        self.assertTrue(integ["ok"])
        self.assertEqual(len(integ["artifacts"]), 2)

    def test_no_delegation_without_benefit(self):
        plan = WorkerEconomics.evaluate({"parallel_subtasks": []},
                                        [_w("w1", ["a"])])
        self.assertFalse(plan.use_workers)


class TestBuildPipeline(unittest.TestCase):
    def _ok_runner(self, cmd):
        return {"ok": True, "output": "done"}

    def test_full_pass(self):
        pipe = BuildPipeline(self._ok_runner)
        res = pipe.execute({"name": "demo", "languages": ["python"],
                            "commands": {"build": "make", "test": "pytest"},
                            "expected_artifacts": [
                                {"path": "a.bin", "format": "bin", "size_bytes": 10}]})
        self.assertTrue(res.ok)
        self.assertTrue(res.artifacts[0].verified)

    def test_unverified_artifact_fails(self):
        pipe = BuildPipeline(self._ok_runner)
        res = pipe.execute({"name": "demo",
                            "expected_artifacts": [
                                {"path": "a.bin", "format": "bin", "size_bytes": 0}]})
        self.assertFalse(res.ok)
        self.assertFalse(res.artifacts[0].verified)

    def test_build_failure_flows_to_errors(self):
        pipe = BuildPipeline(lambda cmd: {"ok": False, "error": "boom"})
        res = pipe.execute({"name": "demo", "commands": {"build": "make"},
                            "expected_artifacts": [
                                {"path": "a.bin", "format": "bin", "size_bytes": 5}]})
        self.assertFalse(res.ok)
        self.assertTrue(res.errors)

    def test_readiness_matrix(self):
        assess = BuildPipeline.assess_readiness
        self.assertEqual(assess(["a"], ["a"]), Readiness.READY)
        self.assertEqual(assess(["a"], ["a"], degraded=["a"]),
                         Readiness.READY_AFTER_SAFE_PROVISIONING)
        self.assertEqual(assess(["a"], ["a"], approval_needed=["a"]),
                         Readiness.READY_AFTER_APPROVAL)
        self.assertEqual(assess(["a"], []), Readiness.INCOMPATIBLE)
        self.assertEqual(assess(["a"], [], remote_available=True),
                         Readiness.REMOTE_RECOMMENDED)

    def test_benchmark_measures(self):
        out = benchmark("noop", lambda: 42, repeats=3)
        self.assertEqual(out["n"], 3)
        self.assertIn("p50_s", out)


if __name__ == "__main__":
    unittest.main()
