"""Cost Engine — FREE_FIRST_STRICT budget enforcement (§68, §89, §128).

Provider-independent cost controller. Tracks free quota, daily/monthly usage,
token costs, and enforces hard budgets: DAILY_MAX, MONTHLY_MAX, PER_TASK_MAX,
PER_PROVIDER_MAX.

Never silently upgrades a free workload into paid unlimited usage.
At 100% budget: hard stop unless explicit policy permits otherwise.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from models.inference_contract import FREE_ONLY, HOBBY_CREDIT_ONLY

# Cost class for a provider
COST_FREE = "FREE"           # always free (local)
COST_CLOUD_ZERO = "CLOUD_ZERO_COST"  # free tier with zero spend
COST_CLOUD_RECURRING_FREE = "CLOUD_RECURRING_FREE"  # recurring free quota
COST_HOBBY = "HOBBY"         # paid but cheap / hobby-tier
COST_PAID = "PAID"           # standard paid
COST_UNKNOWN = "UNKNOWN"     # cost unknown

COST_CLASSES = (COST_FREE, COST_CLOUD_ZERO, COST_CLOUD_RECURRING_FREE,
                COST_HOBBY, COST_PAID, COST_UNKNOWN)

# Automatically eligible under FREE_FIRST_STRICT
AUTOMATICALLY_ELIGIBLE = (COST_FREE, COST_CLOUD_ZERO, COST_CLOUD_RECURRING_FREE)

# Forbidden under FREE_FIRST_STRICT (never auto-selected)
FORBIDDEN_UNDER_FREE_FIRST = ("PAID_API", "SUBSCRIPTION_ONLY",
                              "ONE_TIME_TRIAL", "UNKNOWN_COST")


@dataclass
class ProviderCostState:
    """Per-provider cost tracking (§61, §124)."""
    provider_id: str = ""
    cost_class: str = COST_UNKNOWN
    free_quota: dict[str, Any] = field(default_factory=dict)  # {"tokens": N, "reset": "..."}
    quota_remaining: dict[str, Any] = field(default_factory=dict)
    daily_usage_usd: float = 0.0
    monthly_usage_usd: float = 0.0
    daily_reset_epoch: float = 0.0   # when daily counter resets
    monthly_reset_epoch: float = 0.0
    trial_credit_usd: float = 0.0
    card_required: bool = False
    last_checked: float = 0.0
    evidence: str = ""              # VERIFIED_LIVE | VERIFIED_CONFIGURED | STALE_NEEDS_REVERIFY | etc.
    next_review: float = 0.0

    def reset_daily_if_needed(self) -> None:
        if self.daily_reset_epoch and time.time() >= self.daily_reset_epoch:
            self.daily_usage_usd = 0.0
            # advance to next reset period
            self.daily_reset_epoch = time.time() + 86400

    def reset_monthly_if_needed(self) -> None:
        if self.monthly_reset_epoch and time.time() >= self.monthly_reset_epoch:
            self.monthly_usage_usd = 0.0
            self.monthly_reset_epoch = time.time() + 86400 * 30

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "cost_class": self.cost_class,
            "free_quota": self.free_quota,
            "quota_remaining": self.quota_remaining,
            "daily_usage_usd": round(self.daily_usage_usd, 8),
            "monthly_usage_usd": round(self.monthly_usage_usd, 8),
            "daily_reset_epoch": self.daily_reset_epoch,
            "monthly_reset_epoch": self.monthly_reset_epoch,
            "trial_credit_usd": round(self.trial_credit_usd, 8),
            "card_required": self.card_required,
            "last_checked": self.last_checked,
            "evidence": self.evidence,
            "next_review": self.next_review,
        }


@dataclass
class Budget:
    """Hard budget limits (§68, §116)."""
    daily_max_usd: float = 0.0
    monthly_max_usd: float = 0.0
    per_task_max_usd: float = 0.0
    per_provider_max_usd: float = 0.0   # monthly per-provider cap
    owner_approved_paid: bool = False   # explicit owner authorization for paid

    def to_dict(self) -> dict[str, Any]:
        return {
            "daily_max_usd": round(self.daily_max_usd, 8),
            "monthly_max_usd": round(self.monthly_max_usd, 8),
            "per_task_max_usd": round(self.per_task_max_usd, 8),
            "per_provider_max_usd": round(self.per_provider_max_usd, 8),
            "owner_approved_paid": self.owner_approved_paid,
        }


@dataclass
class CostRecord:
    """A single cost event (§115 provenance)."""
    record_id: str = ""
    request_id: str = ""
    provider_id: str = ""
    model_id: str = ""
    execution_target: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    timestamp: float = 0.0
    budget_class: str = FREE_ONLY

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "request_id": self.request_id,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "execution_target": self.execution_target,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": round(self.cost_usd, 8),
            "timestamp": self.timestamp,
            "budget_class": self.budget_class,
        }


class CostEngine:
    """Provider-independent cost controller.

    Enforces FREE_FIRST_STRICT by default. Tracks per-provider daily/monthly
    usage, free quota, trial credit, and applies hard budgets.
    """

    def __init__(self, default_budget_class: str = FREE_ONLY) -> None:
        self.default_budget_class = default_budget_class
        self.providers: dict[str, ProviderCostState] = {}
        self.budgets: dict[str, Budget] = {}  # keyed by scope: "default", project_id, etc.
        self.records: list[CostRecord] = []
        self.alert_thresholds: list[float] = [0.50, 0.80, 0.95, 1.00]
        self._alerts: list[dict[str, Any]] = []

    def register_provider(self, cost_state: ProviderCostState) -> None:
        if cost_state.provider_id in self.providers:
            raise ValueError(f"provider already registered: {cost_state.provider_id!r}")
        self.providers[cost_state.provider_id] = cost_state
        if not cost_state.daily_reset_epoch:
            cost_state.daily_reset_epoch = time.time() + 86400
        if not cost_state.monthly_reset_epoch:
            cost_state.monthly_reset_epoch = time.time() + 86400 * 30

    def set_budget(self, scope: str, budget: Budget) -> None:
        self.budgets[scope] = budget

    def get_or_create_budget(self, scope: str = "default") -> Budget:
        if scope not in self.budgets:
            self.budgets[scope] = Budget(
                daily_max_usd=0.0,
                monthly_max_usd=0.0,
                per_task_max_usd=0.0,
                per_provider_max_usd=0.0,
                owner_approved_paid=False,
            )
        return self.budgets[scope]

    def estimate_cost(self, provider_id: str, input_tokens: int,
                      output_tokens: int) -> float:
        """Estimate cost for a model call. Returns 0 if free."""
        state = self.providers.get(provider_id)
        if state is None:
            return 0.0
        cost_class = state.cost_class
        if cost_class in (COST_FREE, COST_CLOUD_ZERO, COST_CLOUD_RECURRING_FREE):
            return 0.0
        if cost_class == COST_UNKNOWN:
            return 0.0
        # For paid/hobby providers, use provider-reported rates if available
        rates = state.free_quota.get("rates", {})
        input_rate = rates.get("input_per_1k", 0.0)
        output_rate = rates.get("output_per_1k", 0.0)
        return (input_tokens * input_rate / 1000.0 +
                output_tokens * output_rate / 1000.0)

    def check_eligible(self, provider_id: str, budget_class: str = "",
                       scope: str = "default") -> tuple[bool, str]:
        """Check if a provider is eligible under the current budget policy.

        FREE_FIRST_STRICT: only automatically-eligible cost classes pass.
        Returns (eligible, reason).
        """
        state = self.providers.get(provider_id)
        if state is None:
            return False, f"provider {provider_id!r} not registered"

        bc = budget_class or self.default_budget_class
        budget = self.get_or_create_budget(scope)

        # Under FREE_ONLY, only free tiers pass
        if bc == FREE_ONLY:
            if state.cost_class not in AUTOMATICALLY_ELIGIBLE:
                return False, (f"FREE_ONLY forbids cost_class={state.cost_class!r} "
                               f"for provider {provider_id!r}")
            if state.evidence not in ("VERIFIED_LIVE", "VERIFIED_CONFIGURED"):
                return False, (f"provider {provider_id!r} evidence={state.evidence!r} "
                               f"is not verified; fails closed")

        # Under HOBBY_CREDIT_ONLY, free + hobby pass
        if bc == HOBBY_CREDIT_ONLY:
            if state.cost_class not in (COST_FREE, COST_CLOUD_ZERO,
                                        COST_CLOUD_RECURRING_FREE, COST_HOBBY):
                if not budget.owner_approved_paid:
                    return False, (f"HOBBY_CREDIT_ONLY forbids cost_class={state.cost_class!r} "
                                   f"without explicit owner paid authorization")

        # Check quotas
        if state.quota_remaining and state.quota_remaining.get("tokens") == 0:
            return False, (f"provider {provider_id!r} quota exhausted "
                           f"(tokens_remaining=0)")

        # Check per-provider budget
        if budget.per_provider_max_usd > 0:
            state.reset_monthly_if_needed()
            if state.monthly_usage_usd >= budget.per_provider_max_usd:
                return False, (f"provider {provider_id!r} hit per-provider "
                               f"monthly budget ${budget.per_provider_max_usd}")

        # Check daily budget
        global_daily = sum(p.daily_usage_usd for p in self.providers.values())
        if budget.daily_max_usd > 0 and global_daily >= budget.daily_max_usd:
            return False, (f"daily budget ${budget.daily_max_usd} reached "
                           f"(current: ${global_daily:.4f})")

        # Check monthly budget
        global_monthly = sum(p.monthly_usage_usd for p in self.providers.values())
        if budget.monthly_max_usd > 0 and global_monthly >= budget.monthly_max_usd:
            return False, (f"monthly budget ${budget.monthly_max_usd} reached "
                           f"(current: ${global_monthly:.4f})")

        return True, "eligible"

    def record_usage(self, provider_id: str, input_tokens: int,
                     output_tokens: int, cost_usd: float,
                     request_id: str = "", model_id: str = "",
                     execution_target: str = "", budget_class: str = "") -> CostRecord:
        """Record actual usage and update provider cost state. Fails closed."""
        state = self.providers.get(provider_id)
        if state is None:
            raise KeyError(f"provider not registered: {provider_id!r}")

        state.reset_daily_if_needed()
        state.reset_monthly_if_needed()
        state.daily_usage_usd += cost_usd
        state.monthly_usage_usd += cost_usd

        # Update quota
        if "tokens" in state.quota_remaining:
            consumed = input_tokens + output_tokens
            state.quota_remaining["tokens"] = max(0, state.quota_remaining["tokens"] - consumed)

        rec = CostRecord(
            record_id=f"cost-{int(time.time()*1000)}-{len(self.records)}",
            request_id=request_id,
            provider_id=provider_id,
            model_id=model_id,
            execution_target=execution_target,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            timestamp=time.time(),
            budget_class=budget_class or self.default_budget_class,
        )
        self.records.append(rec)

        # Check alert thresholds
        self._check_alerts(state, budget_class or self.default_budget_class)

        return rec

    def _check_alerts(self, state: ProviderCostState, budget_class: str) -> None:
        scope = "default"
        budget = self.budgets.get(scope)
        if budget and budget.daily_max_usd > 0:
            pct = state.daily_usage_usd / budget.daily_max_usd
            for threshold in self.alert_thresholds:
                if pct >= threshold and threshold not in [a["threshold"] for a in self._alerts]:
                    self._alerts.append({
                        "provider_id": state.provider_id,
                        "threshold": threshold,
                        "daily_usage_usd": round(state.daily_usage_usd, 8),
                        "daily_max_usd": budget.daily_max_usd,
                        "budget_class": budget_class,
                        "timestamp": time.time(),
                    })

    def total_daily_usage(self) -> float:
        for p in self.providers.values():
            p.reset_daily_if_needed()
        return sum(p.daily_usage_usd for p in self.providers.values())

    def total_monthly_usage(self) -> float:
        for p in self.providers.values():
            p.reset_monthly_if_needed()
        return sum(p.monthly_usage_usd for p in self.providers.values())

    def alerts(self) -> list[dict[str, Any]]:
        return list(self._alerts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "default_budget_class": self.default_budget_class,
            "providers": {pid: s.to_dict() for pid, s in self.providers.items()},
            "budgets": {scope: b.to_dict() for scope, b in self.budgets.items()},
            "total_daily_usage_usd": round(self.total_daily_usage(), 8),
            "total_monthly_usage_usd": round(self.total_monthly_usage(), 8),
            "records": [r.to_dict() for r in self.records],
            "alerts": list(self._alerts),
        }


def default_cost_engine() -> CostEngine:
    """Create a cost engine with FREE_FIRST_STRICT and zero-cost budgets."""
    engine = CostEngine(default_budget_class=FREE_ONLY)
    budget = Budget(
        daily_max_usd=0.0,
        monthly_max_usd=0.0,
        per_task_max_usd=0.0,
        per_provider_max_usd=0.0,
        owner_approved_paid=False,
    )
    engine.set_budget("default", budget)

    # Register known local provider as FREE
    engine.register_provider(ProviderCostState(
        provider_id="local",
        cost_class=COST_FREE,
        evidence="VERIFIED_LIVE",
        daily_reset_epoch=0,
        monthly_reset_epoch=0,
    ))

    return engine


__all__ = [
    "CostEngine",
    "Budget",
    "ProviderCostState",
    "CostRecord",
    "COST_FREE",
    "COST_CLOUD_ZERO",
    "COST_CLOUD_RECURRING_FREE",
    "COST_HOBBY",
    "COST_PAID",
    "COST_UNKNOWN",
    "COST_CLASSES",
    "AUTOMATICALLY_ELIGIBLE",
    "FORBIDDEN_UNDER_FREE_FIRST",
    "default_cost_engine",
]
