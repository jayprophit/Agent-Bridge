"""Multi-agent fabric bootstrap: task contract, registry, selection,
FREE_FIRST_STRICT filtering, lease/timeout/retry, verification,
optional-blocker continuation. Uses stub adapters; real-worker proofs run
as live evidence, not unit tests."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from orchestrator import (
    AGENT_BRIDGE,
    HERMES,
    OLLAMA,
    OPENCODE,
    OPENCLAW,
    Orchestrator,
    OrchestratorError,
    OrchestratorTask,
    WorkerUnavailable,
    seed_worker_registry,
    select_worker,
)
from task_dag import TaskStatus
from worker_adapters import OLLAMA_ROLE_MODELS, OpenClawAdapter


class StubAdapter:
    def __init__(self, result=None, fail=None):
        self.result = result or {"ok": True, "result": {"done": True},
                                 "changed_files": [], "test_results": {}}
        self.fail = fail
        self.calls = 0

    def execute(self, task):
        self.calls += 1
        if self.fail:
            raise RuntimeError(self.fail)
        return dict(self.result)


class RegistryTests(unittest.TestCase):
    def test_seed_has_canonical_workers(self):
        reg = seed_worker_registry()
        for wid in (HERMES, OPENCODE, OLLAMA, AGENT_BRIDGE, OPENCLAW):
            self.assertIn(wid, reg.workers)

    def test_openclaw_registers_offline_not_absent(self):
        reg = seed_worker_registry()
        self.assertEqual(reg.workers[OPENCLAW].state, "OFFLINE")

    def test_ollama_role_models_are_installed_ids(self):
        self.assertIn("qwen3:0.6b", OLLAMA_ROLE_MODELS["FAST_LOCAL"])
        self.assertIn("moondream:latest", OLLAMA_ROLE_MODELS["VISION_LOCAL"])


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.reg = seed_worker_registry()

    def test_planning_routes_to_hermes(self):
        t = OrchestratorTask(objective="plan it", role="planner")
        self.assertEqual(select_worker(t, self.reg), HERMES)

    def test_coding_routes_to_opencode(self):
        t = OrchestratorTask(objective="fix it", role="coder")
        self.assertEqual(select_worker(t, self.reg), OPENCODE)

    def test_review_routes_to_ollama(self):
        t = OrchestratorTask(objective="review it", role="reviewer")
        self.assertEqual(select_worker(t, self.reg), OLLAMA)

    def test_tool_routes_to_bridge(self):
        t = OrchestratorTask(objective="slice it", role="tool",
                             required_capabilities=["cura-slice"])
        self.assertEqual(select_worker(t, self.reg), AGENT_BRIDGE)

    def test_busy_worker_raises_not_waits(self):
        self.reg.workers[OLLAMA].state = "BUSY"
        t = OrchestratorTask(objective="review it", role="reviewer")
        with self.assertRaises(WorkerUnavailable):
            select_worker(t, self.reg)


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="orch_"))
        self.stub = StubAdapter()
        self.orch = Orchestrator(self.tmp, adapters={"ollama": self.stub})

    def test_submit_dispatch_verify_complete(self):
        tid = self.orch.submit(OrchestratorTask(
            objective="review the summary", role="reviewer",
            acceptance_tests=[], expected_artifacts=[]))
        out = self.orch.dispatch(tid)
        self.assertEqual(out["status"], TaskStatus.VERIFIED_COMPLETE.value)
        self.assertEqual(self.stub.calls, 1)

    def test_dependencies_gate_readiness(self):
        a = self.orch.submit(OrchestratorTask(objective="first", role="reviewer"))
        b = self.orch.submit(OrchestratorTask(objective="second", role="reviewer",
                                              dependencies=[a]))
        ready_ids = [t.task_id for t in self.orch.ready()]
        self.assertIn(a, ready_ids)
        self.assertNotIn(b, ready_ids)
        self.orch.dispatch(a)
        ready_ids = [t.task_id for t in self.orch.ready()]
        self.assertIn(b, ready_ids)

    def test_failed_verification_retries_then_fails(self):
        bad = StubAdapter(result={"ok": True, "result": {}})  # missing artifact
        orch = Orchestrator(self.tmp / "r", adapters={"ollama": bad})
        tid = orch.submit(OrchestratorTask(
            objective="produce it", role="reviewer",
            expected_artifacts=["report.md"]))
        out = orch.dispatch(tid)
        self.assertIn(out["status"], (TaskStatus.RETRYING.value,
                                      TaskStatus.FAILED.value))

    def test_adapter_crash_becomes_retryable_failure(self):
        boom = StubAdapter(fail="worker exploded")
        orch = Orchestrator(self.tmp / "c", adapters={"ollama": boom})
        tid = orch.submit(OrchestratorTask(objective="x", role="reviewer"))
        out = orch.dispatch(tid)
        self.assertIn(out["status"], (TaskStatus.RETRYING.value,
                                      TaskStatus.FAILED.value))
        self.assertTrue(orch.get(tid).errors)

    def test_cancel_stops_task(self):
        tid = self.orch.submit(OrchestratorTask(objective="x", role="reviewer"))
        self.orch.cancel(tid, "owner stopped it")
        self.assertEqual(self.orch.get(tid).status, TaskStatus.CANCELLED.value)

    def test_free_first_rejects_paid_cost_class(self):
        with self.assertRaises(OrchestratorError):
            self.orch.submit(OrchestratorTask(
                objective="x", role="reviewer",
                required_capabilities=["PAID_API"]))

    def test_snapshot_persists_tasks(self):
        tid = self.orch.submit(OrchestratorTask(objective="x", role="reviewer"))
        path = self.orch.snapshot()
        self.assertTrue(path.exists())
        self.assertIn(tid, path.read_text(encoding="utf-8"))


class AdapterBoundaryTests(unittest.TestCase):
    def test_opencode_probe_reports_version(self):
        from worker_adapters import OpenCodeAdapter
        probe = OpenCodeAdapter().probe()
        self.assertTrue(probe["available"])
        self.assertIn("1.", probe["version"])

    def test_opencode_refuses_without_workdir(self):
        from worker_adapters import OpenCodeAdapter
        t = OrchestratorTask(objective="x", role="coder")
        out = OpenCodeAdapter().execute(t)
        self.assertFalse(out["ok"])
        self.assertIn("repo or worktree", out["error"])

    def test_ollama_probe_sees_fleet(self):
        from worker_adapters import OllamaWorkerAdapter
        probe = OllamaWorkerAdapter().probe()
        self.assertTrue(probe["available"])
        self.assertGreaterEqual(probe["fleet_size"], 15)

    def test_bridge_probe_reports_runtime(self):
        from worker_adapters import BridgeWorkerAdapter
        probe = BridgeWorkerAdapter(".").probe()
        self.assertTrue(probe["available"])

    def test_bridge_refuses_unknown_kind(self):
        from worker_adapters import BridgeWorkerAdapter
        t = OrchestratorTask(objective="x", role="tool")
        t.result = {"kind": "teleport-task"}
        out = BridgeWorkerAdapter(".").execute(t)
        self.assertFalse(out["ok"])


class OpenClawAdapterTests(unittest.TestCase):
    def test_probe_is_honest(self):
        probe = OpenClawAdapter().probe()
        self.assertIn("available", probe)
        if not probe["available"]:
            self.assertIn("BLOCKED_OPTIONAL", probe["reason"])

    def test_execute_never_fakes_success(self):
        out = OpenClawAdapter().execute(object())
        self.assertFalse(out["ok"])
        self.assertTrue(out.get("blocked_optional"))


if __name__ == "__main__":
    unittest.main()
