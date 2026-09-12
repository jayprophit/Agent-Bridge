"""v0.5: scorecard, timeline, manifest, export redaction."""
import shutil
import tempfile
import unittest
from pathlib import Path

from resultkit import change_manifest, export_json, export_markdown, scorecard, timeline


def _tr(**kw):
    base = {"status": "COMPLETED", "mode": "build",
            "files_created": ["a.py"], "files_modified": [],
            "files_deleted": [], "commands_executed": [{"exit_code": 0}],
            "tests": {"ran": 1, "passed": 1, "all_passed": True,
                      "quality": "GOOD", "quality_reasons": ["ok"],
                      "verified": True},
            "review_verdict": "approve", "errors": []}
    base.update(kw)
    return base


class TestScorecard(unittest.TestCase):
    def test_all_pass(self):
        sc = scorecard(_tr())
        cats = sc["categories"]
        self.assertEqual(cats["FILES"]["status"], "PASS")
        self.assertEqual(cats["TESTS"]["status"], "PASS")
        self.assertEqual(cats["ORACLE"]["status"], "PASS")
        self.assertEqual(cats["REVIEW"]["status"], "PASS")
        # categorical only: no numeric universal score anywhere
        self.assertNotIn("quality_score", sc)
        self.assertNotIn("overall_score", sc)
        for c in cats.values():
            self.assertNotIsInstance(c.get("status"), (int, float))

    def test_suspicious_blocks_strong(self):
        tr = _tr(tests={"ran": 1, "passed": 1, "all_passed": True,
                        "quality": "SUSPICIOUS", "quality_reasons": ["x"],
                        "verified": False})
        cats = scorecard(tr)["categories"]
        self.assertEqual(cats["ORACLE"]["status"], "FAIL")
        self.assertEqual(cats["TESTS"]["status"], "WEAK")

    def test_security_violation_fails(self):
        tr = _tr(errors=[{"kind": "SANDBOX_VIOLATION", "step": 1, "error": "x"}])
        self.assertEqual(scorecard(tr)["categories"]["SECURITY"]["status"], "FAIL")


class TestTimelineManifest(unittest.TestCase):
    def test_timeline_from_events(self):
        evs = [{"event": "task.started", "timestamp": "2026-01-01T00:00:00"},
               {"event": "approval.requested", "timestamp": "2026-01-01T00:00:05",
                "action": {"action": "write", "path": "a.txt"}},
               {"event": "mystery", "timestamp": "2026-01-01T00:00:06"},
               {"step": 3, "timestamp": "2026-01-01T00:00:07",
                "action": {"action": "shell"}, "executed": True,
                "result": {"ok": True}}]
        tl = timeline(evs)
        self.assertTrue(any("task accepted" in t for t in tl))
        self.assertTrue(any("APPROVAL REQUIRED" in t for t in tl))
        self.assertFalse(any("mystery" in t for t in tl))

    def test_manifest_shapes(self):
        journal = [{"path": "a.py", "action": "write", "action_id": "a-1",
                    "backup": None, "restore_id": ""}]
        m = change_manifest(journal)
        self.assertEqual(m[0]["operation"], "write")
        self.assertTrue(m[0]["verified"])


class TestExportRedaction(unittest.TestCase):
    def test_exports_redact(self):
        tr = _tr()
        tr["token"] = "secret-123"
        evs = [{"event": "task.started",
                "note": "Bearer secret-123 plus .bridge/memory/x content"}]
        js = export_json(tr, evs)
        self.assertNotIn("secret-123", js)
        self.assertNotIn(".bridge/memory/x", js)
        md = export_markdown(tr, evs)
        self.assertNotIn("secret-123", md)
        self.assertIn("PASS", md)


if __name__ == "__main__":
    unittest.main()
