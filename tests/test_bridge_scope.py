"""H01 bridge scoping tests (AT-22 ready, single-owner today).

The canonical envelope carries owner_id / workspace_id / tenant_id. These
tests prove:
- Backward compatibility: empty scope = sole owner, existing messages unaffected
- Round-trip: scope survives to_dict/from_dict
- Cross-scope refusal when enforcement is enabled
- Violations are recorded (auditable) even when not refused
- The schema is multi-tenant-ready WITHOUT pretending multi-user exists
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from compute.agent_message import (
    AgentMessage,
    Intent,
    build_task_assign,
)
from compute.agent_message_bus import AgentMessageBus
from compute.bridge_scope import (
    DEFAULT_WORKSPACE,
    SOLE_OWNER,
    ScopeGuard,
    WorkerScope,
    normalize_scope,
    scopes_equal,
)


# --- scope normalisation ---------------------------------------------------------

class TestScopeNormalization:
    def test_empty_scope_is_sole_owner(self):
        """Empty values denote the sole-owner default (V2 H12)."""
        assert normalize_scope("", "", "") == (SOLE_OWNER, DEFAULT_WORKSPACE, "")

    def test_scope_equality(self):
        a = normalize_scope("", "", "")
        b = normalize_scope("", "", "")
        assert scopes_equal(a, b) is True

    def test_different_scopes_not_equal(self):
        a = normalize_scope("owner-a", "ws-1", "")
        b = normalize_scope("owner-b", "ws-1", "")
        assert scopes_equal(a, b) is False


# --- envelope backward compatibility --------------------------------------------------

class TestEnvelopeScopeBackwardCompat:
    def test_default_scope_is_sole_owner(self):
        """Existing messages without scope fields still work (single owner)."""
        msg = AgentMessage(task_id="T-1", intent=Intent.DM)
        assert msg.owner_id == ""
        assert msg.workspace_id == ""
        assert msg.tenant_id == ""

    def test_scope_roundtrip(self):
        """Scope survives serialisation."""
        msg = AgentMessage(
            task_id="T-2", intent=Intent.TASK_ASSIGN,
            owner_id="owner-a", workspace_id="ws-1", tenant_id="tenant-x")
        msg2 = AgentMessage.from_dict(msg.to_dict())
        assert msg2.owner_id == "owner-a"
        assert msg2.workspace_id == "ws-1"
        assert msg2.tenant_id == "tenant-x"

    def test_empty_scope_roundtrip(self):
        msg = AgentMessage(task_id="T-3", intent=Intent.DM)
        msg2 = AgentMessage.from_dict(msg.to_dict())
        assert msg2.owner_id == ""
        assert msg2.workspace_id == ""

    def test_old_dict_without_scope_loads(self):
        """A dict serialised BEFORE the scope fields existed still loads."""
        d = AgentMessage(task_id="T-4", intent=Intent.DM).to_dict()
        del d["scope"]  # simulate an old serialisation
        msg = AgentMessage.from_dict(d)
        assert msg.owner_id == ""
        assert msg.tenant_id == ""

    def test_build_task_assign_accepts_scope(self):
        msg = build_task_assign(
            task_id="T-5", objective="test",
            owner_id="owner-a", workspace_id="ws-1", tenant_id="tenant-x")
        assert msg.owner_id == "owner-a"
        assert msg.workspace_id == "ws-1"
        assert msg.tenant_id == "tenant-x"


# --- scope guard: single-owner mode (today) ---------------------------------------------

class TestScopeGuardSingleOwner:
    def test_single_owner_default_no_violation(self):
        """Today: all messages default to sole-owner scope and pass."""
        guard = ScopeGuard(enforce=False)
        guard.register_worker(WorkerScope(worker_id="hermes/supervisor"))
        guard.register_worker(WorkerScope(worker_id="opencode/opencode-01"))
        msg = AgentMessage(
            task_id="T-10", intent=Intent.TASK_ASSIGN,
            sender_agent="hermes", sender_worker="supervisor",
            receiver_agent="opencode", receiver_worker="opencode-01")
        result = guard.check_message(msg)
        assert result["allowed"] is True
        assert result["violation"] is False

    def test_no_guard_wired_passes(self, tmp_path):
        """Without a guard wired, the bus check is a pass-through."""
        bus = AgentMessageBus(db_path=Path(tmp_path) / "bus.db")
        msg = AgentMessage(task_id="T-11", intent=Intent.DM)
        assert bus.check_scope(msg)["allowed"] is True

    def test_unregistered_worker_passes(self):
        """Unregistered workers are sole-owner by default (backward compat)."""
        guard = ScopeGuard()
        msg = AgentMessage(
            task_id="T-12", intent=Intent.TASK_ASSIGN,
            sender_agent="opencode", sender_worker="unregistered",
            receiver_agent="hermes", receiver_worker="supervisor")
        result = guard.check_message(msg)
        assert result["allowed"] is True


# --- scope guard: enforcement mode (multi-owner ready) ------------------------------------

class TestScopeGuardEnforcement:
    def _registered_guard(self):
        """A guard with two owners registered, enforcement ON."""
        guard = ScopeGuard(enforce=True)
        guard.register_worker(WorkerScope(
            worker_id="hermes/supervisor",
            owner_id="owner-a", workspace_id="ws-a"))
        guard.register_worker(WorkerScope(
            worker_id="opencode/opencode-a",
            owner_id="owner-a", workspace_id="ws-a"))
        guard.register_worker(WorkerScope(
            worker_id="opencode/opencode-b",
            owner_id="owner-b", workspace_id="ws-b"))
        return guard

    def test_cross_owner_message_refused(self):
        """AT-22: a message crossing owners is refused under enforcement."""
        guard = self._registered_guard()
        msg = AgentMessage(
            task_id="X-1", intent=Intent.TASK_ASSIGN,
            sender_agent="hermes", sender_worker="supervisor",
            receiver_agent="opencode", receiver_worker="opencode-b",
            owner_id="owner-a", workspace_id="ws-a")
        result = guard.check_message(msg)
        assert result["allowed"] is False
        assert result["violation"] is True

    def test_same_scope_message_allowed(self):
        guard = self._registered_guard()
        msg = AgentMessage(
            task_id="X-2", intent=Intent.TASK_ASSIGN,
            sender_agent="hermes", sender_worker="supervisor",
            receiver_agent="opencode", receiver_worker="opencode-a",
            owner_id="owner-a", workspace_id="ws-a")
        result = guard.check_message(msg)
        assert result["allowed"] is True

    def test_violation_recorded_even_when_not_refused(self):
        """Violations are AUDITABLE even in single-owner (non-enforcing) mode."""
        guard = ScopeGuard(enforce=False)
        guard.register_worker(WorkerScope(
            worker_id="hermes/supervisor",
            owner_id="owner-a", workspace_id="ws-a"))
        guard.register_worker(WorkerScope(
            worker_id="opencode/opencode-b",
            owner_id="owner-b", workspace_id="ws-b"))
        msg = AgentMessage(
            task_id="X-3", intent=Intent.TASK_ASSIGN,
            sender_agent="hermes", sender_worker="supervisor",
            receiver_agent="opencode", receiver_worker="opencode-b",
            owner_id="owner-a", workspace_id="ws-a")
        result = guard.check_message(msg)
        # Single-owner mode: logged but allowed (only one scope exists today)
        assert result["allowed"] is True
        assert result["violation"] is True
        assert len(guard.violations()) == 1

    def test_enforcement_can_be_enabled(self):
        """Turning enforcement on is a config change, not an architecture change."""
        guard = ScopeGuard(enforce=False)
        guard.register_worker(WorkerScope(
            worker_id="hermes/supervisor",
            owner_id="owner-a", workspace_id="ws-a"))
        guard.register_worker(WorkerScope(
            worker_id="opencode/opencode-b",
            owner_id="owner-b", workspace_id="ws-b"))
        msg = AgentMessage(
            task_id="X-4", intent=Intent.TASK_ASSIGN,
            sender_agent="hermes", sender_worker="supervisor",
            receiver_agent="opencode", receiver_worker="opencode-b",
            owner_id="owner-a", workspace_id="ws-a")
        assert guard.check_message(msg)["allowed"] is True  # single-owner today
        guard.enable_enforcement()
        assert guard.check_message(msg)["allowed"] is False  # multi-owner: refused

    def test_worker_extra_workspace_grant(self):
        """A worker can be granted additional workspaces within its owner."""
        guard = ScopeGuard(enforce=True)
        guard.register_worker(WorkerScope(
            worker_id="opencode/oc-1",
            owner_id="owner-a", workspace_id="ws-a",
            granted_workspaces=("ws-shared",)))
        assert guard.check_action("opencode/oc-1", "owner-a", "ws-shared") is True
        assert guard.check_action("opencode/oc-1", "owner-a", "ws-other") is False
        assert guard.check_action("opencode/oc-1", "owner-b", "ws-shared") is False

    def test_action_violation_recorded(self):
        guard = ScopeGuard(enforce=True)
        guard.register_worker(WorkerScope(
            worker_id="opencode/oc-1", owner_id="owner-a", workspace_id="ws-a"))
        guard.check_action("opencode/oc-1", "owner-b", "ws-b")
        violations = guard.violations()
        assert len(violations) == 1
        assert violations[0]["kind"] == "action_scope_violation"

    def test_summary_states_single_owner_mode(self):
        """Honest summary: the mode is stated, not pretended away."""
        guard = ScopeGuard()
        s = guard.summary()
        assert s["mode"] == "single-owner (default)"
        assert "single-owner" in s["note"]


# --- bus integration -------------------------------------------------------------------

class TestBusScopeIntegration:
    def test_bus_with_scope_guard(self, tmp_path):
        """The bus can gate messages through a wired scope guard."""
        bus = AgentMessageBus(db_path=Path(tmp_path) / "bus.db")
        guard = ScopeGuard(enforce=True)
        guard.register_worker(WorkerScope(
            worker_id="hermes/supervisor",
            owner_id="owner-a", workspace_id="ws-a"))
        guard.register_worker(WorkerScope(
            worker_id="opencode/opencode-b",
            owner_id="owner-b", workspace_id="ws-b"))
        bus.set_scope_guard(guard)

        msg = AgentMessage(
            task_id="BS-1", intent=Intent.TASK_ASSIGN,
            sender_agent="hermes", sender_worker="supervisor",
            receiver_agent="opencode", receiver_worker="opencode-b",
            owner_id="owner-a", workspace_id="ws-a")
        result = bus.check_scope(msg)
        assert result["allowed"] is False

    def test_scoped_task_assign_full_cycle(self, tmp_path):
        """A scoped task round-trips through the durable bus intact."""
        bus = AgentMessageBus(db_path=Path(tmp_path) / "bus.db")
        msg = build_task_assign(
            task_id="BS-2", objective="scoped work",
            sender_agent="hermes", sender_worker="supervisor",
            receiver_agent="opencode", receiver_worker="opencode-01",
            owner_id="owner-a", workspace_id="ws-1")
        bus.submit(msg)
        messages = bus.get_outbox("hermes", "supervisor")
        assert messages[0]["task_id"] == "BS-2"
