"""Deterministic mock runtime/provider for UI/client tests (no Ollama).

Simulates scripted runs: success, approval gate, failure, revise loop,
rollback availability, cancellation, loop detection. The reference shell
talks to it through the same public client surface (or embedded runtime
with an injected provider factory).
"""
from __future__ import annotations

from typing import Any


class MockProvider:
    """Scripted model: pops planned replies, then a safe finish."""

    def __init__(self, script: list[str], model: str = "mock-model"):
        self.script = list(script)
        self.model = model
        self.calls = 0

    def list_models(self) -> list[str]:
        return [self.model]

    def chat(self, messages, temperature: float = 0.1,
             num_predict: int = 640) -> str:
        self.calls += 1
        if self.script:
            return self.script.pop(0)
        return '{"action":"finish","message":"mock done"}'


def factory_for(scripts: dict[str, list[str]], model: str = "mock-model"):
    provs: dict[str, MockProvider] = {}

    def make(role: str) -> MockProvider:
        if role not in provs:
            provs[role] = MockProvider(list(scripts.get(role, scripts.get("*", []))),
                                       model)
        return provs[role]

    make.provs = provs  # type: ignore[attr-defined]
    return make


SUCCESS = {
    "*": ['{"action":"write","path":"ok.txt","content":"mock hi"}',
          '{"action":"finish","message":"mock success"}'],
}

NEEDS_APPROVAL = {
    "*": ['{"action":"delete","path":"victim.txt"}',
          '{"action":"finish","message":"mock approval flow"}'],
}

FAILURE = {
    "*": ['{"action":"read","path":"missing.txt"}',
          '{"action":"read","path":"missing.txt"}',
          '{"action":"read","path":"missing.txt"}',
          '{"action":"finish","message":"mock failure flow"}'],
}
