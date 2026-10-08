"""Canonical Aetherius Inference Request/Response Contract (§87).

Provider-independent schemas. Genesis must not need provider-specific
request structures. Provider-specific objects are translated inside
provider adapters.

All schemas are plain dataclasses with to_dict/from_dict for JSON
serialisation. No external dependencies.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any


# -- Privacy classification --------------------------------------------------
PRIVACY_PUBLIC = "PUBLIC"
PRIVACY_PROJECT = "PROJECT"
PRIVACY_PERSONAL = "PERSONAL"
PRIVACY_CONFIDENTIAL = "CONFIDENTIAL"
PRIVACY_SECRET_LOCAL_ONLY = "SECRET_LOCAL_ONLY"

PRIVACY_CLASSES = (
    PRIVACY_PUBLIC,
    PRIVACY_PROJECT,
    PRIVACY_PERSONAL,
    PRIVACY_CONFIDENTIAL,
    PRIVACY_SECRET_LOCAL_ONLY,
)

# -- Budget classes (§5, §68) -----------------------------------------------
FREE_ONLY = "FREE_ONLY"
HOBBY_CREDIT_ONLY = "HOBBY_CREDIT_ONLY"
OWNER_APPROVED_PAID = "OWNER_APPROVED_PAID"
CUSTOM_LIMIT = "CUSTOM_LIMIT"

BUDGET_CLASSES = (FREE_ONLY, HOBBY_CREDIT_ONLY, OWNER_APPROVED_PAID, CUSTOM_LIMIT)

# -- Provider error normalisation (§88) ---------------------------------------
AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
RATE_LIMITED = "RATE_LIMITED"
QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
CONTEXT_EXCEEDED = "CONTEXT_EXCEEDED"
INVALID_REQUEST = "INVALID_REQUEST"
TIMEOUT = "TIMEOUT"
NETWORK_FAILURE = "NETWORK_FAILURE"
PROVIDER_INTERNAL = "PROVIDER_INTERNAL"
SAFETY_REJECTION = "SAFETY_REJECTION"
UNSUPPORTED_CAPABILITY = "UNSUPPORTED_CAPABILITY"
BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
PRIVACY_VIOLATION = "PRIVACY_VIOLATION"

ERROR_CLASSES = (
    AUTHENTICATION_ERROR,
    RATE_LIMITED,
    QUOTA_EXHAUSTED,
    MODEL_UNAVAILABLE,
    CONTEXT_EXCEEDED,
    INVALID_REQUEST,
    TIMEOUT,
    NETWORK_FAILURE,
    PROVIDER_INTERNAL,
    SAFETY_REJECTION,
    UNSUPPORTED_CAPABILITY,
    BUDGET_EXCEEDED,
    PRIVACY_VIOLATION,
)

RETRYABLE_ERRORS = (RATE_LIMITED, QUOTA_EXHAUSTED, TIMEOUT,
                    NETWORK_FAILURE, PROVIDER_INTERNAL, MODEL_UNAVAILABLE)
NON_RETRYABLE_ERRORS = (AUTHENTICATION_ERROR, CONTEXT_EXCEEDED,
                        INVALID_REQUEST, SAFETY_REJECTION,
                        UNSUPPORTED_CAPABILITY, BUDGET_EXCEEDED,
                        PRIVACY_VIOLATION)


def _now() -> float:
    return time.time()


def _new_id(prefix: str) -> str:
    return f"{prefix}-" + uuid.uuid4().hex[:12]


@dataclass
class ToolParameter:
    name: str = ""
    type: str = "string"
    description: str = ""
    required: bool = False
    enum: list[str] = field(default_factory=list)


@dataclass
class AetheriusToolCall:
    """One tool call requested by a model (§87)."""
    id: str = ""
    name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    arguments_str: str = ""  # raw string from provider if dict-parse fails

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "arguments": self.arguments,
            "arguments_str": self.arguments_str,
        }


@dataclass
class AetheriusToolResult:
    """Result of executing a tool call (§87)."""
    tool_call_id: str = ""
    tool_name: str = ""
    output: str = ""
    error: str = ""
    success: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_call_id": self.tool_call_id,
            "tool_name": self.tool_name,
            "output": self.output,
            "error": self.error,
            "success": self.success,
            "metadata": self.metadata,
        }


@dataclass
class AetheriusUsageRecord:
    """Token + resource usage for one inference request (§87)."""
    request_id: str = ""
    model_id: str = ""
    provider: str = ""
    execution_target: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: float = 0.0
    cost_currency: str = "USD"
    wall_time_s: float = 0.0
    first_token_s: float = 0.0
    tokens_per_sec: float = 0.0
    provider_usage: dict[str, Any] = field(default_factory=dict)  # raw usage block

    def add(self, other: "AetheriusUsageRecord") -> "AetheriusUsageRecord":
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_creation_tokens += other.cache_creation_tokens
        self.cache_read_tokens += other.cache_read_tokens
        self.cost_usd += other.cost_usd
        return self

    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "model_id": self.model_id,
            "provider": self.provider,
            "execution_target": self.execution_target,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_creation_tokens": self.cache_creation_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cost_usd": round(self.cost_usd, 8),
            "cost_currency": self.cost_currency,
            "wall_time_s": round(self.wall_time_s, 4),
            "first_token_s": round(self.first_token_s, 4),
            "tokens_per_sec": round(self.tokens_per_sec, 2),
            "provider_usage": self.provider_usage,
        }


@dataclass
class AetheriusProviderError:
    """Normalised provider error (§88)."""
    error_class: str = ""
    message: str = ""
    provider_code: str = ""      # raw HTTP code or provider error code
    provider_message: str = ""    # raw provider error text
    retryable: bool = False
    retry_after_s: float = 0.0
    cost_incurred: float = 0.0
    quota_reset_at: float = 0.0
    quota_remaining: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_class": self.error_class,
            "message": self.message,
            "provider_code": self.provider_code,
            "provider_message": self.provider_message,
            "retryable": self.retryable,
            "retry_after_s": self.retry_after_s,
            "cost_incurred": round(self.cost_incurred, 8),
            "quota_reset_at": self.quota_reset_at,
            "quota_remaining": self.quota_remaining,
            "raw": self.raw,
        }


@dataclass
class AetheriusModelError:
    """Model-level error: refusal, safety, context exceeded, etc."""
    error_class: str = ""
    message: str = ""
    refusal: bool = False
    safe: bool = True
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_class": self.error_class,
            "message": self.message,
            "refusal": self.refusal,
            "safe": self.safe,
            "raw": self.raw,
        }


@dataclass
class AetheriusInferenceEvent:
    """Streaming event emitted during inference (§87).

    One event per token chunk, tool call, usage update, or status change.
    """
    event_id: str = ""
    request_id: str = ""
    event_type: str = ""  # "content", "tool_call", "tool_call_done", "usage",
                           # "finish", "error", "routing", "metadata"
    content: str = ""
    tool_call: dict[str, Any] = field(default_factory=dict)
    usage: dict[str, Any] = field(default_factory=dict)
    error: dict[str, Any] = field(default_factory=dict)
    routing: dict[str, Any] = field(default_factory=dict)
    finish_reason: str = ""  # "stop", "length", "tool_calls", "error"
    timestamp: float = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "request_id": self.request_id,
            "event_type": self.event_type,
            "content": self.content,
            "tool_call": self.tool_call,
            "usage": self.usage,
            "error": self.error,
            "routing": self.routing,
            "finish_reason": self.finish_reason,
            "timestamp": self.timestamp,
        }


@dataclass
class AetheriusRoutingDecision:
    """Record of how a model/provider was selected (§87, §115)."""
    decision_id: str = ""
    request_id: str = ""
    selected_model: str = ""
    selected_provider: str = ""
    selected_execution_target: str = ""
    reasoning: str = ""
    privacy_path: str = ""
    data_leaving_local: bool = False
    cost_estimate_usd: float = 0.0
    fallback_chain: list[str] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "request_id": self.request_id,
            "selected_model": self.selected_model,
            "selected_provider": self.selected_provider,
            "selected_execution_target": self.selected_execution_target,
            "reasoning": self.reasoning,
            "privacy_path": self.privacy_path,
            "data_leaving_local": self.data_leaving_local,
            "cost_estimate_usd": round(self.cost_estimate_usd, 8),
            "fallback_chain": self.fallback_chain,
            "alternatives": self.alternatives,
            "timestamp": self.timestamp,
        }


@dataclass
class AetheriusInferenceRequest:
    """Provider-independent inference request (§87).

    A request should be capable of expressing:
      request_id, identity, project/workspace, capability, model preference,
      provider preference, privacy classification, budget, latency class,
      quality target, context requirement, tool requirement, vision/audio
      requirement, structured-output requirement, streaming, temperature,
      reasoning controls, deadline, retry policy, fallback policy.
    """
    request_id: str = field(default_factory=lambda: _new_id("req"))
    genesis_identity: str = "genesis"
    user_identity: str = ""
    project: str = ""
    workspace: str = ""
    capability: str = ""                # coding, reasoning, review, vision, etc.
    model_preference: str = ""          # preferred model_id if any
    provider_preference: str = ""       # preferred provider_id if any
    privacy_classification: str = PRIVACY_PROJECT
    budget_class: str = FREE_ONLY
    max_cost_usd: float = 0.0           # hard ceiling for this request
    latency_class: str = "interactive"  # interactive | batch | best_effort
    quality_target: str = ""            # e.g. "high", "medium"
    min_context_tokens: int = 0
    max_context_tokens: int = 0
    requires_tool_calling: bool = False
    requires_vision: bool = False
    requires_audio_input: bool = False
    requires_audio_output: bool = False
    requires_structured_output: bool = False
    requires_embedding: bool = False
    streaming: bool = False
    messages: list[dict[str, Any]] = field(default_factory=list)
    tools: list[dict[str, Any]] = field(default_factory=list)
    temperature: float = 0.1
    top_p: float = 1.0
    max_tokens: int = 2048
    reasoning_effort: str = ""          # low | medium | high
    seed: int = 0
    deadline_s: float = 0.0             # 0 = no deadline
    retry_policy: dict[str, Any] = field(default_factory=lambda: {
        "max_retries": 2,
        "backoff_s": 5.0,
        "retry_on": list(RETRYABLE_ERRORS),
        "non_retryable_on": list(NON_RETRYABLE_ERRORS),
    })
    fallback_policy: dict[str, Any] = field(default_factory=lambda: {
        "allow_fallback": True,
        "same_model_alternate_endpoint": True,
        "alternate_compatible_model": True,
        "local_fallback": True,
        "queue_if_no_fallback": True,
        "owner_notification": True,
    })
    trace_id: str = ""
    provenance: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.request_id:
            self.request_id = _new_id("req")
        if not self.trace_id:
            self.trace_id = _new_id("trace")
        if self.privacy_classification not in PRIVACY_CLASSES:
            raise ValueError(f"unknown privacy class: {self.privacy_classification!r}")
        if self.budget_class not in BUDGET_CLASSES:
            raise ValueError(f"unknown budget class: {self.budget_class!r}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AetheriusInferenceRequest":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def effective_privacy(self) -> bool:
        """True if this request must never leave local (SECRET_LOCAL_ONLY)."""
        return self.privacy_classification == PRIVACY_SECRET_LOCAL_ONLY

    def data_leaves_local(self) -> bool:
        """Whether the privacy classification permits data to leave local."""
        if self.privacy_classification == PRIVACY_SECRET_LOCAL_ONLY:
            return False
        if self.privacy_classification == PRIVACY_CONFIDENTIAL:
            return False
        return True


@dataclass
class AetheriusInferenceResponse:
    """Provider-independent inference response (§87)."""
    request_id: str = ""
    model_id: str = ""          # logical model that ran
    model_variant: str = ""     # variant/quantization that ran
    provider: str = ""          # provider_id that served
    execution_target: str = ""  # execution-target ID
    provider_response: str = ""  # final text content
    tool_calls: list[AetheriusToolCall] = field(default_factory=list)
    tool_results: list[AetheriusToolResult] = field(default_factory=list)
    finish_reason: str = ""     # stop | length | tool_calls | error
    usage: AetheriusUsageRecord = field(default_factory=AetheriusUsageRecord)
    routing: AetheriusRoutingDecision = field(default_factory=AetheriusRoutingDecision)
    error: AetheriusProviderError | AetheriusModelError | None = None
    cost_usd: float = 0.0
    latency_s: float = 0.0
    first_token_s: float = 0.0
    cached: bool = False
    timestamp: float = field(default_factory=_now)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict
        return {
            "request_id": self.request_id,
            "model_id": self.model_id,
            "model_variant": self.model_variant,
            "provider": self.provider,
            "execution_target": self.execution_target,
            "provider_response": self.provider_response,
            "tool_calls": [t.to_dict() for t in self.tool_calls],
            "tool_results": [t.to_dict() for t in self.tool_results],
            "finish_reason": self.finish_reason,
            "usage": self.usage.to_dict() if self.usage else {},
            "routing": self.routing.to_dict() if self.routing else {},
            "error": self.error.to_dict() if self.error else None,
            "cost_usd": round(self.cost_usd, 8),
            "latency_s": round(self.latency_s, 4),
            "first_token_s": round(self.first_token_s, 4),
            "cached": self.cached,
            "timestamp": self.timestamp,
            "raw": self.raw,
        }


# -- API path constants (§86) -------------------------------------------------
AI_GATEWAY_BASE = "/aetherius/v1"
AI_GATEWAY_PATHS = {
    "inference": f"{AI_GATEWAY_BASE}/inference",
    "models": f"{AI_GATEWAY_BASE}/models",
    "providers": f"{AI_GATEWAY_BASE}/providers",
    "jobs": f"{AI_GATEWAY_BASE}/jobs",
    "agents": f"{AI_GATEWAY_BASE}/agents",
    "embeddings": f"{AI_GATEWAY_BASE}/embeddings",
    "health": f"{AI_GATEWAY_BASE}/health",
    "routing_dry_run": f"{AI_GATEWAY_BASE}/routing/dry-run",
}


def is_retryable_error(error_class: str) -> bool:
    return error_class in RETRYABLE_ERRORS


def is_non_retryable_error(error_class: str) -> bool:
    return error_class in NON_RETRYABLE_ERRORS


__all__ = [
    # privacy
    "PRIVACY_PUBLIC", "PRIVACY_PROJECT", "PRIVACY_PERSONAL",
    "PRIVACY_CONFIDENTIAL", "PRIVACY_SECRET_LOCAL_ONLY", "PRIVACY_CLASSES",
    # budget
    "FREE_ONLY", "HOBBY_CREDIT_ONLY", "OWNER_APPROVED_PAID", "CUSTOM_LIMIT",
    "BUDGET_CLASSES",
    # errors
    "AUTHENTICATION_ERROR", "RATE_LIMITED", "QUOTA_EXHAUSTED",
    "MODEL_UNAVAILABLE", "CONTEXT_EXCEEDED", "INVALID_REQUEST", "TIMEOUT",
    "NETWORK_FAILURE", "PROVIDER_INTERNAL", "SAFETY_REJECTION",
    "UNSUPPORTED_CAPABILITY", "BUDGET_EXCEEDED", "PRIVACY_VIOLATION",
    "ERROR_CLASSES", "RETRYABLE_ERRORS", "NON_RETRYABLE_ERRORS",
    "is_retryable_error", "is_non_retryable_error",
    # dataclasses
    "AetheriusInferenceRequest", "AetheriusInferenceResponse",
    "AetheriusInferenceEvent", "AetheriusToolCall", "AetheriusToolResult",
    "AetheriusUsageRecord", "AetheriusProviderError",
    "AetheriusModelError", "AetheriusRoutingDecision",
    # api paths
    "AI_GATEWAY_BASE", "AI_GATEWAY_PATHS",
]
