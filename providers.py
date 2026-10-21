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
             num_predict: int = 640,
             think: bool | None = None) -> str:
        ...

    def supports_think_control(self) -> bool:
        """Whether this model's thinking can be turned off.

        Discovered from the runtime, not guessed from the model's name.
        """
        return False


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

    def _get(self, path: str) -> dict[str, Any]:
        """Read-only discovery passthrough to the canonical transport.

        runtime.AgentRuntime.model_inventory() calls this to fetch the FULL
        /api/tags payload — size, modified_at, details — which list_models()'
        name-only list does not carry. Removing it during consolidation broke
        that caller (hasattr(prov, "_get") silently degraded to an empty
        inventory). It is read-only (never loads weights) and routes through
        V2 so transport stays canonical; ProviderError contract preserved.
        """
        try:
            return self._v2._get(path)
        except Exception as e:
            raise ProviderError(f"cannot reach Ollama at {self.host}: {e}")

    def supports_think_control(self) -> bool:
        """Whether this model can reason, and so can be asked not to.

        The answer comes from the runtime's own declaration of the
        model's capabilities, not from its name. A model that can think
        is asked not to, so that it answers in the content field where
        the action is read from.
        """
        try:
            return bool(self._v2.discover(self.model).reasoning)
        except Exception:
            return False

    def chat(self, messages: list[dict[str, str]], temperature: float = 0.1,
             num_predict: int = 640,
             think: bool | None = None) -> str:
        """Ask the model, and return what it actually answered.

        ``think`` is forwarded only when it is given. A reasoning model
        that is left to think answers in its thinking field and leaves
        the content empty, and the caller gets nothing to act on. The
        Bridge asks such a model to answer directly, and says so in the
        error when the model spends its whole output budget thinking.
        """
        try:
            data = self._v2.chat(self.model, messages,
                                 temperature=temperature,
                                 num_predict=num_predict, think=think)
        except Exception as e:  # V2 normalized errors → ProviderError
            raise ProviderError(f"Ollama chat failed: {e}")
        text = data.get("content", "")
        if not text:
            reasoning = str(data.get("thinking", "") or "")
            if reasoning:
                raise ProviderError(
                    f"the model answered only in its thinking and produced no "
                    f"content ({len(reasoning)} characters of reasoning); it "
                    f"used its whole output budget before it answered")
            raise ProviderError(f"empty chat response: {str(dict(data))[:500]}")
        return text



def create_provider(kind: str, **kwargs: Any) -> ModelProvider:
    if kind == "ollama":
        return OllamaProvider(**kwargs)
    raise ProviderError(
        f"provider {kind!r} not implemented in v0.3 (available: 'ollama')")


OllamaClient = OllamaProvider
OllamaError = ProviderError
