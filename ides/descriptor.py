"""Vendor-neutral IDE and workspace descriptors."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

IDE_TYPES = (
    "DESKTOP_IDE", "DESKTOP_EDITOR", "TERMINAL_EDITOR", "AI_NATIVE_IDE",
    "WEB_IDE", "CLOUD_IDE", "REMOTE_IDE", "MOBILE_IDE", "NOTEBOOK",
    "SCIENTIFIC_IDE", "GAME_ENGINE_EDITOR", "EMBEDDED_IDE", "CUSTOM_IDE",
    "UNKNOWN_IDE",
)

IDE_STATUSES = ("AVAILABLE", "UNAVAILABLE", "UNKNOWN_IDE", "ADAPTER_REQUIRED",
                "OFFLINE", "AUTH_REQUIRED")


@dataclass
class IDEScriptor:
    ide_id: str
    name: str = ""
    version: str = ""
    ide_type: str = "UNKNOWN_IDE"
    vendor: str = ""
    platform: str = "unknown"
    architecture: str = ""
    executable: str = ""
    install_path: str = ""
    running: bool = False
    local_or_remote: str = "unknown"
    discovery_method: str = ""
    protocols: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    workspaces: list[str] = field(default_factory=list)
    agent_ids: list[str] = field(default_factory=list)
    status: str = "UNKNOWN_IDE"
    limitations: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.ide_id:
            raise ValueError("ide_id must be non-empty")
        if self.ide_type not in IDE_TYPES:
            raise ValueError(f"unknown IDE type: {self.ide_type}")
        if self.status not in IDE_STATUSES:
            raise ValueError(f"unknown IDE status: {self.status}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def supports(self, capability: str) -> bool:
        return capability in self.capabilities


@dataclass
class WorkspaceDescriptor:
    workspace_id: str
    name: str = ""
    path_or_reference: str = ""
    project_type: str = ""
    languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    repository: str = ""
    branch: str = ""
    local_or_remote: str = "unknown"
    node_id: str = ""
    associated_ides: list[str] = field(default_factory=list)
    preferred_ide: str = ""
    build_system: str = ""
    test_system: str = ""
    runtime: str = ""
    container: str = ""
    virtual_environment: str = ""
    protected: bool = False
    precious: bool = False
    last_opened: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.workspace_id:
            raise ValueError("workspace_id must be non-empty")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
