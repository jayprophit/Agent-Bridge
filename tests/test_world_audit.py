"""Full world-state audit tests (P21, REQ-p21-world-state-audit)."""
import unittest

from world_audit import (
    FAILED,
    INCONCLUSIVE,
    VERIFIED,
    ExpectedEffect,
    Observation,
    PolicyEvidence,
    ProhibitedEffect,
    UnchangedInvariant,
    WorldAuditError,
    audit_world,
    read_filesystem,
)


def obs(ref, observed=None, observed_hash="", evidence_ref=""):
    return Observation(object_ref=ref, observed=observed, observed_hash=observed_hash,
                       observed_at="2026-09-25T00:00:00", source="fixture", evidence_ref=evidence_ref)


class TestVerdicts(unittest.TestCase):
    def test_correct_object_correct_value_verifies(self):
        report = audit_world(
            "op-1",
            expected=[ExpectedEffect("cfg", expected="safe")],
            observations={"cfg": obs("cfg", "safe", evidence_ref="read-1")},
            policy=PolicyEvidence("pol-1", True, principal="genesis", capability="fs.write"),
            scope=["cfg"],
        )
        self.assertEqual(report.verdict, VERIFIED)
        self.assertEqual(report.scope_not_checked, [])
        self.assertEqual(report.unresolved, [])
        self.assertIn("read-1", report.evidence_refs)
        self.assertIn("policy:pol-1", report.evidence_refs)

    def test_wrong_value_fails(self):
        report = audit_world(
            "op-1",
            expected=[ExpectedEffect("cfg", expected="safe")],
            observations={"cfg": obs("cfg", "unsafe")},
        )
        self.assertEqual(report.verdict, FAILED)
        self.assertEqual(report.checks[0].reason, "value mismatch")

    def test_required_target_unchanged_fails(self):
        report = audit_world(
            "op-1",
            unchanged=[UnchangedInvariant("sibling", pre_state="B")],
            observations={"sibling": obs("sibling", "B-CHANGED")},
        )
        self.assertEqual(report.verdict, FAILED)
        self.assertIn("UNEXPECTED_CHANGE", report.checks[0].reason)

    def test_protected_unchanged_passes(self):
        report = audit_world(
            "op-1",
            expected=[ExpectedEffect("cfg", expected="safe")],
            unchanged=[UnchangedInvariant("sibling", pre_state="B")],
            observations={"cfg": obs("cfg", "safe"), "sibling": obs("sibling", "B")},
            policy=PolicyEvidence("pol-1", True),
        )
        self.assertEqual(report.verdict, VERIFIED)

    def test_prohibited_effects(self):
        created = audit_world(
            "op-1",
            prohibited=[ProhibitedEffect("newfile", "created")],
            observations={"newfile": obs("newfile", "oops")},
        )
        self.assertEqual(created.verdict, FAILED)
        absent = audit_world(
            "op-1",
            prohibited=[ProhibitedEffect("newfile", "created")],
            observations={"newfile": obs("newfile", None)},
            require_policy=False,
        )
        self.assertEqual(absent.verdict, VERIFIED)
        self.assertIn("(policy)", absent.unresolved)
        deleted = audit_world(
            "op-1",
            prohibited=[ProhibitedEffect("keepme", "deleted")],
            observations={"keepme": obs("keepme", None)},
        )
        self.assertEqual(deleted.verdict, FAILED)


class TestHonesty(unittest.TestCase):
    def test_missing_readback_is_inconclusive(self):
        report = audit_world("op-1", expected=[ExpectedEffect("cfg", expected="safe")])
        self.assertEqual(report.verdict, INCONCLUSIVE)
        self.assertEqual(report.unresolved, ["(policy)", "cfg"])

    def test_missing_policy_evidence_blocks_verified(self):
        report = audit_world(
            "op-1",
            expected=[ExpectedEffect("cfg", expected="safe")],
            observations={"cfg": obs("cfg", "safe")},
        )
        self.assertEqual(report.verdict, INCONCLUSIVE)
        self.assertIn("(policy)", report.unresolved)

    def test_explicit_denial_fails(self):
        report = audit_world(
            "op-1",
            expected=[ExpectedEffect("cfg", expected="safe")],
            observations={"cfg": obs("cfg", "safe")},
            policy=PolicyEvidence("pol-1", False),
        )
        self.assertEqual(report.verdict, FAILED)

    def test_claim_success_contradicted_by_readback(self):
        # Tool said ok; independent read says otherwise: read wins.
        report = audit_world(
            "op-1",
            expected=[ExpectedEffect("cfg", expected="safe")],
            observations={"cfg": obs("cfg", "corrupt")},
            policy=PolicyEvidence("pol-1", True),
        )
        self.assertEqual(report.verdict, FAILED)

    def test_partial_observation_not_falsely_verified(self):
        report = audit_world(
            "op-1",
            expected=[ExpectedEffect("a", expected=1), ExpectedEffect("b", expected=2)],
            observations={"a": obs("a", 1)},
            policy=PolicyEvidence("pol-1", True),
            scope=["a", "b", "c"],
        )
        self.assertEqual(report.verdict, INCONCLUSIVE)
        self.assertEqual(report.scope_checked, ["a", "b"])
        self.assertEqual(report.scope_not_checked, ["c"])

    def test_hash_mode_and_subset_mode(self):
        import hashlib
        digest = hashlib.sha256(b"v").hexdigest()
        hashed = audit_world(
            "op-1",
            expected=[ExpectedEffect("f", expected_hash=digest, comparison="hash")],
            observations={"f": obs("f", "v", digest)},
            policy=PolicyEvidence("pol-1", True),
        )
        self.assertEqual(hashed.verdict, VERIFIED)
        subset = audit_world(
            "op-1",
            expected=[ExpectedEffect("api", expected={"mode": "safe"}, comparison="subset")],
            observations={"api": obs("api", {"mode": "safe", "extra": 1})},
            policy=PolicyEvidence("pol-1", True),
        )
        self.assertEqual(subset.verdict, VERIFIED)

    def test_extra_changed_object_reported(self):
        report = audit_world(
            "op-1",
            expected=[ExpectedEffect("cfg", expected="safe")],
            unchanged=[UnchangedInvariant("sibling", pre_state="B")],
            observations={"cfg": obs("cfg", "safe"), "sibling": obs("sibling", "B!")},
            policy=PolicyEvidence("pol-1", True),
        )
        self.assertEqual(report.verdict, FAILED)
        kinds = {c.object_ref: c.verdict for c in report.checks}
        self.assertEqual(kinds["cfg"], VERIFIED)
        self.assertEqual(kinds["sibling"], FAILED)

    def test_deterministic_ordering(self):
        kwargs = {
            "expected": [ExpectedEffect("b", expected=1), ExpectedEffect("a", expected=1)],
            "observations": {"a": obs("a", 1), "b": obs("b", 1)},
            "policy": PolicyEvidence("pol-1", True),
        }
        first = audit_world("op", **kwargs).to_dict()
        second = audit_world("op", **kwargs).to_dict()
        self.assertEqual(first, second)
        self.assertEqual([c["object_ref"] for c in first["checks"] if c["object_ref"] != "(policy)"], ["a", "b"])


class TestValidation(unittest.TestCase):
    def test_malformed_inputs_rejected(self):
        with self.assertRaises(WorldAuditError):
            audit_world("  ")
        with self.assertRaises(WorldAuditError):
            audit_world("op", expected=[ExpectedEffect("", expected=1)])
        with self.assertRaises(WorldAuditError):
            audit_world("op", expected=[ExpectedEffect("a", comparison="vibes")])
        with self.assertRaises(WorldAuditError):
            audit_world("op", prohibited=[ProhibitedEffect("a", "teleported")])
        with self.assertRaises(WorldAuditError):
            audit_world("op", policy=PolicyEvidence("", True))

    def test_redaction_option_hashes_values(self):
        report = audit_world(
            "op-1",
            expected=[ExpectedEffect("cfg", expected="s3cret")],
            observations={"cfg": obs("cfg", "s3cret")},
            policy=PolicyEvidence("pol-1", True),
        )
        dumped = report.to_dict(hash_values=True)
        self.assertNotIn("s3cret", str(dumped))
        self.assertEqual(report.verdict, VERIFIED)


class TestFilesystemReader(unittest.TestCase):
    def test_reads_and_hashes_without_mutation(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "cfg.json"
            target.write_text('{"mode": "safe"}', encoding="utf-8")
            before = target.read_bytes()
            observation = read_filesystem(str(target))
            self.assertEqual(observation.observed, '{"mode": "safe"}')
            self.assertEqual(len(observation.observed_hash), 64)
            self.assertEqual(target.read_bytes(), before)
            report = audit_world(
                "op-1",
                expected=[ExpectedEffect(str(target), expected='{"mode": "safe"}')],
                observations={str(target): observation},
                policy=PolicyEvidence("pol-1", True),
            )
            self.assertEqual(report.verdict, VERIFIED)
            missing = read_filesystem(str(Path(tmp) / "ghost.txt"))
            self.assertIsNone(missing.observed)


if __name__ == "__main__":
    unittest.main()
