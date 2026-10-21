"""BRIDGE-E2E-006: Deterministic unit test for bridge scope guard contract.

Tests the H01/§19 scope guard:
  (1) a cross-scope message is refused when enforce=True
  (2) a same-scope message is allowed
  (3) violations are recorded regardless of enforce mode

Do NOT modify production code.
"""

from compute.bridge_scope import ScopeGuard, WorkerScope
from compute.agent_message import AgentMessage


def test_bridge_scope_contract():
    """Test the scope guard contract per BRIDGE-E2E-006."""
    guard = ScopeGuard(enforce=True)

    # --- Register two workers in different owner scopes ---
    sender_scope = WorkerScope(
        worker_id="supervisor",
        owner_id="owner-a",
        workspace_id="ws-a",
    )
    receiver_scope = WorkerScope(
        worker_id="opencode-b",
        owner_id="owner-b",
        workspace_id="ws-b",
    )
    guard.register_worker(sender_scope)
    guard.register_worker(receiver_scope)

    # --- (1) cross-scope message is refused when enforce=True ---
    cross_msg = AgentMessage(
        sender_agent="hermes",
        sender_worker="supervisor",
        receiver_agent="opencode",
        receiver_worker="opencode-b",
        owner_id="owner-a",
        workspace_id="ws-a",
    )
    result = guard.check_message(cross_msg)
    assert result["allowed"] is False, (
        f"Expected cross-scope message to be refused with enforce=True, got {result}"
    )

    # --- (2) same-scope message is allowed ---
    same_msg = AgentMessage(
        sender_agent="hermes",
        sender_worker="supervisor",
        receiver_agent="opencode",
        receiver_worker="supervisor",
        owner_id="owner-a",
        workspace_id="ws-a",
    )
    result2 = guard.check_message(same_msg)
    assert result2["allowed"] is True, (
        f"Expected same-scope message to be allowed, got {result2}"
    )

    # --- (3) violations are recorded regardless of enforce mode ---
    assert len(guard.violations()) > 0, (
        "Expected at least one violation recorded for cross-scope attempt"
    )


if __name__ == "__main__":
    test_bridge_scope_contract()
    print("All BRIDGE-E2E-006 contract tests passed!")