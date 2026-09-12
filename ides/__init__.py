"""Universal IDE/editor/workspace discovery and routing (v0.7)."""
from ides.descriptor import IDEScriptor, WorkspaceDescriptor
from ides.discovery import IDEAdapterRegistry, IDEDiscoveryManager, IDEDiscoveryProbe
from ides.registry import IDERegistry, WorkspaceRegistry
from ides.router import IDERouter, IDERoutingDecision

__all__ = [
    "IDEScriptor", "WorkspaceDescriptor", "IDEAdapterRegistry",
    "IDEDiscoveryManager", "IDEDiscoveryProbe", "IDERegistry",
    "WorkspaceRegistry", "IDERouter", "IDERoutingDecision",
]
