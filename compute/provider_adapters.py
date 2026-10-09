"""Provider capability registry (§2).

Every provider implementation must ADVERTISE CAPABILITY SUPPORT HONESTLY.

The rule being enforced:

    Unsupported capability -> FAIL OR DOWNGRADE EXPLICITLY, never silently
    ignore.

Silent ignoring is the failure mode this prevents: a router asks for
``structured_output``, the provider cannot do it, and returns prose. Without
an explicit failure the router records a successful call and downstream code
parses text as JSON. Honest advertising turns that into an immediate,
attributable error.

Providers here are declared, not probed. A declaration is evidence of
intent, not of a live connection — ``probe_state`` tracks that distinction
so nothing claims LIVE access it does not have.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from compute.error_taxonomy import (
    ALL_CAPABILITIES,
    SUPPORT_DEGRADED,
    SUPPORT_FULL,
    ProviderCapabilities,
    UnsupportedCapabilityError,
)

# Evidence states (§23). A declaration is never VERIFIED_LIVE.
DECLARED = "declared"
VERIFIED_LOCAL = "verified_local"
VERIFIED_LIVE = "verified_live"
BLOCKED_OWNER = "blocked_owner"
UNKNOWN = "unknown"


@dataclass
class ProviderAdapter:
    """A provider implementation and its honest capability declaration."""

    provider_id: str
    display_name: str
    capabilities: ProviderCapabilities
    probe_state: str = DECLARED
    # Cloud providers need owner-rotated credentials before any live call.
    requires_credentials: bool = False
    endpoint: str | None = None
    notes: str = ""

    def require(self, capability: str) -> str:
        """Fail loudly if this provider cannot honour the capability."""
        return self.capabilities.check(capability)

    def supports(self, capability: str) -> str:
        return self.capabilities.support_level(capability)

    def as_dict(self) -> dict:
        return {
            "provider_id": self.provider_id,
            "display_name": self.display_name,
            "probe_state": self.probe_state,
            "requires_credentials": self.requires_credentials,
            "endpoint": self.endpoint,
            "capabilities": self.capabilities.as_dict(),
            "notes": self.notes,
        }


class ProviderAdapterRegistry:
    """Registry of provider adapters and their honest capabilities (§2)."""

    def __init__(self):
        self._providers: dict[str, ProviderAdapter] = {}

    def register(self, adapter: ProviderAdapter) -> ProviderAdapter:
        if adapter.provider_id in self._providers:
            raise ValueError(
                f"provider '{adapter.provider_id}' already registered"
            )
        self._providers[adapter.provider_id] = adapter
        return adapter

    def get(self, provider_id: str) -> ProviderAdapter | None:
        return self._providers.get(provider_id)

    def find_for_capability(self, capability: str,
                            full_only: bool = True) -> list[ProviderAdapter]:
        """Providers that can honour a capability.

        ``full_only=True`` excludes degraded support, because a degraded
        provider is not a valid target for a capability that was requested
        explicitly.
        """
        wanted = SUPPORT_FULL if full_only else None
        out = []
        for adapter in self._providers.values():
            level = adapter.supports(capability)
            if wanted is None or level == wanted:
                out.append(adapter)
        return sorted(out, key=lambda a: a.provider_id)

    def resolve(self, provider_id: str, capability: str) -> ProviderAdapter:
        """Return the provider if it can honour the capability, else raise."""
        adapter = self._providers.get(provider_id)
        if adapter is None:
            raise KeyError(f"unknown provider '{provider_id}'")
        adapter.require(capability)
        return adapter

    def summary(self) -> dict:
        return {
            "providers": {pid: a.as_dict()
                          for pid, a in sorted(self._providers.items())},
            "count": len(self._providers),
            "capability_coverage": {
                cap: sorted(a.provider_id for a in self.find_for_capability(cap))
                for cap in ALL_CAPABILITIES
            },
        }


def build_default_registry() -> ProviderAdapterRegistry:
    """Declare the known providers with honest capability sets.

    Nothing here is probed. Cloud providers carry ``requires_credentials``
    and ``probe_state=BLOCKED_OWNER`` because their credentials were exposed
    and must be rotated by the owner before any live call (§21).
    """
    reg = ProviderAdapterRegistry()

    # Local runtime: real capability, no credentials needed. This is what
    # makes local-first routing possible while cloud stays blocked.
    reg.register(ProviderAdapter(
        provider_id="ollama-local",
        display_name="Ollama (local)",
        capabilities=ProviderCapabilities(
            provider_id="ollama-local",
            supports=frozenset({
                "streaming", "tool_calling", "structured_output",
                "vision", "reasoning_controls",
            }),
            degraded=frozenset({"prompt_caching"}),
            notes={
                "prompt_caching": "model-dependent; some builds re-cache per call",
                "batch": "not exposed by the local API",
            },
        ),
        probe_state=VERIFIED_LOCAL,
        requires_credentials=False,
        endpoint="http://127.0.0.1:11434",
    ))

    reg.register(ProviderAdapter(
        provider_id="llama-cpp-local",
        display_name="llama.cpp (local, CPU-first)",
        capabilities=ProviderCapabilities(
            provider_id="llama-cpp-local",
            supports=frozenset({
                "streaming", "structured_output", "reasoning_controls",
            }),
            degraded=frozenset({"tool_calling"}),
            notes={"tool_calling": "grammar-constrained, not native tool use"},
        ),
        probe_state=VERIFIED_LOCAL,
        requires_credentials=False,
    ))

    # Cloud providers: BLOCKED_OWNER pending credential rotation (§21).
    cloud = [
        ("openrouter", "OpenRouter", {"streaming", "tool_calling",
                                      "structured_output", "vision",
                                      "prompt_caching", "reasoning_controls"}),
        ("groq", "Groq", {"streaming", "tool_calling", "structured_output",
                          "reasoning_controls"}),
        ("gemini", "Google Gemini", {"streaming", "tool_calling",
                                     "structured_output", "vision",
                                     "prompt_caching", "batch",
                                     "reasoning_controls"}),
        ("huggingface", "Hugging Face", {"streaming", "tool_calling",
                                         "structured_output"}),
        ("deepseek", "DeepSeek", {"streaming", "tool_calling",
                                  "structured_output",
                                  "prompt_caching",
                                  "reasoning_controls"}),
    ]
    for pid, name, caps in cloud:
        reg.register(ProviderAdapter(
            provider_id=pid,
            display_name=name,
            capabilities=ProviderCapabilities(
                provider_id=pid,
                supports=frozenset(caps),
                notes={"access": "credentials exposed previously; "
                                 "owner rotation required before live use"},
            ),
            probe_state=BLOCKED_OWNER,
            requires_credentials=True,
        ))

    return reg


__all__ = [
    "ALL_CAPABILITIES", "BLOCKED_OWNER", "DECLARED", "ProviderAdapter",
    "ProviderAdapterRegistry", "ProviderCapabilities", "SUPPORT_DEGRADED",
    "SUPPORT_FULL", "UNKNOWN", "UnsupportedCapabilityError", "VERIFIED_LIVE",
    "VERIFIED_LOCAL", "build_default_registry",
]
