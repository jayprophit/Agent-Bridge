"""v0.3: recycle/restore, multi-hunk patch + dry-run, diff, atomic writes."""
import shutil
import tempfile
import unittest
from pathlib import Path

from executor import Executor


class TestRecycle(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="v03_rec_"))
        self.ex = Executor(self.tmp, session_id="s1")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_delete_recycles_and_restores(self):
        self.ex.do_write("gone.txt", "precious")
        r = self.ex.do_delete("gone.txt")
        self.assertTrue(r["ok"], r)
        self.assertTrue(r.get("recycled"))
        self.assertFalse((self.tmp / "gone.txt").exists())
        rid = r["restore_id"]
        rr = self.ex.do_restore(rid)
        self.assertTrue(rr["ok"], rr)
        self.assertEqual((self.tmp / "gone.txt").read_text(), "precious")

    def test_restore_unknown_id_refused(self):
        r = self.ex.do_restore("r-nope-1234")
        self.assertFalse(r["ok"])

    def test_permanent_delete(self):
        self.ex.do_write("p.txt", "x")
        r = self.ex.do_delete("p.txt", permanent=True)
        self.assertTrue(r["ok"], r)
        self.assertTrue(r.get("permanent"))
        self.assertFalse((self.tmp / "p.txt").exists())

    def test_recycle_never_leaves_workspace(self):
        self.ex.do_write("a.txt", "x")
        r = self.ex.do_delete("a.txt")
        rec = self.tmp / ".bridge" / "recycle"
        self.assertTrue(rec.exists())
        for p in rec.rglob("*"):
            self.assertEqual(p.resolve().relative_to(self.tmp.resolve()) is not None, True)


class TestMultiHunkPatch(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="v03_patch_"))
        self.ex = Executor(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_multi_replace(self):
        self.ex.do_write("m.txt", "aaa\nbbb\nccc\n")
        r = self.ex.dispatch({"action": "patch", "path": "m.txt",
                              "edits": [{"old": "aaa", "new": "AAA"},
                                        {"old": "ccc", "new": "CCC"}]})
        self.assertTrue(r["ok"], r)
        text = (self.tmp / "m.txt").read_text()
        self.assertIn("AAA", text)
        self.assertIn("CCC", text)
        self.assertIn("bbb", text)

    def test_insert_before_after(self):
        self.ex.do_write("i.txt", "middle\n")
        r = self.ex.dispatch({"action": "patch", "path": "i.txt",
                              "edits": [{"anchor": "middle\n", "insert": "top\n",
                                         "position": "before"},
                                        {"anchor": "middle\n", "insert": "bottom\n",
                                         "position": "after"}]})
        self.assertTrue(r["ok"], r)
        self.assertEqual((self.tmp / "i.txt").read_text().splitlines(),
                         ["top", "middle", "bottom"])

    def test_dry_run_no_mutation(self):
        self.ex.do_write("d.txt", "one\ntwo\n")
        r = self.ex.dispatch({"action": "patch", "path": "d.txt",
                              "edits": [{"old": "one", "new": "ONE"}],
                              "dry_run": True})
        self.assertTrue(r["ok"], r)
        self.assertTrue(r.get("dry_run"))
        self.assertTrue(r.get("would_succeed"))
        self.assertTrue(any(h.get("range") == [1, 1] for h in r.get("hunks", [])))
        self.assertEqual((self.tmp / "d.txt").read_text(), "one\ntwo\n")

    def test_dry_run_reports_failure(self):
        self.ex.do_write("e.txt", "abc\n")
        r = self.ex.dispatch({"action": "patch", "path": "e.txt",
                              "edits": [{"old": "zzz", "new": "Z"}],
                              "dry_run": True})
        self.assertFalse(r["ok"])
        self.assertFalse(r.get("would_succeed"))
        self.assertEqual((self.tmp / "e.txt").read_text(), "abc\n")

    def test_noop_edit_and_patch_refused(self):
        self.ex.do_write("n.txt", "same\n")
        r = self.ex.do_edit("n.txt", "same", "same")
        self.assertFalse(r["ok"])
        self.assertIn("no-op", r["error"])
        self.assertEqual((self.tmp / "n.txt").read_text(), "same\n")
        r2 = self.ex.dispatch({"action": "patch", "path": "n.txt",
                               "edits": [{"old": "same", "new": "same"}]})
        self.assertFalse(r2["ok"])
        self.assertIn("no-op", r2["error"])


class TestDiffAndAtomic(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="v03_diff_"))
        self.ex = Executor(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_file_and_session_diff(self):
        self.ex.do_write("f.txt", "a\nb\n", action_id="a1")
        self.ex.do_edit("f.txt", "b", "B", action_id="a2")
        d = self.ex.do_diff(target="file", path="f.txt")
        self.assertTrue(d["ok"], d)
        self.assertIn("-b", d["diff"])
        self.assertIn("+B", d["diff"])
        s = self.ex.do_diff(target="session")
        self.assertTrue(s["ok"])
        self.assertIn("f.txt", s["diff"])

    def test_atomic_write_no_leftovers(self):
        self.ex.do_write("w.txt", "data")
        leftovers = list(self.tmp.glob(".bridge-tmp-*")) + list(self.tmp.glob("*.part"))
        self.assertEqual(leftovers, [])
        self.assertEqual((self.tmp / "w.txt").read_text(), "data")


if __name__ == "__main__":
    unittest.main()
