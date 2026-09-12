"""Vendor-neutral agent descriptors for Agent Bridge v0.7."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

AGENT_TYPES = (
    "MODEL_PROVIDER", "LOCAL_INFERENCE_RUNTIME", "REMOTE_MODEL_PROVIDER",
    "IDE_AGENT", "CODING_AGENT", "CLI_AGENT", "DESKTOP_AGENT",
    "MOBILE_AGENT", "WEB_AGENT", "AUTONOMOUS_AGENT", "SPECIALIST_AGENT",
    "MULTIMODAL_AGENT", "VOICE_AGENT", "VISION_AGENT", "TOOL_AGENT",
    "MCP_SERVER", "MCP_CLIENT", "A2A_AGENT", "REMOTE_AGENT", "NODE_AGENT",
    "CUSTOM_AGENT", "UNKNOWN_AGENT",
)

AGENT_STATUSES = (
    "AVAILABLE", "UNAVAILABLE", "UNKNOWN_AGENT", "ADAPTER_REQUIRED",
    "AUTH_REQUIRED", "OFFLINE",
)


@dataclass
class AgentDescriptor:
    agent_id: str
    display_name: str = ""
    agent_type: str = "UNKNOWN_AGENT"
    status: str = "UNKNOWN_AGENT"
    description: str = ""
    endpoint: str = ""
    provider_id: str = ""
    model_ids: list[str] = field(default_factory=list)
    protocols: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    local_or_remote: str = "unknown"
    requires_auth: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.agent_id:
            raise ValueError("agent_id must be non-empty")
        if self.agent_type not in AGENT_TYPES:
            raise ValueError(f"unknown agent type: {self.agent_type}")
        if self.status not in AGENT_STATUSES:
            raise ValueError(f"unknown agent status: {self.status}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def routable(self) -> bool:
        return self.status == "AVAILABLE" and bool(self.protocols or self.endpoint)
