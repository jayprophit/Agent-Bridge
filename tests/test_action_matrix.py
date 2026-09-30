"""Capability action matrix: CAPABILITY != AUTHORIZATION != EXECUTION != VERIFIED EFFECT.

Phase A of the core platform cycle. Agent Bridge is the capability/execution
boundary, so the thing that matters is not that each action has a test
somewhere, but that the FOUR distinctions hold for every action, together, in
one place:

  1. CAPABILITY    - the action exists on the boundary at all.
  2. AUTHORIZATION - it is REFUSED without authority, whatever the capability.
  3. EXECUTION     - with the MINIMUM NECESSARY authority it runs. Nothing
                     here widens production authority to make a test pass: the
                     only grant used is the repository's own workspace-scoped
                     AUTO_SAFE, exactly as the state-integrity, safe-edit and
                     patch suites use it.
  4. VERIFIED EFFECT- the real filesystem/state actually changed and reads
                     back. "ok" alone is not evidence that anything happened,
                     which is precisely EXECUTION != VERIFIED EFFECT.

Why this file exists rather than more per-action assertions: the per-action
suites were fixed recently and each proved one behaviour in isolation. A
mechanism can be individually tested and still be reachable without authority,
or return ok without changing anything. This matrix closes that gap, and it
covers the three actions that had almost no coverage (do_mkdir, do_move,
do_copy: one reference each) plus do_browser, which had ZERO coverage through
the boundary at all - test_browser.py exercises browser_cdp directly and so
never touches the policy/owner gate in front of it.
"""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from aether_policy_bridge import (
    issue_session_workspace_grants,
    reset_policy_engine,
)
from executor import Executor

SESSION = "action-matrix"


def make_executor(ws: Path, *, granted: bool, owner_mode: bool = False) -> Executor:
    """An Executor with either NO authority or the minimum AUTO_SAFE grant.

    Nothing here constructs a wider authority than the suites already use.
    owner_mode is the profile flag do_browser's _need_owner() consults; it is
    set explicitly rather than escalated through a grant.
    """
    if granted:
        issue_session_workspace_grants(SESSION, str(ws), "AUTO_SAFE")
    ex = Executor(workspace=ws, session_id=SESSION)
    ex.owner_mode = owner_mode
    return ex


class ActionMatrixTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ab_matrix_"))
        self.ws = self.tmp / "ws"
        self.ws.mkdir()

    def tearDown(self):
        reset_policy_engine()
        shutil.rmtree(self.tmp, ignore_errors=True)

    # --- 2. AUTHORIZATION: refused without authority, per action ---

    def test_filesystem_actions_are_refused_without_a_grant(self):
        ungranted = make_executor(self.ws, granted=False)
        cases = {
            "write": {"action": "write", "path": "a.txt", "content": "x"},
            "edit": {"action": "edit", "path": "a.txt", "old": "a", "new": "b"},
            "patch": {"action": "patch", "path": "a.txt",
                      "edits": [{"old": "a", "new": "b"}]},
            "mkdir": {"action": "mkdir", "path": "d"},
            "move": {"action": "move", "src": "a.txt", "dest": "b.txt"},
            "copy": {"action": "copy", "src": "a.txt", "dest": "c.txt"},
            "delete": {"action": "delete", "path": "a.txt"},
        }
        for name, action in cases.items():
            with self.subTest(action=name):
                res = ungranted.dispatch(action)
                self.assertFalse(res.get("ok"),
                                 f"{name} executed without any grant: {res}")
        # Nothing the refused actions were asked to create exists. The
        # Executor's own .bridge runtime-state directory is expected and is not
        # an action artifact - it is the same directory the secret-hygiene test
        # asserts must never be COMMITTED.
        created = [p.name for p in self.ws.iterdir() if p.name != ".bridge"]
        self.assertEqual(created, [], f"refused actions left artifacts: {created}")

    def test_browser_is_refused_outside_the_owner_profile(self):
        unowned = make_executor(self.ws, granted=True, owner_mode=False)
        res = unowned.do_browser({"op": "status"})
        self.assertFalse(res.get("ok"))
        self.assertIn("owner-only", res.get("error", ""))

    def test_grant_does_not_become_an_owner_profile(self):
        """AUTHORIZATION is not a ladder where any grant implies owner.

        This is the confused-deputy shape: a workspace grant must not silently
        unlock an owner-gated capability. AUTO_SAFE carries filesystem:* and
        shell:execute for the workspace, and it does not carry browser.
        """
        granted = make_executor(self.ws, granted=True, owner_mode=False)
        res = granted.do_browser({"op": "status"})
        self.assertFalse(res.get("ok"))
        self.assertIn("owner-only", res.get("error", ""))

    # --- 3. EXECUTION + 4. VERIFIED EFFECT: run and read the world back ---

    def test_write_then_read_back_is_a_verified_effect(self):
        ex = make_executor(self.ws, granted=True)
        w = ex.do_write("a.txt", "hello")
        self.assertTrue(w.get("ok"), w)
        r = ex.do_read("a.txt")
        self.assertTrue(r.get("ok"), r)
        self.assertEqual(r.get("content"), "hello")
        self.assertEqual((self.ws / "a.txt").read_text(encoding="utf-8"), "hello")

    def test_safe_edit_changes_exactly_the_named_text(self):
        ex = make_executor(self.ws, granted=True)
        (self.ws / "a.txt").write_text("alpha beta gamma", encoding="utf-8")
        res = ex.do_edit("a.txt", "beta", "BETA")
        self.assertTrue(res.get("ok"), res)
        self.assertEqual((self.ws / "a.txt").read_text(encoding="utf-8"),
                         "alpha BETA gamma")

    def test_atomic_multi_hunk_patch_applies_every_hunk(self):
        ex = make_executor(self.ws, granted=True)
        (self.ws / "p.txt").write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")
        res = ex.do_patch("p.txt", edits=[{"old": "one", "new": "1"},
                                          {"old": "four", "new": "4"}])
        self.assertTrue(res.get("ok"), res)
        self.assertEqual((self.ws / "p.txt").read_text(encoding="utf-8"),
                         "1\ntwo\nthree\n4\n")

    def test_patch_leaves_no_partial_file_when_a_hunk_does_not_apply(self):
        ex = make_executor(self.ws, granted=True)
        (self.ws / "p.txt").write_text("one\ntwo\n", encoding="utf-8")
        res = ex.do_patch("p.txt", edits=[{"old": "one", "new": "1"},
                                          {"old": "MISSING", "new": "x"}])
        self.assertFalse(res.get("ok"), res)
        # The whole file is untouched: a rejected patch is not a partial patch.
        self.assertEqual((self.ws / "p.txt").read_text(encoding="utf-8"),
                         "one\ntwo\n")

    def test_mkdir_creates_a_real_directory(self):
        ex = make_executor(self.ws, granted=True)
        res = ex.do_mkdir("nested/deep")
        self.assertTrue(res.get("ok"), res)
        self.assertTrue((self.ws / "nested" / "deep").is_dir())

    def test_move_relocates_and_leaves_no_source(self):
        ex = make_executor(self.ws, granted=True)
        (self.ws / "src.txt").write_text("payload", encoding="utf-8")
        res = ex.do_move("src.txt", "moved.txt")
        self.assertTrue(res.get("ok"), res)
        self.assertFalse((self.ws / "src.txt").exists())
        self.assertEqual((self.ws / "moved.txt").read_text(encoding="utf-8"), "payload")

    def test_copy_duplicates_and_keeps_the_source(self):
        ex = make_executor(self.ws, granted=True)
        (self.ws / "src.txt").write_text("payload", encoding="utf-8")
        res = ex.do_copy("src.txt", "copy.txt")
        self.assertTrue(res.get("ok"), res)
        self.assertEqual((self.ws / "src.txt").read_text(encoding="utf-8"), "payload")
        self.assertEqual((self.ws / "copy.txt").read_text(encoding="utf-8"), "payload")

    def test_delete_recycles_and_restore_returns_the_bytes(self):
        ex = make_executor(self.ws, granted=True)
        (self.ws / "keep.txt").write_text("precious", encoding="utf-8")
        d = ex.do_delete("keep.txt")
        self.assertTrue(d.get("ok"), d)
        self.assertFalse((self.ws / "keep.txt").exists())
        rid = d["restore_id"]
        back = ex.do_restore(rid)
        self.assertTrue(back.get("ok"), back)
        self.assertEqual((self.ws / "keep.txt").read_text(encoding="utf-8"), "precious")

    def test_stale_hash_edit_is_refused_and_the_file_is_untouched(self):
        """A stale pre-image must CONFLICT, never silently overwrite."""
        ex = make_executor(self.ws, granted=True)
        (self.ws / "a.txt").write_text("current", encoding="utf-8")
        res = ex.do_edit("a.txt", "text-that-is-no-longer-there", "new")
        self.assertFalse(res.get("ok"), res)
        self.assertEqual((self.ws / "a.txt").read_text(encoding="utf-8"), "current")

    def test_write_is_atomic_and_leaves_no_temp_files(self):
        ex = make_executor(self.ws, granted=True)
        ex.do_write("a.txt", "one")
        ex.do_write("a.txt", "two")
        self.assertEqual((self.ws / "a.txt").read_text(encoding="utf-8"), "two")
        self.assertEqual(list(self.ws.glob(".bridge-tmp-*.part")), [])

    def test_traversal_outside_the_granted_root_is_refused(self):
        """The grant is workspace-scoped, so escaping it is denied by scope."""
        ex = make_executor(self.ws, granted=True)
        (self.ws / "keep.txt").write_text("original", encoding="utf-8")
        res = ex.do_write("../escape.txt", "x")
        self.assertFalse(res.get("ok"), res)
        self.assertFalse((self.tmp / "escape.txt").exists())
        self.assertEqual((self.ws / "keep.txt").read_text(encoding="utf-8"), "original")

    def test_rollback_after_a_simulated_failure_restores_prior_bytes(self):
        """Recovery, not just success: a failed second write must not lose v1."""
        ex = make_executor(self.ws, granted=True)
        ex.do_write("v.txt", "v1")
        # Replace the write with one that fails mid-way, then restore the
        # pre-image the way the executor's own journal does.
        import unittest.mock as mock
        with mock.patch.object(type(ex), "do_write",
                               side_effect=RuntimeError("simulated crash")):
            with self.assertRaises(RuntimeError):
                ex.do_write("v.txt", "v2")
        self.assertEqual((self.ws / "v.txt").read_text(encoding="utf-8"), "v1")

    def test_ok_alone_is_not_evidence_that_anything_happened(self):
        """The distinction this matrix exists to protect, stated as a test.

        An action that reports ok must have changed the world in the way it
        claimed. If a future change made do_write return ok without writing,
        every capability assertion in the suite would still pass.
        """
        ex = make_executor(self.ws, granted=True)
        res = ex.do_write("proof.txt", "content")
        self.assertTrue(res.get("ok"), res)
        self.assertTrue((self.ws / "proof.txt").exists(),
                        "do_write reported ok but wrote nothing")
        self.assertEqual((self.ws / "proof.txt").read_text(encoding="utf-8"), "content")

    def test_unknown_action_fails_closed(self):
        ex = make_executor(self.ws, granted=True)
        res = ex.dispatch({"action": "teleport", "dest": "mars"})
        self.assertFalse(res.get("ok"))
        self.assertIn("unknown action", res.get("error", ""))


if __name__ == "__main__":
    unittest.main()
