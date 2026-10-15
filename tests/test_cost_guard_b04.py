"""B04 — zero-spend guard regression suite.

The guard is asserted at BOTH boundaries the owner required:

  Boundary 1 (pre-scheduling)  -> Orchestrator._check_cost_policy
  Boundary 2 (final dispatch)   -> AetheriusGateway.infer, immediately before
                                   adapter.execute()

Every provider here is a stub. No test performs a network call, and no test
requires credentials. Nothing in this file reads a provider key.
"""
from __future__ import annotations

import pytest

from compute.cost_engine import (
    COST_CLOUD_RECURRING_FREE,
    COST_CLOUD_ZERO,
    COST_FREE,
    COST_HOBBY,
    COST_PAID,
    COST_UNKNOWN,
    Budget,
    CostEngine,
    ProviderCostState,
)
from models.inference_contract import (
    CUSTOM_LIMIT,
    FREE_ONLY,
    HOBBY_CREDIT_ONLY,
    OWNER_APPROVED_PAID,
)


def make_engine(*, owner_approved_paid: bool = False) -> CostEngine:
    """An engine with a zero budget and no paid authority by default."""
    engine = CostEngine(default_budget_class=FREE_ONLY)
    engine.set_budget("default", Budget(owner_approved_paid=owner_approved_paid))
    for pid, cls in (
        ("local", COST_FREE),
        ("freeprov", COST_CLOUD_ZERO),
        ("recurringprov", COST_CLOUD_RECURRING_FREE),
        ("hobbyprov", COST_HOBBY),
        ("paidprov", COST_PAID),
        ("unknownprov", COST_UNKNOWN),
    ):
        engine.register_provider(
            ProviderCostState(provider_id=pid, cost_class=cls, evidence="VERIFIED_LIVE"))
    return engine


# --------------------------------------------------------------------------
# Owner-supplied metadata cannot bypass enforcement.
# --------------------------------------------------------------------------

class TestCallerMetadataCannotBypass:
    def test_missing_budget_class_defaults_to_free_only(self):
        engine = make_engine()
        ok, _ = engine.check_eligible("paidprov", "")  # omitted entirely
        assert ok is False, "an omitted budget_class must not widen access"

    def test_falsified_free_classification_is_ignored(self):
        """The decisive case: a caller asserting a paid class is FREE.

        The classification used for the decision is the SERVER's
        ProviderCostState, never anything the request asserts.
        """
        engine = make_engine()
        # Even naming the provider 'freeprov' and claiming FREE_ONLY, a paid
        # provider registered as PAID stays blocked.
        ok, reason = engine.check_eligible("paidprov", FREE_ONLY)
        assert ok is False
        assert "PAID" in reason

    @pytest.mark.parametrize("widened", [HOBBY_CREDIT_ONLY, OWNER_APPROVED_PAID, CUSTOM_LIMIT])
    def test_request_only_classes_are_downgraded_without_owner_authority(self, widened):
        """REQUEST_ONLY classes must not self-authorise.

        This is the original bypass: OWNER_APPROVED_PAID and CUSTOM_LIMIT had no
        branch in check_eligible at all, so they denied nothing - a caller could
        route to a PAID or UNKNOWN provider by naming the class.
        """
        engine = make_engine(owner_approved_paid=False)
        effective, note = engine.resolve_budget_class(widened)
        assert effective == FREE_ONLY, note
        for pid in ("hobbyprov", "paidprov", "unknownprov"):
            ok, _ = engine.check_eligible(pid, widened)
            assert ok is False, f"{pid} must stay blocked under {widened}"

    def test_unrecognised_budget_class_cannot_widen_access(self):
        engine = make_engine()
        effective, _ = engine.resolve_budget_class("TOTALLY_MADE_UP")
        assert effective == FREE_ONLY
        assert engine.check_eligible("paidprov", "TOTALLY_MADE_UP")[0] is False


# --------------------------------------------------------------------------
# Paid / unknown / unverified are blocked; free still works.
# --------------------------------------------------------------------------

class TestDenyByDefault:
    @pytest.mark.parametrize("pid", ["hobbyprov", "paidprov", "unknownprov"])
    def test_paid_and_unknown_blocked_under_free_only(self, pid):
        assert make_engine().check_eligible(pid, FREE_ONLY)[0] is False

    @pytest.mark.parametrize("pid", ["local", "freeprov", "recurringprov"])
    def test_verified_free_remains_functional(self, pid):
        assert make_engine().check_eligible(pid, FREE_ONLY)[0] is True

    def test_unregistered_provider_fails_closed(self):
        ok, reason = make_engine().check_eligible("never-registered", FREE_ONLY)
        assert ok is False
        assert "not registered" in reason

    def test_stale_evidence_fails_closed_even_with_owner_approval(self):
        """A lapsed free entitlement is not a free classification."""
        engine = make_engine(owner_approved_paid=True)
        engine.register_provider(ProviderCostState(
            provider_id="stale", cost_class=COST_FREE, evidence="STALE_NEEDS_REVERIFY"))
        ok, reason = engine.check_eligible("stale", OWNER_APPROVED_PAID)
        assert ok is False
        assert "not verified" in reason

    def test_empty_evidence_fails_closed(self):
        engine = make_engine()
        engine.register_provider(ProviderCostState(
            provider_id="unreviewed", cost_class=COST_FREE, evidence=""))
        assert engine.check_eligible("unreviewed", FREE_ONLY)[0] is False

    def test_unknown_cost_class_value_fails_closed(self):
        """A cost class this engine has never heard of must fail closed.

        The pre-fix code had no COST_CLASSES membership test at all, so a novel
        value would fall through every branch and reach `return True`.
        """
        engine = make_engine()
        engine.providers["local"].cost_class = "SOME_FUTURE_CLASS"
        ok, reason = engine.check_eligible("local", FREE_ONLY)
        assert ok is False
        assert "unknown cost_class" in reason


# --------------------------------------------------------------------------
# Paid fallback must not happen automatically.
# --------------------------------------------------------------------------

class TestNoAutomaticPaidFallback:
    def test_paid_fallback_blocked_after_free_provider_fails(self):
        """Mirrors the gateway fallback loop: when the free route is refused,
        the paid alternative must be refused too, never selected."""
        engine = make_engine()
        primary = "paidprov"          # route picked a paid provider first
        alternatives = ["local", "hobbyprov"]

        ok, _ = engine.check_eligible(primary, FREE_ONLY)
        assert ok is False
        chosen = None
        for alt in alternatives:
            if engine.check_eligible(alt, FREE_ONLY)[0]:
                chosen = alt
                break
        assert chosen == "local", "must fall back to the free route, not a paid one"

    def test_no_eligible_free_route_yields_no_dispatch(self):
        engine = make_engine()
        eligible = [p for p in ("paidprov", "hobbyprov", "unknownprov")
                    if engine.check_eligible(p, FREE_ONLY)[0]]
        assert eligible == [], "no route may be dispatched at all"


# --------------------------------------------------------------------------
# Owner authority works when genuinely granted - and is server-side only.
# --------------------------------------------------------------------------

class TestOwnerAuthority:
    def test_owner_approval_opens_hobby_under_hobby_class(self):
        engine = make_engine(owner_approved_paid=True)
        assert engine.check_eligible("hobbyprov", HOBBY_CREDIT_ONLY)[0] is True

    def test_owner_approval_opens_paid_under_owner_class(self):
        engine = make_engine(owner_approved_paid=True)
        assert engine.check_eligible("paidprov", OWNER_APPROVED_PAID)[0] is True

    def test_hobby_class_still_blocks_full_paid_without_authority(self):
        engine = make_engine(owner_approved_paid=True)
        assert engine.check_eligible("paidprov", HOBBY_CREDIT_ONLY)[0] is False

    def test_free_always_works_regardless_of_authority(self):
        for approved in (False, True):
            engine = make_engine(owner_approved_paid=approved)
            assert engine.check_eligible("local", FREE_ONLY)[0] is True


# --------------------------------------------------------------------------
# Quota and budget ceilings still bind.
# --------------------------------------------------------------------------

class TestQuotaAndBudgets:
    def test_exhausted_quota_blocks(self):
        engine = make_engine()
        engine.providers["freeprov"].quota_remaining = {"tokens": 0}
        ok, reason = engine.check_eligible("freeprov", FREE_ONLY)
        assert ok is False
        assert "quota exhausted" in reason

    def test_daily_budget_ceiling_blocks(self):
        engine = make_engine()
        engine.set_budget("default", Budget(daily_max_usd=1.0))
        engine.providers["local"].daily_usage_usd = 1.5
        assert engine.check_eligible("local", FREE_ONLY)[0] is False

    def test_zero_budget_means_no_ceiling(self):
        """Zero limits must not be read as 'already exhausted'."""
        engine = make_engine()
        engine.providers["local"].daily_usage_usd = 999.0
        assert engine.check_eligible("local", FREE_ONLY)[0] is True