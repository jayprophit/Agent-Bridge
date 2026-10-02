"""Records are not evidence. The world is.

Every durable artifact the Bridge keeps -- the idempotency store, the session
snapshot, the history archive, the checkpoint manifest -- lives in the
workspace, under a directory the model cannot write, but written by the same
user account as everything else. Nothing in that directory is authentic by
construction, so a record may never be the reason the system reports an
effect it cannot confirm.

These tests attack the records directly: forge them, truncate them, retarget
them, and require the Bridge to refuse rather than comply. They also pin the
durability and the protected-path rules that make the refusals possible.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path

from checkpoints import CheckpointManager, _valid_label
from executor import Executor, Sandbox, SandboxViolation, atomic_write_text
from protocol import action_fingerprint


class TestIdempotencyStoreIsNotAuthority(unittest.TestCase):
    """The store can suppress a mutation or fake one; neither may stand."""

    def setUp(self):
        from aether_policy_bridge import issue_session_workspace_grants
        self.tmp = Path(tempfile.mkdtemp(prefix="evidence_"))
        self.sid = "s-evidence-test"
        issue_session_workspace_grants(self.sid, str(self.tmp), "AUTO_SAFE")
        self.ex = Executor(self.tmp, session_id=self.sid)

    def tearDown(self):
        from aether_policy_bridge import reset_policy_engine
        reset_policy_engine()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _store(self, records: dict) -> Path:
        p = self.tmp / ".bridge" / "sessions" / "s1" / "completed_actions.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(records), encoding="utf-8")
        return p

    def test_forged_success_for_an_unperformed_write_is_refused(self):
        action = {"action": "write", "path": "ghost.txt", "content": "x"}
        record = {"ok": True, "verified": True, "dedup": True,
                  "path": "ghost.txt",
                  "_action_fingerprint": action_fingerprint(action)}
        self.ex.completed["a-1"] = dict(record)
        r = self.ex.dispatch(dict(action), action_id="a-1")
        self.assertFalse(r["ok"])
        self.assertEqual(r["kind"], "STALE_IDEMPOTENCY_RECORD")
        self.assertFalse(r.get("executed", False))
        self.assertFalse((self.tmp / "ghost.txt").exists(),
                         "a forged record produced a real effect")

    def test_forged_delete_record_cannot_hide_a_surviving_file(self):
        action = {"action": "delete", "path": "keep.txt"}
        (self.tmp / "keep.txt").write_text("still here", encoding="utf-8")
        self.ex.completed["a-2"] = {
            "ok": True, "path": "keep.txt",
            "_action_fingerprint": action_fingerprint(action)}
        r = self.ex.dispatch(dict(action), action_id="a-2")
        self.assertFalse(r["ok"])
        self.assertEqual(r["kind"], "STALE_IDEMPOTENCY_RECORD")
        self.assertTrue((self.tmp / "keep.txt").exists())

    def test_genuine_record_still_dedups(self):
        action = {"action": "write", "path": "real.txt", "content": "v"}
        first = self.ex.dispatch(dict(action), action_id="a-3")
        self.assertTrue(first["ok"])
        second = self.ex.dispatch(dict(action), action_id="a-3")
        self.assertTrue(second.get("dedup"), second)
        self.assertTrue(second.get("effect_verified"))

    def test_record_is_reusable_after_the_effect_comes_back(self):
        # A record is not permanently poisoned: if the world matches again,
        # replay is legitimate.
        action = {"action": "write", "path": "flip.txt", "content": "v"}
        self.assertTrue(self.ex.dispatch(dict(action), action_id="a-4")["ok"])
        target = self.tmp / "flip.txt"
        saved = target.read_text(encoding="utf-8")
        target.write_text("other", encoding="utf-8")
        self.assertFalse(self.ex.dispatch(dict(action), action_id="a-4")["ok"])
        target.write_text(saved, encoding="utf-8")
        again = self.ex.dispatch(dict(action), action_id="a-4")
        self.assertTrue(again.get("dedup"), again)

    def test_shell_records_are_not_replayable(self):
        # A shell outcome leaves nothing in the world to check, so it cannot
        # be certified: no claim means no certification.
        action = {"action": "shell", "command": "python -c \"print(1)\""}
        r = self.ex.dispatch(dict(action), action_id="a-5")
        self.assertNotIn("_effect", self.ex.completed.get("a-5", {}))
        # and with no assertion a re-request is refused rather than trusted
        self.ex.completed["a-6"] = {"ok": True,
                                    "_action_fingerprint": action_fingerprint(action)}
        again = self.ex.dispatch(dict(action), action_id="a-6")
        self.assertFalse(again.get("ok"), again)

    def test_unverifiable_record_is_audited(self):
        action = {"action": "write", "path": "audited.txt", "content": "v"}
        self.ex.completed["a-7"] = {"ok": True,
                                    "_action_fingerprint": action_fingerprint(action)}
        self.ex.dispatch(dict(action), action_id="a-7")
        log = self.tmp / ".bridge" / "logs" / "audit.jsonl"
        self.assertTrue(log.exists(), "an unverified record left no trace")
        kinds = [json.loads(line)["kind"]
                 for line in log.read_text(encoding="utf-8").splitlines() if line]
        self.assertIn("idempotency_record_unverified", kinds)


class TestRecoveryLoaderRejectsUncheckableRecords(unittest.TestCase):
    """Recovery must re-establish truth, not adopt whatever is on disk."""

    def setUp(self):
        from aether_policy_bridge import issue_session_workspace_grants
        self.tmp = Path(tempfile.mkdtemp(prefix="recover_"))
        self.sid = "s-recover-test"
        issue_session_workspace_grants(self.sid, str(self.tmp), "AUTO_SAFE")
        self.ex = Executor(self.tmp, session_id=self.sid)
        self.store = self.tmp / ".bridge" / "sessions" / self.sid / \
            "completed_actions.json"

    def tearDown(self):
        from aether_policy_bridge import reset_policy_engine
        reset_policy_engine()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_store(self, records: dict) -> None:
        self.store.parent.mkdir(parents=True, exist_ok=True)
        self.store.write_text(json.dumps(records), encoding="utf-8")

    def _load(self) -> tuple[int, int]:
        from bridge import load_completed_records
        self.ex.completed.clear()
        return load_completed_records(self.ex, self.store)

    def test_genuine_records_are_adopted(self):
        action = {"action": "write", "path": "real.txt", "content": "v"}
        self.assertTrue(self.ex.dispatch(dict(action), action_id="a-1")["ok"])
        from executor import atomic_write_text
        atomic_write_text(self.store, json.dumps(self.ex.completed, default=str))
        kept, dropped = self._load()
        self.assertEqual((kept, dropped), (1, 0))

    def test_forged_success_without_a_checkable_effect_is_dropped(self):
        action = {"action": "write", "path": "forged.txt", "content": "v"}
        self._write_store({"a-2": {"ok": True, "verified": True,
                                  "path": "forged.txt",
                                  "_action_fingerprint": action_fingerprint(action)}})
        kept, dropped = self._load()
        self.assertEqual((kept, dropped), (0, 1))
        self.assertNotIn("a-2", self.ex.completed)
        # and so the action really runs instead of being reported done
        r = self.ex.dispatch(dict(action), action_id="a-2")
        self.assertTrue(r["ok"], r)
        self.assertTrue((self.tmp / "forged.txt").exists())

    def test_a_corrupt_store_is_ignored_without_crashing_recovery(self):
        self.store.parent.mkdir(parents=True, exist_ok=True)
        self.store.write_text("{not json", encoding="utf-8")
        self.assertEqual(self._load(), (0, 0))

    def test_a_non_object_store_is_ignored(self):
        self._write_store(["a-1", "a-2"])
        self.assertEqual(self._load(), (0, 0))

    def test_missing_store_is_not_an_error(self):
        self.assertEqual(self._load(), (0, 0))

    def test_checkable_record_still_fails_when_the_world_disagrees(self):
        # Adoption is not trust: the assertion is re-checked on replay.
        action = {"action": "write", "path": "flip.txt", "content": "v"}
        self.assertTrue(self.ex.dispatch(dict(action), action_id="a-3")["ok"])
        from executor import atomic_write_text
        atomic_write_text(self.store, json.dumps(self.ex.completed, default=str))
        (self.tmp / "flip.txt").write_text("tampered", encoding="utf-8")
        kept, _ = self._load()
        self.assertEqual(kept, 1)
        r = self.ex.dispatch(dict(action), action_id="a-3")
        self.assertEqual(r["kind"], "STALE_IDEMPOTENCY_RECORD")
        # Refused, not silently re-applied: a record we cannot trust must not
        # also quietly overwrite whatever is there now.
        self.assertFalse(r["executed"])
        self.assertEqual((self.tmp / "flip.txt").read_text(), "tampered")

    def test_caller_can_retry_deliberately_and_the_effect_lands(self):
        # A refusal is not a dead end: retrying under a fresh id does the work.
        action = {"action": "write", "path": "retry.txt", "content": "v"}
        self.assertTrue(self.ex.dispatch(dict(action), action_id="a-4")["ok"])
        (self.tmp / "retry.txt").unlink()
        first = self.ex.dispatch(dict(action), action_id="a-4")
        self.assertEqual(first["kind"], "STALE_IDEMPOTENCY_RECORD")
        second = self.ex.dispatch(dict(action), action_id="a-5")
        self.assertTrue(second["ok"], second)
        self.assertEqual((self.tmp / "retry.txt").read_text(), "v")


class TestProtectedPathsAtDepth(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="prot_"))
        self.sb = Sandbox(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_nested_internal_directory_is_protected(self):
        for p in ("sub/.bridge/x.txt", ".bridge/x.txt",
                  "sub/.bridge/logs/audit.jsonl", "a/b/c/.bridge/sessions/s.json"):
            with self.assertRaises(SandboxViolation, msg=p):
                self.sb.resolve(p)

    def test_ordinary_nested_paths_still_work(self):
        self.assertEqual(self.sb.resolve("a/b/.gitattributes"),
                         (self.tmp / "a" / "b" / ".gitattributes").resolve())


class TestCheckpointLabelIsANameNotAPath(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ckpt_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_traversal_labels_are_rejected(self):
        for bad in ("../escape", "a/b", "a\\b", "..", ".", "", "   ",
                    "x" * 200, "nul\x00byte", "has:colon", "q?mark"):
            with self.assertRaises(ValueError, msg=bad):
                _valid_label(bad)

    def test_ordinary_labels_are_accepted(self):
        self.assertEqual(_valid_label(" bridge-v06 "), "bridge-v06")
        self.assertEqual(_valid_label("a.b-c_1"), "a.b-c_1")

    def test_manager_cannot_be_pointed_outside_the_checkpoint_store(self):
        with self.assertRaises(ValueError):
            CheckpointManager(self.tmp, "../../elsewhere")

    def test_manifest_cannot_retarget_a_backup_outside_the_store(self):
        outside = Path(tempfile.mkdtemp(prefix="outside_"))
        try:
            secret = outside / "secret.txt"
            secret.write_text("PRIVATE", encoding="utf-8")
            mgr = CheckpointManager(self.tmp, "cp1")
            mgr.dir.mkdir(parents=True, exist_ok=True)
            mgr.manifest_path.write_text(json.dumps({
                "files": {"stolen.txt": {"existed": True,
                                        "backup": str(secret)}}}), encoding="utf-8")
            out = mgr.rollback()
            self.assertFalse(out["ok"])
            self.assertFalse((self.tmp / "stolen.txt").exists(),
                             "rollback copied a file from outside the checkpoint")
            self.assertTrue(out["errors"])
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_legitimate_backup_still_restores(self):
        mgr = CheckpointManager(self.tmp, "cp2")
        mgr.snapshot("f.txt", True, b"original")
        (self.tmp / "f.txt").write_text("changed", encoding="utf-8")
        out = mgr.rollback()
        self.assertTrue(out["ok"], out)
        self.assertEqual((self.tmp / "f.txt").read_text(), "original")


class TestAtomicDurability(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="atomic_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_replace_leaves_no_partial_file_and_keeps_the_old_content(self):
        target = self.tmp / "s.json"
        atomic_write_text(target, "first")
        self.assertEqual(target.read_text(), "first")
        atomic_write_text(target, "second")
        self.assertEqual(target.read_text(), "second")
        self.assertEqual([p.name for p in self.tmp.iterdir()], ["s.json"])

    def test_a_write_that_cannot_commit_changes_nothing(self):
        # If the commit step fails, the previous content must survive whole.
        # A write-in-place would already have truncated the file by then, and
        # the loader could not tell that from a short record.
        import executor as executor_mod
        target = self.tmp / "s.json"
        atomic_write_text(target, "good")

        def boom(*_a, **_k):
            raise OSError("simulated commit failure")

        original = executor_mod.os.replace
        executor_mod.os.replace = boom
        try:
            with self.assertRaises(OSError):
                atomic_write_text(target, "half-written")
        finally:
            executor_mod.os.replace = original
        self.assertEqual(target.read_text(), "good")
        self.assertEqual([p.name for p in self.tmp.iterdir()], ["s.json"],
                         "a temporary file was left behind")

    def test_a_bad_value_is_rejected_before_anything_is_touched(self):
        target = self.tmp / "s.json"
        atomic_write_text(target, "good")
        with self.assertRaises(TypeError):
            atomic_write_text(target, 12345)  # type: ignore[arg-type]
        self.assertEqual(target.read_text(), "good")
        self.assertEqual([p.name for p in self.tmp.iterdir()], ["s.json"])

    def test_a_concurrent_reader_never_sees_a_partial_file(self):
        # The property that matters for a state file: a reader either sees the
        # whole old content or the whole new content, never a prefix.
        #
        # A commit may legitimately fail here. On Windows a file cannot be
        # replaced while a handle is open, and a reader spinning with no pause
        # holds it open almost continuously. What must never happen is a silent
        # partial write: a failed commit raises and leaves the old content.
        target = self.tmp / "big.json"
        old = "O" * 400_000
        new = "N" * 400_000
        atomic_write_text(target, old)
        seen: set[int] = set()
        stop = threading.Event()

        def reader():
            while not stop.is_set():
                try:
                    seen.add(len(target.read_text(encoding="utf-8")))
                except OSError:
                    pass

        t = threading.Thread(target=reader, daemon=True)
        t.start()
        committed = refused = 0
        try:
            for _ in range(40):
                try:
                    atomic_write_text(target, new)
                    committed += 1
                except PermissionError:
                    refused += 1
        finally:
            stop.set()
            t.join(timeout=10)
        self.assertTrue(seen)
        self.assertTrue(seen <= {len(old), len(new)},
                        f"a partial file was observable: sizes {sorted(seen)}")
        self.assertGreaterEqual(committed + refused, 40)
        # every refusal left the previous content whole
        self.assertIn(len(target.read_text(encoding="utf-8")), {len(old), len(new)})

    def test_a_contended_commit_still_succeeds_with_a_polite_reader(self):
        # With a reader that pauses between reads -- how a real consumer
        # behaves -- the commit succeeds rather than being starved.
        target = self.tmp / "polite.json"
        atomic_write_text(target, "old")
        stop = threading.Event()

        def reader():
            while not stop.is_set():
                try:
                    target.read_text(encoding="utf-8")
                except OSError:
                    pass
                time.sleep(0.001)

        t = threading.Thread(target=reader, daemon=True)
        t.start()
        try:
            for _ in range(25):
                atomic_write_text(target, "new")
        finally:
            stop.set()
            t.join(timeout=10)
        self.assertEqual(target.read_text(), "new")


class TestRedactionCoversEveryCredentialKey(unittest.TestCase):
    """The persisted-redaction set must not be narrower than the ones used
    elsewhere in the Bridge, or a key scrubbed everywhere else is stored
    here."""

    def test_credential_shaped_keys_are_redacted(self):
        from memory import redact_persisted
        for key in ("api_key", "authorization", "private_key", "pairing_token",
                    "challenge", "password", "secret", "token", "key"):
            out = redact_persisted({key: "LEAKED-VALUE", "path": "a.txt"})
            self.assertNotIn("LEAKED-VALUE", str(out), key)
            self.assertEqual(out["path"], "a.txt", key)

    def test_runtime_and_transport_redaction_sets_are_covered(self):
        import memory
        for module, attr in (("runtime", "REDACT_KEYS"),
                             ("nodes.node_transport", "REDACT_KEYS")):
            mod = __import__(module, fromlist=[attr])
            other = getattr(mod, attr, None)
            if not other:
                continue
            missing = {str(k).lower() for k in other} - set(memory.REDACTED_KEYS)
            self.assertFalse(missing, f"{module}.{attr} not covered: {missing}")


if __name__ == "__main__":
    unittest.main()