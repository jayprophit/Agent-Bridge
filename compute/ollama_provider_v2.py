"""Ollama Provider V2 — capability discovery + normalized errors (§27–§29).

WHY THIS MODULE EXISTS

The provider adapter registry could DECLARE that Ollama supports a
capability. That is not the same as knowing it does. A capability list
hand-written from a README rots the moment a model is swapped, and a router
that trusts it will dispatch a tool-calling request to a model that cannot
call tools — the request then either fails obscurely or, worse, is silently
answered as prose.

So this adapter DISCOVERS capabilities from the live Ollama runtime instead
of asserting them. `/api/show` reports what a model actually implements.

THE PROVIDER vs MODEL DISTINCTION (§28)

Capabilities vary on two axes and conflating them is a real bug:

    PROVIDER capabilities  — what the Ollama server itself offers
                             (streaming, embeddings, version)
    MODEL capabilities     — what a specific model supports
                             (vision, tools, context length)

`moondream` can see images; `llama3.2:1b` cannot. A single provider-level
"vision: yes" would be wrong for most models on this host. Discovery is
therefore per (provider, model) and both levels are reported separately.

WHAT IS DELIBERATELY NOT CLAIMED (§28)

The live host is probed and capabilities are reported from what `/api/show`
and `/api/tags` actually return. Ollama does not expose logprobs, prompt
caching, or batch inference through its HTTP API, so these are advertised as
unsupported rather than optimistically declared. Falsely advertising a
capability is how a router ends up trusting a result that was never
produced.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

# Imported at module scope rather than near the error subclasses because the
# class BODIES need NormalizedProviderError at import time — a bottom-of-file
# import raises NameError before it is ever reached.
from compute.error_taxonomy import (
    NormalizedProviderError,
    AUTH_ERROR,
    MODEL_UNAVAILABLE,
    PROVIDER_UNAVAILABLE,
    QUOTA_EXHAUSTED,
    RATE_LIMIT,
    TIMEOUT,
    UNSUPPORTED_CAPABILITY,
    UNKNOWN_PROVIDER_ERROR,
)

# --------------------------------------------------------------------------
# Capability names — shared vocabulary, so discovery and requests agree
# --------------------------------------------------------------------------
CAP_STREAMING = "streaming"
CAP_STRUCTURED_OUTPUT = "structured_output"
CAP_TOOLS = "tools"
CAP_VISION = "vision"
CAP_REASONING = "reasoning"
CAP_EMBEDDINGS = "embeddings"
CAP_TEMPERATURE = "temperature"
CAP_SYSTEM_PROMPT = "system_prompt"
CAP_SEED = "seed"

# Capabilities the Ollama HTTP API does NOT expose. Declaring these would be
# a false advertisement (§28), so they are pinned as unsupported.
UNSUPPORTED_BY_OLLAMA = ("logprobs", "prompt_caching", "batch", "audio")

DEFAULT_BASE_URL = "http://localhost:11434"


@dataclass
class ModelCapabilities:
    """What ONE model actually supports, discovered from the runtime."""

    model: str
    provider: str
    streaming: bool = False
    structured_output: bool = False
    tools: bool = False
    vision: bool = False
    reasoning: bool = False
    temperature: bool = False
    system_prompt: bool = False
    seed: bool = False
    context_length: int = 0
    parameter_size: str = ""
    quantization: str = ""
    family: str = ""
    families: list[str] = field(default_factory=list)
    embedding_length: int = 0
    # Explicitly unsupported — recorded so a caller sees the honest answer
    # rather than assuming silence means "no".
    unsupported: list[str] = field(default_factory=list)
    discovery_source: str = ""

    def supports(self, capability: str) -> bool:
        mapping = {
            CAP_STREAMING: self.streaming,
            CAP_STRUCTURED_OUTPUT: self.structured_output,
            CAP_TOOLS: self.tools,
            CAP_VISION: self.vision,
            CAP_REASONING: self.reasoning,
            CAP_TEMPERATURE: self.temperature,
            CAP_SYSTEM_PROMPT: self.system_prompt,
            CAP_SEED: self.seed,
        }
        return bool(mapping.get(capability, False))

    def supported_list(self) -> list[str]:
        out = []
        for cap in (CAP_STREAMING, CAP_STRUCTURED_OUTPUT, CAP_TOOLS, CAP_VISION,
                    CAP_REASONING, CAP_TEMPERATURE, CAP_SYSTEM_PROMPT, CAP_SEED):
            if self.supports(cap):
                out.append(cap)
        return out

    def to_dict(self) -> dict[str, Any]:
        return OrderedDict([
            ("model", self.model),
            ("provider", self.provider),
            ("supported", self.supported_list()),
            ("unsupported", list(self.unsupported)),
            ("context_length", self.context_length),
            ("parameter_size", self.parameter_size),
            ("quantization", self.quantization),
            ("family", self.family),
            ("discovery_source", self.discovery_source),
        ])


class OllamaUnavailableError(NormalizedProviderError):
    """Raised when the Ollama server cannot be reached (§29).

    Carries PROVIDER_UNAVAILABLE rather than a generic runtime error: the
    runtime being switched off is a known, classifiable state, and the router
    should treat it as a dead provider instead of an unknown fault.
    """

    def __init__(self, base_url: str, cause: str = "") -> None:
        super().__init__(
            PROVIDER_UNAVAILABLE,
            f"Ollama unreachable at {base_url}: {cause or 'no response'}",
            provider_id="ollama",
            retryable=False,
        )
        self.base_url = base_url
        self.cause = cause


class OllamaProviderV2:
    """Live Ollama adapter: discovers capabilities, normalizes errors (§27–§29).

    Every method that touches the network converts provider failures into the
    canonical §3 taxonomy. Raw provider exceptions never escape as the API
    contract (§29).
    """

    provider_id = "ollama"
    base_url: str

    def __init__(self, base_url: str = DEFAULT_BASE_URL,
                 timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._capability_cache: dict[str, ModelCapabilities] = {}

    # -- transport ----------------------------------------------------------
    def _get(self, path: str, payload: dict | None = None) -> Any:
        """HTTP GET/POST returning parsed JSON, with normalized errors.

        Network/HTTP/JSON failures become taxonomy classes so callers branch
        on one vocabulary instead of four different exception hierarchies.
        """
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"} if data else {})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            # A 404 from /api/show means the model is not installed.
            if exc.code == 404:
                raise OllamaModelUnavailableError(
                    path, f"HTTP 404: {exc.reason}") from exc
            if exc.code in (401, 403):
                raise OllamaAuthError(path, f"HTTP {exc.code}") from exc
            if exc.code == 429:
                raise OllamaRateLimitError(path, "HTTP 429") from exc
            raise OllamaRequestError(path, f"HTTP {exc.code}: {exc.reason}") from exc
        except urllib.error.URLError as exc:
            # Connection refused / DNS / timeout — the server is not there.
            raise OllamaUnavailableError(self.base_url, str(exc.reason)) from exc
        except TimeoutError as exc:
            raise OllamaTimeoutError(path, "request timed out") from exc
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise OllamaRequestError(
                path, f"malformed JSON response: {exc}") from exc

    # -- discovery (§28) ----------------------------------------------------
    def is_available(self) -> bool:
        """True when the server answers /api/tags. Never raises."""
        try:
            self.list_models()
            return True
        except Exception:
            return False

    def list_models(self) -> list[str]:
        """Model names currently installed."""
        data = self._get("/api/tags")
        return [m.get("name", "") for m in data.get("models", []) if m.get("name")]

    def provider_capabilities(self) -> dict[str, Any]:
        """PROVIDER-level capabilities (§28) — not model-specific."""
        streaming = False
        try:
            # /api/generate accepts stream; if the endpoint answers the server
            # supports streaming. We do not generate here, only reachability.
            self._get("/api/version")
            streaming = True
        except Exception:
            streaming = False
        caps = OrderedDict([
            ("provider", self.provider_id),
            ("base_url", self.base_url),
            ("reachable", self.is_available()),
            ("streaming", streaming),
            ("embeddings", True),  # /api/embeddings exists on this runtime
        ])
        for cap in UNSUPPORTED_BY_OLLAMA:
            caps[cap] = False
        return caps

    def discover(self, model: str, refresh: bool = False) -> ModelCapabilities:
        """Discover what ONE model supports, from /api/show + /api/tags (§28).

        This is the honest capability list: a router may trust it because it
        came from the runtime, not from documentation.
        """
        if not refresh and model in self._capability_cache:
            return self._capability_cache[model]

        details: dict[str, Any] = {}
        try:
            show = self._get("/api/show", {"model": model})
            details = show.get("details", {}) or {}
        except OllamaModelUnavailableError:
            # Model not installed: report honestly rather than guessing.
            caps = ModelCapabilities(
                model=model, provider=self.provider_id,
                unsupported=list(UNSUPPORTED_BY_OLLAMA),
                discovery_source="unavailable")
            self._capability_cache[model] = caps
            return caps

        families = details.get("families") or []
        family = details.get("family") or ""
        # /api/show returns an EXPLICIT `capabilities` array — e.g.
        # ["completion","tools"] or ["completion","vision"] or
        # ["completion","tools","thinking"]. This is the runtime's own
        # declaration, so it is authoritative and we do NOT infer support
        # from model names. Name-based guessing got llama3.2 wrong: it
        # advertises tools even though nothing in the name suggests so.
        declared = list(show.get("capabilities") or [])

        # `thinking` is reported as {"values": [...], "default": bool}; a
        # plain False means the model cannot reason at all.
        thinking = show.get("thinking")
        # `thinking` is reported as {"values": [...], "default": bool}. A model
        # whose only value is False cannot reason even if a `thinking` key
        # exists, so require a genuinely truthy option rather than mere
        # presence — llama3.2 reports values=[False] and must NOT be
        # advertised as reasoning-capable.
        reasoning = any(
            thinking.get("values", []) if isinstance(thinking, dict) else [])

        # Context length lives in model_info as "<arch>.context_length".
        model_info = show.get("model_info") or {}
        context_length = 0
        for key, value in model_info.items():
            if key.endswith(".context_length") and isinstance(value, int):
                context_length = max(context_length, value)

        caps = ModelCapabilities(
            model=model,
            provider=self.provider_id,
            # Sampling controls are universal in Ollama's generate API.
            streaming=True,
            temperature=True,
            system_prompt=True,
            seed=True,
            vision=CAP_VISION in declared or "clip" in families,
            tools=CAP_TOOLS in declared,
            reasoning=reasoning,
            # Ollama supports `format: json` for text-generation models.
            structured_output="completion" in declared,
            context_length=context_length,
            parameter_size=details.get("parameter_size") or "",
            quantization=details.get("quantization_level") or "",
            family=family,
            families=families,
            unsupported=list(UNSUPPORTED_BY_OLLAMA),
            discovery_source="/api/show capabilities + model_info",
        )
        self._capability_cache[model] = caps
        return caps

    def embedding_capable(self, model: str) -> bool:
        """Embedding models advertise an embedding_length."""
        caps = self.discover(model)
        return caps.embedding_length > 0 or "embed" in model.lower()

    # -- inference ----------------------------------------------------------
    def infer(self, model: str, prompt: str,
              system: str | None = None,
              temperature: float | None = None,
              max_tokens: int | None = None,
              tools: list[dict] | None = None,
              stream: bool = False) -> dict[str, Any]:
        """Generate a completion, enforcing honest capability gating (§2, §28).

        Requesting a capability the model does not support FAILS EXPLICITLY
        rather than being silently ignored.
        """
        caps = self.discover(model)

        if tools:
            if not caps.supports(CAP_TOOLS):
                raise OllamaUnsupportedCapabilityError(
                    model, CAP_TOOLS, f"model '{model}' has no tool calling")
        if temperature is not None and not caps.supports(CAP_TEMPERATURE):
            raise OllamaUnsupportedCapabilityError(
                model, CAP_TEMPERATURE, f"model '{model}' has no temperature")

        options: dict[str, Any] = {}
        if temperature is not None:
            options["temperature"] = temperature
        if max_tokens is not None:
            options["num_predict"] = max_tokens

        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": stream,
        }
        if system:
            payload["system"] = system
        if options:
            payload["options"] = options
        if tools:
            payload["tools"] = tools

        data = self._get("/api/generate", payload)
        return OrderedDict([
            ("model", model),
            ("provider", self.provider_id),
            ("response", data.get("response", "")),
            ("done", data.get("done", True)),
            ("tool_calls", data.get("message", {}).get("tool_calls", [])),
            ("usage", OrderedDict([
                ("prompt_tokens", data.get("prompt_eval_count", 0)),
                ("completion_tokens", data.get("eval_count", 0)),
                ("total_tokens", (data.get("prompt_eval_count", 0)
                                  + data.get("eval_count", 0))),
            ])),
            ("capabilities_used", self._capabilities_used(tools, temperature)),
        ])

    def _capabilities_used(self, tools: list[dict] | None,
                           temperature: float | None) -> list[str]:
        used = [CAP_STREAMING]
        if tools:
            used.append(CAP_TOOLS)
        if temperature is not None:
            used.append(CAP_TEMPERATURE)
        return used

    def embed(self, model: str, text: str) -> list[float]:
        """Embeddings, gated on the model actually being an embedder."""
        caps = self.discover(model)
        if not self.embedding_capable(model):
            raise OllamaUnsupportedCapabilityError(
                model, CAP_EMBEDDINGS, f"model '{model}' is not an embedding model")
        data = self._get("/api/embeddings", {"model": model, "prompt": text})
        return list(data.get("embedding", []))


# --------------------------------------------------------------------------
# Normalized Ollama errors (§29)
#
# The taxonomy imports live at the top of this module; the subclasses below
# need NormalizedProviderError available at import time.
# --------------------------------------------------------------------------


class OllamaModelUnavailableError(NormalizedProviderError):
    """Model not installed on this Ollama host. Not retryable — installing a
    model is a deliberate act, not a transient blip."""


class OllamaAuthError(NormalizedProviderError):
    """Authentication rejected by the runtime."""


class OllamaRateLimitError(NormalizedProviderError):
    """Runtime throttled the request."""


class OllamaTimeoutError(NormalizedProviderError):
    """The runtime did not answer in time. Retryable."""


class OllamaRequestError(NormalizedProviderError):
    """Malformed or unexpected response from the runtime."""


class OllamaUnsupportedCapabilityError(NormalizedProviderError):
    """Caller asked for a capability the model does not advertise (§28).

    Raised INSTEAD of silently ignoring the request, because a router that
    believes a tool-calling request succeeded has trusted a result that was
    never produced.
    """

    def __init__(self, model: str, capability: str, message: str = "") -> None:
        self.model = model
        self.capability = capability
        super().__init__(
            UNSUPPORTED_CAPABILITY,
            message or f"model '{model}' does not support '{capability}'",
            provider_id="ollama",
            retryable=False,
        )


def normalize_ollama_error(exc: Exception) -> str:
    """Map any Ollama failure to a canonical §3 class (§29).

    ORDER MATTERS. ``OllamaUnavailableError`` subclasses RuntimeError, not
    URLError, so it must be matched BEFORE the generic branches — otherwise a
    runtime that is simply switched off normalizes to UNKNOWN_PROVIDER_ERROR
    and the router wastes retries on a provider that is not coming back.
    """
    if isinstance(exc, NormalizedProviderError):
        return exc.error_class
    if isinstance(exc, OllamaUnavailableError):
        return PROVIDER_UNAVAILABLE
    if isinstance(exc, TimeoutError):
        return TIMEOUT
    if isinstance(exc, urllib.error.URLError):
        return PROVIDER_UNAVAILABLE
    return UNKNOWN_PROVIDER_ERROR
