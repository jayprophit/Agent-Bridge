"""Read-only, repeatable IDE discovery primitives."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Any

from ides.descriptor import IDEScriptor
from ides.registry import IDERegistry


@dataclass(frozen=True)
class IDEDiscoveryProbe:
    probe_id: str
    discover: Callable[[], Iterable[IDEScriptor]]
    enabled: bool = True


class IDEAdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, Any] = {}

    def register(self, protocol_id: str, adapter: Any) -> None:
        if not protocol_id:
            raise ValueError("protocol_id must be non-empty")
        self._adapters[protocol_id] = adapter

    def supports(self, protocol_id: str) -> bool:
        return protocol_id in self._adapters

    def get(self, protocol_id: str) -> Any:
        try:
            return self._adapters[protocol_id]
        except KeyError:
            raise KeyError(f"no IDE adapter for protocol: {protocol_id!r}")


class IDEDiscoveryManager:
    def __init__(self, registry: IDERegistry | None = None,
                 adapters: IDEAdapterRegistry | None = None) -> None:
        self.registry = registry or IDERegistry()
        self.adapters = adapters or IDEAdapterRegistry()
        self._probes: dict[str, IDEDiscoveryProbe] = {}
        self._seen_ids: set[str] = set()

    def add_probe(self, probe: IDEDiscoveryProbe) -> None:
        if not probe.probe_id:
            raise ValueError("probe_id must be non-empty")
        self._probes[probe.probe_id] = probe

    def refresh(self) -> list[IDEScriptor]:
        discovered: dict[str, IDEScriptor] = {}
        for probe in self._probes.values():
            if not probe.enabled:
                continue
            for descriptor in probe.discover():
                if not isinstance(descriptor, IDEScriptor):
                    raise TypeError("IDE probes must return IDEScriptor values")
                supports_protocol = any(
                    self.adapters.supports(protocol)
                    for protocol in descriptor.protocols
                )
                if descriptor.status == "UNKNOWN_IDE":
                    descriptor.status = (
                        "AVAILABLE" if supports_protocol
                        else "ADAPTER_REQUIRED" if descriptor.protocols
                        else "UNKNOWN_IDE"
                    )
                discovered[descriptor.ide_id] = descriptor

        for ide_id in self._seen_ids - discovered.keys():
            existing = self.registry.get(ide_id)
            existing.running = False
            existing.status = "OFFLINE"
            self.registry.register(existing, replace=True)
        for descriptor in discovered.values():
            self.registry.register(descriptor, replace=True)
        self._seen_ids = set(discovered)
        return self.registry.list()

    def list(self, **filters: str) -> list[IDEScriptor]:
        return self.registry.list(**filters)

    def describe(self, ide_id: str) -> dict:
        return self.registry.describe(ide_id)

    def health(self, ide_id: str) -> dict[str, Any]:
        ide = self.registry.get(ide_id)
        return {"ide_id": ide.ide_id, "status": ide.status,
                "running": ide.running, "healthy": ide.status == "AVAILABLE"}
