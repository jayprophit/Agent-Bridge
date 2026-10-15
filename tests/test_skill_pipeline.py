"""Version skill acquisition pipeline tests (V2 H03, AT-23).

AT-23 acceptance: a worker contributes a skill candidate; provenance/tests/
security review precede release; Genesis invokes the approved skill alone;
rollback works.  Untrusted workers cannot self-install.
"""
from __future__ import annotations

import pytest

from compute.skill_pipeline import (
    PublishedSkill,
    SkillCandidate,
    SkillPipeline,
    SkillPipelineError,
    SkillStage,
)


# --- helpers ------------------------------------------------------------------

def _candidate(app_id="pytool", version="1.0.0",
               submitted_by="worker-test-1", source_hash=""):
    c = SkillCandidate(
        app_id=app_id, name=app_id, version=version,
        description="test skill", proposed_bridge_adapter="pytool_adapter.py",
        required_capabilities=("TEXT_PROCESSING",),
        required_os_deps=("python3",),
        required_model_capabilities=(),
        permissions_requested=(),
        source_url="https://example.com/pytool",
        license="MIT",
        source_hash=source_hash,
        submitted_by=submitted_by,
    )
    # If source_hash is empty, set it to the expected hash (pre-verified
    # candidate where the worker already computed the correct hash).
    if not c.source_hash:
        c.source_hash = c.expected_hash
    return c


def _tampered_candidate(**kw):
    """A candidate whose source_hash does NOT match its payload."""
    import copy
    c = _candidate(**kw)
    c.source_hash = "wronghash"
    return c


def _full_pipeline(pipeline, candidate):
    """Drive a candidate through ALL gates to published."""
    cid = candidate.candidate_id
    pipeline.provenance_review(cid, "reviewer-1", True, "license OK")
    pipeline.sandbox_tests(cid, "reviewer-1", True, "ran in isolation")
    pipeline.security_review(cid, "sec-1", True, granted_permissions=())
    pipeline.benchmark(cid, "reviewer-1", True, genesis_solo=True,
                        details="genesis ran benchmark alone")
    return pipeline.approve_and_publish(cid, approver="approver-1",
                                        genesis_solo=True)


# --- AT-23: candidate submission ------------------------------------------------

class TestAT23SkillPromotion:
    def test_worker_submits_candidate(self):
        """A worker can submit a skill candidate — it starts in PROPOSED."""
        p = SkillPipeline()
        c = _candidate()
        p.submit(c)
        assert c.candidate_id in p.all_candidates()
        # Candidate exists but is NOT in the production registry
        assert c.app_id not in [a.app_id for a in p.registry._apps.values()]

    def test_candidate_cannot_self_install(self):
        """Untrusted workers cannot reach the published/approved stage."""
        p = SkillPipeline()
        c = _candidate(submitted_by="worker-rando")
        p.submit(c)
        # Even after submitting, the worker cannot publish without passing gates
        with pytest.raises(SkillPipelineError, match="cannot publish"):
            p.approve_and_publish(c.candidate_id, approver="worker-rando")

    def test_duplicate_candidate_rejected(self):
        """Same app_id@version cannot be submitted twice."""
        p = SkillPipeline()
        c = _candidate()
        p.submit(c)
        with pytest.raises(SkillPipelineError, match="already submitted"):
            p.submit(c)


# --- AT-23: provenance ---------------------------------------------------------

class TestProvenanceReview:
    def test_provenance_pass_requires_license(self):
        p = SkillPipeline()
        c = _candidate()
        p.submit(c)
        # Remove license to simulate missing provenance
        c.license = ""
        # Provenance should reject because no license was declared
        with pytest.raises(SkillPipelineError, match="no license"):
            p.provenance_review(c.candidate_id, "r", True, "no license")

    def test_provenance_rejects_tampered_hash(self):
        p = SkillPipeline()
        c = _tampered_candidate()
        p.submit(c)
        p.provenance_review(c.candidate_id, "r", True, "license OK")
        p.sandbox_tests(c.candidate_id, "r", True, "ok")
        p.security_review(c.candidate_id, "s", True)
        p.benchmark(c.candidate_id, "r", True, genesis_solo=True)
        # publish should fail on hash mismatch
        with pytest.raises(SkillPipelineError, match="source_hash mismatch"):
            p.approve_and_publish(c.candidate_id, approver="r")

    def test_provenance_rejects_more_permissions_than_requested(self):
        """Security review cannot grant permissions the worker didn't ask for."""
        p = SkillPipeline()
        c = _candidate()
        p.submit(c)
        p.provenance_review(c.candidate_id, "r", True)
        p.sandbox_tests(c.candidate_id, "r", True)
        with pytest.raises(SkillPipelineError, match="beyond what was requested"):
            p.security_review(c.candidate_id, "s", True,
                             granted_permissions=("root_shell",))


# --- AT-23: full pipeline to publish -------------------------------------------

class TestPipelineToPublish:
    def test_full_pipeline_publishes_to_registry(self):
        """All gates passed -> skill appears in production registry."""
        p = SkillPipeline()
        c = _candidate()
        p.submit(c)
        pub = _full_pipeline(p, c)
        assert pub is not None
        assert pub.app_id == "pytool"
        # The skill should appear in published history and be active
        assert p.active_version("pytool").version == "1.0.0"

    def test_publish_requires_all_gates(self):
        """Cannot publish if any gate is missing."""
        p = SkillPipeline()
        c = _candidate()
        p.submit(c)
        # Only provenance done
        p.provenance_review(c.candidate_id, "r", True, "ok")
        with pytest.raises(SkillPipelineError, match="missing gates"):
            p.approve_and_publish(c.candidate_id, approver="r")

    def test_sandbox_failure_blocks(self):
        p = SkillPipeline()
        c = _candidate()
        p.submit(c)
        p.provenance_review(c.candidate_id, "r", True, "ok")
        with pytest.raises(SkillPipelineError, match="sandbox tests failed"):
            p.sandbox_tests(c.candidate_id, "r", False, "crashed")

    def test_security_failure_blocks(self):
        p = SkillPipeline()
        c = _candidate()
        p.submit(c)
        p.provenance_review(c.candidate_id, "r", True, "ok")
        p.sandbox_tests(c.candidate_id, "r", True, "ok")
        with pytest.raises(SkillPipelineError, match="security review rejected"):
            p.security_review(c.candidate_id, "s", False, "dangerous perms")

    def test_benchmark_failure_blocks(self):
        p = SkillPipeline()
        c = _candidate()
        p.submit(c)
        p.provenance_review(c.candidate_id, "r", True, "ok")
        p.sandbox_tests(c.candidate_id, "r", True, "ok")
        p.security_review(c.candidate_id, "s", True)
        with pytest.raises(SkillPipelineError, match="benchmark failed"):
            p.benchmark(c.candidate_id, "r", False, genesis_solo=False)


# --- AT-23: Genesis solo capability --------------------------------------------

class TestGenesisSolo:
    def test_published_skill_has_genesis_solo_flag(self):
        """The published record tracks whether Genesis can invoke it alone."""
        p = SkillPipeline()
        c = _candidate()
        p.submit(c)
        pub = _full_pipeline(p, c)
        assert pub.genesis_solo is True

    def test_candidate_without_provenance_blocked_from_publish(self):
        """A candidate that failed provenance cannot be published."""
        p = SkillPipeline()
        c = _candidate()
        p.submit(c)
        with pytest.raises(SkillPipelineError, match="provenance rejected"):
            p.provenance_review(c.candidate_id, "r", False, "no license")
        # Candidate never passed gates, so publish is blocked
        with pytest.raises(SkillPipelineError, match="missing gates"):
            p.approve_and_publish(c.candidate_id, approver="r")


# --- AT-23: rollback -----------------------------------------------------------

class TestRollback:
    def test_rollback_reverts_to_previous_version(self):
        """Rollback restores a prior version; old versions preserved."""
        p = SkillPipeline()
        # Version 1
        c1 = _candidate(version="1.0.0")
        p.submit(c1)
        pub1 = _full_pipeline(p, c1)
        assert p.active_version("pytool").version == "1.0.0"

        # Version 2 (supersedes 1)
        c2 = _candidate(version="2.0.0")
        p.submit(c2)
        pub2 = _full_pipeline(p, c2)
        assert p.active_version("pytool").version == "2.0.0"

        # Rollback to v1
        rolled = p.rollback("pytool", "1.0.0", actor="hermes")
        assert rolled.version == "1.0.0"
        assert p.active_version("pytool").version == "1.0.0"
        assert len(p.published_versions("pytool")) == 2

    def test_rollback_unknown_version_fails(self):
        p = SkillPipeline()
        c1 = _candidate(version="1.0.0")
        p.submit(c1)
        _full_pipeline(p, c1)
        with pytest.raises(SkillPipelineError, match="not found"):
            p.rollback("pytool", "9.9.9", "hermes")

    def test_rollback_with_no_history_fails(self):
        p = SkillPipeline()
        with pytest.raises(SkillPipelineError, match="no published versions"):
            p.rollback("nope", "1.0.0", "hermes")

    def test_published_versions_preserved_immortal(self):
        """Superseded versions are never erased — only marked superseded."""
        p = SkillPipeline()
        c1 = _candidate(version="1.0.0")
        p.submit(c1)
        _full_pipeline(p, c1)
        c2 = _candidate(version="2.0.0")
        p.submit(c2)
        _full_pipeline(p, c2)
        # Both versions exist in history
        versions = p.published_versions("pytool")
        assert len(versions) == 2
        assert versions[0].version == "1.0.0"
        assert versions[1].version == "2.0.0"
        # The superseded version has an audit event
        audit = p.audit_log_for("pytool@1.0.0")
        assert any(e.action == "superseded" for e in audit)


# --- audit / introspection ----------------------------------------------------

class TestAuditAndIntrospection:
    def test_audit_log_tracks_all_stages(self):
        p = SkillPipeline()
        c = _candidate()
        p.submit(c)
        _full_pipeline(p, c)
        actions = [e.action for e in p.audit_log_for(c.candidate_id)]
        assert "submitted" in actions
        assert "provenance_passed" in actions
        assert "sandbox_passed" in actions
        assert "security_passed" in actions
        assert "benchmark_passed" in actions
        assert "published" in actions

    def test_expected_hash_computed(self):
        c = _candidate()
        assert c.expected_hash != ""
        assert len(c.expected_hash) == 64  # sha256 hex

    def test_sign_hash_on_publish(self):
        """Published skills have a deterministic sign hash."""
        p = SkillPipeline()
        c = _candidate()
        p.submit(c)
        pub = _full_pipeline(p, c)
        assert pub.sign_hash != ""
        assert len(pub.sign_hash) == 64
        assert pub.source_hash == c.expected_hash
