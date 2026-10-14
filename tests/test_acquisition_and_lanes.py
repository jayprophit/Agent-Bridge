"""Tests for the §7 acquisition queue + §14/§15 project lanes."""
import json
import os
import time

import pytest

from compute.acquisition_queue import (
    AcquisitionQueue, AppRecord,
    DISCOVERED, LAUNCHED, ACCOUNT_IDENTIFIED, PLAN_DETERMINED,
    MODELS_ENUMERATED, QUOTA_PROFILED, AGENT_MODE_TESTED,
    BOUNDARY_TASK_SUBMITTED, RESULT_VERIFIED, CAPABILITY_REGISTERED,
    REJECTED, FINAL_STATES, STAGES,
)
from compute.project_lanes import (
    DEFAULT_LANES, compute_starvation, lane_assignments,
    StarvationReport, LaneSnapshot, DEFAULT_STALENESS_S,
)


# ===================== acquisition_queue =====================

class TestAcquisitionQueue:
    def test_append_only_durable(self, tmp_path):
        p = tmp_path / "apps.jsonl"
        q = AcquisitionQueue(str(p))
        q.discover("claude", name="Claude", category="agent-app",
                   source="desktop-shortcut")
        # reload from disk
        q2 = AcquisitionQueue(str(p))
        assert "claude" in q2._apps
        assert q2._apps["claude"].name == "Claude"
        # line count == 1 append
        assert len(p.read_text().strip().splitlines()) == 1

    def test_discover_idempotent(self, tmp_path):
        q = AcquisitionQueue(str(tmp_path / "apps.jsonl"))
        q.discover("goose", source="start-menu")
        q.discover("goose", source="start-menu")   # second write
        assert len(q) == 1

    def test_advance_through_pipeline(self, tmp_path):
        q = AcquisitionQueue(str(tmp_path / "apps.jsonl"))
        q.discover("cursor", source="desktop-shortcut")
        rec = q.advance("cursor", LAUNCHED)
        assert rec.current_stage == LAUNCHED
        rec = q.advance("cursor", AGENT_MODE_TESTED, evidence=["agent mode found"])
        assert rec.agent_mode_confirmed
        # cannot advance a final state
        q.register_capability("cursor", worker_id="cursor-worker",
                              control_channel="cli", free_available=True)
        assert q._apps["cursor"].current_stage == CAPABILITY_REGISTERED
        assert q._apps["cursor"].verification_status == "AUTOPILOT_READY"
        with pytest.raises(ValueError):
            q.advance("cursor", REJECTED)   # final state locked

    def test_unassessed_returns_non_final_only(self, tmp_path):
        q = AcquisitionQueue(str(tmp_path / "apps.jsonl"))
        q.discover("a"); q.discover("b")
        q.advance("a", CAPABILITY_REGISTERED)   # final
        unassessed = q.unassessed(now=time.time())
        assert len(unassessed) == 1
        assert unassessed[0]["app_id"] == "b"

    def test_stale_detected_by_last_action(self, tmp_path):
        q = AcquisitionQueue(str(tmp_path / "apps.jsonl"))
        rec = q.discover("manus")
        rec.last_action_at = time.time() - 90000   # >24h stale
        now = time.time()
        unassessed = q.unassessed(now=now)
        assert len(unassessed) == 1
        assert (now - unassessed[0]["last_action_epoch"]) > 86400


# ===================== project_lanes =====================

class TestProjectLanes:
    def test_lane_starvation_detected(self):
        """§15: a lane with unblocked work, no active workers, progress >1h stale."""
        now = 1_000_000.0
        lanes = DEFAULT_LANES
        wproj = {
            "Aetherius OS": {"active": 0, "has_unblocked_work": True,
                             "last_progress_epoch": now - 7200},
            "Genesis": {"active": 1, "has_unblocked_work": True,
                        "last_progress_epoch": now - 10},
        }
        rep = compute_starvation(lanes, wproj, now=now)
        assert rep.has_starvation
        assert any(l["project"] == "Aetherius OS" for l in rep.starved_lanes)
        # Genesis has an active worker and fresh progress — not starved
        assert not any(l["project"] == "Genesis" for l in rep.starved_lanes)

    def test_no_starvation_when_no_work(self):
        lanes = DEFAULT_LANES
        now = 1_000_000.0
        wproj = {"Aetherius OS": {"active": 0, "has_unblocked_work": False,
                                  "last_progress_epoch": 0}}
        rep = compute_starvation(lanes, wproj, now=now)
        assert not rep.has_starvation

    def test_lane_snapshot_is_starved(self):
        snap = LaneSnapshot("l1", "IDE", "HIGH", min_workers=2,
                            has_unblocked_work=True, active_workers=0,
                            last_progress_epoch=100.0,
                            stale_threshold_s=3600.0)
        assert snap.is_starved(now=5000.0)      # 4900s stale > 3600
        assert not snap.is_starved(now=200.0)   # 100s stale < 3600

    def test_lane_assignment_plan_priority_order(self):
        rep = StarvationReport(
            starved_lanes=[
                {"lane_id": "genesis", "project": "Genesis",
                 "priority": "HIGH", "active_workers": 0,
                 "min_workers": 1, "stale_for_s": 5000,
                 "stale_threshold_s": 3600, "roles_needed": ["research"]},
                {"lane_id": "infra", "project": "Agent-Bridge",
                 "priority": "MEDIUM", "active_workers": 0,
                 "min_workers": 1, "stale_for_s": 5000,
                 "stale_threshold_s": 3600, "roles_needed": ["runtime"]},
            ])
        plan = lane_assignments(rep, free_worker_capacity=1)
        # HIGH before MEDIUM
        assert plan[0]["priority"] == "HIGH"
        assert len(plan) == 1

    def test_default_lanes_cover_portfolio(self):
        """§14: the portfolio must cover the active projects."""
        projects = {l["project"] for l in DEFAULT_LANES}
        # the owner's active projects
        assert "Agent-Bridge" in projects
        assert "Aetherius OS" in projects
        assert "Genesis" in projects
        assert "IDE Workspace" in projects
        assert "MAT" in projects
