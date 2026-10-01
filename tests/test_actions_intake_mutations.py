"""Mutation proof for POST /v1/actions.

A green intake suite proves nothing unless breaking the guarantees turns it
red. Each mutation is applied to a scratch copy of the repository, the intake
tests are run there, and the copy is discarded. Repo files are never modified.
Only tests/test_actions_intake.py runs per mutation (fast); the full suite is
the commit gate, not the mutation gate.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TARGETS = ["tests/test_actions_intake.py", "tests/test_action_id_uniqueness.py"]

# Directories that carry no importable source or fixtures for these tests.
SKIP_DIRS = shutil.ignore_patterns(
    ".git", "__pycache__", ".pytest_cache", "node_modules", ".opencode",
    "local", "reports", "ui", "*.pyc", "*.obj")

# (label, relative file, old snippet, new snippet, tests expected to fail)
MUTATIONS = [
    ("intake bypasses protocol.validate_action",
     "actions.py",
     "    ok, validated = validate_action(action)\n"
     "    if not ok:\n"
     "        return None, f\"invalid action: {validated}\"\n"
     "    return validated, \"\"",
     "    return action, \"\"",
     # Verb allow-listing happens earlier and is untouched by this mutation;
     # what must fail here is field-level validation (missing content/old),
     # which lives ONLY in validate_action.
     ["test_missing_action_fields_are_400"]),
    ("intake stops refusing patterns and escapes",
     "actions.py",
     "def _refuse_pattern_or_escape(value: str, what: str) -> str:",
     "def _refuse_pattern_or_escape(value: str, what: str) -> str:\n"
     "    return \"\"  # MUTATED: the real checks below become dead code",
     ["test_globs_are_400",
      "test_escapes_and_absolute_refs_are_400",
      "test_move_to_outside_workspace_is_refused"]),
    ("intake grants owner elevation without authorization",
     "actions.py",
     "    if mode in (\"OWNER\", \"owner\", \"OWNER_FULL_ACCESS\"):\n"
     "        if not runtime.cfg.owner_authorized:\n"
     "            return False, (\"owner elevation refused: this runtime is not \"\n"
     "                           \"owner-authorized\")\n"
     "        return True, \"\"",
     "    if mode in (\"OWNER\", \"owner\", \"OWNER_FULL_ACCESS\"):\n"
     "        return True, \"\"",
     ["test_owner_mode_without_authorization_is_403"]),
    ("intake reports success for denied work",
     "actions.py",
     "        if denied and not effected:",
     "        if False:",
     ["test_deny_blocks_with_truth",
      "test_all_denied_is_blocked_not_success"]),
    ("intake silently drops interactivity",
     "actions.py",
     "                interactive=interactive)",
     "                interactive=False)",
     ["test_ask_pauses_for_a_resolvable_approval",
      "test_deny_blocks_with_truth",
      "test_all_denied_is_blocked_not_success",
      "test_cancelled_action_maps_cancelled"]),
    ("approval pauses never surface as WAITING_APPROVAL",
     "actions.py",
     "    if pending:\n"
     "        out = dict(base)\n"
     "        out.update({\"outcome\": \"WAITING_APPROVAL\", \"status\": rec.status,\n"
     "                    \"approval_id\": pending[0], \"approval_ids\": pending})\n"
     "        return out",
     "    if False:  # MUTATED: pauses fall through to terminal/timeout mapping\n"
     "        out = dict(base)\n"
     "        out.update({\"outcome\": \"WAITING_APPROVAL\", \"status\": rec.status,\n"
     "                    \"approval_id\": pending[0], \"approval_ids\": pending})\n"
     "        return out",
     ["test_ask_pauses_for_a_resolvable_approval",
      "test_deny_blocks_with_truth",
      "test_all_denied_is_blocked_not_success",
      "test_cancelled_action_maps_cancelled"]),
    ("action id collisions are silently aliased",
     "actions.py",
     "        if prior[\"fingerprint\"] != fingerprint:",
     "        if False:  # MUTATED: different actions share one id",
     ["test_same_id_different_action_is_409"]),
    ("payload path silently overrides the validated resource (D5)",
     "actions.py",
     "        conflict = _slot_conflict(payload, \"path\", resource)\n"
     "        if conflict:\n"
     "            return None, conflict",
     "        pass  # MUTATED: smuggled slot wins",
     ["test_payload_path_cannot_override_resource"]),
    ("action ids restart per task, aliasing cross-task effects (D4a)",
     "state.py",
     "        return (f\"a-{self.session_id}-{self.task_id}-\"\n"
     "                f\"{self.step}-{self._action_seq}\")",
     "        return (f\"a-{self.session_id}-\"  # MUTATED: task identity dropped\n"
     "                f\"{self.step}-{self._action_seq}\")",
     # Caught at the contract level. Notably the integration tests still pass
     # under this mutation because the fingerprint check (D4b) independently
     # preserves correctness: the two fixes are independent layers, and this
     # proves it.
     ["test_ids_differ_across_tasks"]),
    ("idempotency ignores the requested effect (D4b)",
     "executor.py",
     "        if action_id and action_id in self.completed and action.get(\"action\") in _MUT:\n"
     "            prior = dict(self.completed[action_id])\n"
     "            if prior.pop(\"_action_fingerprint\", None) == action_fingerprint(action):",
     "        if action_id and action_id in self.completed and action.get(\"action\") in _MUT:\n"
     "            prior = dict(self.completed[action_id])\n"
     "            if True:  # MUTATED: verb match alone suppresses execution",
     ["test_different_actions_same_id_both_execute"]),
]


class MutationSensitivity(unittest.TestCase):
    maxDiff = None

    def _run(self, cwd: Path) -> subprocess.CompletedProcess:
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
