"""The workspace a path names must not depend on how it is spelled.

A label is bound to a workspace so that a label reused for a different
workspace is refused rather than silently rebound. On Windows the short
form of a path names the same directory as the long form, and a
temporary directory is routinely handed to a caller in one spelling and
recorded in the other. Comparing the strings said a label was bound to
a workspace it was actually bound to, and the caller got a conflict for
a path that never changed.

The same thing happened in the authorization, which said a workspace
was outside the root it was in.

This is the test that says so.
"""

import ctypes
import os
import tempfile
import unittest
from pathlib import Path

import runtime as runtime_module
import workspace_paths
from runtime import AgentRuntime, RuntimeConfig
from workspace_paths import canonical_workspace, same_workspace


def short_path(long: str) -> str:
    """The short form of a Windows path, when there is one."""
    if os.name != "nt":
        return long
    try:
        get_short = ctypes.windll.kernel32.GetShortPathNameW
        get_short.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p,
                              ctypes.DWORD]
        buffer = ctypes.create_unicode_buffer(1024)
        if get_short(long, buffer, 1024):
            return buffer.value
    except Exception:
        return long
    return long


class TestWorkspaceSpelling(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="label_ws_"))
        self.rt = AgentRuntime(RuntimeConfig(
            allowed_workspace_roots=[str(self.tmp)]))

    def test_two_spellings_of_one_path_are_one_path(self):
        """A relative component is another spelling of the same place."""
        canonical = str(self.tmp.resolve())
        alternate = str((self.tmp / ".." / self.tmp.name))
        self.assertNotEqual(canonical, alternate,
                            "the two spellings have to differ for this to "
                            "mean anything")
        self.assertTrue(same_workspace(canonical, alternate))

    def test_the_short_form_and_the_long_form_are_one_path(self):
        """On Windows the short form of a path names the same place."""
        long_form = str(self.tmp.resolve())
        short_form = short_path(long_form)
        if short_form == long_form:
            self.skipTest("this path has no short form")
        self.assertNotEqual(long_form, short_form)
        self.assertTrue(same_workspace(long_form, short_form),
                        "the short form and the long form are the same "
                        "directory and have to compare equal")

    def test_the_canonical_form_expands_the_short_form(self):
        long_form = str(self.tmp.resolve())
        short_form = short_path(long_form)
        if short_form == long_form:
            self.skipTest("this path has no short form")
        self.assertEqual(str(canonical_workspace(short_form)).lower(),
                         long_form.lower())

    def test_a_label_bound_to_one_spelling_resolves_under_another(self):
        """The label resolves rather than refusing."""
        session = self.rt.create_session(self.tmp)
        self.rt.bind_session_label("wf-9", session.session_id)
        alternate = str((self.tmp / ".." / self.tmp.name))
        resolved = self.rt.resolve_session_label("wf-9", alternate)
        self.assertEqual(resolved, session.session_id)

    def test_a_label_bound_to_a_different_workspace_is_still_refused(self):
        """The check is not weakened: a genuinely different path is refused."""
        other = Path(tempfile.mkdtemp(prefix="label_other_"))
        self.addCleanup(lambda: other.rmdir())
        session = self.rt.create_session(self.tmp)
        self.rt.bind_session_label("wf-9", session.session_id)
        with self.assertRaises(ValueError):
            self.rt.resolve_session_label("wf-9", str(other))

    def test_a_workspace_in_the_short_form_is_authorized(self):
        """The authorization does not refuse a root it is inside."""
        long_form = str(self.tmp.resolve())
        short_form = short_path(long_form)
        if short_form == long_form:
            self.skipTest("this path has no short form")
        workspace = self.tmp / "proj"
        workspace.mkdir()
        short_workspace = short_path(str(workspace.resolve()))
        allowed = self.rt.authorize_workspace(short_workspace)
        self.assertTrue(same_workspace(allowed, str(workspace.resolve())),
                        f"the authorization returned {allowed} for "
                        f"{short_workspace}")


if __name__ == "__main__":
    unittest.main()
