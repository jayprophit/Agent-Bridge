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
TARGETS = ["tests/test_actions_intake.py", "tests/test_action_id_uniqueness.py",
           "tests/test_recovery_privacy.py", "tests/test_evidence_integrity.py",
           "tests/test_untrusted_input.py", "tests/test_cross_process_state.py"]

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
    ("denied content persists to disk unredacted",
     "memory.py",
     "            redacted = redact_persisted(self.data)\n"
     "            self.path.write_text(json.dumps(redacted, indent=2)[:300_000],",
     "            self.path.write_text(json.dumps(self.data, indent=2)[:300_000],",
     ["test_denied_content_boundary"]),
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
    ("recorded completions are replayed without checking the world",
     "executor.py",
     "                holds, reason = self._verify_effect(claim)\n"
     "                if not holds:",
     "                holds, reason = True, \"MUTATED: never re-checked\"\n"
     "                if not holds:",
     ["test_forged_success_for_an_unperformed_write_is_refused",
      "test_recorded_success_is_refused_when_the_world_disagrees",
      "test_checkable_record_still_fails_when_the_world_disagrees"]),
    ("unverifiable claims are treated as holding",
     "executor.py",
     "        if not isinstance(claim, dict):\n"
     "            return False, \"no checkable effect assertion\"",
     "        if not isinstance(claim, dict):\n"
     "            return True, \"MUTATED: an absent claim counts as proof\"",
     ["test_forged_delete_record_cannot_hide_a_surviving_file",
      "test_unverifiable_record_is_audited"]),
    ("recovery adopts records with no checkable effect",
     "bridge.py",
     "        if (isinstance(rec, dict)\n"
     "                and isinstance(rec.get(\"_effect\"), dict)\n"
     "                and isinstance(rec.get(\"_action_fingerprint\"), str)):\n"
     "            kept[aid] = rec\n"
     "        else:\n"
     "            dropped += 1",
     "        if isinstance(rec, dict):\n"
     "            kept[aid] = rec  # MUTATED: uncheckable records adopted\n"
     "        else:\n"
     "            dropped += 1",
     ["test_forged_success_without_a_checkable_effect_is_dropped"]),
    ("internal directories are protected only at the root",
     "executor.py",
     "    segs = [s for s in rel.replace(\"\\\\\", \"/\").split(\"/\") if s and s != \".\"]\n"
     "    return any(s.lower() in PROTECTED_PREFIXES for s in segs)",
     "    segs = [s for s in rel.replace(\"\\\\\", \"/\").split(\"/\") if s and s != \".\"]\n"
     "    return segs[0].lower() in PROTECTED_PREFIXES  # MUTATED: depth ignored",
     ["test_nested_internal_directory_is_protected"]),
    ("checkpoint labels are treated as paths",
     "checkpoints.py",
     "    if \"/\" in lbl or \"\\\\\" in lbl or lbl in (\".\", \"..\"):\n"
     "        raise ValueError(f\"checkpoint label must be a single name: {label!r}\")",
     "    if False:  # MUTATED: separators and traversal accepted\n"
     "        raise ValueError(f\"checkpoint label must be a single name: {label!r}\")",
     ["test_traversal_labels_are_rejected",
      "test_manager_cannot_be_pointed_outside_the_checkpoint_store"]),
    ("rollback trusts the backup path named by the manifest",
     "checkpoints.py",
     "            bp = (self.workspace / blob).resolve()\n"
     "            bp.relative_to(self.base.resolve())",
     "            bp = (self.workspace / blob).resolve()",
     ["test_manifest_cannot_retarget_a_backup_outside_the_store"]),
    ("credential-shaped keys persist unredacted",
     "memory.py",
     "    \"secret\", \"password\", \"token\", \"key\", \"api_key\", \"authorization\",\n"
     "    \"private_key\", \"pairing_token\", \"challenge\", \"credential\", \"credentials\",\n"
     "    \"response\",",
     "    \"content\",",
     ["test_credential_shaped_keys_are_redacted",
      "test_runtime_and_transport_redaction_sets_are_covered"]),
    ("state files are written in place",
     "executor.py",
     "    for attempt in range(attempts):\n"
     "        try:\n"
     "            os.replace(tmp, target)\n"
     "            return",
     "    for attempt in range(1):\n"
     "        try:\n"
     "            with open(target, \"w\", encoding=\"utf-8\") as f:  # MUTATED\n"
     "                f.write(Path(tmp).read_text(encoding=\"utf-8\"))\n"
     "            os.unlink(tmp)\n"
     "            return",
     ["test_a_write_that_cannot_commit_changes_nothing",
      "test_a_concurrent_reader_never_sees_a_partial_file"]),
    ("untrusted file bytes reach the model unfenced",
     "bridge.py",
     "        if isinstance(slim.get(k), str):\n"
     "            slim[k] = fence_untrusted(truncate_middle(slim[k], 2000)\n"
     "                                     if len(slim[k]) > 2000 else slim[k])",
     "        if isinstance(slim.get(k), str) and len(slim[k]) > 2000:\n"
     "            slim[k] = truncate_middle(slim[k], 2000)  # MUTATED: no fence",
     ["test_result_text_fences_content_stdout_and_stderr",
      "test_a_file_read_reaches_the_model_inside_the_envelope"]),
    ("the data envelope can be closed by its own payload",
     "bridge.py",
     "    body = text.replace(UNTRUSTED_END, UNTRUSTED_END.replace(\"<\", \"[\")[:16])\n"
     "    body = body.replace(UNTRUSTED_FENCE, UNTRUSTED_FENCE.replace(\"<\", \"[\")[:16])",
     "    body = text  # MUTATED: markers passed through intact",
     ["test_content_cannot_close_the_envelope_early",
      "test_content_cannot_open_a_fake_envelope"]),
    ("the idempotency store is overwritten instead of merged",
     "bridge.py",
     "    with WorkspaceLock(workspace, \"completed_actions\"):\n"
     "        try:\n"
     "            existing = json.loads(cpath.read_text(encoding=\"utf-8\"))\n"
     "            if not isinstance(existing, dict):\n"
     "                existing = {}\n"
     "        except (OSError, ValueError):\n"
     "            existing = {}\n"
     "        existing.update(executor.completed)\n"
     "        atomic_write_text(cpath, json.dumps(existing, default=str)[:500_000])",
     "    atomic_write_text(cpath,  # MUTATED: no lock, no merge\n"
     "                      json.dumps(executor.completed, default=str)[:500_000])",
     ["test_concurrent_writers_do_not_lose_each_others_records"]),
    ("the checkpoint manifest is overwritten instead of merged",
     "checkpoints.py",
     "        with WorkspaceLock(self.workspace, f\"checkpoint-{self.label}\"):\n"
     "            existing = self._load()\n"
     "            if isinstance(existing.get(\"files\"), dict):\n"
     "                for rel, entry in existing[\"files\"].items():\n"
     "                    man.setdefault(\"files\", {}).setdefault(rel, entry)\n"
     "            self.dir.mkdir(parents=True, exist_ok=True)",
     "        if True:  # MUTATED: no lock, no merge\n"
     "            self.dir.mkdir(parents=True, exist_ok=True)",
     ["test_concurrent_snapshots_keep_every_file",
      "test_every_surviving_backup_is_actually_restorable"]),
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
