"""Model-provider abstraction (v0.3). Only Ollama is implemented.

Future providers (llama.cpp, LM Studio, OpenAI-compatible local servers,
cloud, Genesis-native) implement ModelProvider without touching the bridge.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
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

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self.host + path, data=data,
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:2000]
            raise ProviderError(f"HTTP {e.code} {path}: {detail}")
        except urllib.error.URLError as e:
            raise ProviderError(f"cannot reach Ollama at {self.host}: {e.reason}")
        except TimeoutError:
            raise ProviderError("Ollama request timed out")
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            raise ProviderError(f"non-JSON response: {body[:500]!r}")

    def _get(self, path: str) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(self.host + path, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise ProviderError(f"cannot reach Ollama at {self.host}: {e.reason}")

    def list_models(self) -> list[str]:
        data = self._get("/api/tags")
        return [m.get("name", "") for m in data.get("models", [])]

    def chat(self, messages: list[dict[str, str]], temperature: float = 0.1,
             num_predict: int = 640) -> str:
        data = self._post("/api/chat", {
            "model": self.model, "messages": messages, "stream": False,
            "options": {"temperature": temperature, "num_predict": num_predict},
        })
        text = (data.get("message") or {}).get("content", "")
        if not text:
            raise ProviderError(f"empty chat response: {str(data)[:500]}")
        return text


def create_provider(kind: str, **kwargs: Any) -> ModelProvider:
    if kind == "ollama":
        return OllamaProvider(**kwargs)
    raise ProviderError(
        f"provider {kind!r} not implemented in v0.3 (available: 'ollama')")


OllamaClient = OllamaProvider
OllamaError = ProviderError
