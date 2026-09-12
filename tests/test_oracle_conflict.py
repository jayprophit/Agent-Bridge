"""v0.6: oracle assert* recognition + reviewer evidence conflict."""
import shutil
import tempfile
import unittest
from pathlib import Path

from bridge import run_bridge
from config import BridgeConfig
from oracle import UNITTEST_ASSERTS, _parse_test_file, assess
from reviewer import check_evidence_conflict, parse_verdict
from tests.helpers import FakeProvider


class TestAssertRecognition(unittest.TestCase):
    def test_unittest_methods_counted(self):
        tmp = Path(tempfile.mkdtemp(prefix="v06_or_"))
        try:
            (tmp / "t.py").write_text(
                "import unittest\n"
                "class T(unittest.TestCase):\n"
                "    def test_a(self):\n"
                "        self.assertEqual(1, 1)\n"
                "        self.assertTrue(True)\n"
                "        self.assertIn('a', 'abc')\n"
                "        self.assertRaises(ValueError, int, 'x')\n"
                "        self.assertIsNone(None)\n")
            info = _parse_test_file(tmp / "t.py")
            self.assertTrue(info["ok"])
            self.assertGreaterEqual(info["asserts"], 5)
            for m in ("assertEqual", "assertTrue", "assertIn",
                      "assertRaises", "assertIsNone"):
                self.assertIn(m, info["assert_methods"])
                self.assertIn(m, UNITTEST_ASSERTS)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_bare_assert_calls_counted(self):
        tmp = Path(tempfile.mkdtemp(prefix="v06_or2_"))
        try:
            (tmp / "t.py").write_text("assertEqual(f(), 1)\n")
            info = _parse_test_file(tmp / "t.py")
            self.assertGreaterEqual(info["asserts"], 1)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_plain_assert_kept(self):
        tmp = Path(tempfile.mkdtemp(prefix="v06_or3_"))
        try:
            (tmp / "t.py").write_text("assert 1 == 1\n")
            info = _parse_test_file(tmp / "t.py")
            self.assertEqual(info["asserts"], 1)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestEvidenceConflict(unittest.TestCase):
    def test_detects_assertion_denial(self):
        v, _ = parse_verdict('{"verdict":"revise","issues":["there are no assertions"],'
                             '"recommendations":[],"confidence":0.9}')
        c = check_evidence_conflict(
            v, {"quality": "GOOD",
                "evidence": {"asserts": 3, "assert_methods": ["assertEqual"]}})
        self.assertIsNotNone(c)
        self.assertEqual(c["kind"], "REVIEWER_EVIDENCE_CONFLICT")
        self.assertEqual(c["asserts_found"], 3)

    def test_no_conflict_when_agreeing(self):
        v, _ = parse_verdict('{"verdict":"approve","issues":[],"recommendations":[],'
                             '"confidence":1.0}')
        self.assertIsNone(check_evidence_conflict(v, {"evidence": {"asserts": 2}}))

    def test_no_conflict_when_truly_empty(self):
        v, _ = parse_verdict('{"verdict":"revise","issues":["no tests at all"],'
                             '"recommendations":[],"confidence":0.5}')
        self.assertIsNone(check_evidence_conflict(
            v, {"evidence": {"asserts": 0, "assert_methods": []}}))


class TestConflictStopsLoop(unittest.TestCase):
    def _cfg(self, tmp, authority):
        return BridgeConfig(workspace=tmp, mode="build", approval="AUTO_SAFE",
                            max_steps=12, non_interactive=True,
                            enable_reviewer=True,
                            review_authority=authority)

    def test_evidence_gated_stops_repeat(self):
        tmp = Path(tempfile.mkdtemp(prefix="v06_conf_"))
        try:
            (tmp / "app.py").write_text("def f():\n return 1\n")
            cfg = self._cfg(tmp, "EVIDENCE_GATED")
            coder = FakeProvider([
                '{"action":"write","path":"test_app.py","content":"import unittest\\nimport app\\nclass T(unittest.TestCase):\\n def test_x(self):\\n  self.assertEqual(app.f(), 1)"}',
                '{"action":"test","command":"python test_app.py"}',
                '{"action":"finish","message":"done"}',
                '{"action":"finish","message":"done again"}',
            ])
            rev = FakeProvider([
                '{"verdict":"revise","issues":["there are no assertions"],'
                '"recommendations":["add asserts"],"confidence":0.9}',
                '{"verdict":"revise","issues":["there are no assertions"],'
                '"recommendations":["add asserts"],"confidence":0.9}',
            ])
            out = run_bridge(cfg, "t", providers={"coder": coder, "planner": coder,
                                                  "general": coder, "reviewer": rev})
            self.assertTrue(out.get("finished"), out)
            self.assertEqual(out.get("kind"), "REVIEWER_UNRELIABLE_FOR_THIS_DECISION")
            self.assertTrue((tmp / "test_app.py").exists())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_authoritative_keeps_old_behavior(self):
        tmp = Path(tempfile.mkdtemp(prefix="v06_conf2_"))
        try:
            (tmp / "app.py").write_text("def f():\n return 1\n")
            cfg = self._cfg(tmp, "AUTHORITATIVE")
            cfg.max_revision_cycles = 1
            coder = FakeProvider([
                '{"action":"finish","message":"done"}',
                '{"action":"finish","message":"done"}',
            ])
            rev = FakeProvider([
                '{"verdict":"revise","issues":["there are no assertions"],'
                '"recommendations":[],"confidence":0.9}',
                '{"verdict":"revise","issues":["still no assertions"],'
                '"recommendations":[],"confidence":0.9}',
            ])
            out = run_bridge(cfg, "t", providers={"coder": coder, "planner": coder,
                                                  "general": coder, "reviewer": rev})
            self.assertFalse(out.get("finished", False))
            self.assertEqual(out.get("kind"), "REVISION_EXHAUSTED")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
