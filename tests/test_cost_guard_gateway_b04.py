"""B04 Boundary 2 — the gateway must never dispatch a rejected request.

These tests drive the REAL `AetheriusGateway.infer()` and assert at the
adapter: a refused request must not call `adapter.execute`. That is the
property that matters - not merely that an error object came back, but that no
external model API was touched.

Adapters are stubs. No network call is made and no credential is read.
"""
from __future__ import annotations

import pytest

from compute.cost_engine import (
    COST_CLOUD_ZERO,
    COST_FREE,
    COST_HOBBY,
    COST_PAID,
    COST_UNKNOWN,
    Budget,
    ProviderCostState,
)
from compute.ai_gateway import AetheriusGateway
from models.inference_contract import (
    CUSTOM_LIMIT,
    FREE_ONLY,
    HOBBY_CREDIT_ONLY,
    OWNER_APPROVED_PAID,
    AetheriusInferenceRequest,
)


class SpyAdapter:
    """Records dispatch. Never performs I/O."""

    def __init__(self, provider_id: str = "spy"):
        self.provider_id = provider_id
        self.calls = 0

    def execute(self, request):  # noqa: D401 - stub
        self.calls += 1
        return {
            "content": "ok",
            "model": "stub-model",
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            "cost_usd": 0.0,
            "wall_time_s": 0.01,
        }


class StubRoutingDecision:
    def __init__(self, provider, alternatives=()):
        self.selected_provider = provider
        self.selected_model = "stub-model"
        self.alternatives = list(alternatives)
        # `_build_routing_decision` reads these off the decision.
        self.reasoning = "stub routing decision for B04 boundary tests"


class StubRouter:
    def __init__(self, decision):
        self.decision = decision

    def route(self, **kwargs):
        return self.decision


def build_gateway(monkeypatch, *, provider_id, cost_class, owner_approved=False):
    """A gateway whose router always selects `provider_id`, with a spy adapter."""
    engine = AetheriusGateway.__new__(AetheriusGateway)
    engine._request_count = 0

    cost_engine = AetheriusGateway.__init__.__globals__["CostEngine"](
        default_budget_class=FREE_ONLY)
    cost_engine.set_budget("default", Budget(owner_approved_paid=owner_approved))
    cost_engine.register_provider(ProviderCostState(
        provider_id=provider_id, cost_class=cost_class, evidence="VERIFIED_LIVE"))
    engine.cost_engine = cost_engine

    decision = StubRoutingDecision(provider_id)
    engine.router = StubRouter(decision)

    spy = SpyAdapter(provider_id)

    class Registry:
        def get_adapter(self, pid):
            return spy if pid == provider_id else None

    engine.provider_registry = Registry()
    return engine, spy, decision


def req(**kw):
    base = dict(capability="summarise", budget_class=FREE_ONLY)
    base.update(kw)
    return AetheriusInferenceRequest(**base)


class TestRejectedRequestsNeverDispatch:
    @pytest.mark.parametrize("cost_class", [COST_PAID, COST_HOBBY, COST_UNKNOWN])
    def test_paid_class_never_reaches_adapter(self, cost_class):
        engine, spy, _ = build_gateway(None, provider_id="prov", cost_class=cost_class)
        resp = engine.infer(req())
        assert spy.calls == 0, "adapter.execute must not be called for a denied provider"
        assert resp.error is not None

    @pytest.mark.parametrize("widened", [HOBBY_CREDIT_ONLY, OWNER_APPROVED_PAID, CUSTOM_LIMIT])
    def test_widened_budget_class_never_reaches_adapter(self, widened):
        """The original exploit path, end to end."""
        engine, spy, _ = build_gateway(
            None, provider_id="prov", cost_class=COST_PAID, owner_approved=False)
        resp = engine.infer(req(budget_class=widened))
        assert spy.calls == 0, f"{widened} must not dispatch a paid provider"
        assert resp.error is not None

    def test_unverified_provider_never_reaches_adapter(self):
        engine, spy, _ = build_gateway(None, provider_id="prov", cost_class=COST_FREE)
        engine.cost_engine.providers["prov"].evidence = "STALE_NEEDS_REVERIFY"
        resp = engine.infer(req())
        assert spy.calls == 0
        assert resp.error is not None

    def test_provider_wiped_after_routing_still_cannot_dispatch(self):
        """Proves boundary 2 re-checks rather than trusting boundary 1.

        The provider is registered when routing happens and removed before
        dispatch. Only a fresh check at the dispatch boundary catches this.
        """
        engine, spy, _ = build_gateway(None, provider_id="prov", cost_class=COST_PAID)
        # Boundary 1 runs inside infer(); simulate provider state changing
        # mid-flight by making the eligibility check fail on the second call.
        calls = {"n": 0}
        real = engine.cost_engine.check_eligible

        def flaky(pid, bc="", scope="default"):
            calls["n"] += 1
            if calls["n"] >= 2:
                return False, "simulated: authorisation revoked mid-flight"
            return real(pid, bc, scope)

        engine.cost_engine.check_eligible = flaky
        resp = engine.infer(req())
        assert spy.calls == 0, "second (dispatch-time) check must block"
        assert resp.error is not None


class TestLegitimateRoutesStillWork:
    @pytest.mark.parametrize("cost_class", [COST_FREE, COST_CLOUD_ZERO])
    def test_verified_free_provider_still_dispatches(self, cost_class):
        engine, spy, _ = build_gateway(None, provider_id="prov", cost_class=cost_class)
        resp = engine.infer(req())
        assert spy.calls == 1, "verified free routes must keep working"
        assert resp.error is None

    def test_default_local_inference_still_works(self):
        engine, spy, _ = build_gateway(None, provider_id="local", cost_class=COST_FREE)
        resp = engine.infer(req())
        assert spy.calls == 1
        assert resp.error is None

    def test_owner_approved_paid_still_works_when_actually_authorised(self):
        """The fix must not remove legitimate owner authority."""
        engine, spy, _ = build_gateway(
            None, provider_id="prov", cost_class=COST_PAID, owner_approved=True)
        resp = engine.infer(req(budget_class=OWNER_APPROVED_PAID))
        assert spy.calls == 1
        assert resp.error is None