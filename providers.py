"""Model-provider abstraction (v0.3). Only Ollama is implemented.

Future providers (llama.cpp, LM Studio, OpenAI-compatible local servers,
cloud, Genesis-native) implement ModelProvider without touching the bridge.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ProviderError(Exception):
    pass


class ModelProvider(ABC):
    kind: str = "base"

    def __init__(self, model: str, timeout_s: int = 120):
        self.model = model
        self.timeout_s = timeout_s

    @abstractmethod
    def list_models(self) -> list[str]:
        ...

    @abstractmethod
    def chat(self, messages: list[dict[str, str]], temperature: float = 0.1,
             num_predict: int = 640) -> str:
        ...


class OllamaProvider(ModelProvider):
    kind = "ollama"

    def __init__(self, host: str = "http://127.0.0.1:11434",
                 model: str = "hhao/qwen2.5-coder-tools:3b", timeout_s: int = 120):
        super().__init__(model, timeout_s)
        self.host = host.rstrip("/")
        # Canonical lease-aware transport. This class no longer speaks Ollama
        # HTTP directly: it delegates every model-touching call to
        # OllamaProviderV2 so there is exactly ONE place that decides keep_alive,
        # residency and error vocabulary. The public contract (chat()->str,
        # list_models(), ProviderError) is preserved for every existing caller.
        from compute.ollama_provider_v2 import OllamaProviderV2
        self._v2 = OllamaProviderV2(base_url=self.host, timeout=float(timeout_s))

    def list_models(self) -> list[str]:
        try:
            return self._v2.list_models()
        except Exception as e:  # preserve ProviderError contract
            raise ProviderError(f"cannot reach Ollama at {self.host}: {e}")

    def chat(self, messages: list[dict[str, str]], temperature: float = 0.1,
             num_predict: int = 640) -> str:
        try:
            data = self._v2.chat(self.model, messages,
                                 temperature=temperature, num_predict=num_predict)
        except Exception as e:  # V2 normalized errors → ProviderError
            raise ProviderError(f"Ollama chat failed: {e}")
        text = data.get("content", "")
        if not text:
            raise ProviderError(f"empty chat response: {str(dict(data))[:500]}")
        return text



def create_provider(kind: str, **kwargs: Any) -> ModelProvider:
    if kind == "ollama":
        return OllamaProvider(**kwargs)
    raise ProviderError(
        f"provider {kind!r} not implemented in v0.3 (available: 'ollama')")


OllamaClient = OllamaProvider
OllamaError = ProviderError
