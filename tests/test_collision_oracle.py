"""v0.4: write-collision policy + oracle/test-quality + change-awareness."""
import shutil
import tempfile
import unittest
from pathlib import Path

from bridge import run_bridge
from config import BridgeConfig
from oracle import assess
from tests.helpers import FakeProvider


def _cfg(tmp: Path, **kw) -> BridgeConfig:
    args = dict(workspace=tmp, mode="build", approval="AUTO_SAFE",
                max_steps=10, non_interactive=True, enable_reviewer=False)
    args.update(kw)
    return BridgeConfig(**args)


class TestCollisionPolicy(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="v04_col_"))
        (self.tmp / "seed.txt").write_text("user original\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, collision: str, script: list[str]):
        cfg = _cfg(self.tmp, collision=collision)
        return run_bridge(cfg, "t", provider=FakeProvider(script))

    def test_default_requires_approval_deny_keeps_file(self):
        out = self._run("REQUIRE_APPROVAL",
                        ['{"action":"write","path":"seed.txt","content":"clobber"}',
                         '{"action":"write","path":"seed.txt","content":"clobber"}',
                         '{"action":"write","path":"seed.txt","content":"clobber"}',
                         '{"action":"finish","message":"x"}'])
        self.assertEqual((self.tmp / "seed.txt").read_text(), "user original\n")
        kinds = {h.get("kind") for h in out["history"] if h.get("kind")}
        self.assertIn("APPROVAL_DENIED", kinds)

    def test_refuse_blocks(self):
        out = self._run("REFUSE",
                        ['{"action":"write","path":"seed.txt","content":"clobber"}',
                         '{"action":"finish","message":"x"}'])
        self.assertEqual((self.tmp / "seed.txt").read_text(), "user original\n")
        self.assertTrue(any(h.get("kind") == "COLLISION_DENIED" for h in out["history"]))

    def test_overwrite_allows_once(self):
        out = self._run("OVERWRITE",
                        ['{"action":"write","path":"seed.txt","content":"new"}',
                         '{"action":"finish","message":"ok"}'])
        self.assertTrue(out.get("finished"), out)
        self.assertEqual((self.tmp / "seed.txt").read_text(), "new")
        man = list((self.tmp / ".bridge" / "checkpoints").rglob("manifest.json"))
        self.assertTrue(man, "checkpoint manifest must exist for executed write")

    def test_create_backup_routes_through_approval(self):
        out = self._run("CREATE_BACKUP",
                        ['{"action":"write","path":"seed.txt","content":"new2"}',
                         '{"action":"write","path":"seed.txt","content":"new2"}',
                         '{"action":"write","path":"seed.txt","content":"new2"}',
                         '{"action":"finish","message":"ok"}'])
        # non-interactive: approval required, so no silent clobber
        self.assertEqual((self.tmp / "seed.txt").read_text(), "user original\n")

    def test_bridge_created_rewrite_allowed_by_default(self):
        out = self._run("REQUIRE_APPROVAL",
                        ['{"action":"write","path":"fresh.txt","content":"v1"}',
                         '{"action":"finish","message":"ok"}'])
        self.assertTrue(out.get("finished"), out)
        self.assertTrue((self.tmp / "fresh.txt").exists())


class TestOracle(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="v04_oracle_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_good(self):
        (self.tmp / "calc.py").write_text("def add(a,b):\n return a+b\n")
        (self.tmp / "test_calc.py").write_text(
            "import calc\nassert calc.add(1,2)==3\nassert calc.add(0,0)==0\n")
        r = assess(["calc.py"], ["test_calc.py"], "+def add", [{"passed": True}],
                   self.tmp)
        self.assertEqual(r["quality"], "GOOD")

    def test_suspicious_no_exercise(self):
        (self.tmp / "core.py").write_text("def f():\n return 1\n")
        (self.tmp / "test_x.py").write_text("assert 1==1\nassert 2==2\n")
        r = assess(["core.py"], ["test_x.py"], "+def f", [{"passed": True}], self.tmp)
        self.assertEqual(r["quality"], "SUSPICIOUS")

    def test_suspicious_no_asserts(self):
        (self.tmp / "core.py").write_text("X=1\n")
        (self.tmp / "test_x.py").write_text("import core\nprint('hi')\n")
        r = assess(["core.py"], ["test_x.py"], "", [{"passed": True}], self.tmp)
        self.assertEqual(r["quality"], "SUSPICIOUS")

    def test_weak_no_tests(self):
        r = assess(["a.py"], [], "", [], self.tmp)
        self.assertEqual(r["quality"], "WEAK")

    def test_weak_shell_only_verification(self):
        r = assess(["a.py"], [], "", [{"passed": True}], self.tmp)
        self.assertEqual(r["quality"], "WEAK")
        self.assertIn("shell", r["reasons"][0])

    def test_suspicious_not_fully_verified(self):
        cfg = _cfg(self.tmp)
        fake = FakeProvider([
            '{"action":"write","path":"core.py","content":"X=1"}',
            '{"action":"write","path":"test_c.py","content":"assert 1==1"}',
            '{"action":"test","command":"python test_c.py"}',
            '{"action":"finish","message":"ok"}'])
        out = run_bridge(cfg, "t", provider=fake)
        tr = out.get("task_result", {})
        self.assertEqual(tr.get("tests", {}).get("quality"), "SUSPICIOUS")
        # must NOT be represented as fully verified
        self.assertFalse(tr.get("tests", {}).get("verified"))


if __name__ == "__main__":
    unittest.main()
