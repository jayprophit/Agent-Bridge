"""Dynamic, model-independent agent registry."""
from __future__ import annotations

from typing import Iterable

from agents.descriptor import AgentDescriptor


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, AgentDescriptor] = {}

    def register(self, descriptor: AgentDescriptor, replace: bool = False) -> None:
        if descriptor.agent_id in self._agents and not replace:
            raise ValueError(f"duplicate agent_id: {descriptor.agent_id}")
        self._agents[descriptor.agent_id] = descriptor

    def register_many(self, descriptors: Iterable[AgentDescriptor]) -> None:
        for descriptor in descriptors:
            self.register(descriptor)

    def unregister(self, agent_id: str) -> None:
        self._agents.pop(agent_id, None)

    def get(self, agent_id: str) -> AgentDescriptor:
        try:
            return self._agents[agent_id]
        except KeyError:
            raise KeyError(f"unknown agent: {agent_id!r}")

    def ids(self) -> list[str]:
        return sorted(self._agents)

    def list(self, agent_type: str = "", status: str = "",
             protocol: str = "", capability: str = "") -> list[AgentDescriptor]:
        result = []
        for agent in self._agents.values():
            if agent_type and agent.agent_type != agent_type:
                continue
            if status and agent.status != status:
                continue
            if protocol and protocol not in agent.protocols:
                continue
            if capability and capability not in agent.capabilities:
                continue
            result.append(agent)
        return sorted(result, key=lambda item: item.agent_id)

    def search(self, query: str, limit: int = 20) -> list[AgentDescriptor]:
        words = [word.lower() for word in query.split() if word]
        scored = []
        for agent in self._agents.values():
            haystack = " ".join((
                agent.agent_id, agent.display_name, agent.description,
                agent.agent_type, " ".join(agent.capabilities),
                " ".join(agent.protocols),
            )).lower()
            score = sum(2 for word in words if word in haystack)
            if score:
                scored.append((score, agent))
        scored.sort(key=lambda item: (-item[0], item[1].agent_id))
        return [agent for _, agent in scored[:limit]]

    def describe(self, agent_id: str) -> dict:
        return self.get(agent_id).to_dict()

    def __len__(self) -> int:
        return len(self._agents)
