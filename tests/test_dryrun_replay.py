"""v0.3: dry-run zero-mutation + replay audit/verify."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from bridge import run_bridge
from config import BridgeConfig
from replay import audit, verify
from tests.helpers import FakeProvider


def _cfg(tmp: Path, **kw) -> BridgeConfig:
    args = dict(workspace=tmp, mode="build", approval="AUTO_SAFE",
                max_steps=8, non_interactive=True, enable_reviewer=False)
    args.update(kw)
    return BridgeConfig(**args)


SCRIPT = ['{"action":"write","path":"plan.txt","content":"hello"}',
          '{"action":"patch","path":"plan.txt","edits":[{"old":"hello","new":"world"}]}',
          '{"action":"shell","command":"python plan.txt"}',
          '{"action":"finish","message":"plan: create plan.txt then patch it"}']


class TestDryRun(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="v03_dry_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_dry_run_zero_mutations(self):
        cfg = _cfg(self.tmp, dry_run=True)
        before = sorted(p.name for p in self.tmp.iterdir())
        out = run_bridge(cfg, "dry task", provider=FakeProvider(list(SCRIPT)))
        self.assertTrue(out.get("finished"), out)
        after = sorted(p.name for p in self.tmp.iterdir())
        # dry-run writes NOTHING: no plan.txt, no .bridge, no memory, no logs
        self.assertEqual(before, after)
        self.assertEqual(after, [])
        previews = [h for h in out["history"] if "NOT EXECUTED" in str(h.get("note", ""))]
        self.assertTrue(previews)
        self.assertTrue(any("patch" in str(h.get("action", "")) for h in previews))

    def test_dry_run_shows_approvals(self):
        cfg = _cfg(self.tmp, dry_run=True)
        out = run_bridge(cfg, "dry task", provider=FakeProvider(list(SCRIPT)))
        kinds = [h.get("result", {}).get("approval_preview") for h in out["history"]
                 if h.get("result", {}).get("approval_preview")]
        self.assertTrue(kinds)


class TestReplay(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="v03_replay_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run_with_jsonl(self) -> Path:
        jl = self.tmp / "sess.jsonl"
        cfg = _cfg(self.tmp)
        cfg.logging.jsonl_log = str(jl)
        # Phase 1.1 amendment: the script performs a passing test so
        # finish carries verification evidence. Replay assertions unchanged.
        fake = FakeProvider(['{"action":"write","path":"r.txt","content":"print(1)\\n"}',
                             '{"action":"test","command":"python r.txt"}',
                             '{"action":"finish","message":"ok"}'])
        out = run_bridge(cfg, "replay task", provider=fake)
        self.assertTrue(out.get("finished"), out)
        return jl

    def test_audit_no_execution(self):
        jl = self._run_with_jsonl()
        before = (self.tmp / "r.txt").read_text()
        a = audit(jl)
        self.assertTrue(a["ok"])
        self.assertEqual(a["mode"], "audit")
        self.assertIn("nothing was executed", a["note"])
        self.assertEqual((self.tmp / "r.txt").read_text(), before)

    def test_verify_confirms(self):
        jl = self._run_with_jsonl()
        v = verify(jl, self.tmp)
        self.assertTrue(v["ok"], v)
        self.assertGreaterEqual(v["checked"], 1)
        self.assertEqual(v["mismatched"], [])

    def test_verify_detects_missing(self):
        jl = self._run_with_jsonl()
        (self.tmp / "r.txt").unlink()
        v = verify(jl, self.tmp)
        self.assertFalse(v["ok"])
        self.assertTrue(v["mismatched"])


if __name__ == "__main__":
    unittest.main()
