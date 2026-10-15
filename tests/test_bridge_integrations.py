"""Bridge integration tests: H06 auto-conflict + H02 control commands + E2E brief.

Covers the corrections from 2026-10-15:
- H06 integration: contradictory typed claims auto-create conflict cases (§21)
- H02 bridge control: PAUSE/CANCEL/RECALL/REVOKE/EMERGENCY_HALT with
  short-lived leases, descendant propagation, and stale-response denial (§23-§25)
- OpenCodeAdapter.render_for_worker: complete brief, never a control nudge (§14)
"""
from __future__ import annotations

import tempfile
import time
from pathlib import Path

import pytest

from compute.agent_message import (
    AgentMessage,
    Intent,
    build_task_assign,
)
from compute.agent_message_bus import AgentMessageBus
from compute.bridge_control import (
    BridgeControlChannel,
    ControlOutcome,
    LeaseState,
)
from compute.conflict_resolution import (
    Claim,
    ClaimRegistry,
    ClaimType,
    Confidence,
    ResolutionStatus,
)
from compute.worker_bridge_adapters import OpenCodeAdapter


# --- H06 bridge integration (§21) --------------------------------------------------

class TestBridgeConflictIntegration:
    def _make_bus(self, tmp_path):
        return AgentMessageBus(db_path=Path(tmp_path) / "bus.db")

    def _claim(self, cid, content, agent="opencode",
               ctype=ClaimType.CLAIM):
        return Claim(
            claim_id=cid, content=content, claim_type=ctype,
            confidence=Confidence.OBSERVED,
            source_agent=agent, source_worker=f"{agent}-01",
            task_id="CONFLICT-001")

    def test_no_registry_wired_is_noop(self, tmp_path):
        """Without a registry wired, submit_claim is a safe no-op."""
        bus = self._make_bus(tmp_path)
        result = bus.submit_claim(self._claim("c1", "X is true"))
        assert result["conflicts"] == []
        assert "no claim registry" in result["note"]

    def test_contradictory_claims_create_conflict(self, tmp_path):
        """§21: two contradictory claims auto-create a conflict case."""
        bus = self._make_bus(tmp_path)
        registry = ClaimRegistry()
        bus.set_claim_registry(registry)

        bus.submit_claim(self._claim("c1", "The test file exists",
                                      agent="opencode"))
        result = bus.submit_claim(
            self._claim("c2", "The test file does not exist",
                        agent="codex"))
        assert len(result["conflicts"]) == 1
        assert "verification_task" in result
        assert "QA-VERIFY-CONFLICT-001" in result["verification_task"]

    def test_agreeing_claims_no_conflict(self, tmp_path):
        """Identical/non-contradictory claims do not create conflicts."""
        bus = self._make_bus(tmp_path)
        registry = ClaimRegistry()
        bus.set_claim_registry(registry)
        bus.submit_claim(self._claim("c1", "Version is 1.18.30"))
        result = bus.submit_claim(
            self._claim("c2", "Version is 1.18.30", agent="codex"))
        assert result["conflicts"] == []

    def test_both_claims_preserved_after_conflict(self, tmp_path):
        """§21: conflicting claims are BOTH preserved in the registry."""
        bus = self._make_bus(tmp_path)
        registry = ClaimRegistry()
        bus.set_claim_registry(registry)
        bus.submit_claim(self._claim("c1", "Feature works"))
        bus.submit_claim(self._claim("c2", "Feature does not work",
                                      agent="codex"))
        claims = registry.claims_for_task("CONFLICT-001")
        assert len(claims) == 2

    def test_conflict_resolvable_by_evidence(self, tmp_path):
        """§21: the auto-created conflict resolves by EVIDENCE, not voting."""
        bus = self._make_bus(tmp_path)
        registry = ClaimRegistry()
        bus.set_claim_registry(registry)
        bus.submit_claim(self._claim("c1", "Feature works"))
        bus.submit_claim(self._claim("c2", "Feature does not work",
                                      agent="codex"))
        conflict = registry.unresolved_conflicts("CONFLICT-001")[0]
        registry.resolve_by_evidence(
            conflict.conflict_id, winning_claim_id="c1",
            evidence="independent test run T-001 passed", resolver="H-SA-QA")
        assert conflict.status == ResolutionStatus.RESOLVED_BY_EVIDENCE
        # Loser preserved, not erased
        assert registry.get_claim("c2") is not None
        assert registry.get_claim("c2").superseded_by == "c1"


# --- H02 bridge control commands (§23-§25) --------------------------------------------

class TestBridgeControlChannel:
    def test_grant_and_check_lease(self):
        """§24: leases are granted and checked."""
        ch = BridgeControlChannel()
        ch.grant_lease("opencode-01", capabilities=("coding",))
        check = ch.check_lease("opencode-01")
        assert check["authorized"] is True
        assert "coding" in check["capabilities"]

    def test_short_lease_expires(self):
        """§24: expired leases fail closed."""
        ch = BridgeControlChannel()
        ch.grant_lease("w1", duration_s=0.1)
        time.sleep(0.15)
        check = ch.check_lease("w1")
        assert check["authorized"] is False
        assert "fail closed" in check["reason"]

    def test_no_lease_fails_closed(self):
        """§24: a worker with no lease is not authorized."""
        ch = BridgeControlChannel()
        check = ch.check_lease("unknown-worker")
        assert check["authorized"] is False

    def test_pause_acknowledged(self):
        """§23: PAUSE must be acknowledged."""
        ch = BridgeControlChannel()
        ch.grant_lease("w1")
        result = ch.pause("w1")
        assert result.acknowledged is True
        assert result.outcome == ControlOutcome.ACKNOWLEDGED

    def test_cancel_acknowledged(self):
        ch = BridgeControlChannel()
        ch.grant_lease("w1")
        result = ch.cancel("w1", task_id="T-001")
        assert result.acknowledged is True
        assert "T-001" in result.evidence[1]

    def test_recall_cascades_to_descendants(self):
        """§25: RECALL revokes nested/team workers transitively."""
        ch = BridgeControlChannel()
        ch.grant_lease("team-lead", parent_worker_id="")
        ch.grant_lease("worker-a", parent_worker_id="team-lead")
        ch.grant_lease("subagent-c", parent_worker_id="worker-a")
        result = ch.recall("team-lead")
        assert result.acknowledged is True
        assert "worker-a" in result.affected_workers
        assert "subagent-c" in result.affected_workers
        # All descendants lose authority
        assert ch.check_lease("worker-a")["authorized"] is False
        assert ch.check_lease("subagent-c")["authorized"] is False

    def test_revoke_capability(self):
        """§23: REVOKE removes a specific capability."""
        ch = BridgeControlChannel()
        ch.grant_lease("w1", capabilities=("coding", "terminal"))
        result = ch.revoke_capability("w1", "terminal")
        assert result.acknowledged is True
        check = ch.check_lease("w1")
        assert "terminal" not in check["capabilities"]
        assert "coding" in check["capabilities"]

    def test_revoke_nonexistent_capability_rejected(self):
        ch = BridgeControlChannel()
        ch.grant_lease("w1", capabilities=("coding",))
        result = ch.revoke_capability("w1", "nonexistent")
        assert result.outcome == ControlOutcome.REJECTED

    def test_emergency_halt_denies_all(self):
        """§23: EMERGENCY_HALT denies ALL consequential actions."""
        ch = BridgeControlChannel()
        ch.grant_lease("w1")
        ch.grant_lease("w2")
        result = ch.emergency_halt()
        assert result.acknowledged is True
        assert ch.is_halted is True
        assert ch.check_lease("w1")["authorized"] is False
        assert ch.check_lease("w2")["authorized"] is False

    def test_emergency_halt_blocks_side_effects(self):
        """§25: recalled workers' side effects do NOT execute."""
        ch = BridgeControlChannel()
        ch.grant_lease("w1")
        ch.recall("w1")
        verdict = ch.authorize_side_effects("w1", ["write file", "commit"])
        assert verdict["allowed"] is False
        assert verdict["denied"] == ["write file", "commit"]

    def test_stale_response_after_recall_denied(self):
        """§25: authority checked at EXECUTION time — old responses fail."""
        ch = BridgeControlChannel()
        ch.grant_lease("w1")
        # Worker is recalled...
        ch.recall("w1")
        # ...but an old response arrives later requesting side effects
        verdict = ch.authorize_side_effects("w1", ["deploy to prod"])
        assert verdict["allowed"] is False

    def test_valid_lease_authorizes_side_effects(self):
        ch = BridgeControlChannel()
        ch.grant_lease("w1")
        verdict = ch.authorize_side_effects("w1", ["write test file"])
        assert verdict["allowed"] is True

    def test_lift_emergency_halt(self):
        ch = BridgeControlChannel()
        ch.emergency_halt()
        assert ch.is_halted is True
        ch.lift_emergency_halt("owner")
        assert ch.is_halted is False

    def test_control_log_audit(self):
        """§36: every control command is logged."""
        ch = BridgeControlChannel()
        ch.grant_lease("w1")
        ch.pause("w1")
        ch.recall("w1")
        log = ch.control_log()
        assert len(log) >= 2
        assert all("timestamp" in e for e in log)


# --- worker brief rendering (§14) ---------------------------------------------------

class TestWorkerBriefRendering:
    def _task(self):
        return build_task_assign(
            task_id="BRIDGE-E2E-004",
            objective="Create a deterministic unit test for class_reserve",
            sender_agent="hermes", sender_worker="supervisor",
            receiver_agent="opencode", receiver_worker="opencode-01",
            project_id="Agent-Bridge",
            write_set=["tests/bridge_e2e_fixture_test.py"],
            branch="unit/test-branch",
            worktree="C:/repos/Agent-Bridge",
            priority=20,
            evidence_refs=["compute/resource_governor.py"])

    def test_brief_is_complete(self):
        """§14: brief carries EVERYTHING — not a control nudge."""
        adapter = OpenCodeAdapter()
        brief = adapter.render_for_worker(self._task())
        # All required sections present
        assert "TASK_ID: BRIDGE-E2E-004" in brief
        assert "PROJECT: Agent-Bridge" in brief
        assert "OBJECTIVE:" in brief
        assert "baseline" in brief.lower()
        assert "WRITE_SET" in brief
        assert "tests/bridge_e2e_fixture_test.py" in brief
        assert "BRANCH: unit/test-branch" in brief
        assert "ZERO_INCREMENTAL_SPEND" in brief
        assert "compute/resource_governor.py" in brief
        assert "ACK TASK_ID=BRIDGE-E2E-004" in brief
        assert "TASK_START TASK_ID=BRIDGE-E2E-004" in brief
        assert "TASK_COMPLETE TASK_ID=BRIDGE-E2E-004" in brief

    def test_brief_forbids_owner_questions(self):
        """§14: the brief instructs autonomous completion."""
        adapter = OpenCodeAdapter()
        brief = adapter.render_for_worker(self._task())
        assert "Do NOT ask the owner" in brief

    def test_brief_not_just_a_nudge(self):
        """The failure mode we're fixing: 'continue TASK-X' is NOT enough."""
        adapter = OpenCodeAdapter()
        brief = adapter.render_for_worker(self._task())
        assert len(brief) > 500  # a real brief, not a one-liner
        assert "class_reserve" in brief or "unit test" in brief.lower()


# --- H03 skill candidate intake (§22) ---------------------------------------------

class TestSkillCandidateIntake:
    def _candidate_msg(self, app_id="worker-tool", version="0.1.0"):
        return AgentMessage(
            message_id="msg_skill_001",
            sender_agent="opencode", sender_worker="opencode-01",
            receiver_agent="hermes", receiver_worker="bridge-supervisor",
            task_id="SKILL-CAND-001",
            intent=Intent.SKILL_CANDIDATE,
            objective="Reusable log-summarising workflow discovered during task",
            payload={
                "app_id": app_id,
                "name": "Worker Log Summariser",
                "version": version,
                "description": "Summarises worker logs into typed findings",
                "bridge_adapter": "logsum_adapter.py",
                "required_capabilities": ["TEXT_PROCESSING"],
                "permissions_requested": ["read_logs"],
                "license": "MIT",
            })

    def test_no_pipeline_wired(self, tmp_path):
        """Without a pipeline wired, submission fails honestly."""
        bus = AgentMessageBus(db_path=Path(tmp_path) / "bus.db")
        result = bus.submit_skill_candidate(self._candidate_msg())
        assert result["submitted"] is False
        assert "no skill pipeline" in result["reason"]

    def test_candidate_submitted_not_installed(self, tmp_path):
        """§22: a worker CANNOT self-install — submission only creates CANDIDATE."""
        from compute.skill_pipeline import SkillPipeline
        bus = AgentMessageBus(db_path=Path(tmp_path) / "bus.db")
        pipeline = SkillPipeline()
        bus.set_skill_pipeline(pipeline)

        result = bus.submit_skill_candidate(self._candidate_msg())
        assert result["submitted"] is True
        assert result["stage"] == "candidate"
        assert "no self-install" in result["note"]

        # The candidate exists but is NOT in the production registry
        assert "worker-tool" in pipeline.all_candidates().keys() or \
            any(c.app_id == "worker-tool" for c in pipeline.all_candidates().values())
        # And it cannot publish without the full review pipeline
        with pytest.raises(Exception):
            pipeline.approve_and_publish("worker-tool@0.1.0",
                                          approver="opencode-01")

    def test_missing_app_id_rejected(self, tmp_path):
        from compute.skill_pipeline import SkillPipeline
        bus = AgentMessageBus(db_path=Path(tmp_path) / "bus.db")
        bus.set_skill_pipeline(SkillPipeline())
        result = bus.submit_skill_candidate(self._candidate_msg(app_id=""))
        assert result["submitted"] is False
        assert "app_id" in result["reason"]

    def test_full_promotion_path_from_bridge_candidate(self, tmp_path):
        """§22: a bridge-submitted candidate CAN be promoted by review."""
        from compute.skill_pipeline import SkillPipeline
        bus = AgentMessageBus(db_path=Path(tmp_path) / "bus.db")
        pipeline = SkillPipeline()
        bus.set_skill_pipeline(pipeline)

        result = bus.submit_skill_candidate(self._candidate_msg())
        cid = result["candidate_id"]
        # Drive the full review pipeline (reviewers, not the worker)
        pipeline.provenance_review(cid, "H-SA-SECURITY", True, "MIT licence verified")
        pipeline.sandbox_tests(cid, "H-SA-QA", True, "isolated run clean")
        pipeline.security_review(cid, "H-SA-SECURITY", True,
                                  granted_permissions=("read_logs",))
        pipeline.benchmark(cid, "H-SA-QA", True, genesis_solo=True,
                           details="genesis invoked adapter alone")
        published = pipeline.approve_and_publish(cid, approver="hermes-supervisor",
                                                  genesis_solo=True)
        assert published.app_id == "worker-tool"
        # Genesis can now invoke the same underlying capability (§22)
        assert published.genesis_solo is True
