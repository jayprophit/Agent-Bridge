"""Deterministic fake model provider for v0.3 unit tests (no Ollama)."""
from __future__ import annotations


class FakeProvider:
    def __init__(self, script: list[str], model: str = "fake-test-model"):
        self.script = list(script)
        self.model = model
        self.calls = 0

    def list_models(self) -> list[str]:
        return [self.model]

    def chat(self, messages, temperature: float = 0.1, num_predict: int = 640) -> str:
        self.calls += 1
        if self.script:
            return self.script.pop(0)
        return '{"action":"finish","message":"default-finish"}'


class RoleFakeProviders:
    """Per-role scripted providers: role -> FakeProvider."""

    def __init__(self, scripts: dict[str, list[str]], model: str = "fake-test-model"):
        self.providers = {r: FakeProvider(s, model) for r, s in scripts.items()}
        self.model = model

    def for_role(self, role: str) -> FakeProvider:
        if role not in self.providers:
            self.providers[role] = FakeProvider([], self.model)
        return self.providers[role]
