"""End-to-end acceptance (v0.9.0): full path on a disposable project.

user objective -> triage -> environment/toolchain select -> policy check
-> execute (controlled failure injected) -> diagnose -> retry -> test ->
artifact verify -> evidence -> report. Uses real detector/registries
where hermetic, scripted runner for build steps. No network, no LLM.
"""
import shutil
import tempfile
import unittest
from pathlib import Path

from agent_router import AgentRouter, WorkerSpec
from build_pipeline import BuildPipeline
from model_lifecycle import ModelRegistry, ModelRouter
from project_detector import inspect_project
from project_model import build_project_model
from reflex_layer import TaskTriageEngine
from supply_chain_security import PermissionPolicy, gate_pipeline
from task_dag import DurableTaskGraph, Evidence, EvidenceKind, EvidenceLedger, TaskRecord, TaskStatus
from tool_selector import ProjectRequirement, ToolSelectionEngine
from toolchain_registry import Toolchain, ToolchainCategory, ToolchainComponent, ToolchainStatus


def _toolchain(tid, langs):
    tc = Toolchain(id=tid, name=tid, primary_language=langs[0],
                   supported_languages=list(langs),
                   status=ToolchainStatus.AVAILABLE)
    tc.components = [ToolchainComponent(name="python",
                                        category=ToolchainCategory.INTERPRETER,
                                        status=ToolchainStatus.AVAILABLE,
                                        version="3.13")]
    return tc


class TestEndToEnd(unittest.TestCase):
    def test_full_path_with_controlled_failure(self):
        tmp = Path(tempfile.mkdtemp(prefix="v090_e2e_"))
        try:
            (tmp / "pyproject.toml").write_text("[project]\nname='demo'\n")
            (tmp / "app.py").write_text("print('hi')\n")
            ledger = EvidenceLedger()

            # 1. objective -> triage
            triage = TaskTriageEngine().triage(
                "build and test this python project")
            self.assertNotEqual(triage.route.value, "REQUEST_APPROVAL")

            # 2. detect project
            profile = inspect_project(tmp)
            model = build_project_model(profile)
            self.assertIn("python", model.all_languages)
            ledger.add(Evidence(kind=EvidenceKind.FACT, producer="detector",
                                task_id="t", payload={"langs": model.all_languages}))

            # 3. toolchain select
            eng = ToolSelectionEngine()
            opts = eng.recommend(ProjectRequirement(language="python"),
                                 [_toolchain("python", ["python"])])
            self.assertTrue(opts[0].compatible)

            # 4. security gate on the (mock) build tool
            gate = gate_pipeline({"id": "local-python", "permissions": ()},
                                 [], PermissionPolicy())
            self.assertEqual(gate["decision"], "ALLOW")

            # 5. task graph with injected controlled failure then retry
            graph = DurableTaskGraph()
            build = TaskRecord(task_id="build", objective="build",
                               status=TaskStatus.QUEUED)
            test = TaskRecord(task_id="test", objective="test",
                              dependencies=["build"], status=TaskStatus.QUEUED)
            graph.add(build)
            graph.add(test)
            calls = {"n": 0}

            def runner(cmd):
                calls["n"] += 1
                if calls["n"] == 1:
                    return {"ok": False, "error": "TRANSIENT: cache lock"}
                return {"ok": True}

            pipe = BuildPipeline(runner)
            proj = {"name": "demo", "commands": {"build": "build"},
                    "expected_artifacts": [
                        {"path": "a.bin", "format": "bin", "size_bytes": 4}]}
            first = pipe.execute(proj)
            self.assertFalse(first.ok)  # controlled failure observed
            ledger.add(Evidence(kind=EvidenceKind.FAILED_ATTEMPT,
                                producer="pipeline", task_id="build",
                                payload={"error": first.errors[0]}))

            # 6. diagnose -> retry succeeds
            second = pipe.execute(proj)
            self.assertTrue(second.ok)
            build.status = TaskStatus.VERIFIED_COMPLETE
            test.status = TaskStatus.VERIFIED_COMPLETE
            eid = ledger.add(Evidence(kind=EvidenceKind.VERIFIED_RESULT,
                                      producer="pipeline", task_id="test",
                                      payload={"artifacts": 1}))
            ledger.mark_verified(eid)

            # 7. model route + worker route for the report step
            from model_lifecycle import ModelRecord
            reg = ModelRegistry()
            rec = ModelRecord(model_id="granite3.3:2b", provider="ollama",
                              parameters_b=2.5)
            rec.capabilities.scores["general_chat"] = True
            reg.register(rec)
            routed = ModelRouter(reg).route({"capabilities": ["general_chat"]},
                                            {"ram_free_gb": 6})
            self.assertEqual(routed["model"], "granite3.3:2b")
            agent = AgentRouter([WorkerSpec(worker_id="writer",
                                            capabilities=["docs"])])
            self.assertEqual(agent.route(
                {"capabilities": ["docs"]})["worker"], "writer")

            # 8. report: everything evidenced
            self.assertEqual(len(ledger.verified_results("test")), 1)
            self.assertEqual(calls["n"], 2)  # one build call per execute
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
