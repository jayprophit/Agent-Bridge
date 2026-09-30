"""Mutation proof for the approved-action grant + approval channel.

A green test proves nothing unless breaking the mechanism turns it red.
Each mutation below is applied to a scratch copy of the repo, the target
test is run, and the copy is discarded. Repo files are never modified.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TARGETS = ["tests/test_external_approvals.py"]

# Directories that carry no importable source or fixtures for these tests.
# .opencode (52 MB) and local/ (35 MB) are archives; copying them would make
# each mutation copy take minutes for no gain.
SKIP_DIRS = shutil.ignore_patterns(
    ".git", "__pycache__", ".pytest_cache", "node_modules", ".opencode",
    "local", "reports", "ui", "*.pyc", "*.obj")

# (label, relative file, old snippet, new snippet, tests expected to fail)
MUTATIONS = [
    ("grant ignores glob characters",
     "aether_policy_bridge.py",
     'if not raw or any(ch in raw for ch in GLOB_RESOURCE_CHARS):',
     'if not raw:',
     ["test_glob_resources_are_never_granted",
      "test_a_glob_filename_would_not_become_a_workspace_grant"]),
    ("grant accepts absolute/namespaced references",
     "aether_policy_bridge.py",
     'if (raw.startswith("workspace:") or raw.startswith("/")\n'
     '            or (len(raw) > 1 and raw[1] == ":")):',
     'if False:',
     ["test_absolute_and_namespaced_references_are_refused"]),
    ("grant accepts workspace escapes",
     "aether_policy_bridge.py",
     'if not candidate.startswith(f"{ws}/"):\n        return ""',
     'if False:\n        return candidate',
     ["test_workspace_escape_is_never_granted"]),
    ("approval grant is never revoked (standing capability)",
     "bridge.py",
     "for res_ref in _issued:\n"
     "            revoke_approved_action_grant(session.session_id, ws_str, act_name,\n"
     "                                         res_ref)",
     "for res_ref in []:\n"
     "            revoke_approved_action_grant(session.session_id, ws_str, act_name,\n"
     "                                         res_ref)",
     ["test_approval_does_not_leave_a_standing_grant"]),
    ("executor stops gating the second resource of move/copy",
     "executor.py",
     'if act in ("move", "copy"):\n'
     '            out = []\n'
     '            for key in ("src", "dest"):\n'
     '                val = action.get(key)\n'
     '                if isinstance(val, str) and val:\n'
     '                    out.append(val)\n'
     '            return out or [""]',
     'if act in ("move", "copy"):\n'
     '            val = action.get("src")\n'
     '            return [val if isinstance(val, str) else ""]',
     ["test_executor_gates_every_touched_resource",
      "test_approved_move_cannot_carry_an_unchecked_destination"]),
    ("served sessions are always non-interactive (D1 returns)",
     "runtime.py",
     "            non_interactive=not interactive)",
     "            non_interactive=True)",
     ["test_ask_pauses_and_surfaces_pending_approval",
      "test_approve_executes_the_bounded_action",
      "test_deny_is_enforced_and_reported_as_no_effect"]),
    ("interactive sessions allowed without the owner switch",
     "runtime.py",
     'if interactive and not self.cfg.external_approvals:\n'
     '            raise PermissionError(',
     'if False:\n'
     '            raise PermissionError(',
     ["test_interactive_session_refused_when_channel_disabled"]),
    ("effect truth always claims success",
     "bridge.py",
     '        "effect_achieved": effect_achieved,',
     '        "effect_achieved": True,',
     ["test_deny_is_enforced_and_reported_as_no_effect"]),
]


class MutationSensitivity(unittest.TestCase):
    maxDiff = None

    def _run(self, cwd: Path) -> subprocess.CompletedProcess:
        # No -x: every failing test name must be visible, otherwise a mutation
        # that fails the wrong test would look like a caught mutation.
        return subprocess.run(
            [sys.executable, "-m", "pytest", *TARGETS, "-q", "--no-header",
             "-p", "no:cacheprovider"],
            cwd=str(cwd), capture_output=True, text=True, timeout=1800)

    def test_every_mutation_is_caught(self):
        failures: list[str] = []
        for label, rel, old, new, expect in MUTATIONS:
            with self.subTest(mutation=label):
                scratch = Path(tempfile.mkdtemp(prefix="mut_"))
                try:
                    repo = scratch / "repo"
                    shutil.copytree(REPO, repo, ignore=SKIP_DIRS)
                    target = repo / rel
                    text = target.read_text(encoding="utf-8")
                    self.assertIn(old, text, f"mutation anchor missing: {label}")
                    target.write_text(text.replace(old, new, 1),
                                      encoding="utf-8")
                    proc = self._run(repo)
                    out = proc.stdout + proc.stderr
                    if proc.returncode == 0:
                        failures.append(f"{label}: SUITE STILL GREEN")
                        continue
                    for name in expect:
                        if name not in out:
                            failures.append(
                                f"{label}: failed, but {name} was not the "
                                f"failing test")
                finally:
                    shutil.rmtree(scratch, ignore_errors=True)
        self.assertEqual(failures, [], "mutation proof incomplete:\n" +
                         "\n".join(failures))


if __name__ == "__main__":
    unittest.main()
