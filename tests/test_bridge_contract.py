"""Runtime wiring tests: the REAL run_bridge obeys the contract (§8).

Uses deterministic FakeProvider scripts (no Ollama). Covers: intake
rejection, finish-gate refusal, valid full loop, fallback under contract,
restart/504 survival, session contract file, service telemetry exposure.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

from bridge import run_bridge
from config import BridgeConfig
from tests.helpers import FakeProvider

WRITE = '{"action":"write","path":"w.py","content":"print(1)\\n"}'
WRITE2 = '{"action":"write","path":"t_ok.py","content":"print(1)\\n"}'
TEST = '{"action":"test","command":"python w.py"}'
TEST2 = '{"action":"test","command":"python t_ok.py"}'
FINISH = '{"action":"finish","message":"done"}'


def _cfg(tmp: Path, **kw) -> BridgeConfig:
    args = dict(workspace=tmp, mode="build", approval="AUTO_SAFE",
                max_steps=10, non_interactive=True, enable_reviewer=False,
                collision="OVERWRITE")
    args.update(kw)
    return BridgeConfig(**args)


class TestRuntimeIntake(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rct_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_empty_task_rejected_plan_missing(self):
        out = run_bridge(_cfg(self.tmp), "   ", provider=FakeProvider([]))
        self.assertFalse(out.get("ok", True))
        self.assertEqual(out.get("kind"), "EXECUTION_POLICY_VIOLATION")
        self.assertIn("PLAN_MISSING", out.get("error", ""))
        c = out.get("contract", {})
        self.assertEqual(c.get("plan_version"), 0)

    def test_blank_task_rejected(self):
        out = run_bridge(_cfg(self.tmp), "", provider=FakeProvider([]))
        self.assertEqual(out.get("kind"), "EXECUTION_POLICY_VIOLATION")


class TestFinishGate(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rcf_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_finish_without_verification_refused(self):
        out = run_bridge(_cfg(self.tmp), "write it", provider=FakeProvider([
            WRITE, FINISH]))
        kinds = [h.get("kind") for h in out["history"] if h.get("kind")]
        self.assertIn("VERIFICATION_MISSING", kinds)
        self.assertIsNone(out.get("finished"))
        # the refusal is recorded in the contract ledger, not silent
        c = out.get("contract", {})
        self.assertEqual(c.get("state"), "BLOCK_WITH_EVIDENCE")

    def test_valid_loop_completes_with_proof(self):
        out = run_bridge(_cfg(self.tmp), "write and verify",
                         provider=FakeProvider([WRITE, TEST, FINISH]))
        self.assertTrue(out.get("finished"), out)
        c = out.get("contract", {})
        self.assertEqual(c.get("state"), "COMPLETE")
        self.assertGreaterEqual(c.get("plan_version", 0), 1)
        self.assertEqual(c["telemetry"]["planned_ok"], 1)
        self.assertEqual(c["telemetry"]["unresolved_bypasses"], 0)

    def test_read_only_run_completes_honestly(self):
        out = run_bridge(_cfg(self.tmp), "inspect", provider=FakeProvider([
            '{"action":"list","path":"."}', FINISH]))
        self.assertTrue(out.get("finished"), out)
        self.assertEqual(out.get("contract", {}).get("state"), "COMPLETE")


class TestFallbackContract(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rcb_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_fallback_recorded_as_reroute(self):
        import bridge as _bridge
        from providers import ProviderError
        real_create = _bridge.create_provider
        calls = {"n": 0}
        script = [WRITE2, TEST2, FINISH]

        def flaky(kind: str = "", **kw):  # type: ignore[no-untyped-def]
            calls["n"] += 1
            if calls["n"] == 1:
                raise ProviderError("primary down")
            return FakeProvider(list(script), model="fb-model")

        _bridge.create_provider = flaky  # type: ignore[method-assign]
        try:
            cfg = _cfg(self.tmp, model="ghost-primary")
            cfg.fallback = {"general": ["fb-model"], "planner": ["fb-model"],
                            "coder": ["fb-model"], "reviewer": ["fb-model"]}
            out = run_bridge(cfg, "fallback task")
        finally:
            _bridge.create_provider = real_create
        self.assertTrue(out.get("finished"), out)
        c = out.get("contract", {})
        self.assertEqual(c.get("state"), "COMPLETE")
        self.assertGreaterEqual(c["telemetry"]["reroutes"], 1)


class TestRuntimePersistence(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rcp_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_session_contract_file_written(self):
        out = run_bridge(_cfg(self.tmp), "write and verify",
                         provider=FakeProvider([WRITE, TEST, FINISH]))
        self.assertTrue(out.get("finished"), out)
        sess_dirs = list((self.tmp / ".bridge" / "sessions").iterdir())
        self.assertTrue(sess_dirs)
        contract_file = sess_dirs[0] / "contract.json"
        self.assertTrue(contract_file.exists())
        data = json.loads(contract_file.read_text(encoding="utf-8"))
        self.assertIn(out["session_id"], list(data.get("tasks", {}).keys())[0])

    def test_restart_reloads_shared_ledger(self):
        from execution_contract import ExecutionContract
        out = run_bridge(_cfg(self.tmp), "write and verify",
                         provider=FakeProvider([WRITE, TEST, FINISH]))
        self.assertTrue(out.get("finished"), out)
        ctid = next(iter(
            json.loads((self.tmp / ".bridge" / "execution_contract.json")
                       .read_text(encoding="utf-8"))["tasks"]))
        cx2 = ExecutionContract(
            self.tmp / ".bridge" / "execution_contract.json")
        self.assertEqual(cx2.state_of(ctid), "COMPLETE")

    def test_corrupt_ledger_does_not_block_run(self):
        ledger = self.tmp / ".bridge" / "execution_contract.json"
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text("{corrupt 504 body", encoding="utf-8")
        out = run_bridge(_cfg(self.tmp), "write and verify",
                         provider=FakeProvider([WRITE, TEST, FINISH]))
        self.assertTrue(out.get("finished"), out)
        self.assertEqual(out.get("contract", {}).get("state"), "COMPLETE")


class TestDefaultAgentPath(unittest.TestCase):
    def test_run_task_follows_lifecycle(self):
        from unittest.mock import Mock
        from agent.default_agent import AgentRegistries, DefaultAgent
        from tools.registry import ToolRegistry
        tmp = Path(tempfile.mkdtemp(prefix="rcd_"))
        try:
            regs = AgentRegistries(
                tool_registry=ToolRegistry(), model_registry=Mock(),
                provider_registry=Mock(), model_router=Mock(),
                tool_router=Mock())
            agent = DefaultAgent(regs)
            session = agent.create_session(str(tmp))
            out = agent.run_task(session, "do the thing")
            self.assertIn("contract", out)
            self.assertEqual(out["contract"]["state"], "COMPLETE")
            self.assertGreaterEqual(
                out["contract"]["plan_version"], 1)
            self.assertEqual(
                out["contract"]["telemetry"]["unresolved_bypasses"], 0)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestServiceTelemetry(unittest.TestCase):
    def test_taskcenter_exposes_loop_telemetry(self):
        from runtime import AgentRuntime, RuntimeConfig
        from service import serve
        tmp = Path(tempfile.mkdtemp(prefix="rcs_"))
        try:
            rt = AgentRuntime(RuntimeConfig(
                allowed_workspace_roots=[str(tmp)]))
            srv = serve(rt, "127.0.0.1", 0)
            port = srv.server_address[1]
            th = threading.Thread(target=srv.serve_forever, daemon=True)
            th.start()
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/v1/taskcenter",
                        timeout=15) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                self.assertIn("loop_telemetry", body)
                tel = body["loop_telemetry"]
                self.assertIn("unresolved_bypasses", tel)
                self.assertIn("adaptations", tel)
            finally:
                srv.shutdown()
                srv.server_close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
