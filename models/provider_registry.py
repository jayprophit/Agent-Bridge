"""ProviderRegistry (v0.7). Catalog of model providers.

Providers are backends that serve models (Ollama, OpenAI, Anthropic, etc.).
Each provider is registered with its capabilities and authentication status.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# provider families
OLLAMA = "ollama"
LLAMA_CPP = "llama_cpp"
LM_STUDIO = "lm_studio"
OPENAI_COMPATIBLE = "openai_compatible"
OPENAI_API = "openai_api"
ANTHROPIC = "anthropic"
GOOGLE = "google"
DEEPSEEK = "deepseek"
MOONSHOT = "moonshot"
GITHUB_COPILOT = "github_copilot"

PROVIDER_FAMILIES = (
    OLLAMA, LLAMA_CPP, LM_STUDIO, OPENAI_COMPATIBLE, OPENAI_API,
    ANTHROPIC, GOOGLE, DEEPSEEK, MOONSHOT, GITHUB_COPILOT
)

# provider statuses
PROVIDER_AVAILABLE = "PROVIDER_AVAILABLE"
PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
AUTH_REQUIRED = "AUTH_REQUIRED"
AUTH_FAILED = "AUTH_FAILED"
NOT_CONFIGURED = "NOT_CONFIGURED"
OFFLINE = "OFFLINE"
INTERFACE_ONLY = "INTERFACE_ONLY"

PROVIDER_STATUSES = (
    PROVIDER_AVAILABLE, PROVIDER_UNAVAILABLE, AUTH_REQUIRED,
    AUTH_FAILED, NOT_CONFIGURED, OFFLINE, INTERFACE_ONLY
)


@dataclass
class ProviderRecord:
    provider_id: str
    provider_family: str = ""
    display_name: str = ""
    description: str = ""
    version: str = "0.7.0"
    status: str = NOT_CONFIGURED
    authenticated: bool = False
    local_or_remote: str = "unknown"  # "local" | "remote" | "unknown"
    endpoint: str = ""
    requires_auth: bool = False
    requires_network: bool = False
    supports_streaming: bool = False
    supports_tool_calling: bool = False
    supports_vision: bool = False
    supports_audio_input: bool = False
    supports_audio_output: bool = False
    supports_structured_output: bool = False
    api_key_configured: bool = False
    config_path: str = ""
    capabilities: dict = field(default_factory=dict)
    limitations: str = ""
    
    def __post_init__(self) -> None:
        if self.provider_family not in PROVIDER_FAMILIES:
            raise ValueError(f"unknown provider family: {self.provider_family}")
        # Define all valid statuses including INTERFACE_ONLY
        all_valid_statuses = (PROVIDER_AVAILABLE, PROVIDER_UNAVAILABLE, AUTH_REQUIRED,
                             AUTH_FAILED, NOT_CONFIGURED, OFFLINE, INTERFACE_ONLY)
        if self.status not in all_valid_statuses:
            raise ValueError(f"unknown provider status: {self.status}")
    
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProviderRegistry:
    """ID-keyed provider registry. Adapters self-register; duplicates rejected."""
    
    def __init__(self):
        self._providers: dict[str, ProviderRecord] = {}
        self._adapters: dict[str, Any] = {}
    
    def register(self, record: ProviderRecord, adapter: Any = None) -> None:
        if not record.provider_id:
            raise ValueError("provider_id must be non-empty")
        if record.provider_id in self._providers:
            raise ValueError(f"duplicate provider_id: {record.provider_id}")
        self._providers[record.provider_id] = record
        if adapter is not None:
            self._adapters[record.provider_id] = adapter
    
    def get(self, provider_id: str) -> ProviderRecord:
        try:
            return self._providers[provider_id]
        except KeyError:
            raise KeyError(f"unknown provider: {provider_id!r}")
    
    def adapter_for(self, provider_id: str) -> Any:
        try:
            return self._adapters[provider_id]
        except KeyError:
            raise KeyError(f"no adapter registered: {provider_id!r}")
    
    def ids(self) -> list[str]:
        return sorted(self._providers)
    
    def __len__(self) -> int:
        return len(self._providers)
    
    def list(self, family: str = "", status: str = "",
             local_or_remote: str = "") -> list[ProviderRecord]:
        out = []
        for rec in self._providers.values():
            if family and rec.provider_family != family:
                continue
            if status and rec.status != status:
                continue
            if local_or_remote and rec.local_or_remote != local_or_remote:
                continue
            out.append(rec)
        return sorted(out, key=lambda r: r.provider_id)
    
    def search(self, query: str, limit: int = 20) -> list[ProviderRecord]:
        words = [w.lower() for w in query.split() if w]
        scored = []
        for rec in self._providers.values():
            hay = f"{rec.provider_id} {rec.display_name} {rec.description}".lower()
            score = sum(2 for w in words if w in hay)
            if score:
                scored.append((score, rec))
        scored.sort(key=lambda t: (-t[0], t[1].provider_id))
        return [r for _, r in scored[:limit]]
    
    def describe(self, provider_id: str) -> dict[str, Any]:
        return self.get(provider_id).to_dict()
    
    def status_of(self, provider_id: str) -> dict[str, Any]:
        rec = self.get(provider_id)
        return {"provider_id": rec.provider_id, "status": rec.status,
                "authenticated": rec.authenticated,
                "local_or_remote": rec.local_or_remote,
                "endpoint": rec.endpoint, "limitations": rec.limitations}
    
    def health(self, provider_id: str) -> dict[str, Any]:
        rec = self.get(provider_id)
        adapter = self._adapters.get(provider_id)
        if adapter is None or not hasattr(adapter, "health"):
            return {"provider_id": provider_id, "status": rec.status,
                    "healthy": rec.status == PROVIDER_AVAILABLE}
        try:
            return {"provider_id": provider_id, **adapter.health()}
        except Exception as e:  # noqa: BLE001
            return {"provider_id": provider_id, "status": rec.status,
                    "healthy": False, "error": str(e)[:200]}
    
    def available_providers(self) -> list[ProviderRecord]:
        return [p for p in self._providers.values()
                if p.status == PROVIDER_AVAILABLE]
    
    def local_providers(self) -> list[ProviderRecord]:
        return [p for p in self._providers.values()
                if p.local_or_remote == "local"]
    
    def remote_providers(self) -> list[ProviderRecord]:
        return [p for p in self._providers.values()
                if p.local_or_remote == "remote"]