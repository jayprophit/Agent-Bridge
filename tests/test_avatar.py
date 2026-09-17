"""Avatar controller tests (no UI, no models)."""
import unittest

from avatar_controller import (AVATAR_STATES, AvatarController, AvatarEventAdapter,
                    TASK_TO_AVATAR)


class AvatarTests(unittest.TestCase):
    def test_states_known(self):
        for s in ("idle", "listening", "thinking", "working", "coding",
                  "testing", "waiting", "success", "warning", "error",
                  "offline"):
            self.assertIn(s, AVATAR_STATES)

    def test_rejects_unknown(self):
        with self.assertRaises(ValueError):
            AvatarController().set_state("dancing")

    def test_task_mapping(self):
        c = AvatarController()
        self.assertEqual(c.from_task_status("EXECUTING").state, "working")
        self.assertEqual(c.from_task_status("COMPLETED").state, "success")
        self.assertEqual(c.from_task_status("FAILED").state, "error")
        self.assertEqual(c.offline().state, "offline")

    def test_progress_clamped(self):
        c = AvatarController()
        self.assertEqual(c.set_state("working", progress_pct=999).progress_pct, 100.0)
        self.assertEqual(c.set_state("working", progress_pct=-5).progress_pct, 0.0)

    def test_event_feed(self):
        adapter = AvatarEventAdapter()
        adapter.handle({"event": "task.started", "task_id": "t-1"})
        adapter.handle({"event": "task.progress", "task_id": "t-1",
                        "progress_pct": 50})
        out = adapter.handle({"event": "task.completed"})
        self.assertEqual(out["state"]["state"], "success")
        adapter.handle({"event": "fallback.triggered", "from": "m-a"})
        self.assertEqual(adapter.controller.snapshot()["state"], "warning")
        self.assertEqual(len(adapter.log), 4)

    def test_unknown_event_keeps_state(self):
        adapter = AvatarEventAdapter()
        before = adapter.controller.snapshot()["state"]
        adapter.handle({"event": "something-entirely-new"})
        self.assertEqual(adapter.controller.snapshot()["state"], before)


if __name__ == "__main__":
    unittest.main()
