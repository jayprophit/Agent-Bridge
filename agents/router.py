"""Capability-based routing for discovered agents."""
from __future__ import annotations

from agents.registry import AgentRegistry


class AgentRouter:
    def __init__(self, registry: AgentRegistry) -> None:
        self.registry = registry

    def route(self, required_capabilities: list[str] | None = None,
              protocol: str = "", local_only: bool = False):
        required = set(required_capabilities or [])
        candidates = []
        for agent in self.registry.list(status="AVAILABLE", protocol=protocol):
            if required and not required.issubset(agent.capabilities):
                continue
            if local_only and agent.local_or_remote != "local":
                continue
            candidates.append(agent)
        if not candidates:
            raise LookupError("no available agent matches routing requirements")
        return candidates[0]
