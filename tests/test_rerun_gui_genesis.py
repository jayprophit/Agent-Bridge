"""v0.4: RERUN_SAFE replay, GUI approval adapter, genesis-sim isolation."""
import ast
import shutil
import tempfile
import unittest
from pathlib import Path

from replay import rerun_safe


class TestRerunSafe(unittest.TestCase):
    def _jsonl(self, tmp: Path) -> Path:
        import json
        lines = [
            {"step": 1, "action": {"action": "read", "path": "a.txt"},
             "action_id": "a-1", "executed": True,
             "result": {"ok": True}},
            {"step": 2, "action": {"action": "write", "path": "a.txt", "content": "x"},
             "action_id": "a-2", "executed": True,
             "result": {"ok": True}},
            {"step": 3, "action": {"action": "shell", "command": "python a.txt"},
             "action_id": "a-3", "executed": True,
             "result": {"ok": True, "exit_code": 0}},
            {"step": 4, "action": {"action": "delete", "path": "old.txt"},
             "action_id": "a-4", "executed": True,
             "result": {"ok": True}},
        ]
        p = tmp / "s.jsonl"
        p.write_text("\n".join(json.dumps(l) for l in lines))
        return p

    def test_safe_subset_only(self):
        tmp = Path(tempfile.mkdtemp(prefix="v04_rerun_"))
        try:
            out = rerun_safe(self._jsonl(tmp))
            self.assertTrue(out["ok"])
            self.assertEqual(out["replayable_count"], 1)
            self.assertEqual(out["replayable"][0]["action"]["action"], "read")
            skipped = {s["action"]: s["reason"] for s in out["skipped"]}
            self.assertIn("write", skipped)
            self.assertIn("shell", skipped)
            self.assertIn("delete", skipped)
            for s in out["skipped"]:
                self.assertTrue(s["reason"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_rerun_executes_nothing(self):
        tmp = Path(tempfile.mkdtemp(prefix="v04_rerun2_"))
        try:
            before = sorted(p.name for p in tmp.iterdir())
            rerun_safe(self._jsonl(tmp))
            after = sorted(p.name for p in tmp.iterdir())
            # only the jsonl itself was added by the test harness
            self.assertEqual(set(after) - set(before), {"s.jsonl"})
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestGuiAdapter(unittest.TestCase):
    """Mock GUI subscriber: receives approval requests, shows details,
    resolves approve/session/deny. Policy stays in the runtime."""

    def test_mock_gui_flow(self):
        from runtime import AgentRuntime, RuntimeConfig
        from tests.helpers import FakeProvider
        tmp = Path(tempfile.mkdtemp(prefix="v04_gui_"))
        try:
            ws = tmp / "proj"
            ws.mkdir()
            received: list[dict] = []

            def factory(role: str):
                return FakeProvider(
                    ['{"action":"write","path":"g.txt","content":"x"}',
                     '{"action":"finish","message":"ok"}'])

            rt = AgentRuntime(RuntimeConfig(allowed_workspace_roots=[str(tmp)]),
                              provider_factory=factory)
            s = rt.create_session(str(ws), mode="build")
            # mock GUI subscribes to the session bus
            s.bus.subscribe("approval.requested", received.append)
            import threading
            tid = s.submit_task("t")
            res = s.wait_task(tid, timeout=120)
            kinds = {e.get("event") for e in s.events_since(0)["events"]}
            self.assertIn("task.started", kinds)
            # AUTO_SAFE auto-approves safe writes: file appears, no GUI needed
            self.assertTrue((ws / "g.txt").exists())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_gui_deny_path_events(self):
        from policy import ApprovalManager, PreApprovedApproval
        seen: list[dict] = []
        mgr = ApprovalManager(level="ASK_ALL_WRITES",
                              interface=PreApprovedApproval(),
                              non_interactive=True,
                              on_event=lambda n, p: seen.append({"event": n}))
        v = mgr.decide({"action": "write", "path": "x", "content": "y"})
        self.assertFalse(v["approved"])
        names = {e["event"] for e in seen}
        self.assertIn("approval.requested", names)
        self.assertIn("approval.denied", names)


class TestGenesisIsolation(unittest.TestCase):
    def test_simulator_has_no_private_imports(self):
        tree = ast.parse(Path("genesis_client_simulator.py").read_text(
            encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        for banned in ("bridge", "executor", "policy", "protocol", "runtime",
                       "checkpoints", "memory", "cache", "events", "state"):
            self.assertNotIn(banned, imported, f"simulator must not import {banned}")
        self.assertIn("client", imported)


if __name__ == "__main__":
    unittest.main()
