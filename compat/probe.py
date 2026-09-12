"""Model capability probe (v0.8). Measures interaction modes, no name rules.

Drives scripted probe exchanges through a duck-typed model caller
(generate(prompt) -> str) at registration/benchmark time. Selects the
compat mode automatically via compat.modes.select_modes().
"""
from __future__ import annotations

import json
from typing import Any, Callable

from compat.modes import select_modes

PROBE_JSON_TASK = (
    'Reply with exactly one JSON object and nothing else: '
    '{"tool": "tools.list", "arguments": {}}'
)
PROBE_STRUCTURED_TASK = (
    'Reply with exactly one JSON object with keys "tool" and "arguments" '
    'for a fictional "probe.ping" tool.'
)
PROBE_TEXT_TASK = "Say the word BLUE and nothing else."


class ModelCapabilityProbe:
    """Probe a model caller for interaction capabilities."""

    def __init__(self, timeout_s: int = 120):
        self.timeout_s = timeout_s

    def probe(self, generate: Callable[[str], str],
              context_tokens: int = 0) -> dict[str, Any]:
        """Run scripted probes. Never raises on model failure."""
        evidence: dict[str, Any] = {"context_tokens": context_tokens}
        try:
            strict = self._strict_json_ok(generate(PROBE_JSON_TASK))
        except Exception:
            strict = False
        try:
            bridge = self._bridge_ok(generate(PROBE_STRUCTURED_TASK))
        except Exception:
            bridge = False
        try:
            text = self._text_ok(generate(PROBE_TEXT_TASK))
        except Exception:
            text = False
        evidence.update({
            "native_tools": False,  # only provider adapters can claim this
            "bridge_structured": bool(bridge),
            "strict_json": bool(strict),
            "text_actions": bool(text),
            "vision": False,
            "audio": False,
            "streaming": False,
            "reasoning_reliability": None,
        })
        evidence["modes"] = select_modes(evidence)
        return evidence

    @staticmethod
    def _strict_json_ok(reply: str) -> bool:
        try:
            obj = json.loads(reply.strip())
        except (ValueError, AttributeError):
            return False
        return isinstance(obj, dict) and obj.get("tool") == "tools.list"

    @staticmethod
    def _bridge_ok(reply: str) -> bool:
        try:
            obj = json.loads(reply.strip())
        except (ValueError, AttributeError):
            return "probe.ping" in (reply or "")
        return isinstance(obj, dict) and isinstance(obj.get("tool"), str)

    @staticmethod
    def _text_ok(reply: str) -> bool:
        return (reply or "").strip().upper() == "BLUE"
