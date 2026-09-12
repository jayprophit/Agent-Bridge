"""Generic protocol registry; vendor names are not a whitelist."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

KNOWN_PROTOCOLS = (
    "OPENAI_COMPATIBLE", "OLLAMA_COMPATIBLE", "LOCAL_HTTP_INFERENCE",
    "REST", "JSON_RPC", "SSE", "WEBSOCKET", "CLI_AGENT", "MCP", "A2A",
    "AGENT_BRIDGE_NATIVE", "CUSTOM_PLUGIN",
)


@dataclass(frozen=True)
class ProtocolDefinition:
    protocol_id: str
    adapter: Any = None
    description: str = ""


class ProtocolRegistry:
    def __init__(self) -> None:
        self._protocols: dict[str, ProtocolDefinition] = {}

    def register(self, definition: ProtocolDefinition) -> None:
        if not definition.protocol_id:
            raise ValueError("protocol_id must be non-empty")
        self._protocols[definition.protocol_id] = definition

    def get(self, protocol_id: str) -> ProtocolDefinition:
        try:
            return self._protocols[protocol_id]
        except KeyError:
            raise KeyError(f"unknown protocol: {protocol_id!r}")

    def supports(self, protocol_id: str) -> bool:
        return protocol_id in self._protocols

    def ids(self) -> list[str]:
        return sorted(self._protocols)
