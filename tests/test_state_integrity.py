"""State integrity / crash recovery / concurrent-write tests (v0.8).

Disposable fixtures only. Verifies EXISTING mechanisms (no new source):
atomic temp-file+fsync+replace writes, journal backups enabling rollback,
interrupted-task identifiability, artifact ID uniqueness, and
same-file concurrent-write behavior (whole-version wins, never torn).
"""
import os
import tempfile
import threading
import unittest
from pathlib import Path

from executor import Executor
from tools.artifacts import ArtifactRegistry


class AtomicWriteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ab_state_")
        self.ws = Path(self.tmp.name) / "ws"
        self.ws.mkdir()
        self.ex = Executor(workspace=self.ws)

    def tearDown(self):
        self.tmp.cleanup()

    def test_write_is_exact_and_leaves_no_partials(self):
        res = self.ex.dispatch({"action": "write", "path": "a.txt",
                                "content": "hello"})
        self.assertTrue(res.get("ok"), res)
        self.assertEqual((self.ws / "a.txt").read_text(encoding="utf-8"),
                         "hello")
        leftovers = list(self.ws.glob(".bridge-tmp-*.part"))
        self.assertEqual(leftovers, [])

    def test_refused_write_leaves_original_intact(self):
        (self.ws / "keep.txt").write_text("original", encoding="utf-8")
        res = self.ex.dispatch({"action": "write",
                                "path": "../evil.txt", "content": "x"})
        self.assertFalse(res.get("ok"))
        self.assertEqual((self.ws / "keep.txt").read_text(encoding="utf-8"),
                         "original")
        self.assertFalse((Path(self.tmp.name) / "evil.txt").exists())

    def test_journal_backup_enables_rollback(self):
        self.ex.dispatch({"action": "write", "path": "v.txt",
                          "content": "v1"})
        self.ex.dispatch({"action": "write", "path": "v.txt",
                          "content": "v2"})
        writes = [e for e in self.ex.journal
                  if e.get("action") == "write" and e.get("path") == "v.txt"]
        self.assertEqual(len(writes), 2)
        # Second write recorded the pre-image: restore proves rollback.
        backup = writes[1]["backup"]
        (self.ws / "v.txt").write_bytes(backup)
        self.assertEqual((self.ws / "v.txt").read_text(encoding="utf-8"),
                         "v1")


class CrashRecoveryTests(unittest.TestCase):
    def test_interrupted_multistep_is_identifiable(self):
        with tempfile.TemporaryDirectory(prefix="ab_crash_") as d:
            ws = Path(d) / "ws"
            ws.mkdir()
            ex = Executor(workspace=ws)
            # Step 1-2 commit; step 3 "crashes" (never dispatched).
            self.assertTrue(ex.dispatch(
                {"action": "write", "path": "s1.txt",
                 "content": "one"})["ok"])
            self.assertTrue(ex.dispatch(
                {"action": "write", "path": "s2.txt",
                 "content": "two"})["ok"])
            # No completion record exists for the unfinished plan, and the
            # supposedly-produced third artifact is verifiably absent.
            self.assertFalse((ws / "s3.txt").exists())
            done = [e for e in ex.journal if e.get("plan_complete")]
            self.assertEqual(done, [])
            self.assertTrue((ws / "s1.txt").exists())
            self.assertTrue((ws / "s2.txt").exists())

    def test_artifact_ids_never_collide(self):
        reg = ArtifactRegistry()
        ids = {reg.register("report", f"ref-{i}")["artifact_id"]
               for i in range(50)}
        self.assertEqual(len(ids), 50)

    def test_missing_artifact_verification_honest(self):
        reg = ArtifactRegistry()
        entry = reg.register("file", "no/such/file.bin")
        self.assertEqual(entry["verification"], "MISSING")


class ConcurrentWriteTests(unittest.TestCase):
    def test_independent_files_parallel_safe(self):
        with tempfile.TemporaryDirectory(prefix="ab_conc_") as d:
            ws = Path(d) / "ws"
            ws.mkdir()
            ex = Executor(workspace=ws)
            results = {}
            threads = [
                threading.Thread(
                    target=lambda i=i: results.setdefault(
                        i, ex.dispatch({"action": "write",
                                        "path": f"f{i}.txt",
                                        "content": f"content-{i}"})))
                for i in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self.assertTrue(all(r.get("ok") for r in results.values()))
            for i in range(8):
                self.assertEqual(
                    (ws / f"f{i}.txt").read_text(encoding="utf-8"),
                    f"content-{i}")

    def test_same_file_never_torn(self):
        # Documented behavior: concurrent same-file writers serialize
        # through atomic replace; the winner is whole, never partial.
        # (Cross-task same-file work should use the scheduler
        # write-collision guard to order writers deterministically.)
        with tempfile.TemporaryDirectory(prefix="ab_conc2_") as d:
            ws = Path(d) / "ws"
            ws.mkdir()
            ex = Executor(workspace=ws)
            v1 = "A" * 5000
            v2 = "B" * 5000
            outs = []
            threads = [
                threading.Thread(target=lambda c=c: outs.append(
                    ex.dispatch({"action": "write", "path": "shared.txt",
                                 "content": c})))
                for c in (v1, v2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self.assertTrue(all(o.get("ok") for o in outs))
            final = (ws / "shared.txt").read_text(encoding="utf-8")
            self.assertIn(final, (v1, v2))
            self.assertTrue(final == v1 or final == v2)


if __name__ == "__main__":
    unittest.main()
