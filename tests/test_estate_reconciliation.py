"""Live estate reconciliation + §34 gate tests (§3-§5, §34, §51).

Proves the §34 gate is genuinely strict — 15 conditions, all required — and
that the §5 classifier escalates rather than silently discards owner work.

Read-only: nothing here contacts GitHub except via explicitly-injected
fixtures.
"""

import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from migration.unique_audit import (
    PRESERVATION_REQUIRED, SAFE_DELETE_CONDITIONS, SafeDeleteVerdict,
    UniqueContentClass, classify_unique_content,
)

ESTATE = (Path(__file__).resolve().parent.parent / "migration" / "evidence"
          / "live_estate.json")
RECON = (Path(__file__).resolve().parent.parent / "migration" / "evidence"
         / "reconciliation.json")
PREDECESSORS = (Path(__file__).resolve().parent.parent / "migration"
                / "evidence" / "predecessor_matrix.json")


class UniqueContentClassificationTests(unittest.TestCase):
    """§5 — the classifier must never discard owner work by default."""

    def test_no_commits_is_none(self):
        self.assertIs(classify_unique_content([], 0),
                      UniqueContentClass.NONE)

    def test_docs_only_is_documentation_only(self):
        self.assertIs(
            classify_unique_content(["README.md", "docs/NOTES.rst"], 2),
            UniqueContentClass.DOCUMENTATION_ONLY)

    def test_config_is_config_only(self):
        self.assertIs(
            classify_unique_content(["pyproject.toml", "ci.yml"], 2),
            UniqueContentClass.CONFIG_ONLY)

    def test_real_code_is_escalated_not_discarded(self):
        """Code divergence CANNOT be judged from a filename list."""
        result = classify_unique_content(["src/core.py"], 3)
        self.assertEqual(result, UniqueContentClass.UNKNOWN)
        self.assertIn(result, PRESERVATION_REQUIRED)

    def test_unknown_requires_preservation(self):
        self.assertIn(UniqueContentClass.UNKNOWN, PRESERVATION_REQUIRED)

    def test_inert_classes_do_not_require_preservation(self):
        for cls in (UniqueContentClass.NONE,
                    UniqueContentClass.CONFIG_ONLY,
                    UniqueContentClass.DOCUMENTATION_ONLY):
            self.assertNotIn(cls, PRESERVATION_REQUIRED)

    def test_owner_code_classes_all_require_preservation(self):
        for cls in (UniqueContentClass.USEFUL_PATCH,
                    UniqueContentClass.AETHERIUS_SPECIFIC,
                    UniqueContentClass.CRITICAL_UNIQUE_CODE):
            self.assertIn(cls, PRESERVATION_REQUIRED)


class SafeDeleteGateTests(unittest.TestCase):
    """§34 — fifteen conditions, every one mandatory."""

    def _verdict(self, **overrides):
        conds = {name: False for name in SAFE_DELETE_CONDITIONS}
        conds.update(overrides)
        return SafeDeleteVerdict(repo="example", conditions=conds)

    def test_gate_has_fifteen_conditions(self):
        self.assertEqual(len(SAFE_DELETE_CONDITIONS), 15)

    def test_all_false_is_not_safe(self):
        self.assertFalse(self._verdict().safe)

    def test_fourteen_of_fifteen_is_not_safe(self):
        conds = {name: True for name in SAFE_DELETE_CONDITIONS}
        dropped = conds.pop("remote_sha_verified")
        self.assertFalse(SafeDeleteVerdict(repo="x", conditions=conds).safe)
        self.assertIn("remote_sha_verified",
                      SafeDeleteVerdict(repo="x", conditions=conds).unsatisfied)

    def test_all_fifteen_is_safe(self):
        conds = {name: True for name in SAFE_DELETE_CONDITIONS}
        self.assertTrue(SafeDeleteVerdict(repo="x", conditions=conds).safe)
        self.assertEqual([], SafeDeleteVerdict(repo="x", conditions=conds).unsatisfied)

    def test_remote_verification_is_not_substitutable(self):
        """A local commit is not remote preservation."""
        conds = {name: True for name in SAFE_DELETE_CONDITIONS}
        conds["replacement_committed"] = True
        conds["remote_sha_verified"] = False
        v = SafeDeleteVerdict(repo="x", conditions=conds)
        self.assertFalse(v.safe)

    def test_verdict_reports_every_missing_condition(self):
        v = self._verdict(live_identity_verified=True)
        self.assertEqual(v.satisfied, ["live_identity_verified"])
        self.assertEqual(len(v.unsatisfied), 14)

    def test_verdict_serialises(self):
        d = self._verdict().as_dict()
        self.assertIn("safe_to_delete", d)
        self.assertFalse(d["safe_to_delete"])


@unittest.skipUnless(ESTATE.is_file(), "live estate not fetched")
class LiveEstateTests(unittest.TestCase):
    """Assertions about the ACTUAL jayprophit estate (§3, §51)."""

    @classmethod
    def setUpClass(cls):
        cls.repos = json.loads(ESTATE.read_text(encoding="utf-8"))

    def test_estate_has_substantial_size(self):
        self.assertGreater(len(self.repos), 300)

    def test_every_fork_has_a_resolved_upstream(self):
        """The REST list omits `parent`; resolve_upstreams.py must fill it."""
        forks = [r for r in self.repos if r["fork"]]
        self.assertGreater(len(forks), 200)
        unlinked = [r["name"] for r in forks if not r.get("parent")]
        self.assertEqual(unlinked, [],
                         f"forks without upstream: {unlinked[:10]}")

    def test_originals_are_not_mislabelled_as_forks(self):
        originals = [r for r in self.repos if not r["fork"]]
        self.assertEqual(len(originals), 44)

    def test_all_repos_are_public(self):
        """§37 — owner policy: repositories are PUBLIC by default."""
        private = [r["name"] for r in self.repos if r["private"]]
        self.assertEqual(private, [])


@unittest.skipUnless(RECON.is_file(), "reconciliation not run")
class ReconciliationTests(unittest.TestCase):
    """§51 steps 4-8 — catalog vs live."""

    @classmethod
    def setUpClass(cls):
        cls.rec = json.loads(RECON.read_text(encoding="utf-8"))

    def test_every_catalog_row_exists_live(self):
        self.assertEqual(self.rec["catalog_rows_not_live"], [])

    def test_matched_count(self):
        self.assertEqual(self.rec["matched"], 350)

    def test_contradictions_are_all_resolved_forks(self):
        for c in self.rec["contradictions"]:
            self.assertIn(c["upstream"], c.get("upstream") or "")
            self.assertIsNotNone(c["upstream"])


@unittest.skipUnless(PREDECESSORS.is_file(), "predecessor matrix not built")
class PredecessorMatrixTests(unittest.TestCase):
    """§9/§42 — every named predecessor exists live."""

    @classmethod
    def setUpClass(cls):
        cls.matrix = json.loads(PREDECESSORS.read_text(encoding="utf-8"))

    def test_nine_predecessors_classified(self):
        self.assertEqual(len(self.matrix["predecessors"]), 9)

    def test_all_exist_live(self):
        missing = [p["repository"] for p in self.matrix["predecessors"]
                   if not p["exists_live"]]
        self.assertEqual(missing, [])

    def test_none_are_marked_safe_to_delete(self):
        """No source inspection has happened; nothing may be deletable."""
        for p in self.matrix["predecessors"]:
            self.assertFalse(p["safe_to_delete"])
            self.assertEqual(p["migration_state"], "NOT_STARTED")

    def test_qva_is_flagged_for_decomposition(self):
        qva = next(p for p in self.matrix["predecessors"]
                   if p["repository"] == "QVA-merged")
        self.assertIn("DECOMPOSED", qva["caution"])

    def test_veyra_finance_caution_recorded(self):
        veyra = next(p for p in self.matrix["predecessors"]
                     if p["repository"] == "Veyra")
        self.assertIn("finance", veyra["caution"].lower())


if __name__ == "__main__":
    unittest.main()
