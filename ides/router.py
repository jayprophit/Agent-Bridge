"""Capability-based IDE routing with explicit headless fallback."""
from __future__ import annotations

from dataclasses import dataclass

from ides.descriptor import IDEScriptor
from ides.registry import IDERegistry


@dataclass(frozen=True)
class IDERoutingDecision:
    ide: IDEScriptor | None
    mode: str
    reason: str
    fallback: bool = False


class IDERouter:
    def __init__(self, registry: IDERegistry) -> None:
        self.registry = registry

    def route(self, required_capabilities: list[str] | None = None,
              workspace_id: str = "", preferred_ide: str = "",
              mode: str = "AUTO") -> IDERoutingDecision:
        required = set(required_capabilities or [])
        if mode == "HEADLESS":
            return IDERoutingDecision(None, mode, "headless mode requested")

        candidates = [
            ide for ide in self.registry.list(status="AVAILABLE")
            if required.issubset(ide.capabilities)
        ]
        if preferred_ide:
            preferred = [ide for ide in candidates if ide.ide_id == preferred_ide]
            if preferred:
                return IDERoutingDecision(preferred[0], mode, "owner/workspace preference")
        if candidates:
            return IDERoutingDecision(candidates[0], mode, "capability match")
        return IDERoutingDecision(None, "HEADLESS", "no compatible IDE available", True)
