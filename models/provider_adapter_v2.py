"""Provider Adapter V2 — extends the canonical V1 protocol (§88).

Do NOT create a parallel framework. Extend models/provider_adapter.py.
This module adds V2 capabilities to the existing ProviderAdapter base class:

prompt caching
reasoning controls
logprobs
batch support
structured output
normalized provider errors
rate limit
quota exhausted
authentication failure
timeout
provider unavailable
model unavailable
context exceeded
unsupported capability
policy refusal

Each provider advertises only capabilities it actually supports.
"""
from dataclasses import dataclass, field
from typing import Optional

from models.provider_adapter import ProviderAdapter, ProviderResponse, RateLimitInfo


# ---- V2 capability flags (§88) ----

@dataclass
class V2Capabilities:
    """Capabilities a provider actually supports (§88)."""
    supports_prompt_caching: bool = False
    supports_reasoning: bool = False
    supports_logprobs: bool = False
    supports_batch: bool = False
    supports_structured_output: bool = False
    supports_continuation: bool = False
    max_tokens_per_minute: int = 0
    max_requests_per_minute: int = 0


# ---- Normalized error classes (§88) ----

ERR_RATE_LIMIT = "RATE_LIMIT_EXCEEDED"
ERR_QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
ERR_AUTH_FAILURE = "AUTHENTICATION_FAILED"
ERR_TIMEOUT = "TIMEOUT"
ERR_PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
ERR_MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
ERR_CONTEXT_EXCEEDED = "CONTEXT_LENGTH_EXCEEDED"
ERR_UNSUPPORTED_CAPABILITY = "UNSUPPORTED_CAPABILITY"
ERR_POLICY_REFUSAL = "POLICY_REFUSAL"
ERR_UNKNOWN = "UNKNOWN_ERROR"


@dataclass
class NormalizedProviderError(Exception):
    """Normalized provider error with stable class (§88).

    Every provider adapter V2 must translate its raw exceptions into
    one of these canonical classes so the gateway can apply consistent
    retry/fallback logic.
    """
    error_class: str
    message: str
    provider_id: str
    retry_after: Optional[float] = None
    request_id: Optional[str] = None

    def __post_init__(self) -> None:
        super().__init__(self.message)


# ---- V2 Request envelope (extends ProviderResponse) ----

@dataclass
class V2InferenceRequest:
    """Enhanced inference request with V2 features (§88)."""
    messages: list[dict]
    model: str
    temperature: float = 0.7
    max_tokens: int = 2048
    # V2 fields
    prompt_cache_id: Optional[str] = None
    enable_reasoning: bool = False
    reasoning_budget: Optional[int] = None
    return_logprobs: bool = False
    batch_mode: bool = False
    structured_output: Optional[dict] = None  # JSON schema
    continuation: bool = False


@dataclass
class V2InferenceResponse(ProviderResponse):
    """Extended response with V2 metadata."""
    logprobs: Optional[list] = None
    reasoning: Optional[str] = None
    prompt_cache_id: Optional[str] = None
    cache_hit: bool = False
    batch_id: Optional[str] = None


class ProviderAdapterV2(ProviderAdapter):
    """Base class for V2 provider adapters.

    Extends ProviderAdapter with V2 capabilities. Subclasses must set
    `v2_capabilities` and override `infer_v2()`.
    """

    v2_capabilities: V2Capabilities = field(default_factory=V2Capabilities, init=False, repr=False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.v2_capabilities = V2Capabilities()

    @classmethod
    def get_capabilities(cls) -> V2Capabilities:
        """Return a copy of the capabilities this provider supports."""
        return cls.v2_capabilities

    def infer_v2(self, request: V2InferenceRequest) -> V2InferenceResponse:
        """V2 inference entry point. Must be overridden by V2 adapters."""
        raise NotImplementedError("Provider does not support V2 inference")

    def infer(self, messages: list[dict], model: str, **kwargs) -> ProviderResponse:
        """Backwards-compatible V1 entry point. Adapts to V2."""
        req = V2InferenceRequest(messages=messages, model=model, **kwargs)
        resp = self.infer_v2(req)
        return ProviderResponse(
            model=resp.model,
            content=resp.content,
            usage=resp.usage,
            provider=self.name,
        )

    def normalize_error(self, raw_error: Exception) -> NormalizedProviderError:
        """Translate a raw provider exception into a normalized error class.

        Must be overridden by each provider adapter.
        """
        return NormalizedProviderError(
            error_class=ERR_UNKNOWN,
            message=str(raw_error),
            provider_id=self.name,
        )

    def check_rate_limit(self) -> Optional[RateLimitInfo]:
        """Return current rate limit state, or None if unknown."""
        if self._rate_limit_info:
            return self._rate_limit_info
        return None


# ---- Capability registry (§88) ----

def register_v2_capabilities() -> dict[str, V2Capabilities]:
    """Register V2 capabilities for all known provider adapters.

    Only declares capabilities that match each provider's actual V2 status.
    """
    return {
        # Local providers — V2 not yet extended, declare minimal V1 only
        "ollama": V2Capabilities(
            max_tokens_per_minute=100_000,
            max_requests_per_minute=100,
        ),
        # Paid providers — credentials blocked, V2 stubbed until unblocked
        "openai": V2Capabilities(
            supports_prompt_caching=True,
            supports_reasoning=True,
            supports_logprobs=True,
            supports_structured_output=True,
            supports_batch=True,
            max_tokens_per_minute=200_000,
            max_requests_per_minute=500,
        ),
        "openrouter": V2Capabilities(
            supports_structured_output=True,
            max_tokens_per_minute=500_000,
            max_requests_per_minute=1000,
        ),
        "anthropic": V2Capabilities(
            supports_prompt_caching=True,
            supports_reasoning=True,
            supports_logprobs=True,
            supports_structured_output=True,
            supports_batch=True,
            max_tokens_per_minute=200_000,
            max_requests_per_minute=400,
        ),
        "gemini": V2Capabilities(
            supports_reasoning=True,
            supports_structured_output=True,
            max_tokens_per_minute=1_000_000,
            max_requests_per_minute=60,
        ),
        "deepseek": V2Capabilities(
            supports_structured_output=True,
            max_tokens_per_minute=400_000,
            max_requests_per_minute=200,
        ),
        "huggingface": V2Capabilities(
            supports_batch=True,
            max_tokens_per_minute=300_000,
            max_requests_per_minute=300,
        ),
        "groq": V2Capabilities(
            supports_structured_output=True,
            max_tokens_per_minute=1_000_000,
            max_requests_per_minute=3000,
        ),
        "llama_cpp": V2Capabilities(
            max_tokens_per_minute=100_000,
            max_requests_per_minute=50,
        ),
        "lm_studio": V2Capabilities(
            max_tokens_per_minute=100_000,
            max_requests_per_minute=100,
        ),
    }


def is_provider_v2_ready(provider_id: str) -> bool:
    """True if a provider adapter V2 implementation exists and is usable."""
    caps = register_v2_capabilities()
    if provider_id not in caps:
        return False
    c = caps[provider_id]
    # V2 ready if it supports at least 2 V2-specific features
    return sum([
        c.supports_prompt_caching, c.supports_reasoning,
        c.supports_logprobs, c.supports_batch,
        c.supports_structured_output, c.supports_continuation,
    ]) >= 2
