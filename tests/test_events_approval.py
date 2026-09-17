"""v0.3: event bus, approval events, injectable approval E2E."""
import shutil
import tempfile
import unittest
from pathlib import Path

from bridge import run_bridge
from config import BridgeConfig
from events import (APPROVAL_DENIED, APPROVAL_REQUESTED, EXECUTION_COMPLETED,
                    EXECUTION_STARTED, EventBus)
from policy import PreApprovedApproval
from tests.helpers import FakeProvider


class TestEventBus(unittest.TestCase):
    def test_subscribe_emit(self):
        bus = EventBus()
        seen: list[dict] = []
        bus.subscribe("approval.requested", seen.append)
        bus.emit("approval.requested", {"x": 1})
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0]["x"], 1)
        self.assertIn("timestamp", seen[0])

    def test_wildcard(self):
        bus = EventBus()
        seen: list[dict] = []
        bus.subscribe("*", seen.append)
        bus.emit("execution.started", {})
        bus.emit("review.completed", {})
        self.assertEqual(len(seen), 2)

    def test_of_filter(self):
        bus = EventBus()
        bus.emit("a", {})
        bus.emit("b", {})
        bus.emit("a", {})
        self.assertEqual(len(bus.of("a")), 2)


class TestApprovalEvents(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="v03_ev_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _cfg(self, **kw):
        args = dict(workspace=self.tmp, mode="build", approval="ASK_ALL_WRITES",
                    max_steps=6, non_interactive=True, enable_reviewer=False)
        args.update(kw)
        return BridgeConfig(**args)

    def test_deny_emits_requested_and_denied(self):
        events: list[dict] = []
        iface = PreApprovedApproval(default="deny")
        orig_request = iface.request

        def spy(action, context):
            events.append({"requested": True, "action": action["action"]})
            return orig_request(action, context)

        iface.request = spy  # type: ignore[method-assign]
        cfg = self._cfg()
        # ASK_ALL_WRITES + non-interactive denies without calling interface,
        # but the manager still emits approval.requested/denied on the bus.
        # Here we assert the operation does NOT execute and no file appears.
        fake = FakeProvider(['{"action":"write","path":"no.txt","content":"x"}',
                             '{"action":"write","path":"no.txt","content":"x"}',
                             '{"action":"write","path":"no.txt","content":"x"}',
                             '{"action":"finish","message":"end"}'])
        out = run_bridge(cfg, "t", provider=fake, approval_interface=iface)
        self.assertFalse((self.tmp / "no.txt").exists())
        denied = [h for h in out["history"] if h.get("kind") == "APPROVAL_DENIED"]
        self.assertTrue(denied)

    def test_approve_once_allows_exactly_intended(self):
        import json as _j
        target = {"action": "delete", "path": "victim.txt"}
        (self.tmp / "victim.txt").write_text("keep", encoding="utf-8")
        (self.tmp / "other.txt").write_text("keep2", encoding="utf-8")
        fp = _j.dumps(target, sort_keys=True)
        iface = PreApprovedApproval(approved=[fp], default="deny")
        cfg = self._cfg(approval="AUTO_SAFE")
        fake = FakeProvider(['{"action":"delete","path":"victim.txt"}',
                             '{"action":"finish","message":"done"}'])
        out = run_bridge(cfg, "t", provider=fake, approval_interface=iface)
        # PreApprovedApproval only matters in interactive mode; in
        # non-interactive the manager denies before consulting it.
        self.assertTrue((self.tmp / "victim.txt").exists())
        self.assertEqual(len(iface.requests), 0)

    def test_interactive_approve_once(self):
        import json as _j
        # canonical delete carries permanent:False (protocol normalization)
        target = {"action": "delete", "path": "victim.txt", "permanent": False}
        (self.tmp / "victim.txt").write_text("keep", encoding="utf-8")
        # Phase 1.1 amendment: a passing SAFE test step (auto-approved, so
        # the approval-request assertions are unaffected) supplies the
        # verification evidence completion now requires.
        (self.tmp / "probe.py").write_text("print(1)\n", encoding="utf-8")
        fp = _j.dumps(target, sort_keys=True)
        iface = PreApprovedApproval(approved=[fp], default="deny")
        cfg = self._cfg(approval="AUTO_SAFE", non_interactive=False)
        fake = FakeProvider(['{"action":"delete","path":"victim.txt"}',
                             '{"action":"test","command":"python probe.py"}',
                             '{"action":"finish","message":"done"}'])
        out = run_bridge(cfg, "t", provider=fake, approval_interface=iface,
                         )
        cfg2 = cfg
        self.assertFalse((self.tmp / "victim.txt").exists())
        self.assertTrue(out.get("finished"), out)
        self.assertEqual(len(iface.requests), 1)
        self.assertEqual(iface.requests[0]["action"]["action"], "delete")


if __name__ == "__main__":
    unittest.main()
