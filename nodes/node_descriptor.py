"""NodeDescriptor (v0.7). Normalized node capability representation.

Provides a standardized representation of node capabilities across different
device types and platforms for cross-device coordination.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any

# Trust levels
OWNER_NODE = "OWNER_NODE"
TRUSTED_NODE = "TRUSTED_NODE"
LIMITED_NODE = "LIMITED_NODE"
UNTRUSTED_NODE = "UNTRUSTED_NODE"

TRUST_LEVELS = (OWNER_NODE, TRUSTED_NODE, LIMITED_NODE, UNTRUSTED_NODE)

# Node states
NODE_ONLINE = "ONLINE"
NODE_OFFLINE = "OFFLINE"
NODE_BUSY = "BUSY"
NODE_DEGRADED = "DEGRADED"
NODE_ERROR = "ERROR"

NODE_STATES = (NODE_ONLINE, NODE_OFFLINE, NODE_BUSY, NODE_DEGRADED, NODE_ERROR)


@dataclass
class NodeDescriptor:
    """Normalized node capability descriptor."""
    node_id: str
    device_class: str = "unknown"  # desktop, laptop, phone, tablet, watch, etc.
    platform: str = "unknown"  # windows, macos, linux, android, ios, etc.
    architecture: str = ""  # x86_64, arm64, etc.
    
    # Status
    online: bool = False
    trust_level: str = UNTRUSTED_NODE
    current_load: float = 0.0  # 0.0 to 1.0
    last_seen: float = field(default_factory=time.monotonic)
    # Resource class (hardware-capacity axis) vs runtime_role (node-function
    # axis). A CONSTRAINED_RUNTIME box can serve a DELEGATION_NODE role.
    resource_class: str = ""
    
    # Runtime role (FULL_RUNTIME, CONSTRAINED_RUNTIME, CLIENT_NODE,
    # DELEGATION_NODE, SENSOR_NODE, DISPLAY_NODE)
    runtime_role: str = ""
    # Capabilities
    tools: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    providers: list[str] = field(default_factory=list)
    agents: list[str] = field(default_factory=list)
    ides: list[str] = field(default_factory=list)
    memory_mb: int = 0
    storage_mb: int = 0
    battery_percent: int = 0
    network_available: bool = False
    
    # Hardware
    cpu_cores: int = 0
    gpu_available: bool = False
    gpu_memory_mb: int = 0
    ai_accelerator: bool = False
    
    # Permissions
    admin_capability: bool = False
    filesystem_write: bool = False
    browser_available: bool = False
    
    # Privacy
    privacy_scope: str = "local"  # local, trusted_lan, restricted
    data_locality: str = "local"  # local, can_delegate, restricted
    
    # Network
    endpoint: str = ""
    latency_ms: int = 0
    bandwidth_mbps: int = 0
    
    # Input/Output devices (presence, not permission)
    input_devices: list[str] = field(default_factory=list)
    output_devices: list[str] = field(default_factory=list)
    input_capabilities: list[str] = field(default_factory=list)
    output_capabilities: list[str] = field(default_factory=list)
    # Local data roots advertised for locality routing (safe subset only)
    data_roots: list[str] = field(default_factory=list)
    
    # Metadata
    display_name: str = ""
    description: str = ""
    version: str = "0.7.0"
    capabilities: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)
    
    def is_capable_of(self, tool_id: str) -> bool:
        """Check if node has a specific tool capability."""
        return tool_id in self.tools or any(tool_id.startswith(f) for f in self.tools)
    
    def has_model(self, model_id: str) -> bool:
        """Check if node has a specific model."""
        return model_id in self.models
    
    def can_delegate(self, task_requirements: dict[str, Any]) -> bool:
        """Check if node can handle a task based on requirements."""
        required_tools = task_requirements.get("required_tools", [])
        required_model = task_requirements.get("required_model", "")
        
        # Check required tools
        for tool in required_tools:
            if not self.is_capable_of(tool):
                return False
        
        # Check required model
        if required_model and not self.has_model(required_model):
            return False
        
        # Check if node is online
        if not self.online:
            return False
        
        # Check trust level
        required_trust = task_requirements.get("min_trust_level", LIMITED_NODE)
        trust_priority = {OWNER_NODE: 4, TRUSTED_NODE: 3, LIMITED_NODE: 2, UNTRUSTED_NODE: 1}
        if trust_priority.get(self.trust_level, 0) < trust_priority.get(required_trust, 0):
            return False
        
        # Check privacy constraints
        privacy_required = task_requirements.get("privacy_policy", "local")
        if privacy_required == "local" and self.privacy_scope != "local":
            return False
        
        return True
    
    def is_mobile(self) -> bool:
        """Check if this is a mobile device."""
        return self.device_class in ("phone", "tablet", "watch", "smart_ring", "smart_glasses")
    
    def is_desktop(self) -> bool:
        """Check if this is a desktop-class device."""
        return self.device_class in ("desktop", "workstation", "server", "laptop")
    
    def has_gpu(self) -> bool:
        """Check if node has GPU capability."""
        return self.gpu_available
    
    def is_battery_powered(self) -> bool:
        """Check if node is battery-powered."""
        return self.battery_percent > 0