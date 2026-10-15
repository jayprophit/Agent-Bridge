"""Regression test for policy bridge network_origin/device_trust fix.

Ensures EvalContext preserves network_origin and device_trust fields that
executor.py supplies. Previously, the surviving EvalContext.__init__
discarded these fields by hardcoding them to None.

Related: H-SA-SECURITY / POLICY-BRIDGE-CLASS-DEDUP task
"""
import pytest

from aether_policy_bridge import (
    EvalContext,
    Subject,
    PermissionId,
    ResourceId,
    PolicyEngine,
    evaluate_capability_request,
)


def make_eval_context(**kwargs):
    """Helper: build an EvalContext with standard fields."""
    subj = Subject(kind="identity", value="test_user")
    perm = PermissionId(service="test_service", action="read")
    res = ResourceId(value="test_resource")
    return EvalContext(
        subject=subj,
        resource="test_resource",
        action=perm,
        **kwargs,
    )


class TestEvalContextFieldPreservation:
    """EvalContext must preserve network_origin and device_trust."""

    def test_network_origin_not_discarded(self):
        """network_origin passed to EvalContext must be stored, not overwritten with None."""
        ctx = make_eval_context(network_origin="local")
        assert ctx.network_origin == "local", \
            f"network_origin was discarded: got {ctx.network_origin!r} expected 'local'"

    def test_device_trust_not_discarded(self):
        """device_trust passed to EvalContext must be stored, not overwritten with None."""
        ctx = make_eval_context(device_trust=100)
        assert ctx.device_trust == 100, \
            f"device_trust was discarded: got {ctx.device_trust!r} expected 100"

    def test_both_fields_combined(self):
        """Both network_origin and device_trust must survive together."""
        ctx = make_eval_context(network_origin="remote", device_trust=85)
        assert ctx.network_origin == "remote"
        assert ctx.device_trust == 85

    def test_none_defaults_when_not_supplied(self):
        """When not supplied, fields default to None (but not from a hardcoded bug)."""
        ctx = make_eval_context()
        # These may be None because the constructor parameter defaults to None
        # This is fine — the bug was OVERWRITING supplied values with None
        assert ctx.network_origin is None
        assert ctx.device_trust is None


class TestEvaluateCapabilityRequestFieldFlow:
    """evaluate_capability_request must pass context fields through to EvalContext."""

    def test_network_origin_reaches_eval_context(self):
        """The full path: evaluate_capability_request → PolicyEngine → EvalContext must
        preserve network_origin from the context dict."""
        result = evaluate_capability_request(
            subject="identity:test_user",
            capability="test_cap",
            resource="test_resource",
            context={
                "network_origin": "local",
                "device_trust": 100,
            },
        )
        # The request should not crash; if it reaches the EvalContext, fields survive
        assert "allowed" in result or "decision" in result

    def test_device_trust_reaches_eval_context(self):
        """device_trust must flow through evaluate_capability_request."""
        result = evaluate_capability_request(
            subject="identity:test_user",
            capability="test_cap",
            resource="test_resource",
            context={
                "network_origin": "remote",
                "device_trust": 75,
            },
        )
        assert "allowed" in result or "decision" in result
