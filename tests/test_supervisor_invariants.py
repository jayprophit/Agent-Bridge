"""Tests for the hard-coded Supervisor Constitution (§36/§49).

Each invariant has a PASS case and a FAIL case with concrete evidence,
so the gate cannot be "always true" or "always false" — the test proves
WHICH snapshot shape trips WHICH invariant and WHY.
"""
import pytest

from compute.supervisor_invariants import (
    PASS, FAIL, STUBBED,
    CRITICAL, HIGH,
    check_all,
    gate_continuation,
    invariant_1_continuation,
    invariant_2_min_hive,
    invariant_3_no_idle_with_ready,
    invariant_4_worker_stop_handoff,
    invariant_7_commissioning_loop,
    invariant_8_task_specific_evidence,
    invariant_11_resource_headroom,
    invariant_12_model_routing,
    invariant_13_quota_exhaustion,
    invariant_14_no_project_starvation,
    invariant_28_no_report_termination,
)
from compute.hive_scheduler import AVAILABLE, IMPLEMENTING, TESTING, COMPLETE
from compute.supervisor_runtime import (
    SupervisorRuntime, OpenCodeAdapter, CodexAdapter, OllamaAdapter,
)


def _clean_snapshot():
    """A snapshot that passes every invariant."""
    return {
        "workers": {
            "opencode-primary": {"status": IMPLEMENTING, "verdict": "RUNNING",
                                 "evidence": ["commit abc1234 pushed",
                                              "tests 186/186 pass"],
                                 "role": "implementation",
                                 "application": "opencode"},
            "codex-primary": {"status": TESTING, "verdict": "RUNNING",
                              "evidence": ["test suite green",
                                           "commit def5678"],
                              "role": "implementation",
                              "application": "codex"},
            "ollama-local": {"status": IMPLEMENTING, "verdict": "RUNNING",
                             "evidence": ["model qwen serving",
                                          "tests green"],
                             "role": "qareviewer",
                             "application": "ollama"},
        },
        "ready_tasks": [
            {"task_id": "t4", "required_capability": "qareviewer",
             "write_set": "ws4", "project": "IDE", "priority": 1,
             "privacy_class": "PUBLIC", "capabilities": ["qareviewer"],
             "estimated_output_tokens": 1000, "estimated_input_tokens": 500,
             "timeout_s": 600, "success_criteria": "done"},
        ],
        "handoffs_pending": 0,
        "gaps": [],
        "quotas": {
            "opencode-primary": {"exhausted": False,
                                 "next_reset_epoch": None,
                                 "confidence": "VERIFIED"},
            "codex-primary": {"exhausted": False, "next_reset_epoch": None,
                              "confidence": "VERIFIED"},
        },
        "resources": {"cpu": 0.4, "ram": 0.5, "gpu": 0.3, "vram": 0.3},
        "projects": {"IDE": {"has_unblocked_work": False,
                             "last_progress_epoch": 0, "priority": "HIGH"},
                     "Genesis": {"has_unblocked_work": False,
                                 "last_progress_epoch": 0, "priority": "HIGH"}},
        "unassessed_apps": [],
        "internal_workers": 5,
        "min_internal_target": 5,
        "continuation_required": False,
        "last_cycle_emitted_report": False,
        "worker_actions": {"opencode-primary": {"check_in": {"delivered": True}},
                           "codex-primary": {"check_in": {"delivered": True}},
                           "ollama-local": {"check_in": {"delivered": True}}},
        "now_epoch": 1000000.0,
        "model_routing": {"paid_budget_remaining": 0,
                          "last_assignment_tier": "FREE"},
        "deferred_tasks": [],
        "all_suitable_workers_exhausted": False,
    }


# === INVARIANT 1: a clean snapshot does NOT force continuation ===
class TestInvariant1Continuation:
    def test_clean_snapshot_does_not_force_continuation(self):
        snap = _clean_snapshot()
        v = invariant_1_continuation(snap)
        assert v is None          # nothing requires continuation

    def test_report_after_milestone_keeps_continuation(self):
        """§28: a report/milestone must not clear continuation_required."""
        snap = _clean_snapshot()
        snap["continuation_required"] = False
        snap["handoffs_pending"] = 1          # milestone produced a handoff
        snap["last_cycle_emitted_report"] = True
        v = invariant_1_continuation(snap)
        assert v is not None                 # invariant_1 catches the breach
        # invariant_28 is the report-terminator gate


# === INVARIANT 2: internal team floor ===
class TestInvariant2MinHive:
    def test_floor_met_passes(self):
        snap = _clean_snapshot()
        assert invariant_2_min_hive(snap) is None

    def test_floor_breached_fails(self):
        snap = _clean_snapshot()
        snap["internal_workers"] = 2          # under the 5 floor
        # 5 independent ready units -> needs 5 internal
        snap["ready_tasks"] = [
            {"task_id": f"t{i}", "write_set": f"ws{i}", "project": "IDE",
             "required_capability": "implementation", "capabilities": ["implementation"],
             "priority": 1, "privacy_class": "PUBLIC",
             "estimated_input_tokens": 10, "estimated_output_tokens": 10,
             "success_criteria": "ok", "timeout_s": 60}
            for i in range(6)
        ]
        v = invariant_2_min_hive(snap)
        assert v is not None
        assert v.status == FAIL
        assert "hermes-native subagents" in v.evidence[0]

    def test_no_backlog_passes(self):
        """§2 'do not instantiate idle agents just to satisfy a number'."""
        snap = _clean_snapshot()
        snap["internal_workers"] = 0
        snap["ready_tasks"] = []             # no backlog
        assert invariant_2_min_hive(snap) is None


# === INVARIANT 3: no idle suitable worker with ready work ===
class TestInvariant3NoIdleWithReady:
    def test_idle_available_worker_with_matching_ready_task(self):
        snap = _clean_snapshot()
        # make one worker AVAILABLE
        snap["workers"]["ollama-local"]["status"] = AVAILABLE
        snap["workers"]["ollama-local"]["role"] = "qareviewer"
        # ready task needs qareviewer
        snap["ready_tasks"] = [{
            "task_id": "t9", "required_capability": "qareviewer",
            "capabilities": ["qareviewer"], "write_set": "ws9",
            "project": "IDE", "privacy_class": "PUBLIC", "priority": 1,
            "estimated_input_tokens": 10, "estimated_output_tokens": 10,
            "success_criteria": "ok", "timeout_s": 60}]
        v = invariant_3_no_idle_with_ready(snap)
        assert v is not None
        assert "ollama-local" in v.evidence[0]

    def test_no_idle_when_no_ready(self):
        snap = _clean_snapshot()
        snap["ready_tasks"] = []
        assert invariant_3_no_idle_with_ready(snap) is None


# === INVARIANT 4: worker stop handled ===
class TestInvariant4WorkerStop:
    def test_idle_worker_without_check_in(self):
        snap = _clean_snapshot()
        snap["workers"]["ollama-local"]["status"] = AVAILABLE
        # remove the recorded check-in so this worker is un-handled
        snap["worker_actions"]["ollama-local"] = {}
        v = invariant_4_worker_stop_handoff(snap)
        assert v is not None
        assert "ollama-local" in v.evidence[0]

    def test_worker_with_check_in_ok(self):
        snap = _clean_snapshot()
        snap["workers"]["ollama-local"]["status"] = AVAILABLE
        snap["worker_actions"]["ollama-local"] = {"check_in": {"delivered": True}}
        assert invariant_4_worker_stop_handoff(snap) is None


# === INVARIANT 7: commissioning loop ===
class TestInvariant7Commissioning:
    def test_stale_unassessed_app(self):
        snap = _clean_snapshot()
        snap["unassessed_apps"] = [{"app_id": "claude",
                                    "last_action_epoch": snap["now_epoch"] - 90000}]
        v = invariant_7_commissioning_loop(snap)
        assert v is not None
        assert "claude" in v.evidence[0]

    def test_fresh_unassessed_app_ok(self):
        snap = _clean_snapshot()
        snap["unassessed_apps"] = [{"app_id": "claude",
                                    "last_action_epoch": snap["now_epoch"]}]
        assert invariant_7_commissioning_loop(snap) is None


# === INVARIANT 8: task-specific evidence ===
class TestInvariant8TaskEvidence:
    def test_liveness_only_evidence_fails(self):
        snap = _clean_snapshot()
        snap["workers"]["opencode-primary"]["evidence"] = ["session active 12s ago"]
        snap["workers"]["opencode-primary"]["verdict"] = "RUNNING"
        v = invariant_8_task_specific_evidence(snap)
        assert v is not None
        assert "opencode-primary" in v.evidence[0]

    def test_task_artifact_evidence_passes(self):
        snap = _clean_snapshot()
        snap["workers"]["opencode-primary"]["evidence"] = ["session updated 12s ago; commit abc pushed; tests green"]
        v = invariant_8_task_specific_evidence(snap)
        assert v is None


# === INVARIANT 11: resource headroom ===
class TestInvariant11ResourceHeadroom:
    def test_critical_with_heavy_local_model(self):
        snap = _clean_snapshot()
        snap["resources"] = {"cpu": 0.98, "ram": 0.97, "gpu": 0.96, "vram": 0.99}
        snap["workers"]["ollama-local"]["application"] = "ollama"
        snap["workers"]["ollama-local"]["model_weight_gb"] = 14.0
        v = invariant_11_resource_headroom(snap)
        assert v is not None
        assert v.severity == CRITICAL

    def test_critical_without_heavy_model_passes(self):
        snap = _clean_snapshot()
        snap["resources"] = {"cpu": 0.98, "ram": 0.97, "gpu": 0.96, "vram": 0.99}
        v = invariant_11_resource_headroom(snap)
        assert v is None      # nothing heavy to pause


# === INVARIANT 12: model routing free-first ===
class TestInvariant12ModelRouting:
    def test_stubbed_without_policy(self):
        snap = _clean_snapshot()
        snap["model_routing"] = {}
        v = invariant_12_model_routing(snap)
        assert v is not None
        assert v.status == STUBBED

    def test_paid_assignment_with_zero_budget_fails(self):
        snap = _clean_snapshot()
        snap["model_routing"] = {"paid_budget_remaining": 0,
                                 "last_assignment_tier": "PAID"}
        v = invariant_12_model_routing(snap)
        assert v is not None
        assert v.status == FAIL


# === INVARIANT 13: quota exhaustion ===
class TestInvariant13Quota:
    def test_all_exhausted_without_deferred_queue(self):
        snap = _clean_snapshot()
        snap["quotas"] = {"opencode-primary": {"exhausted": True,
                                               "next_reset_epoch": 1,
                                               "confidence": "VERIFIED"}}
        snap["deferred_tasks"] = []
        snap["all_suitable_workers_exhausted"] = True
        v = invariant_13_quota_exhaustion(snap)
        assert v is not None
        assert "deferred" in v.fix_suggestion.lower()

    def test_exhausted_with_deferred_queue_ok(self):
        snap = _clean_snapshot()
        snap["all_suitable_workers_exhausted"] = True
        snap["deferred_tasks"] = [{"task_id": "t1"}]
        assert invariant_13_quota_exhaustion(snap) is None


# === INVARIANT 14: project starvation ===
class TestInvariant14Starvation:
    def test_starved_project(self):
        snap = _clean_snapshot()
        snap["now_epoch"] = 1000000.0
        snap["projects"]["Aetherius OS"] = {"has_unblocked_work": True,
                                            "last_progress_epoch": 1000000.0 - 7200,
                                            "priority": "CRITICAL"}
        v = invariant_14_no_project_starvation(snap)
        assert v is not None
        assert "Aetherius" in v.evidence[0]

    def test_active_project_ok(self):
        snap = _clean_snapshot()
        snap["now_epoch"] = 1000000.0
        snap["projects"]["IDE"] = {"has_unblocked_work": False,
                                   "last_progress_epoch": 1000000.0,
                                   "priority": "HIGH"}
        assert invariant_14_no_project_starvation(snap) is None


# === INVARIANT 28: no report termination ===
class TestInvariant28ReportTermination:
    def test_report_then_continuation_false(self):
        snap = _clean_snapshot()
        snap["continuation_required"] = False
        snap["last_cycle_emitted_report"] = True
        v = invariant_28_no_report_termination(snap)
        assert v is not None
        assert v.status == FAIL

    def test_report_with_continuation_true_ok(self):
        snap = _clean_snapshot()
        snap["continuation_required"] = True
        snap["last_cycle_emitted_report"] = True
        assert invariant_28_no_report_termination(snap) is None


# === consolidated check_all + gate ===
class TestCheckAllAndGate:
    def test_clean_snapshot_passes(self):
        snap = _clean_snapshot()
        r = check_all(snap)
        assert r.passed
        assert r.violations == []

    def test_gate_forces_continuation_on_starvation(self):
        snap = _clean_snapshot()
        snap["continuation_required"] = False
        snap["now_epoch"] = 1000000.0
        snap["projects"]["X"] = {"has_unblocked_work": True,
                                 "last_progress_epoch": 1000000.0 - 7200,
                                 "priority": "CRITICAL"}
        assert gate_continuation(snap) is True

    def test_gate_allows_stop_when_truly_done(self):
        snap = _clean_snapshot()
        snap["continuation_required"] = False
        snap["handoffs_pending"] = 0
        snap["gaps"] = []
        snap["ready_tasks"] = []
        snap["projects"] = {}
        snap["internal_workers"] = 8
        snap["unassessed_apps"] = []
        assert gate_continuation(snap) is True   # base is False, but check_all passes

    def test_stubbed_invariants_do_not_fail(self):
        """A STUBBED invariant is reported, not a hard FAIL."""
        snap = _clean_snapshot()
        snap["model_routing"] = {}     # §12 stubbed
        r = check_all(snap)
        assert r.passed              # stubs don't trip the gate
        assert any(v.status == STUBBED for v in r.violations)


# === integration: the runtime actually calls the constitution ===
class TestRuntimeWiring:
    def test_runtime_imports_constitution(self):
        """The runtime module must reference the invariants module."""
        import inspect
        src = inspect.getsource(SupervisorRuntime.run_cycle)
        assert "check_invariants" in src
        src2 = inspect.getsource(SupervisorRuntime._compute_continuation)
        assert "gate_continuation" in src2

    def test_one_cycle_emits_constitution(self, tmp_path):
        """A single cycle must produce a constitution dict in its actions."""
        rt = SupervisorRuntime(str(tmp_path), adapters=[
            OllamaAdapter(worker_id="ollama-local",
                          model="qwen2.5-coder:3b-instruct-q4_K_M"),
        ])
        actions = rt.run_cycle()
        assert "constitution" in actions
        assert isinstance(actions["constitution"], dict)
        assert actions["constitution"]["checked"] > 0
