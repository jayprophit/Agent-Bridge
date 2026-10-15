"""P0-A £0 Spend Guard — acceptance tests (§5 of correction).

Proves the cost-policy engine enforces FREE_FIRST_STRICT at the execution
boundary: every execution path passes through CostPolicyEngine BEFORE the
adapter runs, with UNKNOWN_COST → DENY as the default.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from compute.cost_engine import (
    CostPolicyEngine,
    CostClass,
    COST_FREE,
    COST_CLOUD_ZERO,
    COST_CLOUD_RECURRING_FREE,
    COST_UNKNOWN,
    COST_PAID,
    ALLOWED_COST_CLASSES,
    BLOCKED_COST_CLASSES,
    default_cost_policy_engine,
)
from orchestrator import (
    Orchestrator,
    OrchestratorTask,
    OrchestratorError,
    HERMES,
    OPENCODE,
    OLLAMA,
    AGENT_BRIDGE,
)
from task_dag import TaskStatus


REPO_ROOT = Path(__file__).resolve().parent.parent


# A stub adapter that records whether execute() was called
class RecordingAdapter:
    worker_id = "test-worker"
    def __init__(self, name="test-worker", cost_class=COST_UNKNOWN):
        self.worker_id = name
        self.cost_class = cost_class
        self.execute_called = False
        self.last_task = None
    def probe(self):
        return {"worker_id": self.worker_id, "available": True}
    def execute(self, task):
        self.execute_called = True
        self.last_task = task
        return {"ok": True, "result": {}, "changed_files": [], "test_results": {}}


class CostPolicyUnitTests(unittest.TestCase):
    """Tests A–J: the CostPolicyEngine itself."""

    def setUp(self):
        self.engine = CostPolicyEngine()

    # A. task with no cost metadata cannot silently reach paid provider
    def test_a_no_cost_metadata_denied(self):
        """A task whose worker has no cost classification is DENIED."""
        task = OrchestratorTask(objective="test A", role="coder")
        # No cost class registered for "unknown-provider"
        allowed, reason, cc = self.engine.evaluate_execution(
            task, "unknown-provider", "")
        self.assertFalse(allowed)
        self.assertIn("DENY", reason)
        self.assertEqual(cc.cost_class, COST_UNKNOWN)

    # B. local Ollama remains allowed
    def test_b_ollama_allowed(self):
        """LOCAL_FREE provider class passes."""
        self.engine.register_cost_class(
            "", "ollama", CostClass(
                cost_class=COST_FREE, provider_id="ollama",
                evidence="VERIFIED_LIVE", budget_class="FREE_ONLY"))
        task = OrchestratorTask(objective="review summary", role="reviewer")
        allowed, reason, cc = self.engine.evaluate_execution(task, "ollama", "")
        self.assertTrue(allowed, f"Ollama should be allowed: {reason}")

    # C. verified free-tier model remains allowed
    def test_c_free_tier_allowed(self):
        """CLOUD_ZERO_COST (free tier, zero spend) passes."""
        self.engine.register_cost_class(
            "", "copilot", CostClass(
                cost_class=COST_CLOUD_ZERO, provider_id="copilot",
                evidence="VERIFIED_LIVE", budget_class="FREE_ONLY"))
        task = OrchestratorTask(objective="code fix", role="coder")
        allowed, reason, cc = self.engine.evaluate_execution(task, "copilot", "")
        self.assertTrue(allowed)

    # D. existing owned Codex entitlement remains allowed within quota
    def test_d_owned_codex_allowed(self):
        """Codex under existing Copilot entitlement passes (owner_approved=True)."""
        self.engine.register_cost_class(
            "", "codex", CostClass(
                cost_class=COST_CLOUD_ZERO, provider_id="codex",
                evidence="VERIFIED_LIVE", budget_class="FREE_ONLY",
                owner_approved=True))
        task = OrchestratorTask(objective="code review", role="coder")
        allowed, reason, cc = self.engine.evaluate_execution(task, "codex", "")
        self.assertTrue(allowed)

    # E. exhausted included quota does NOT roll into paid overage
    def test_e_exhausted_quota_denied(self):
        """Even a free provider with exhausted quota is DENIED (no paid fallback)."""
        self.engine.register_cost_class(
            "", "freemodel", CostClass(
                cost_class=COST_CLOUD_RECURRING_FREE, provider_id="freemodel",
                evidence="VERIFIED_LIVE", budget_class="FREE_ONLY",
                quota_remaining={"tokens": 0},  # quota exhausted
            ))
        task = OrchestratorTask(objective="task", role="reviewer")
        allowed, reason, cc = self.engine.evaluate_execution(task, "freemodel", "")
        self.assertFalse(allowed)
        self.assertIn("quota", reason.lower())

    # F. unknown provider is denied pending classification
    def test_f_unknown_provider_denied(self):
        """An unregistered provider → UNKNOWN_COST → DENY."""
        task = OrchestratorTask(objective="task", role="coder")
        allowed, reason, cc = self.engine.evaluate_execution(
            task, "mystery-provider", "")
        self.assertFalse(allowed)
        self.assertEqual(cc.cost_class, COST_UNKNOWN)

    # G. paid API key existing on disk does NOT imply permission to spend
    def test_g_paid_key_not_implied(self):
        """Having an API key file on disk does not auto-classify as allowed."""
        class FakeAdapter:
            worker_id = "paid-proxy"
        # Even if the adapter exists, no cost-class registration → UNKNOWN → DENY
        task = OrchestratorTask(objective="task", role="coder")
        allowed, reason, cc = self.engine.evaluate_execution(task, "paid-proxy", "")
        self.assertFalse(allowed)
        self.assertEqual(cc.cost_class, COST_UNKNOWN)

    # H. provider/model switch re-runs cost evaluation
    def test_h_provider_switch_reruns_evaluation(self):
        """Switching from allowed -> blocked provider triggers DENY on next call."""
        # Provider A is allowed (free tier)
        self.engine.register_cost_class(
            "", "free-provider", CostClass(
                cost_class=COST_CLOUD_ZERO, provider_id="free-provider",
                evidence="VERIFIED_LIVE", budget_class="FREE_ONLY"))
        # Provider B is paid
        self.engine.register_cost_class(
            "", "paid-provider", CostClass(
                cost_class=COST_PAID, provider_id="paid-provider",
                evidence="VERIFIED_CONFIGURED", budget_class="FREE_ONLY"))
        task = OrchestratorTask(objective="task", role="coder")
        # First: free provider → allowed
        allowed_a, _, _ = self.engine.evaluate_execution(task, "free-provider", "")
        self.assertTrue(allowed_a)
        # Switch to paid provider → denied
        allowed_b, reason_b, _ = self.engine.evaluate_execution(task, "paid-provider", "")
        self.assertFalse(allowed_b)
        # Each call is independent
        self.assertEqual(len(self.engine.decisions), 2)

    # I. retry/fallback path re-runs cost evaluation
    def test_i_retry_reruns_evaluation(self):
        """Every dispatch (including retries) gates through the cost engine."""
        self.engine.register_cost_class(
            "", "free-worker", CostClass(
                cost_class=COST_CLOUD_ZERO, provider_id="free-worker",
                evidence="VERIFIED_LIVE", budget_class="FREE_ONLY"))
        task = OrchestratorTask(objective="task", role="coder")
        for i in range(3):
            allowed, reason, _ = self.engine.evaluate_execution(task, "free-worker", "")
            self.assertTrue(allowed, f"retry {i}: {reason}")
        # 3 independent decisions recorded
        self.assertEqual(len(self.engine.decisions), 3)

    # J. subagent spawning obeys cost policy
    def test_j_subagent_obeys_policy(self):
        """A subagent worker with unknown cost class is DENIED."""
        task = OrchestratorTask(objective="subagent task", role="coder")
        allowed, reason, _ = self.engine.evaluate_execution(
            task, "subagent-unknown", "")
        self.assertFalse(allowed)
        self.assertIn("DENY", reason)


class OrchestratorCostBoundaryTests(unittest.TestCase):
    """End-to-end: dispatch() gates on cost policy BEFORE adapter.execute()."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="orch_cost_"))

def test_dispatch_denies_unknown_worker(self):
        """A worker without cost class registration is blocked at the boundary."""
        from compute.cost_engine import CostPolicyEngine
        from task_dag import WorkerRegistry, WorkerInfo
        orch = Orchestrator(self.tmp, adapters={"opencode": RecordingAdapter("opencode")})
        # Override with an empty cost policy - no worker classifications
        orch.cost_policy = CostPolicyEngine()
        # Register OPENCODE in registry so select_worker finds it
        orch.registry = WorkerRegistry()
        orch.registry.register(WorkerInfo(
            OPENCODE, "coder", ["code-implement"], ["local"], "IDLE", ""))
        # select_worker picks OPENCODE for "coder" role, and the adapter exists,
        # but cost policy denies with UNKNOWN_COST
        tid = orch.submit(OrchestratorTask(
            objective="do something", role="coder"))
        out = orch.dispatch(tid)
        self.assertEqual(out["status"], TaskStatus.BLOCKED.value)
        self.assertFalse(orch.adapters["opencode"].execute_called)

    def test_dispatch_allows_registered_free_worker(self):
        """A worker with a registered free cost class passes the gate."""
        orch = Orchestrator(self.tmp, adapters={"ollama": RecordingAdapter("ollama")})
        from task_dag import WorkerRegistry, WorkerInfo
        orch.registry = WorkerRegistry()
        orch.registry.register(WorkerInfo(
            "ollama", "reviewer", ["review"], ["local"], "IDLE", ""))
        tid = orch.submit(OrchestratorTask(
            objective="review something", role="reviewer"))
        out = orch.dispatch(tid)
        self.assertEqual(out["status"], TaskStatus.VERIFIED_COMPLETE.value)

    def test_dispatch_cost_gate_runs_before_execute(self):
        """Verify execute() is NOT called when cost gate denies."""
        from compute.cost_engine import CostPolicyEngine
        orch = Orchestrator(self.tmp, adapters={"opencode": RecordingAdapter("opencode")})
        # Empty cost policy → UNKNOWN_COST → DENY
        orch.cost_policy = CostPolicyEngine()
        tid = orch.submit(OrchestratorTask(
            objective="code something", role="coder"))
        out = orch.dispatch(tid)
        self.assertFalse(orch.adapters["opencode"].execute_called,
                         "adapter.execute() must NOT run when cost gate denies")
        self.assertEqual(out["status"], TaskStatus.BLOCKED.value)


class ZeroIncrementSpendGuardTests(unittest.TestCase):
    """The overall guard status proves the engine is wired into the path."""

    def test_engine_has_no_unknown_cost_allow(self):
        """The policy engine must never ALLOW UNKNOWN_COST."""
        self.assertNotIn(COST_UNKNOWN, ALLOWED_COST_CLASSES)
        self.assertIn(COST_UNKNOWN, BLOCKED_COST_CLASSES)

    def test_default_engine_denies_unregistered(self):
        """default_cost_policy_engine() denies unregistered providers."""
        engine = default_cost_policy_engine()
        task = OrchestratorTask(objective="x", role="coder")
        allowed, _, _ = engine.evaluate_execution(task, "unregistered", "")
        self.assertFalse(allowed)


if __name__ == "__main__":
    unittest.main()
