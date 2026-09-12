"""Universal agent discovery and routing (v0.7)."""
from agents.descriptor import AgentDescriptor
from agents.discovery import AgentAdapterRegistry, AgentDiscoveryManager, DiscoveryProbe
from agents.protocol import KNOWN_PROTOCOLS, ProtocolDefinition, ProtocolRegistry
from agents.registry import AgentRegistry
from agents.router import AgentRouter

__all__ = [
    "AgentDescriptor", "AgentAdapterRegistry", "AgentDiscoveryManager",
    "DiscoveryProbe", "KNOWN_PROTOCOLS", "ProtocolDefinition",
    "ProtocolRegistry", "AgentRegistry", "AgentRouter",
]
