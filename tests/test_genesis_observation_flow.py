"""P5: Genesis -> capability request -> policy -> Bridge -> adapter ->
operation -> result -> receipt -> Genesis observation (in-process proof).

Uses only public runtime interfaces (AgentRuntime/Session) with a fake
model provider and a workspace-scoped session. The observation envelope
built here is the exact handoff shape the Genesis side consumes (P5b):
request id, capability, result summary, receipt digest, audit events.
"""
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from runtime import AgentRuntime, RuntimeConfig
from tests.helpers import FakeProvider


def _rt(tmp: Path, **kw) -> AgentRuntime:
    cfg_kw = dict(allowed_workspace_roots=[str(tmp)])
    factory = kw.pop("provider_factory", None)
    cfg_kw.update(kw)
    return AgentRuntime(RuntimeConfig(**cfg_kw),
                        provider_factory=factory)


def _factory(script, model="fake-m"):
    provs: dict[str, FakeProvider] = {}

    def make(role: str) -> FakeProvider:
        if role not in provs:
            provs[role] = FakeProvider(list(script), model)
        return provs[role]

    return make


def _receipt_digest(receipt: dict) -> str:
    canonical = json.dumps(receipt, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ObservationFlowTests(unittest.TestCase):
    def setUp(self):
        self.ws = Path(tempfile.mkdtemp(prefix="p5_genesis_obs_"))
        self.rt = _rt(
            self.ws,
            provider_factory=_factory(
                ['{"action":"write","path":"note.txt","content":"genesis observation"}']
            ),
        )

    def tearDown(self):
        shutil.rmtree(self.ws, ignore_errors=True)

    def test_safe_write_task_receipt_and_observation(self):
        session = self.rt.create_session(str(self.ws), mode="build")
        result = session.run_task("write genesis observation note", timeout=120)
        # Operation executed through the adapter inside the workspace.
        self.assertEqual(result.get("status"), "COMPLETED")
        self.assertIn("task_id", result)
        self.assertTrue((self.ws / "note.txt").exists())

        # Receipt: status + evidence + audit trail for this task.
        task_id = result["task_id"]
        status = session.task_status(task_id)
        self.assertEqual(status.get("status"), "COMPLETED")
        detail = status.get("result") or {}
        self.assertIn("note.txt", detail.get("files_created") or [])
        events = session.events_since(0).get("events", [])
        task_events = [e for e in events if e.get("task_id") == task_id]
        kinds = {e.get("event") for e in task_events}
        self.assertIn("task.completed", kinds)

        # Genesis-bound observation envelope (P2-GB envelope fields).
        receipt = {
            "request_id": task_id,
            "session_id": session.session_id,
            "identity": "genesis:organism-main",
            "capability": "workspace.write",
            "result": {
                "status": result.get("status"),
                "files_created": result.get("files_created") or [],
            },
            "audit_event_count": len(task_events),
        }
        receipt["receipt_digest"] = _receipt_digest(receipt)
        observation = {
            "source": "agent-bridge",
            "observation": receipt,
        }
        # Envelope is complete, digest is stable and well-formed.
        for field in ("request_id", "session_id", "identity", "capability",
                      "result", "receipt_digest", "audit_event_count"):
            self.assertIn(field, observation["observation"])
        self.assertEqual(len(receipt["receipt_digest"]), 64)
        self.assertEqual(receipt["receipt_digest"],
                         _receipt_digest({k: v for k, v in receipt.items()
                                          if k != "receipt_digest"}))
        self.assertIn("note.txt", receipt["result"]["files_created"])

    def test_workspace_scope_denies_outside_roots(self):
        outside = Path(tempfile.mkdtemp(prefix="p5_out_"))
        try:
            with self.assertRaises(PermissionError):
                self.rt.create_session(str(outside))
        finally:
            shutil.rmtree(outside, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
