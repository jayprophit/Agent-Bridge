"""H10 trust/incident + H11 model asset lifecycle tests (AT-31, AT-32)."""
from __future__ import annotations

import pytest

from compute.trust_incident import (
    Attestation,
    IncidentPhase,
    IncidentResponse,
    InputSource,
    SecurityIncident,
    TrustBoundary,
    TrustLevel,
    compute_content_hash,
)
from compute.model_assets import (
    FineTuningGate,
    ModelAsset,
    ModelAssetRegistry,
    ModelAssetState,
    ModelCapability,
)


# --- H10: trust boundary tests (§1, §2) ------------------------------------------

class TestTrustBoundary:
    def test_default_is_untrusted(self):
        """§1: agent messages, model replies, web pages are UNTRUSTED."""
        boundary = TrustBoundary()
        assert boundary.check_trust("anything", "agent") == TrustLevel.UNTRUSTED

    def test_attested_content_is_verified(self):
        """§1: attested content is VERIFIED."""
        boundary = TrustBoundary()
        content = "This is verified content."
        boundary.attest(content, "hermes-supervisor")
        assert boundary.check_trust(content, "hermes-supervisor") == TrustLevel.VERIFIED

    def test_untrusted_cannot_perform_consequential_actions(self):
        """§2: untrusted source cannot modify instructions, grants, etc."""
        boundary = TrustBoundary()
        result = boundary.gate_action(
            "modify_system_instructions", TrustLevel.UNTRUSTED,
            target="supervisor_invariants.py")
        assert result["allowed"] is False
        assert "untrusted" in result["reason"]

    def test_verified_can_perform_actions(self):
        boundary = TrustBoundary()
        result = boundary.gate_action(
            "update_task", TrustLevel.VERIFIED, target="task-1")
        assert result["allowed"] is True

    def test_blocked_actions_logged(self):
        """§2: blocked untrusted actions are logged for audit."""
        boundary = TrustBoundary()
        boundary.gate_action("create_paid_resource", TrustLevel.UNTRUSTED)
        boundary.gate_action("enable_unsafe_tool", TrustLevel.QUARANTINED)
        blocked = boundary.blocked_actions()
        assert len(blocked) == 2

    def test_quarantine(self):
        """§3: suspicious content is quarantined."""
        boundary = TrustBoundary()
        entry = boundary.quarantine("rm -rf /", "suspicious command")
        assert entry["content_hash"]
        assert "suspicious" in entry["reason"]
        # Quarantined content is detectable
        assert boundary.check_trust("rm -rf /", "") == TrustLevel.QUARANTINED

    def test_content_hash_deterministic(self):
        h1 = compute_content_hash("test content")
        h2 = compute_content_hash("test content")
        assert h1 == h2
        assert len(h1) == 64  # sha256


# --- H10: incident response tests (§3) ----------------------------------------------

class TestIncidentResponse:
    def _full_incident(self):
        """Run through all incident phases (§3)."""
        response = IncidentResponse()
        response.open_incident(
            "INC-001", "Compromised worker credential",
            severity="critical",
            affected_workers=["opencode-01"],
            secrets_to_rotate=["groq/aetherius-dev"])
        response.freeze_work("INC-001", ["opencode-01"])
        response.quarantine_artifacts("INC-001", ["suspicious_output.txt"])
        response.revoke_scopes("INC-001", ["coding", "terminal"])
        response.inspect_provenance("INC-001", "worker-01 sent to unapproved endpoint")
        response.notify_owner("INC-001", "Credential compromise detected on worker-01")
        response.rotate_secrets("INC-001", ["groq/aetherius-dev"])
        response.validate_recovery("INC-001", "clean state verified")
        return response

    def test_incident_starts_in_freeze(self):
        response = IncidentResponse()
        inc = response.open_incident("INC-002", "test incident")
        assert inc.current_phase == IncidentPhase.FREEZE

    def test_full_incident_lifecycle(self):
        """§3: all 8 phases complete."""
        response = self._full_incident()
        inc = response.get_incident("INC-001")
        assert inc.is_resolved()
        assert len(inc.phases_completed) == 7  # all phases except RESUME

    def test_cannot_resume_early(self):
        """§3: cannot resume before all phases complete."""
        response = IncidentResponse()
        response.open_incident("INC-003", "test")
        response.freeze_work("INC-003", ["worker-1"])
        with pytest.raises(ValueError, match="cannot resume"):
            response.resume_work("INC-003")

    def test_quarantined_artifacts(self):
        response = self._full_incident()
        inc = response.get_incident("INC-001")
        assert len(inc.artifacts_quarantined) == 1
        quarantined = response._boundary.quarantined_items()
        assert len(quarantined) == 1

    def test_active_incidents_tracked(self):
        response = IncidentResponse()
        response.open_incident("INC-004", "active incident")
        response.open_incident("INC-005", "another incident")
        active = response.active_incidents()
        assert len(active) == 2


# --- H11: model asset lifecycle tests (§1, §3) -------------------------------------

class TestModelAssetRegistry:
    def _make_asset(self, family="qwen3", version="1.7b",
                    quant="q4_K_M", state=ModelAssetState.DISCOVERED):
        return ModelAsset(
            asset_id=f"{family}-{version}-{quant}",
            family=family, version=version,
            quantisation=quant, format="GGUF",
            state=state,
            capabilities=[ModelCapability.CODING,
                          ModelCapability.TOOL_CALLS],
        )

    def test_register_by_asset_id_not_family_name(self):
        """§3: identity is asset_id, NOT family name."""
        reg = ModelAssetRegistry()
        a1 = self._make_asset(version="1.7b")
        a2 = self._make_asset(version="0.6b")
        reg.register(a1)
        reg.register(a2)
        assert a1.asset_id != a2.asset_id
        assert a1.asset_id == "qwen3-1.7b-q4_K_M"
        assert a2.asset_id == "qwen3-0.6b-q4_K_M"

    def test_duplicate_asset_rejected(self):
        reg = ModelAssetRegistry()
        reg.register(self._make_asset())
        with pytest.raises(ValueError, match="duplicate"):
            reg.register(self._make_asset())

    def test_family_versions(self):
        reg = ModelAssetRegistry()
        reg.register(self._make_asset(version="1.7b"))
        reg.register(self._make_asset(version="0.6b"))
        reg.register(self._make_asset(version="4b"))
        versions = reg.family_versions("qwen3")
        assert len(versions) == 3

    def test_supersede_deprecates_not_deletes(self):
        """§3: superseded versions are preserved, not erased."""
        reg = ModelAssetRegistry()
        reg.register(self._make_asset(version="1.7b"))
        reg.register(self._make_asset(version="2.0"))
        reg.supersede("qwen3", "qwen3-1.7b-q4_K_M", "qwen3-2.0-q4_K_M")
        old = reg.get("qwen3-1.7b-q4_K_M")
        assert old.state == ModelAssetState.DEPRECATED
        assert old.superseded_by == "qwen3-2.0-q4_K_M"

    def test_capability_tests_pass(self):
        """§1: capability tests gate the model state."""
        reg = ModelAssetRegistry()
        reg.register(self._make_asset(state=ModelAssetState.TESTING))
        passed = reg.run_capability_tests(
            "qwen3-1.7b-q4_K_M",
            {"coding": {"passed": True}, "tool_calls": {"passed": True}})
        assert passed is True
        assert reg.get("qwen3-1.7b-q4_K_M").state == ModelAssetState.HOSTED

    def test_capability_tests_fail_quarantines(self):
        """Failed capability tests → QUARANTINED, not served."""
        reg = ModelAssetRegistry()
        reg.register(self._make_asset(state=ModelAssetState.TESTING))
        passed = reg.run_capability_tests(
            "qwen3-1.7b-q4_K_M",
            {"coding": {"passed": False}})
        assert passed is False
        assert reg.get("qwen3-1.7b-q4_K_M").state == ModelAssetState.QUARANTINED

    def test_find_by_capability(self):
        """§1: find models by capability (only hosted + tested)."""
        reg = ModelAssetRegistry()
        reg.register(self._make_asset(state=ModelAssetState.HOSTED))
        reg.get("qwen3-1.7b-q4_K_M").capability_tests_passed = True
        # Add an untested model
        untested = self._make_asset(family="phi4", version="mini")
        untested.capability_tests_passed = False
        reg.register(untested)
        coders = reg.by_capability(ModelCapability.CODING)
        assert len(coders) == 1  # only the tested one

    def test_active_version(self):
        reg = ModelAssetRegistry()
        reg.register(self._make_asset(version="1.7b",
                                        state=ModelAssetState.SERVING))
        reg.register(self._make_asset(version="2.0",
                                        state=ModelAssetState.HOSTED))
        active = reg.active_version("qwen3")
        assert active.version == "1.7b"

    def test_checksum_verification(self):
        """§1: model weights have verifiable checksums."""
        import tempfile, os
        with tempfile.NamedTemporaryFile(delete=False, suffix=".gguf") as f:
            f.write(b"fake model weights for testing")
            path = f.name
        try:
            import hashlib
            checksum = hashlib.sha256(b"fake model weights for testing").hexdigest()
            asset = ModelAsset(
                asset_id="test-model", family="test", version="1.0",
                checksum=checksum, local_path=path)
            assert asset.verify_checksum() is True
            # Wrong checksum fails
            asset.checksum = "wrong"
            assert asset.verify_checksum() is False
        finally:
            os.unlink(path)

    def test_summary(self):
        reg = ModelAssetRegistry()
        reg.register(self._make_asset())
        reg.register(self._make_asset(family="phi4", version="mini"))
        s = reg.summary()
        assert s["total_assets"] == 2
        assert "qwen3" in s["families"]
        assert "phi4" in s["families"]


# --- H11: fine-tuning gate tests (§2) ---------------------------------------------

class TestFineTuningGate:
    def test_permitted_with_permissive_license(self):
        gate = FineTuningGate()
        result = gate.check_permitted(
            model_license="MIT",
            data_consent=True,
            compute_available=True,
            quality_gate=True)
        assert result["permitted"] is True

    def test_blocked_without_consent(self):
        gate = FineTuningGate()
        result = gate.check_permitted(
            model_license="MIT",
            data_consent=False,
            compute_available=True,
            quality_gate=True)
        assert result["permitted"] is False
        assert any("consent" in r for r in result["reasons"])

    def test_blocked_without_compute(self):
        gate = FineTuningGate()
        result = gate.check_permitted(
            model_license="apache-2.0",
            data_consent=True,
            compute_available=False,
            quality_gate=True)
        assert result["permitted"] is False
        assert any("compute" in r for r in result["reasons"])

    def test_not_prerequisite_for_first_milestone(self):
        """§2: fine-tuning is NOT a prerequisite for the gateway milestone."""
        gate = FineTuningGate()
        result = gate.check_permitted("MIT", True, True, True)
        assert "not a prerequisite" in result["note"]
