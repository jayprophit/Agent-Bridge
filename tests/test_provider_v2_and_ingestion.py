"""Provider Adapter V2 + normalized error taxonomy + ingestion tests.

§2   capability advertising — unsupported must FAIL EXPLICITLY
§3   normalized error taxonomy — routing operates on classes, not vendor text
§6-§11 full-account ingestion — no hard-coded repo limit, incremental sync
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from compute.error_taxonomy import (
    ALL_ERROR_CLASSES,
    ERROR_TAXONOMY,
    AUTH_ERROR,
    POLICY_REFUSAL,
    PROVIDER_UNAVAILABLE,
    QUOTA_EXHAUSTED,
    RATE_LIMIT,
    SUPPORT_FULL,
    SUPPORT_NONE,
    TIMEOUT,
    UNKNOWN_PROVIDER_ERROR,
    NormalizedProviderError,
    ProviderCapabilities,
    UnsupportedCapabilityError,
    is_retryable,
    normalize_error,
    requires_owner,
    routing_action,
    should_failover,
)
from compute.provider_adapters import (
    BLOCKED_OWNER,
    DECLARED,
    ProviderAdapterRegistry,
    build_default_registry,
)
from knowledge_fabric.repo_ingestion import (
    ARCHIVED,
    ACTIVE_CANONICAL,
    FORK,
    PREDECESSOR,
    ChangeDetector,
    RepositoryKnowledgeRecord,
    classify_status,
    stable_repo_id,
    utc_now,
)


class NormalizedErrorTaxonomyTests(unittest.TestCase):
    """§3 — routing must operate on normalized classes."""

    def test_taxonomy_covers_every_s3_class(self):
        required = {
            "AUTHENTICATION_ERROR", "RATE_LIMITED", "QUOTA_EXHAUSTED",
            "TIMEOUT", "PROVIDER_INTERNAL", "MODEL_UNAVAILABLE",
            "INVALID_REQUEST", "CONTEXT_EXCEEDED", "SAFETY_REJECTION",
            "UNSUPPORTED_CAPABILITY", "BUDGET_EXCEEDED",
            "PRIVACY_VIOLATION", "UNKNOWN_PROVIDER_ERROR",
        }
        self.assertTrue(required.issubset(set(ALL_ERROR_CLASSES)),
                        f"missing: {required - set(ALL_ERROR_CLASSES)}")

    def test_s3_aliases_map_to_canonical_values(self):
        """§3 names must resolve to the SAME values §88 already defines."""
        self.assertEqual(AUTH_ERROR, "AUTHENTICATION_ERROR")
        self.assertEqual(RATE_LIMIT, "RATE_LIMITED")
        self.assertEqual(QUOTA_EXHAUSTED, "QUOTA_EXHAUSTED")
        self.assertEqual(POLICY_REFUSAL, "SAFETY_REJECTION")
        self.assertEqual(TIMEOUT, "TIMEOUT")

    def test_vendor_text_normalizes_identically(self):
        """Two vendors, same condition, one class (§3)."""
        for raw in ("429 Too Many Requests", "rate_limit_exceeded",
                    "RATE LIMIT hit", "too many requests"):
            self.assertEqual(normalize_error(raw), RATE_LIMIT, raw)

    def test_openai_and_anthropic_auth_phrasings_agree(self):
        self.assertEqual(normalize_error("Unauthorized"), AUTH_ERROR)
        self.assertEqual(normalize_error("invalid api key"), AUTH_ERROR)
        self.assertEqual(normalize_error("401"), AUTH_ERROR)

    def test_already_normalized_input_is_idempotent(self):
        for cls in ALL_ERROR_CLASSES:
            self.assertEqual(normalize_error(cls), cls)

    def test_unrecognised_becomes_unknown_not_guess(self):
        self.assertEqual(normalize_error("wat"), UNKNOWN_PROVIDER_ERROR)
        self.assertEqual(normalize_error(""), UNKNOWN_PROVIDER_ERROR)
        self.assertEqual(normalize_error(None), UNKNOWN_PROVIDER_ERROR)

    def test_auth_is_never_retried(self):
        self.assertFalse(is_retryable(AUTH_ERROR))

    def test_rate_limit_is_retried(self):
        self.assertTrue(is_retryable(RATE_LIMIT))

    def test_budget_block_does_not_fail_over(self):
        """Moving a blocked request to a paid provider violates the block."""
        self.assertFalse(should_failover("BUDGET_EXCEEDED"))
        self.assertFalse(should_failover("PRIVACY_VIOLATION"))

    def test_privacy_block_does_not_fail_over(self):
        self.assertFalse(should_failover("PRIVACY_VIOLATION"))

    def test_provider_outage_does_fail_over(self):
        self.assertTrue(should_failover(PROVIDER_UNAVAILABLE))

    def test_credential_errors_escalate_to_owner(self):
        self.assertTrue(requires_owner(AUTH_ERROR))
        self.assertEqual(routing_action(AUTH_ERROR), "ESCALATE_OWNER")

    def test_budget_block_escalates_not_reroutes(self):
        self.assertEqual(routing_action("BUDGET_EXCEEDED"), "ESCALATE_OWNER")

    def test_unsupported_capability_stops(self):
        self.assertEqual(routing_action("UNSUPPORTED_CAPABILITY"), "STOP")

    def test_error_carries_normalized_class(self):
        err = NormalizedProviderError("rate limit exceeded", "slow down",
                                      provider_id="test")
        self.assertEqual(err.error_class, RATE_LIMIT)
        self.assertTrue(err.retryable)
        self.assertTrue(err.failover_eligible)
        self.assertEqual(err.action, "RETRY")

    def test_taxonomy_is_a_superset_not_a_replacement(self):
        """§2 — existing §88 callers must keep working."""
        from models.inference_contract import ERROR_CLASSES
        self.assertTrue(set(ERROR_CLASSES).issubset(set(ALL_ERROR_CLASSES)))


class CapabilityAdvertisingTests(unittest.TestCase):
    """§2 — unsupported capability must fail or downgrade EXPLICITLY."""

    def _caps(self, supports, degraded=frozenset()):
        return ProviderCapabilities(provider_id="p", supports=supports,
                                    degraded=degraded)

    def test_unsupported_raises_rather_than_silently_ignoring(self):
        caps = self._caps(frozenset({"streaming"}))
        with self.assertRaises(UnsupportedCapabilityError):
            caps.check("vision")

    def test_supported_returns_full(self):
        caps = self._caps(frozenset({"vision"}))
        self.assertEqual(caps.check("vision"), SUPPORT_FULL)

    def test_degraded_is_reported_as_degraded(self):
        caps = self._caps(frozenset({"streaming"}),
                          degraded=frozenset({"prompt_caching"}))
        self.assertEqual(caps.support_level("prompt_caching"), "degraded")

    def test_unsupported_listed_explicitly(self):
        caps = self._caps(frozenset({"streaming"}))
        self.assertIn("vision", caps.as_dict()["unsupported"])

    def test_registry_finds_providers_for_capability(self):
        reg = build_default_registry()
        found = {a.provider_id for a in reg.find_for_capability("streaming")}
        self.assertIn("ollama-local", found)
        self.assertIn("openrouter", found)

    def test_full_only_excludes_degraded(self):
        reg = build_default_registry()
        full = {a.provider_id for a in reg.find_for_capability("prompt_caching")}
        degraded = {a.provider_id for a in reg.find_for_capability(
            "prompt_caching", full_only=False)}
        self.assertNotIn("ollama-local", full)
        self.assertIn("ollama-local", degraded)

    def test_duplicate_registration_rejected(self):
        reg = ProviderAdapterRegistry()
        from compute.provider_adapters import ProviderAdapter
        adapter = ProviderAdapter(
            provider_id="dup", display_name="Dup",
            capabilities=self._caps(frozenset()))
        reg.register(adapter)
        with self.assertRaises(ValueError):
            reg.register(adapter)

    def test_resolve_unknown_provider_raises(self):
        reg = build_default_registry()
        with self.assertRaises(KeyError):
            reg.resolve("nope", "streaming")

    def test_resolve_unsupported_capability_raises(self):
        reg = build_default_registry()
        with self.assertRaises(UnsupportedCapabilityError):
            reg.resolve("llama-cpp-local", "vision")

    def test_cloud_providers_are_blocked_owner(self):
        """§21 — exposed credentials must stay unusable until rotation."""
        reg = build_default_registry()
        for pid in ("openrouter", "groq", "gemini", "huggingface", "deepseek"):
            self.assertEqual(reg.get(pid).probe_state, BLOCKED_OWNER, pid)

    def test_no_provider_claims_verified_live(self):
        """§15 — do not mark LIVE without a real authorized read."""
        reg = build_default_registry()
        for adapter in reg.summary()["providers"].values():
            self.assertIn(adapter["probe_state"],
                          (DECLARED, "verified_local", BLOCKED_OWNER))

    def test_local_providers_need_no_credentials(self):
        reg = build_default_registry()
        self.assertFalse(reg.get("ollama-local").requires_credentials)
        self.assertFalse(reg.get("llama-cpp-local").requires_credentials)


class StableRepoIdTests(unittest.TestCase):
    """§6 — stable IDs that survive reordering."""

    def test_id_is_deterministic(self):
        a = stable_repo_id("jayprophit", "Agent-Bridge")
        b = stable_repo_id("jayprophit", "Agent-Bridge")
        self.assertEqual(a, b)

    def test_id_is_case_insensitive_on_owner(self):
        self.assertEqual(stable_repo_id("JayProphit", "x"),
                         stable_repo_id("jayprophit", "x"))

    def test_distinct_repos_get_distinct_ids(self):
        self.assertNotEqual(stable_repo_id("jayprophit", "a"),
                            stable_repo_id("jayprophit", "b"))


class ChangeDetectorTests(unittest.TestCase):
    """§11 — skip unchanged, inspect only what moved."""

    def _rec(self, name="r", sha="a" * 40, updated="2026-01-01T00:00:00Z"):
        rec = RepositoryKnowledgeRecord(
            repo_id=stable_repo_id("jayprophit", name), name=name,
            owner="jayprophit", url="u", head_sha=sha, updated_at=updated)
        return rec.finalize()

    def test_new_record_is_new(self):
        d = ChangeDetector()
        action, _ = d.evaluate(self._rec("fresh"))
        self.assertEqual(action, "NEW")

    def test_identical_record_is_unchanged(self):
        d = ChangeDetector()
        rec = self._rec()
        d.known[rec.repo_id] = rec
        action, _ = d.evaluate(self._rec())
        self.assertEqual(action, "UNCHANGED")

    def test_head_sha_change_detected(self):
        d = ChangeDetector()
        rec = self._rec()
        d.known[rec.repo_id] = rec
        action, reason = d.evaluate(self._rec(sha="b" * 40))
        self.assertEqual(action, "CHANGED")
        self.assertIn("head", reason)

    def test_metadata_change_detected(self):
        d = ChangeDetector()
        rec = self._rec()
        d.known[rec.repo_id] = rec
        changed = self._rec()
        changed.license = "MIT"
        changed.metadata_hash = ""
        from knowledge_fabric.repo_ingestion import metadata_hash
        from dataclasses import asdict
        changed.metadata_hash = metadata_hash(asdict(changed))
        action, _ = d.evaluate(changed)
        self.assertEqual(action, "CHANGED")

    def test_none_sha_does_not_falsely_report_change(self):
        """Estate has no SHA; None == None must be UNCHANGED, not CHANGED."""
        d = ChangeDetector()
        rec = self._rec(sha=None)
        d.known[rec.repo_id] = rec
        action, _ = d.evaluate(self._rec(sha=None))
        self.assertEqual(action, "UNCHANGED")


class ClassificationTests(unittest.TestCase):
    """§7 lifecycle classification."""

    def test_archived_wins(self):
        self.assertEqual(
            classify_status({"archived": True, "fork": True},
                            is_canonical=True), ARCHIVED)

    def test_canonical_next(self):
        self.assertEqual(
            classify_status({"fork": False}, is_canonical=True),
            ACTIVE_CANONICAL)

    def test_predecessor_classified(self):
        self.assertEqual(
            classify_status({"fork": False}, is_predecessor=True), PREDECESSOR)

    def test_fork_classified(self):
        self.assertEqual(classify_status({"fork": True}), FORK)


class EstateIngestionTests(unittest.TestCase):
    """§6/§7 — the FULL estate, not a 17-repo sample."""

    @classmethod
    def setUpClass(cls):
        p = (Path(__file__).resolve().parent.parent / "knowledge_fabric"
             / "evidence" / "repo_knowledge_state.json")
        cls.state = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None

    def test_estate_state_exists(self):
        self.assertIsNotNone(self.state, "run scripts/ingest_repo_knowledge.py")

    def test_no_hardcoded_repo_limit(self):
        """§6 — do not hard-code a 17-repository limit."""
        src = (Path(__file__).resolve().parent.parent / "knowledge_fabric"
               / "repo_ingestion.py").read_text(encoding="utf-8")
        self.assertNotIn("= 17", src)
        self.assertNotIn("limit=17", src)

    def test_full_estate_ingested(self):
        if self.state is None:
            self.skipTest("ingestion not run")
        # The owner's estate is ~396 repositories, not 17.
        self.assertGreaterEqual(self.state["count"], 350)

    def test_fork_edges_created(self):
        if self.state is None:
            self.skipTest("ingestion not run")
        graph = (Path(__file__).resolve().parent.parent / "knowledge_fabric"
                 / "evidence" / "repo_relationship_graph.json")
        if not graph.is_file():
            self.skipTest("graph not built")
        g = json.loads(graph.read_text(encoding="utf-8"))
        self.assertGreaterEqual(g["edge_counts"]["FORK_OF"], 350)

    def test_predecessor_edges_created(self):
        graph = (Path(__file__).resolve().parent.parent / "knowledge_fabric"
                 / "evidence" / "repo_relationship_graph.json")
        if not graph.is_file():
            self.skipTest("graph not built")
        g = json.loads(graph.read_text(encoding="utf-8"))
        self.assertEqual(g["edge_counts"]["PREDECESSOR_OF"], 9)


if __name__ == "__main__":
    unittest.main()
