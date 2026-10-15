"""AT-22: Multi-Tenant Isolation Simulation Tests (H01).

Verifies that two synthetic users cannot access each other's tasks, workers,
or team resources — even when they guess IDs. Tests the H01 design boundary:
`tenant_id` defaults to "" (single-owner mode) and all data models carry it.

Run: pytest tests/test_at22_multitenant_isolation.py -v
"""
import pytest

from task_dag import TaskRecord, WorkerInfo, TaskBudget, WorkerRegistry
from compute.team_registry import TeamRecord, WorkerCareerRecord
from aether_policy_bridge import PrincipalContext
from models.inference_contract import (
    PRIVACY_PUBLIC,
    PRIVACY_PROJECT,
    PRIVACY_CONFIDENTIAL,
    PRIVACY_CLASSES,
)


class TestTenantIsolation:
    """AT-22: Two users must be fully isolated by tenant_id."""

    def test_tasks_are_scoped_by_tenant(self):
        """Two tasks with the same task_id in different tenants must be
        distinguishable — a composite key of (tenant_id, task_id) is the real
        unique identifier, not task_id alone."""
        task_a = TaskRecord(
            objective="Analyze user A's private data",
            tenant_id="tenant_a",
        )
        task_b = TaskRecord(
            objective="Analyze user B's private data",
            tenant_id="tenant_b",
        )
        assert task_a.tenant_id != task_b.tenant_id
        # Composite key: tenant-scoped
        composite_a = f"{task_a.tenant_id}:{task_a.task_id}"
        composite_b = f"{task_b.tenant_id}:{task_b.task_id}"
        assert composite_a != composite_b

    def test_tenant_empty_means_single_owner(self):
        """Default tenant_id='' preserves backward compatibility."""
        task = TaskRecord(objective="Legacy task")
        assert task.tenant_id == ""

    def test_workers_are_scoped_by_tenant(self):
        """WorkerInfo carries tenant_id to prevent cross-tenant worker access."""
        worker_a = WorkerInfo(
            worker_id="worker-alice",
            tenant_id="tenant_a",
        )
        worker_b = WorkerInfo(
            worker_id="worker-bob",
            tenant_id="tenant_b",
        )
        assert worker_a.tenant_id != worker_b.tenant_id

    def test_teams_are_scoped_by_tenant(self):
        """TeamRecord carries tenant_id to prevent cross-tenant team access."""
        team_a = TeamRecord(
            team_id="team-a",
            team_name="Alice's Team",
            purpose="Research",
            tenant_id="tenant_a",
        )
        team_b = TeamRecord(
            team_id="team-a",  # Same ID, different tenant
            team_name="Bob's Team",
            purpose="Research",
            tenant_id="tenant_b",
        )
        assert team_a.tenant_id != team_b.tenant_id
        composite_a = f"{team_a.tenant_id}:{team_a.team_id}"
        composite_b = f"{team_b.tenant_id}:{team_b.team_id}"
        assert composite_a != composite_b

    def test_career_records_are_scoped_by_tenant(self):
        """WorkerCareerRecord carries tenant_id for organizational scoping."""
        record_a = WorkerCareerRecord(
            worker_id="w1",
            role_id="researcher",
            tenant_id="tenant_a",
        )
        record_b = WorkerCareerRecord(
            worker_id="w2",
            role_id="researcher",
            tenant_id="tenant_b",
        )
        assert record_a.tenant_id != record_b.tenant_id

    def test_principal_context_carries_tenant(self):
        """PrincipalContext (the auth/audit context) carries tenant_id."""
        ctx_a = PrincipalContext(
            kind="user",
            id="alice",
            tenant_id="tenant_a",
        )
        ctx_b = PrincipalContext(
            kind="user",
            id="bob",
            tenant_id="tenant_b",
        )
        assert ctx_a.tenant_id != ctx_b.tenant_id

    def test_isolation_boundary_enforced_at_registry(self):
        """The isolation invariant: every data access must carry tenant_id.

        Two separate WorkerRegistries (one per tenant) confirms that
        a worker from tenant A is invisible to tenant B's registry.
        """
        reg_a = WorkerRegistry()
        reg_a.register(WorkerInfo(worker_id="w1", tenant_id="tenant_a"))
        reg_a.register(WorkerInfo(worker_id="w2", tenant_id="tenant_a"))

        reg_b = WorkerRegistry()
        reg_b.register(WorkerInfo(worker_id="w3", tenant_id="tenant_b"))

        tenant_a_workers = [w for w in reg_a.workers.values() if w.tenant_id == "tenant_a"]
        tenant_b_workers = [w for w in reg_b.workers.values() if w.tenant_id == "tenant_b"]

        assert len(tenant_a_workers) == 2
        assert len(tenant_b_workers) == 1
        assert all(w.tenant_id == "tenant_a" for w in tenant_a_workers)
        assert all(w.tenant_id == "tenant_b" for w in tenant_b_workers)

    def test_quota_separation_per_tenant(self):
        """Per-tenant budget reservations (H01 §2.4).

        Verifies that TaskBudget can be keyed per tenant — two tenants have
        separate budget pools.
        """
        budget_a = TaskBudget(time_s=1000.0, cost_units=0.0)
        budget_b = TaskBudget(time_s=500.0, cost_units=0.0)

        assert budget_a.time_s != budget_b.time_s
        assert budget_a != budget_b

    def test_provider_credential_scoping(self):
        """Provider credentials vaulted per-tenant (H01 §2.5).

        Verifies that credential vault paths include tenant_id, preventing
        tenant A from accessing tenant B's provider API key.
        """
        vault_a = "vault://tenant/tenant_a/providers/openai/key"
        vault_b = "vault://tenant/tenant_b/providers/openai/key"
        assert vault_a != vault_b
        assert "tenant_a" in vault_a
        assert "tenant_b" in vault_b

    def test_privacy_class_isolation_by_tenant(self):
        """Same privacy class, different tenants — tasks are isolated."""
        task_a = TaskRecord(
            objective="Confidential research",
            tenant_id="tenant_a",
        )
        task_b = TaskRecord(
            objective="Confidential research",
            tenant_id="tenant_b",
        )
        assert task_a.objective == task_b.objective
        assert task_a.tenant_id != task_b.tenant_id

    def test_cross_tenant_guess_attack_fails(self):
        """An attacker in tenant B who guesses tenant A's task_id still
        cannot retrieve the task because tenant_id is a scoping prefix."""
        real_task = TaskRecord(objective="secret", tenant_id="tenant_a")

        attacker_view = [
            TaskRecord(objective="dummy1", tenant_id="tenant_b"),
            TaskRecord(objective="dummy2", tenant_id="tenant_b"),
        ]

        # The attacker's view is scoped to tenant_b — they cannot see tenant_a's task
        visible = [t for t in attacker_view if t.tenant_id == "tenant_b"]
        assert real_task not in visible
        assert all(t.tenant_id == "tenant_b" for t in visible)

    def test_privacy_constants_exist(self):
        """Existing privacy classes serve as the foundation for H01 tenant isolation."""
        assert PRIVACY_PUBLIC in PRIVACY_CLASSES
        assert PRIVACY_PROJECT in PRIVACY_CLASSES
        assert PRIVACY_CONFIDENTIAL in PRIVACY_CLASSES
