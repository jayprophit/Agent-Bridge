"""The session label must not treat two spellings of one path as two paths.

A label is bound to a workspace so that a label reused for a different
workspace is refused rather than silently rebound. On Windows the short
form of a path names the same directory as the long form, and a
temporary directory is routinely handed to a caller in one spelling and
recorded in the other. Comparing the strings said a label was bound to
a workspace it was actually bound to, and the caller got a conflict for
a path that never changed.

This is the test that says so.
"""

import tempfile
import unittest
from pathlib import Path

import runtime as runtime_module
from runtime import AgentRuntime, RuntimeConfig


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
        self.assertTrue(runtime_module._same_workspace(canonical, alternate))

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


if __name__ == "__main__":
    unittest.main()
