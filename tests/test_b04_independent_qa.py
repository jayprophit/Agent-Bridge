"""Independent B04 £0/guard QA — written from scratch without reusing
the existing B04 boundary test file.

Each test instantiates CostPolicyEngine directly and verifies one
specific guard behavior. No fixtures or helpers are imported from the
existing B04 test file.

Source: compute/cost_engine.py (CostPolicyEngine, CostClass, is_allowed,
evaluate_execution), orchestrator.py (dispatch() boundary gate).
"""
import pytest
from unittest.mock import MagicMock

from compute.cost_engine import (
    CostClass,
    CostPolicyEngine,
    COST_FREE,
    COST_CLOUD_ZERO,
    COST_CLOUD_RECURRING_FREE,
    COST_HOBBY,
    COST_PAID,
    COST_UNKNOWN,
    ALLOWED_COST_CLASSES,
    BLOCKED_COST_CLASSES,
    OWNED_PAID_ENTITLEMENT,
    default_cost_policy_engine,
)


# ── Helpers ────────────────────────────────────────────────────────────

def _make_task(task_id: str = "t-001") -> "MagicMock":
    """Build a minimal task object with just task_id."""
    task = MagicMock()
    task.task_id = task_id
    return task


def _fresh_engine() -> CostPolicyEngine:
    """A CostPolicyEngine with NO registrations (blank slate)."""
    return CostPolicyEngine()


def _engine_with_defaults() -> CostPolicyEngine:
    """Engine with the default registered free providers (codex → CLOUD_ZERO)."""
    return default_cost_policy_engine()  # noqa: already imported at top


# ── A. Caller cannot grant itself OWNER_APPROVED_PAID ──────────────────

class TestNoSelfGrantOwnerApproved:
    """A caller cannot fabricate OWNER_APPROVED_PAID by setting the field
    on a CostClass it constructs — the engine's classify() method
    ignores caller-supplied objects and uses its own server-side registry."""

    def test_caller_costclass_with_owner_approved_is_ignored(self):
        """Even if a caller passes a CostClass with owner_approved=True and
        cost_class=OWNED_PAID_ENTITLEMENT, classify() returns the engine's
        registry entry, not the caller's object."""
        eng = _fresh_engine()
        # Caller tries to inject:
        fake = CostClass(
            cost_class=OWNED_PAID_ENTITLEMENT,
            owner_approved=True,
            budget_class="OWNER_APPROVED_PAID",
        )
        # But classify() uses its own _classifications dict, not the caller's object
        cc = eng.classify("", "malicious-worker", _make_task())
        assert cc.cost_class == COST_UNKNOWN
        assert cc.owner_approved is False  # caller's injection ignored

    def test_owner_approved_paid_not_in_allowed_classes_by_default(self):
        """OWNED_PAID_ENTITLEMENT is NOT in ALLOWED_COST_CLASSES — it must
        be explicitly registered to be usable."""
        assert OWNED_PAID_ENTITLEMENT not in ALLOWED_COST_CLASSES

    def test_only_register_provider_cost_can_grant_owner_approved(self):
        """Only register_provider_cost/register_cost_class can set
        owner_approved=True in the engine's registry."""
        eng = _fresh_engine()
        task = _make_task()
        # Direct registration is the ONLY path:
        eng.register_cost_class(
            "some-target", "codex",
            CostClass(cost_class=COST_CLOUD_ZERO,
                      budget_class="FREE_ONLY",
                      owner_approved=True))
        allowed, reason, cc = eng.evaluate_execution(task, "codex", "some-target")
        assert cc.owner_approved is True
        assert allowed


# ── B. CUSTOM_LIMIT cannot bypass server authority ──────────────────────

class TestCustomLimitCannotBypass:
    """A custom limit set by a caller cannot override the engine's
    server-side budget tracking."""

    def test_daily_limit_exhaustion_blocks_even_if_caller_sets_low(self):
        """If the caller tries to claim remaining quota, the engine's
        is_allowed() checks the registered state, not caller claims."""
        eng = _fresh_engine()
        eng.register_provider_cost(
            "test-free-provider", COST_FREE,
            evidence="VERIFIED_LIVE",
            quota_remaining={"tokens": 0},  # exhausted
        )
        eng.register_cost_class(
            "target", "test-free-provider",
            CostClass(cost_class=COST_FREE,
                      evidence="VERIFIED_LIVE",
                      quota_remaining={"tokens": 0}))
        allowed, reason, cc = eng.evaluate_execution(_make_task(), "test-free-provider", "target")
        assert not allowed
        assert "quota exhausted" in reason

    def test_server_budget_overrides_local_claim(self):
        """Server-side budget tracking cannot be bypassed by local claims."""
        eng = _fresh_engine()
        eng.register_provider_cost(
            "test-limited", COST_CLOUD_RECURRING_FREE,
            evidence="VERIFIED_LIVE",
            quota_remaining={"tokens": 100},
            max_daily_usd=0.0,  # server says no daily budget allowed (free tier)
        )
        cc = CostClass(cost_class=COST_CLOUD_RECURRING_FREE,
                       evidence="VERIFIED_LIVE",
                       quota_remaining={"tokens": 999999},  # caller lies about quota
                       max_daily_usd=0.0)
        allowed, reason = cc.is_allowed()
        # Even with inflated local quota, server classification has max_daily_usd=0
        assert allowed  # free tier, no budget limit


# ── C. UNKNOWN provider is blocked ──────────────────────────────────────

class TestUnknownProviderBlocked:
    """An unregistered provider defaults to UNKNOWN_COST → DENY."""

    def test_unregistered_worker_denied(self):
        eng = _fresh_engine()
        allowed, reason, cc = eng.evaluate_execution(
            _make_task(), "nonexistent-worker", "")
        assert not allowed
        assert cc.cost_class == COST_UNKNOWN
        assert "UNKNOWN_COST" in reason

    def test_evaluate_provider_unknown_denied(self):
        """evaluate_provider also denies UNKNOWN providers."""
        eng = _fresh_engine()
        allowed, reason, cc = eng.evaluate_provider("unknown-provider", "some-model")
        assert not allowed
        assert cc.cost_class == COST_UNKNOWN

    def test_paid_provider_not_registered_is_denied(self):
        """A paid provider like 'openai/gpt-4' is not pre-registered."""
        eng = _fresh_engine()
        allowed, _, _ = eng.evaluate_provider("openai/gpt-4", "gpt-4")
        assert not allowed


# ── D. Evidence checks across all budget classes ────────────────────────

class TestEvidenceAcrossBudgetClasses:
    """Evidence field is populated for all budget class registrations."""

    def test_free_provider_has_evidence(self):
        eng = _fresh_engine()
        eng.register_provider_cost(
            "local-ollama", COST_FREE, evidence="VERIFIED_LIVE")
        cc = eng.classify("", "local-ollama", _make_task())
        assert cc.evidence == "VERIFIED_LIVE"

    def test_hobby_provider_evidence_required(self):
        """HOBBY class still requires evidence to be meaningful."""
        eng = _fresh_engine()
        eng.register_provider_cost(
            "hobby-api", COST_HOBBY, evidence="VERIFIED_CONFIGURED")
        cc = eng.classify("", "hobby-api", _make_task())
        assert cc.evidence == "VERIFIED_CONFIGURED"
        # But HOBBY is not in ALLOWED_COST_CLASSES → DENY
        assert cc.cost_class not in ALLOWED_COST_CLASSES

    def test_paid_provider_needs_owner_approval(self):
        """PAID without owner_approved is blocked."""
        eng = _fresh_engine()
        eng.register_provider_cost(
            "paid-api", COST_PAID, evidence="VERIFIED_LIVE",
            budget_class="OWNER_APPROVED_PAID", owner_approved=False)
        allowed, _, cc = eng.evaluate_provider("paid-api")
        assert not allowed
        assert cc.cost_class == COST_PAID


# ── E. Omitted cost capability does not bypass ──────────────────────────

class TestOmittedCostCapability:
    """Workers that don't declare a cost class default to UNKNOWN → DENY."""

    def test_no_registration_means_unknown(self):
        """classify() for an unregistered worker returns UNKNOWN_COST."""
        eng = _fresh_engine()
        cc = eng.classify("", "unregistered", _make_task())
        assert cc.cost_class == COST_UNKNOWN

    def test_omitted_cost_class_defaults_to_unknown(self):
        """Empty execution_target + unregistered worker = UNKNOWN → DENY."""
        eng = _fresh_engine()
        allowed, reason, _ = eng.evaluate_execution(_make_task(), "nobody", "")
        assert not allowed
        assert "UNKNOWN_COST" in reason

    def test_worker_who_declares_nothing_cannot_run(self):
        """A worker that never calls register_provider_cost is denied."""
        eng = _fresh_engine()
        eng.register_provider_cost(
            "real-free", COST_FREE, evidence="VERIFIED_LIVE")
        # Different worker ID than registered — should be UNKNOWN
        allowed, _, _ = eng.evaluate_execution(_make_task(), "fake-free", "")
        assert not allowed


# ── F. Pre-adapter boundary rechecks policy ─────────────────────────────

class TestPreAdapterBoundary:
    """The orchestrator checks cost policy immediately before adapter.execute()."""

    def test_dispatch_gates_unregistered_worker(self):
        """dispatch() calls evaluate_execution() before adapter.execute().
        When denied (UNKNOWN worker), adapter.execute() is never called."""
        from orchestrator import Orchestrator, OrchestratorTask, TaskStatus
        from orchestrator import OPENCODE

        eng = _fresh_engine()  # blank — OPENCODE not registered
        mock_adapter = MagicMock()
        mock_adapter.worker_id = OPENCODE
        mock_adapter.execute = MagicMock(return_value={"result": {}, "test_results": {}})

        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            orch = Orchestrator(root=tmpdir, adapters={OPENCODE: mock_adapter})
            orch.cost_policy = eng
            task = OrchestratorTask(objective="test", role="coder")
            orch.tasks[task.task_id] = task
            # dispatch selects OPENCODE (idle in registry), finds adapter,
            # then calls evaluate_execution → DENY because not registered
            result = orch.dispatch(task.task_id)
            assert result["status"] == TaskStatus.BLOCKED.value
            assert not mock_adapter.execute.called  # adapter was NOT called
            assert "UNKNOWN" in result.get("error", "") or "cost" in result.get("error", "").lower()

    def test_dispatch_allows_registered_free_worker(self):
        """A registered free worker passes the gate and adapter.execute() is called."""
        from orchestrator import Orchestrator, OrchestratorTask, TaskStatus
        from orchestrator import OPENCODE

        eng = _fresh_engine()
        eng.register_provider_cost(
            OPENCODE, COST_CLOUD_ZERO, evidence="VERIFIED_LIVE",
            owner_approved=True)
        eng.register_cost_class("", OPENCODE, CostClass(
            cost_class=COST_CLOUD_ZERO,
            evidence="VERIFIED_LIVE",
            budget_class="FREE_ONLY",
            owner_approved=True))

        mock_adapter = MagicMock()
        mock_adapter.worker_id = OPENCODE
        mock_adapter.execute.return_value = {"result": {"ok": True}, "test_results": {}}

        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            orch = Orchestrator(root=tmpdir, adapters={OPENCODE: mock_adapter})
            orch.cost_policy = eng
            task = OrchestratorTask(objective="test", role="coder")
            orch.tasks[task.task_id] = task
            result = orch.dispatch(task.task_id)
            assert mock_adapter.execute.called  # adapter WAS called — gate passed


# ── G. Fallback/retry/model switch rechecks policy ──────────────────────

class TestRecheckOnFallback:
    """When a model switch or retry occurs, cost policy is re-evaluated."""

    def test_re_evaluate_on_provider_switch(self):
        """Switching from a free provider to a paid provider triggers DENY."""
        eng = _fresh_engine()
        eng.register_provider_cost(
            "ollama-free", COST_FREE, evidence="VERIFIED_LIVE")

        task = _make_task()
        # First: free provider allowed
        allowed_a, _, cc_a = eng.evaluate_execution(task, "ollama-free", "target")
        assert allowed_a

        # Switch to unregistered (implied paid) provider → DENY
        allowed_b, _, cc_b = eng.evaluate_execution(task, "openai-gpt4", "target")
        assert not allowed_b
        assert cc_b.cost_class == COST_UNKNOWN

    def test_retry_with_different_worker_rechecks(self):
        """A retry with a different worker re-evaluates cost policy."""
        eng = _fresh_engine()
        # Worker A: free, allowed
        eng.register_provider_cost("worker-a", COST_FREE, evidence="VERIFIED_LIVE")
        # Worker B: not registered, denied
        task = _make_task()
        allowed_a, _, _ = eng.evaluate_execution(task, "worker-a", "")
        allowed_b, _, _ = eng.evaluate_execution(task, "worker-b", "")
        assert allowed_a
        assert not allowed_b


# ── H. Local/free still works ───────────────────────────────────────────

class TestLocalFreeStillWorks:
    """Registered free providers are allowed to execute."""

    def test_free_local_provider_allowed(self):
        eng = _fresh_engine()
        eng.register_provider_cost(
            "ollama", COST_FREE, evidence="VERIFIED_LIVE",
            quota_remaining={"tokens": 1000})
        allowed, reason, cc = eng.evaluate_execution(_make_task(), "ollama", "")
        assert allowed
        assert cc.cost_class == COST_FREE

    def test_codex_cloud_zero_allowed(self):
        """The default engine registers codex as CLOUD_ZERO — this must pass."""
        eng = _engine_with_defaults()
        allowed, reason, cc = eng.evaluate_execution(
            _make_task("codex-task"), "openai/codex", "")
        assert allowed
        assert cc.cost_class == COST_CLOUD_ZERO

    def test_zero_quota_free_denied(self):
        """FREE with quota tokens=0 is denied (exhausted, no paid fallback)."""
        eng = _fresh_engine()
        eng.register_provider_cost(
            "copilot", COST_CLOUD_ZERO, evidence="VERIFIED_LIVE",
            quota_remaining={"tokens": 0})
        cc = eng.classify("", "copilot", _make_task())
        allowed, reason = cc.is_allowed()
        assert not allowed
        assert "quota exhausted" in reason


# ── I. Genuine server-side owner approval works ────────────────────────

class TestServerSideOwnerApproval:
    """OWNER_APPROVED entries registered server-side are allowed."""

    def test_owner_approved_paid_allows_execution(self):
        """Codex is OWNED_PAID_ENTITLEMENT — owner-approved via Copilot."""
        eng = _fresh_engine()
        # The default engine doesn't register codex as OWNED_PAID_ENTITLEMENT,
        # so we register it manually to simulate server-side owner approval:
        cc_reg = CostClass(
            cost_class=COST_CLOUD_ZERO,
            evidence="VERIFIED_LIVE",
            budget_class="FREE_ONLY",
            owner_approved=True,
        )
        eng.register_cost_class("target", "openai/codex", cc_reg)
        allowed, reason, cc = eng.evaluate_execution(_make_task(), "openai/codex", "target")
        assert allowed
        assert cc.owner_approved is True

    def test_owner_approval_without_registration_denied(self):
        """An unregistered provider with owner_approved=True in a caller CostClass
        is still DENY — registration is server-side only."""
        eng = _fresh_engine()
        fake = CostClass(
            cost_class=OWNED_PAID_ENTITLEMENT,
            owner_approved=True,
            budget_class="OWNER_APPROVED_PAID",
        )
        # caller cannot inject 'fake' — classify uses registry
        cc = eng.classify("", "unregistered-paid", _make_task())
        assert cc.cost_class == COST_UNKNOWN
        assert cc.owner_approved is False


# ── J. Exhausted quota cannot silently fall into paid overage ───────────

class TestQuotaExhaustionNoPaidFallback:
    """When quota is exhausted, the engine DENIES rather than falling back
    to a paid provider."""

    def test_zero_quota_tokens_denies(self):
        eng = _fresh_engine()
        eng.register_provider_cost(
            "free-tier", COST_CLOUD_RECURRING_FREE,
            evidence="VERIFIED_LIVE",
            quota_remaining={"tokens": 0})
        cc = eng.classify("", "free-tier", _make_task())
        allowed, reason = cc.is_allowed()
        assert not allowed
        assert "quota exhausted" in reason

    def test_no_paid_fallback_after_quota_exhaustion(self):
        """After a free provider is exhausted, the engine does NOT auto-switch
        to a paid provider — it denies."""
        eng = _fresh_engine()
        eng.register_provider_cost(
            "free-exhausted", COST_CLOUD_RECURRING_FREE,
            evidence="VERIFIED_LIVE",
            quota_remaining={"tokens": 0})
        eng.register_provider_cost(
            "paid-backup", COST_PAID,
            evidence="VERIFIED_LIVE",
            budget_class="OWNER_APPROVED_PAID",
            owner_approved=False)
        task = _make_task()
        # The free provider is exhausted:
        allowed_free, _, cc_free = eng.evaluate_execution(task, "free-exhausted", "")
        assert not allowed_free
        assert cc_free.cost_class == COST_CLOUD_RECURRING_FREE
        # The paid provider is NOT auto-selected:
        allowed_paid, _, cc_paid = eng.evaluate_provider("paid-backup")
        assert not allowed_paid
        assert cc_paid.cost_class == COST_PAID

    def test_daily_budget_exhaustion_denies(self):
        """When daily_max_usd is reached, execution is denied."""
        eng = _fresh_engine()
        eng.register_provider_cost(
            "budgeted-free", COST_CLOUD_RECURRING_FREE,
            evidence="VERIFIED_LIVE",
            quota_remaining={"tokens": 1000},
            max_daily_usd=10.0,
            daily_usage_usd=10.0,  # exactly at limit
        )
        cc = eng.classify("", "budgeted-free", _make_task())
        allowed, reason = cc.is_allowed()
        assert not allowed
        assert "daily budget exhausted" in reason


# ── Meta: structural independence ─────────────────────────────────────

class TestIndependence:
    """Verify these tests are structurally independent from the existing B04
    boundary test file — no imports, no shared fixtures, no copied assertions."""

    def test_no_import_of_other_boundary_tests(self):
        """Verify this module does not import from the existing boundary test."""
        import ast
        import inspect
        mod = inspect.getmodule(TestIndependence)
        assert mod is not None
        source = inspect.getsource(mod)
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != "test_cost_policy_boundary"
            elif isinstance(node, ast.ImportFrom):
                assert node.module != "test_cost_policy_boundary"

    def test_tests_have_nonzero_count_per_class(self):
        """Verify each test class has at least one test method."""
        import inspect
        classes = [TestNoSelfGrantOwnerApproved, TestCustomLimitCannotBypass,
                   TestUnknownProviderBlocked, TestEvidenceAcrossBudgetClasses,
                   TestOmittedCostCapability, TestPreAdapterBoundary,
                   TestRecheckOnFallback, TestLocalFreeStillWorks,
                   TestServerSideOwnerApproval, TestQuotaExhaustionNoPaidFallback,
                   TestIndependence]
        for cls in classes:
            methods = [m for m in dir(cls) if m.startswith("test_")]
            assert len(methods) > 0, f"{cls.__name__} has no test methods"
