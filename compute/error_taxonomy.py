"""Normalized provider/model error taxonomy (§3).

THE RULE THIS MODULE EXISTS TO ENFORCE

    Routing and failover must operate on NORMALIZED error classes, never on
    provider-specific strings. A provider that returns ``429 Too Many
    Requests`` and one that returns ``rate_limit_exceeded`` must produce the
    SAME normalized class, because failover logic has one place to look.

WHY THIS RECONCILES RATHER THAN REPLACES

``models/inference_contract.py`` already defines 13 error classes (§88) and
five files depend on those names. Replacing them would break the AI Gateway,
health model, model roles, circuit breaker and Hybrid Cloud P0 tests.

So this module is a STRICT SUPERSET:

  * the §88 names keep their existing values and stay authoritative
  * §3's names are added as aliases pointing at the same values
  * both spellings normalise identically, so existing callers are untouched

Capability advertising (§2) is also here: a provider must state honestly
what it supports. An unsupported capability must FAIL OR DOWNGRADE
EXPLICITLY — never be silently ignored.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from models.inference_contract import (
    AUTHENTICATION_ERROR,
    BUDGET_EXCEEDED,
    CONTEXT_EXCEEDED,
    ERROR_CLASSES as CANONICAL_ERROR_CLASSES,
    INVALID_REQUEST,
    MODEL_UNAVAILABLE,
    NETWORK_FAILURE,
    NON_RETRYABLE_ERRORS,
    PRIVACY_VIOLATION,
    PROVIDER_INTERNAL,
    QUOTA_EXHAUSTED,
    RATE_LIMITED,
    RETRYABLE_ERRORS,
    SAFETY_REJECTION,
    TIMEOUT,
    UNSUPPORTED_CAPABILITY,
)

# -- §3 required names --------------------------------------------------------
# §3 asks for a specific vocabulary. These map onto the existing §88 values
# so one logical condition has one value regardless of which spelling a
# caller uses.
AUTH_ERROR = AUTHENTICATION_ERROR
RATE_LIMIT = RATE_LIMITED
QUOTA_EXHAUSTED_ALIAS = QUOTA_EXHAUSTED
PROVIDER_UNAVAILABLE = PROVIDER_INTERNAL
MODEL_UNAVAILABLE_ALIAS = MODEL_UNAVAILABLE
CONTEXT_LIMIT = CONTEXT_EXCEEDED
POLICY_REFUSAL = SAFETY_REJECTION
BUDGET_BLOCKED = BUDGET_EXCEEDED
PRIVACY_BLOCKED = PRIVACY_VIOLATION
UNKNOWN_PROVIDER_ERROR = "UNKNOWN_PROVIDER_ERROR"

# The full §3 vocabulary, in the order §3 lists it.
ERROR_TAXONOMY = (
    AUTH_ERROR,
    RATE_LIMIT,
    QUOTA_EXHAUSTED_ALIAS,
    TIMEOUT,
    PROVIDER_UNAVAILABLE,
    MODEL_UNAVAILABLE_ALIAS,
    INVALID_REQUEST,
    CONTEXT_LIMIT,
    POLICY_REFUSAL,
    UNSUPPORTED_CAPABILITY,
    BUDGET_BLOCKED,
    PRIVACY_BLOCKED,
    UNKNOWN_PROVIDER_ERROR,
)

# Everything routing may legitimately see: the §88 set plus §3's extras.
ALL_ERROR_CLASSES = tuple(dict.fromkeys(CANONICAL_ERROR_CLASSES + ERROR_TAXONOMY))

# -- Retry semantics ---------------------------------------------------------
# Routing must never treat a non-retryable failure as transient. Retrying an
# AUTH_ERROR just burns the request and can trip rate limits.
RETRYABLE = frozenset(RETRYABLE_ERRORS)
NON_RETRYABLE = frozenset(NON_RETRYABLE_ERRORS) | {
    UNSUPPORTED_CAPABILITY,
    BUDGET_BLOCKED,
    PRIVACY_BLOCKED,
    UNKNOWN_PROVIDER_ERROR,
}

# Which classes legitimately trigger FAILOVER to another provider/target.
# A budget or privacy block must NOT fail over: moving the same request to a
# paid or remote provider would violate the constraint that caused the block.
FAILOVER_ELIGIBLE = frozenset({
    RATE_LIMITED,
    QUOTA_EXHAUSTED,
    TIMEOUT,
    PROVIDER_INTERNAL,
    MODEL_UNAVAILABLE,
    NETWORK_FAILURE,
})

# Classes that must be escalated to the owner rather than auto-routed.
OWNER_ATTENTION = frozenset({
    AUTHENTICATION_ERROR,   # credentials need rotation
    BUDGET_BLOCKED,         # spend policy, not a fault
    PRIVACY_BLOCKED,        # data-handling policy, not a fault
})

# -- Provider-specific string -> normalized class ----------------------------
# Adapters translate raw provider text into these classes. Matching is
# case-insensitive substring matching, so it tolerates provider phrasing
# differences without an exhaustive enum per vendor.
_PROVIDER_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (AUTHENTICATION_ERROR, (
        "unauthorized", "unauthenticated", "invalid api key", "invalid_api_key",
        "authentication", "auth_error", "forbidden", "permission denied",
        "401", "invalid token", "bad credentials", "apikey",
    )),
    (RATE_LIMITED, (
        "rate limit", "rate_limit", "ratelimit", "too many requests",
        "429", "throttl", "slow down",
    )),
    (QUOTA_EXHAUSTED, (
        "quota", "insufficient_quota", "insufficient quota", "billing",
        "credit exhausted", "out of credits",
    )),
    (TIMEOUT, ("timeout", "timed out", "deadline exceeded", "etimedout")),
    (MODEL_UNAVAILABLE, (
        "model not found", "model_not_found", "does not exist", "unknown model",
        "model unavailable", "no such model", "model_overloaded",
    )),
    (CONTEXT_EXCEEDED, (
        "context length", "context_length", "too long", "maximum context",
        "token limit", "max_tokens", "context window",
    )),
    (INVALID_REQUEST, (
        "invalid request", "invalid_request", "bad request", "malformed",
        "validation error", "missing required", "400", "unprocessable",
    )),
    (SAFETY_REJECTION, (
        "safety", "content policy", "content_filter", "refus", "blocked by",
        "policy violation", "moderation",
    )),
    (UNSUPPORTED_CAPABILITY, (
        "unsupported", "not supported", "capability not available",
        "feature not enabled",
    )),
    (NETWORK_FAILURE, (
        "connection", "network", "dns", "unreachable", "econnreset",
        "socket", "ssl", "tls", "502", "503", "504",
    )),
    (PROVIDER_INTERNAL, (
        "internal", "server error", "500", "bad gateway", "unavailable",
        "overloaded", "capacity",
    )),
)


def normalize_error(raw: Any) -> str:
    """Map a provider-specific error to a normalized class.

    Unrecognised text becomes ``UNKNOWN_PROVIDER_ERROR`` — never silently a
    success, and never a guess at a retryable class.
    """
    if raw is None:
        return UNKNOWN_PROVIDER_ERROR
    text = str(raw).strip().lower()
    if not text:
        return UNKNOWN_PROVIDER_ERROR
    # An already-normalized class is returned unchanged (idempotent).
    upper = str(raw).strip().upper()
    if upper in ALL_ERROR_CLASSES:
        return upper
    for error_class, patterns in _PROVIDER_PATTERNS:
        for pattern in patterns:
            if pattern in text:
                return error_class
    return UNKNOWN_PROVIDER_ERROR


def is_retryable(error_class: str) -> bool:
    """Only genuinely transient failures may be retried."""
    normalized = normalize_error(error_class)
    if normalized in NON_RETRYABLE:
        return False
    return normalized in RETRYABLE


def should_failover(error_class: str) -> bool:
    """Failover eligibility — budget/privacy blocks must NOT fail over."""
    return normalize_error(error_class) in FAILOVER_ELIGIBLE


def requires_owner(error_class: str) -> bool:
    """Classes that need a human, not another provider."""
    return normalize_error(error_class) in OWNER_ATTENTION


def routing_action(error_class: str) -> str:
    """Single decision surface for routing/failover (§3).

    Returns one of RETRY / FAILOVER / STOP / ESCALATE_OWNER.
    """
    normalized = normalize_error(error_class)
    if normalized in OWNER_ATTENTION:
        return "ESCALATE_OWNER"
    if normalized in FAILOVER_ELIGIBLE:
        # Rate limits and quotas are retryable; hard outages fail over.
        return "RETRY" if normalized in RETRYABLE else "FAILOVER"
    if normalized in NON_RETRYABLE:
        return "STOP"
    return "FAILOVER" if normalized in RETRYABLE else "STOP"


# -- §2 capability advertising ----------------------------------------------
# Every capability a provider might advertise. A provider declares support
# honestly; anything undeclared is unsupported by definition.
CAP_PROMPT_CACHING = "prompt_caching"
CAP_REASONING = "reasoning_controls"
CAP_LOGPROBS = "logprobs"
CAP_BATCH = "batch"
CAP_STRUCTURED_OUTPUT = "structured_output"
CAP_TOOL_CALLING = "tool_calling"
CAP_VISION = "vision"
CAP_AUDIO = "audio"
CAP_STREAMING = "streaming"

ALL_CAPABILITIES = (
    CAP_PROMPT_CACHING,
    CAP_REASONING,
    CAP_LOGPROBS,
    CAP_BATCH,
    CAP_STRUCTURED_OUTPUT,
    CAP_TOOL_CALLING,
    CAP_VISION,
    CAP_AUDIO,
    CAP_STREAMING,
)

# A capability may be fully supported, degraded (works with limits), or absent.
SUPPORT_FULL = "full"
SUPPORT_DEGRADED = "degraded"
SUPPORT_NONE = "none"


@dataclass
class ProviderCapabilities:
    """Honest capability declaration (§2).

    ``supports`` must name only capabilities genuinely available. Requesting
    an unsupported capability raises rather than being silently ignored —
    silent degradation is how a routing layer ends up trusting a result that
    was never really produced.
    """

    provider_id: str
    supports: frozenset[str] = field(default_factory=frozenset)
    degraded: frozenset[str] = field(default_factory=frozenset)
    notes: dict[str, str] = field(default_factory=dict)

    def support_level(self, capability: str) -> str:
        if capability in self.supports:
            return SUPPORT_FULL
        if capability in self.degraded:
            return SUPPORT_DEGRADED
        return SUPPORT_NONE

    def check(self, capability: str) -> str:
        """Raise on unsupported, warn-level string on degraded."""
        level = self.support_level(capability)
        if level == SUPPORT_NONE:
            raise UnsupportedCapabilityError(
                f"provider '{self.provider_id}' does not support "
                f"'{capability}'"
            )
        return level

    def as_dict(self) -> dict:
        return {
            "provider_id": self.provider_id,
            "supported": sorted(self.supports),
            "degraded": sorted(self.degraded),
            "unsupported": sorted(
                c for c in ALL_CAPABILITIES if self.support_level(c) == SUPPORT_NONE
            ),
            "notes": dict(self.notes),
        }


class UnsupportedCapabilityError(RuntimeError):
    """Raised when a capability is requested that a provider cannot honour."""


class NormalizedProviderError(RuntimeError):
    """Provider error carrying a normalized class, not vendor text."""

    def __init__(self, error_class: str, message: str,
                 provider_id: str | None = None,
                 retryable: bool | None = None):
        self.error_class = normalize_error(error_class)
        self.provider_id = provider_id
        self.message = message
        self.retryable = (is_retryable(self.error_class)
                          if retryable is None else retryable)
        super().__init__(f"[{self.error_class}] {message}")

    @property
    def failover_eligible(self) -> bool:
        return should_failover(self.error_class)

    @property
    def requires_owner(self) -> bool:
        return requires_owner(self.error_class)

    @property
    def action(self) -> str:
        return routing_action(self.error_class)
