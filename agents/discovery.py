"""Safe, repeatable discovery primitives for agents and protocols."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable

from agents.descriptor import AgentDescriptor
from agents.protocol import ProtocolDefinition, ProtocolRegistry
from agents.registry import AgentRegistry


@dataclass(frozen=True)
class DiscoveryProbe:
    probe_id: str
    discover: Callable[[], Iterable[AgentDescriptor]]
    enabled: bool = True


class AgentAdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, Any] = {}

    def register(self, protocol_id: str, adapter: Any) -> None:
        if not protocol_id:
            raise ValueError("protocol_id must be non-empty")
        self._adapters[protocol_id] = adapter

    def get(self, protocol_id: str) -> Any:
        try:
            return self._adapters[protocol_id]
        except KeyError:
            raise KeyError(f"no agent adapter for protocol: {protocol_id!r}")

    def supports(self, protocol_id: str) -> bool:
        return protocol_id in self._adapters


class AgentDiscoveryManager:
    def __init__(self, registry: AgentRegistry | None = None,
                 protocols: ProtocolRegistry | None = None,
                 adapters: AgentAdapterRegistry | None = None) -> None:
        self.registry = registry or AgentRegistry()
        self.protocols = protocols or ProtocolRegistry()
        self.adapters = adapters or AgentAdapterRegistry()
        self._probes: dict[str, DiscoveryProbe] = {}
        self._last_results: list[str] = []

    def add_probe(self, probe: DiscoveryProbe) -> None:
        if not probe.probe_id:
            raise ValueError("probe_id must be non-empty")
        self._probes[probe.probe_id] = probe

    def register_protocol(self, definition: ProtocolDefinition,
                          adapter: Any = None) -> None:
        self.protocols.register(definition)
        if adapter is not None:
            self.adapters.register(definition.protocol_id, adapter)

    def refresh(self) -> list[AgentDescriptor]:
        discovered: list[AgentDescriptor] = []
        for probe in self._probes.values():
            if not probe.enabled:
                continue
            for descriptor in probe.discover():
                if not isinstance(descriptor, AgentDescriptor):
                    raise TypeError("discovery probes must return AgentDescriptor values")
                supported = any(self.adapters.supports(protocol)
                                for protocol in descriptor.protocols)
                if descriptor.status == "UNKNOWN_AGENT" and supported:
                    descriptor.status = "AVAILABLE"
                elif descriptor.status == "UNKNOWN_AGENT" and descriptor.protocols:
                    descriptor.status = "ADAPTER_REQUIRED"
                self.registry.register(descriptor, replace=True)
                discovered.append(descriptor)
        self._last_results = [item.agent_id for item in discovered]
        return discovered

    def last_results(self) -> list[str]:
        return list(self._last_results)
