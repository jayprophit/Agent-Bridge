"""NodeRegistry (v0.7). Catalog of available nodes for cross-device coordination.

Manages the registry of nodes that can participate in cross-device agent coordination.
Nodes can be physical devices, virtual machines, or any Agent Bridge instance.
"""
from __future__ import annotations

import time
from typing import Any

from nodes.node_descriptor import (
    LIMITED_NODE, NODE_OFFLINE, NODE_ONLINE, TRUSTED_NODE, UNTRUSTED_NODE,
    NodeDescriptor
)


class NodeRegistry:
    """Registry of available nodes for cross-device coordination."""
    
    def __init__(self):
        self._nodes: dict[str, NodeDescriptor] = {}
        self._local_node_id: str = ""
    
    def register(self, node: NodeDescriptor) -> None:
        """Register a node in the registry."""
        if not node.node_id:
            raise ValueError("node_id must be non-empty")
        self._nodes[node.node_id] = node
    
    def unregister(self, node_id: str) -> None:
        """Unregister a node from the registry."""
        if node_id in self._nodes:
            del self._nodes[node_id]
    
    def get(self, node_id: str) -> NodeDescriptor:
        """Get a node by ID."""
        if node_id not in self._nodes:
            raise KeyError(f"node not found: {node_id}")
        return self._nodes[node_id]
    
    def update(self, node_id: str, updates: dict[str, Any]) -> NodeDescriptor:
        """Update a node's descriptor."""
        node = self.get(node_id)
        for key, value in updates.items():
            if hasattr(node, key):
                setattr(node, key, value)
        node.last_seen = time.monotonic()
        return node
    
    def set_local_node(self, node_id: str) -> None:
        """Set the local node ID (this device)."""
        self._local_node_id = node_id
    
    def get_local_node(self) -> NodeDescriptor | None:
        """Get the local node descriptor."""
        if self._local_node_id and self._local_node_id in self._nodes:
            return self._nodes[self._local_node_id]
        return None
    
    def list_nodes(self, online_only: bool = False,
                  trust_level: str = "") -> list[NodeDescriptor]:
        """List nodes with optional filtering."""
        nodes = list(self._nodes.values())
        
        if online_only:
            nodes = [n for n in nodes if n.online]
        
        if trust_level:
            nodes = [n for n in nodes if n.trust_level == trust_level]
        
        return sorted(nodes, key=lambda n: n.node_id)
    
    def online_nodes(self) -> list[NodeDescriptor]:
        """Get all online nodes."""
        return self.list_nodes(online_only=True)
    
    def trusted_nodes(self) -> list[NodeDescriptor]:
        """Get all trusted nodes."""
        return [n for n in self._nodes.values() if n.trust_level in (OWNER_NODE, TRUSTED_NODE)]
    
    def find_by_capability(self, tool_id: str) -> list[NodeDescriptor]:
        """Find nodes that have a specific tool capability."""
        return [n for n in self._nodes.values() if n.is_capable_of(tool_id)]
    
    def find_by_model(self, model_id: str) -> list[NodeDescriptor]:
        """Find nodes that have a specific model."""
        return [n for n in self._nodes.values() if n.has_model(model_id)]
    
    def find_by_device_class(self, device_class: str) -> list[NodeDescriptor]:
        """Find nodes by device class."""
        return [n for n in self._nodes.values() if n.device_class == device_class]
    
    def search(self, query: str, limit: int = 20) -> list[NodeDescriptor]:
        """Search nodes by query string."""
        words = [w.lower() for w in query.split() if w]
        scored = []
        
        for node in self._nodes.values():
            hay = f"{node.node_id} {node.display_name} {node.description} " \
                  f"{node.platform} {node.device_class} " \
                  f"{' '.join(node.tools)} {' '.join(node.models)}".lower()
            score = sum(2 for w in words if w in hay)
            if score:
                scored.append((score, node))
        
        scored.sort(key=lambda t: (-t[0], t[1].node_id))
        return [n for _, n in scored[:limit]]
    
    def mark_offline(self, node_id: str) -> None:
        """Mark a node as offline."""
        if node_id in self._nodes:
            self._nodes[node_id].online = False
            self._nodes[node_id].last_seen = time.monotonic()
    
    def mark_online(self, node_id: str) -> None:
        """Mark a node as online."""
        if node_id in self._nodes:
            self._nodes[node_id].online = True
            self._nodes[node_id].last_seen = time.monotonic()
    
    def update_heartbeat(self, node_id: str, load: float = 0.0) -> None:
        """Update node heartbeat and load."""
        if node_id in self._nodes:
            self._nodes[node_id].last_seen = time.monotonic()
            self._nodes[node_id].current_load = load
            self._nodes[node_id].online = True
    
    def cleanup_stale(self, timeout_seconds: int = 300) -> list[str]:
        """Remove nodes that haven't been seen recently."""
        now = time.monotonic()
        stale_nodes = []
        
        for node_id, node in list(self._nodes.items()):
            if now - node.last_seen > timeout_seconds:
                stale_nodes.append(node_id)
                self.unregister(node_id)
        
        return stale_nodes
    
    def __len__(self) -> int:
        return len(self._nodes)
    
    def ids(self) -> list[str]:
        return sorted(self._nodes.keys())