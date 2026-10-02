"""Two operating-system processes, one workspace.

Every lock in the Bridge was a threading primitive, which means it did not
exist as far as any other process was concerned. That is not a theoretical
gap: the idempotency store is a read-modify-write file, so a second process
recovering or persisting at the same moment would drop the first one's record
-- and a dropped idempotency record is a completed mutation running twice.
The checkpoint manifest had the same shape, where the visible symptom is
softer and worse: rollback quietly restores nothing.

These tests fork real processes. Not threads, not mocks: the whole point is
that a threading lock cannot be the thing under test.
"""
from __future__ import annotations

import json
import multiprocessing as mp
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from bridge import persist_completed_records
from checkpoints import CheckpointManager
from executor import Executor, WorkspaceLock


def _record(ws: str, name: str) -> None:
    """Run in a child process: perform one action and merge its record."""
    from aether_policy_bridge import issue_session_workspace_grants
    from executor import atomic_write_text
    issue_session_workspace_grants("s-" + name, ws, "AUTO_SAFE")
    ex = Executor(Path(ws), session_id="s-" + name)
    action = {"action": "write", "path": f"{name}.txt", "content": name}
    ex.dispatch(dict(action), action_id=f"a-{name}")
    cpath = Path(ws) / ".bridge" / "sessions" / "s-shared" / "completed_actions.json"
    persist_completed_records(ex, cpath, Path(ws))


def _snapshot(ws: str, name: str) -> None:
    """Run in a child process: snapshot one file under a shared label."""
    mgr = CheckpointManager(Path(ws), "shared")
    payload = (name + "-original").encode()
    mgr.snapshot(f"{name}.txt", True, payload)


class TestCrossProcessIdempotencyStore(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="xproc_"))
        self.ws = str(self.tmp)
        self.cpath = (self.tmp / ".bridge" / "sessions" / "s-shared"
                      / "completed_actions.json")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _spawn(self, names: list[str]) -> None:
        ctx = mp.get_context("spawn")
        procs = [ctx.Process(target=_record, args=(self.ws, n)) for n in names]
        for p in procs:
            p.start()
        for p in procs:
            p.join(timeout=120)
            self.assertEqual(p.exitcode, 0, f"child exited {p.exitcode}")

    def test_concurrent_writers_do_not_lose_each_others_records(self):
        # The regression this closes: each child re-reads the store and
        # writes back only what it knows, so the last writer wins and every
        # other process's completed mutation is forgotten.
        self._spawn(["alpha", "beta", "gamma", "delta"])
        stored = json.loads(self.cpath.read_text(encoding="utf-8"))
        for name in ("alpha", "beta", "gamma", "delta"):
            self.assertIn(f"a-{name}", stored,
                          f"{name}'s completed record was lost to a concurrent writer")
            self.assertTrue((self.tmp / f"{name}.txt").exists())

    def test_records_written_sequentially_also_survive(self):
        # Sanity for the merge path itself, independent of contention.
        self._spawn(["solo"])
        self._spawn(["later"])
        stored = json.loads(self.cpath.read_text(encoding="utf-8"))
        self.assertIn("a-solo", stored)
        self.assertIn("a-later", stored)

    def test_the_stored_file_is_always_parsable(self):
        self._spawn(["one", "two", "three"])
        json.loads(self.cpath.read_text(encoding="utf-8"))


class TestCrossProcessCheckpoints(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="xckpt_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_concurrent_snapshots_keep_every_file(self):
        names = ["one", "two", "three", "four"]
        ctx = mp.get_context("spawn")
        procs = [ctx.Process(target=_snapshot, args=(str(self.tmp), n))
                 for n in names]
        for p in procs:
            p.start()
        for p in procs:
            p.join(timeout=120)
            self.assertEqual(p.exitcode, 0, f"child exited {p.exitcode}")
        man = json.loads(
            (self.tmp / ".bridge" / "checkpoints" / "shared" / "manifest.json")
            .read_text(encoding="utf-8"))
        self.assertEqual(sorted(man.get("files", {})), sorted(f"{n}.txt" for n in names))

    def test_every_surviving_backup_is_actually_restorable(self):
        names = ["one", "two", "three"]
        ctx = mp.get_context("spawn")
        procs = [ctx.Process(target=_snapshot, args=(str(self.tmp), n))
                 for n in names]
        for p in procs:
            p.start()
        for p in procs:
            p.join(timeout=120)
        for n in names:
            (self.tmp / f"{n}.txt").write_text("changed", encoding="utf-8")
        out = CheckpointManager(self.tmp, "shared").rollback()
        self.assertTrue(out["ok"], out)
        self.assertEqual(sorted(out["restored"]), sorted(f"{n}.txt" for n in names))
        for n in names:
            self.assertEqual((self.tmp / f"{n}.txt").read_text(), f"{n}-original")


class TestWorkspaceLockItself(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="wlock_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_a_second_process_blocks_until_the_first_releases(self):
        ctx = mp.get_context("spawn")
        first = ctx.Process(target=_hold_then_sleep, args=(str(self.tmp), "t", 2.0))
        first.start()
        try:
            deadline = time.time() + 30
            blocked = False
            while time.time() < deadline:
                try:
                    with WorkspaceLock(self.tmp, "t", timeout_s=0.2):
                        pass
                except TimeoutError:
                    blocked = True
                    break
                time.sleep(0.05)
            self.assertTrue(blocked, "the child never took the cross-process lock")
            started = time.time()
            with WorkspaceLock(self.tmp, "t", timeout_s=30):
                waited = time.time() - started
            self.assertGreater(waited, 0.5,
                               "the second acquire did not wait for the first")
        finally:
            first.join(timeout=60)

    def test_the_lock_is_released_when_the_holder_dies(self):
        # An OS file lock is released by the kernel on process exit, so a
        # crashed run cannot wedge the workspace permanently.
        ctx = mp.get_context("spawn")
        victim = ctx.Process(target=_hold_then_die, args=(str(self.tmp), "crash"))
        victim.start()
        victim.join(timeout=60)
        self.assertEqual(victim.exitcode, 17)
        with WorkspaceLock(self.tmp, "crash", timeout_s=5):
            pass  # a lock left behind by a dead process is not held

    def test_timeout_is_explicit_rather_than_silent(self):
        holder = WorkspaceLock(self.tmp, "busy", timeout_s=5)
        holder.__enter__()
        self.addCleanup(holder._close)
        with self.assertRaises(TimeoutError) as ctx:
            with WorkspaceLock(self.tmp, "busy", timeout_s=0.2):
                pass
        self.assertIn("busy", str(ctx.exception))

    def test_the_lock_file_lives_under_the_protected_directory(self):
        from executor import Sandbox, SandboxViolation
        with WorkspaceLock(self.tmp, "x") as lk:
            rel = str(Path(lk.path).relative_to(self.tmp))
        self.assertIn(".bridge", Path(rel).parts)
        with self.assertRaises(SandboxViolation):
            Sandbox(self.tmp).resolve(rel)


def _hold_then_sleep(ws: str, name: str, seconds: float) -> None:
    with WorkspaceLock(Path(ws), name, timeout_s=30):
        time.sleep(seconds)


def _hold_then_die(ws: str, name: str) -> None:
    import os
    with WorkspaceLock(Path(ws), name, timeout_s=30):
        os._exit(17)


if __name__ == "__main__":
    unittest.main()