"""BRIDGE-E2E-005: Deterministic unit test for BridgeControlChannel control contract.

Tests the H02/§23 control command lifecycle:
  (1) a granted lease authorizes the worker
  (2) after ch.recall(worker) the worker is no longer authorized
  (3) after ch.grant_lease then ch.emergency_halt(), ch.is_halted is True

Do NOT modify production code.
"""

from compute.bridge_control import BridgeControlChannel


def test_bridge_control_contract():
    """Test the BridgeControlChannel contract per BRIDGE-E2E-005."""
    ch = BridgeControlChannel()

    # --- (1) a granted lease authorizes the worker ---
    lease = ch.grant_lease(worker_id="worker-001", capabilities=("read", "write"))
    result = ch.check_lease("worker-001")
    assert result["authorized"] is True, (
        f"Expected worker to be authorized after grant_lease, got {result}"
    )

    # --- (2) after ch.recall(worker) the worker is no longer authorized ---
    recall_result = ch.recall("worker-001")
    assert recall_result.acknowledged is True, (
        f"Expected recall to be acknowledged, got {recall_result}"
    )
    result_after_recall = ch.check_lease("worker-001")
    assert result_after_recall["authorized"] is False, (
        f"Expected worker to be unauthorized after recall, got {result_after_recall}"
    )

    # --- (3) after ch.grant_lease then ch.emergency_halt(), ch.is_halted is True ---
    ch2 = BridgeControlChannel()
    lease2 = ch2.grant_lease(worker_id="worker-002")
    ch2.emergency_halt()
    assert ch2.is_halted is True, (
        f"Expected is_halted to be True after emergency_halt, got {ch2.is_halted}"
    )


if __name__ == "__main__":
    test_bridge_control_contract()
    print("All BRIDGE-E2E-005 contract tests passed!")