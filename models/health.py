"""Model/provider health + circuit breaker (continuous build).

A model/provider failure must NEVER terminate an Agent Bridge workflow.
On repeated failure the breaker trips: record -> circuit-break -> route
another healthy resource -> resume task from checkpoint. After cooldown
and a successful probe the resource rejoins rotation.

States (per routing policy): HEALTHY, DEGRADED, RATE_LIMITED, TIMED_OUT,
INVALID_REQUEST, UNAVAILABLE, BROKEN, COOLDOWN.

Failure kinds recognised: timeout, invalid_request, bad_tool_call,
malformed_output, provider_failure. Unknown kinds count as generic
transient failures (never crash the caller).

Additive only; no import side effects; no I/O. Clock is injectable so
tests stay deterministic (no sleeps).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


class HealthState(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    RATE_LIMITED = "RATE_LIMITED"
    TIMED_OUT = "TIMED_OUT"
    INVALID_REQUEST = "INVALID_REQUEST"
    UNAVAILABLE = "UNAVAILABLE"
    BROKEN = "BROKEN"
    COOLDOWN = "COOLDOWN"


# Failure kinds that map to a terminal (non-retryable-here) state.
_TERMINAL_KIND_STATE = {
    "invalid_request": HealthState.INVALID_REQUEST,
    "provider_failure": HealthState.UNAVAILABLE,
    "timeout": HealthState.TIMED_OUT,
    "rate_limited": HealthState.RATE_LIMITED,
}

# Failure kinds that degrade but keep the resource in rotation briefly.
_DEGRADED_KINDS = frozenset({"bad_tool_call", "malformed_output"})


@dataclass
class BreakerConfig:
    failures_to_trip: int = 3
    degraded_to_trip: int = 5
    cooldown_s: float = 300.0
    rate_limit_cooldown_s: float = 120.0


@dataclass
class BreakerRecord:
    consecutive_failures: int = 0
    degraded_hits: int = 0
    state: HealthState = HealthState.HEALTHY
    cooldown_until: float = 0.0
    last_failure_kind: str = ""
    total_successes: int = 0
    total_failures: int = 0


class CircuitBreaker:
    """Per-resource failure tracking with cooldown and half-open probe."""

    def __init__(self, config: BreakerConfig | None = None,
                 clock: Callable[[], float] | None = None):
        self.config = config or BreakerConfig()
        self._clock = clock or time.monotonic
        self._records: dict[str, BreakerRecord] = {}

    def _rec(self, resource_id: str) -> BreakerRecord:
        return self._records.setdefault(resource_id, BreakerRecord())

    def record_success(self, resource_id: str) -> HealthState:
        rec = self._rec(resource_id)
        rec.consecutive_failures = 0
        rec.degraded_hits = 0
        rec.total_successes += 1
        # A success during/after cooldown closes the breaker (half-open OK).
        rec.state = HealthState.HEALTHY
        rec.cooldown_until = 0.0
        return rec.state

    def record_failure(self, resource_id: str, kind: str = "") -> HealthState:
        rec = self._rec(resource_id)
        kind = (kind or "provider_failure").strip().lower().replace(" ", "_")
        rec.last_failure_kind = kind
        rec.total_failures += 1
        now = self._clock()

        if kind in _DEGRADED_KINDS:
            rec.degraded_hits += 1
            if rec.degraded_hits >= self.config.degraded_to_trip:
                return self._trip(rec, HealthState.BROKEN, now,
                                  self.config.cooldown_s)
            if rec.state == HealthState.HEALTHY:
                rec.state = HealthState.DEGRADED
            return rec.state

        rec.consecutive_failures += 1
        terminal = _TERMINAL_KIND_STATE.get(kind, HealthState.UNAVAILABLE)
        if kind == "rate_limited":
            if rec.consecutive_failures >= self.config.failures_to_trip:
                return self._trip(rec, terminal, now,
                                  self.config.rate_limit_cooldown_s)
        elif rec.consecutive_failures >= self.config.failures_to_trip:
            return self._trip(rec, terminal, now, self.config.cooldown_s)
        # Not yet tripped: single failures degrade but stay routable.
        # Only repeated failure removes the resource from rotation.
        if rec.state == HealthState.HEALTHY:
            rec.state = HealthState.DEGRADED
        return rec.state

    @staticmethod
    def _trip(rec: BreakerRecord, state: HealthState, now: float,
              cooldown_s: float) -> HealthState:
        rec.state = state
        rec.cooldown_until = now + max(0.0, cooldown_s)
        return state

    def state(self, resource_id: str) -> HealthState:
        rec = self._rec(resource_id)
        if rec.state in (HealthState.BROKEN, HealthState.RATE_LIMITED,
                         HealthState.TIMED_OUT, HealthState.UNAVAILABLE,
                         HealthState.INVALID_REQUEST):
            if rec.cooldown_until and self._clock() >= rec.cooldown_until:
                rec.state = HealthState.COOLDOWN
        return rec.state

    def healthy(self, resource_id: str) -> bool:
        """Routing predicate: True only for resources safe to try now."""
        return self.state(resource_id) in (HealthState.HEALTHY,
                                           HealthState.DEGRADED,
                                           HealthState.COOLDOWN)

    def allow_probe(self, resource_id: str) -> bool:
        """Half-open probe: exactly one trial while in COOLDOWN."""
        rec = self._rec(resource_id)
        if self.state(resource_id) == HealthState.COOLDOWN:
            rec.state = HealthState.HEALTHY  # trial; success/failure re-decides
            rec.cooldown_until = 0.0
            return True
        return self.healthy(resource_id)

    def snapshot(self, resource_id: str) -> dict:
        rec = self._rec(resource_id)
        return {"resource": resource_id, "state": self.state(resource_id).value,
                "consecutive_failures": rec.consecutive_failures,
                "degraded_hits": rec.degraded_hits,
                "cooldown_until": rec.cooldown_until,
                "last_failure_kind": rec.last_failure_kind,
                "total_successes": rec.total_successes,
                "total_failures": rec.total_failures}


@dataclass
class ProviderHealthRegistry:
    """One breaker per model/provider id, shared by routers."""

    breaker: CircuitBreaker = field(default_factory=CircuitBreaker)

    def report(self, resource_id: str, ok: bool, kind: str = "") -> HealthState:
        if ok:
            return self.breaker.record_success(resource_id)
        return self.breaker.record_failure(resource_id, kind)

    def healthy(self, resource_id: str) -> bool:
        return self.breaker.healthy(resource_id)

    def pick_first_healthy(self, candidates: list[str]) -> str:
        for cand in candidates:
            if self.breaker.healthy(cand):
                return cand
        return ""
