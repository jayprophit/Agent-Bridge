"""MCP as a versioned replaceable Bridge adapter (P21, REQ-mcp-adapter-boundary).

MCP != Agent Bridge. The bridge speaks its own protocol (protocol.py);
MCP servers speak MCP. This module is the ONLY place the two meet, and
the meeting is descriptive, never executive:

- version negotiation (MCP protocol versions),
- capability discovery (tools/resources/prompts -> Bridge capability
  descriptions),
- transport differences (stdio/websocket/sse) behind one interface.

The adapter never executes, never grants, never imports the executor,
bridge, policy or owner modules. Anything discovered here still executes
only through protocol.validate_action + policy + deterministic executor.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


# --------------------------------------------------------------------------
# Versions
# --------------------------------------------------------------------------

# MCP spec versions the adapter speaks, newest first (negotiation order).
SUPPORTED_MCP_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")


class MCPError(Exception):
    """Base for adapter errors. Transport/execution failures stay typed."""


class MCPVersionError(MCPError):
    """No common MCP protocol version."""


class MCPUnavailable(MCPError):
    """Transport exists as a kind but has no live backend here."""


class MCPDiscoveryError(MCPError):
    """Discovery response malformed."""


def negotiate_version(client_versions: list[str], server_version: str) -> str:
    """Highest common MCP version (our preference order). Fails closed."""
    if not client_versions:
        raise MCPVersionError("client offers no MCP versions")
    if not server_version or not server_version.strip():
        raise MCPVersionError("server reports no MCP version")
    offered = [v for v in SUPPORTED_MCP_VERSIONS if v in client_versions]
    if server_version.strip() in offered:
        return server_version.strip()
    raise MCPVersionError(
        f"no common MCP version (server {server_version.strip()}, "
        f"client overlap {[v for v in client_versions if v in SUPPORTED_MCP_VERSIONS]})"
    )


# --------------------------------------------------------------------------
# Discovery records
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class MCPTool:
    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MCPResource:
    uri: str
    name: str = ""
    mime_type: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MCPPrompt:
    name: str
    description: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MCPDiscovery:
    server: str
    protocol_version: str
    tools: tuple[MCPTool, ...] = ()
    resources: tuple[MCPResource, ...] = ()
    prompts: tuple[MCPPrompt, ...] = ()


def _require_list(payload: Any, what: str) -> list[Any]:
    if not isinstance(payload, list):
        raise MCPDiscoveryError(f"discovery {what} must be a list")
    return payload


def parse_discovery(server: str, protocol_version: str, payload: dict[str, Any]) -> MCPDiscovery:
    """Parse a discovery payload into typed records. Unknown fields are
    preserved opaque in `raw`; nothing here is executable."""
    if not isinstance(payload, dict):
        raise MCPDiscoveryError("discovery payload must be an object")
    tools: list[MCPTool] = []
    for entry in _require_list(payload.get("tools", []), "tools"):
        if not isinstance(entry, dict) or not str(entry.get("name", "")).strip():
            raise MCPDiscoveryError("tool entry requires a non-empty name")
        tools.append(
            MCPTool(
                name=str(entry["name"]).strip(),
                description=str(entry.get("description", "")),
                input_schema=entry["input_schema"] if isinstance(entry.get("input_schema"), dict) else {},
                raw={k: v for k, v in entry.items() if k not in ("name", "description", "input_schema")},
            )
        )
    resources: list[MCPResource] = []
    for entry in _require_list(payload.get("resources", []), "resources"):
        if not isinstance(entry, dict) or not str(entry.get("uri", "")).strip():
            raise MCPDiscoveryError("resource entry requires a non-empty uri")
        resources.append(
            MCPResource(
                uri=str(entry["uri"]).strip(),
                name=str(entry.get("name", "")),
                mime_type=str(entry.get("mimeType", "")),
                raw={k: v for k, v in entry.items() if k not in ("uri", "name", "mimeType")},
            )
        )
    prompts: list[MCPPrompt] = []
    for entry in _require_list(payload.get("prompts", []), "prompts"):
        if not isinstance(entry, dict) or not str(entry.get("name", "")).strip():
            raise MCPDiscoveryError("prompt entry requires a non-empty name")
        prompts.append(
            MCPPrompt(
                name=str(entry["name"]).strip(),
                description=str(entry.get("description", "")),
                raw={k: v for k, v in entry.items() if k not in ("name", "description")},
            )
        )
    return MCPDiscovery(
        server=server,
        protocol_version=protocol_version,
        tools=tuple(tools),
        resources=tuple(resources),
        prompts=tuple(prompts),
    )


# --------------------------------------------------------------------------
# Bridge descriptions (descriptive only — never grants, never executes)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class BridgeCapabilityDescription:
    capability: str
    description: str
    source: str
    mcp_name: str
    mcp_kind: str


def to_bridge_capabilities(discovery: MCPDiscovery) -> list[BridgeCapabilityDescription]:
    """Project MCP records to Bridge capability DESCRIPTIONS. The bridge
    may advertise these; it may not execute or grant from them."""
    out: list[BridgeCapabilityDescription] = []
    for tool in discovery.tools:
        out.append(
            BridgeCapabilityDescription(
                capability=f"mcp.{discovery.server}.{tool.name}",
                description=tool.description or f"MCP tool {tool.name} on {discovery.server}",
                source=f"mcp:{discovery.server}",
                mcp_name=tool.name,
                mcp_kind="tool",
            )
        )
    for resource in discovery.resources:
        out.append(
            BridgeCapabilityDescription(
                capability=f"mcp.{discovery.server}.resource",
                description=f"MCP resource {resource.uri} on {discovery.server}",
                source=f"mcp:{discovery.server}",
                mcp_name=resource.uri,
                mcp_kind="resource",
            )
        )
    for prompt in discovery.prompts:
        out.append(
            BridgeCapabilityDescription(
                capability=f"mcp.{discovery.server}.prompt.{prompt.name}",
                description=prompt.description or f"MCP prompt {prompt.name} on {discovery.server}",
                source=f"mcp:{discovery.server}",
                mcp_name=prompt.name,
                mcp_kind="prompt",
            )
        )
    return out


# --------------------------------------------------------------------------
# Transports
# --------------------------------------------------------------------------

class MCPTransport(ABC):
    """One interface for stdio/websocket/sse differences."""

    kind: str = "unknown"

    @abstractmethod
    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Single MCP request. Raises MCPError on any failure."""

    def discover(self, server: str, protocol_version: str) -> MCPDiscovery:
        payload = self.request("discovery", {})
        if not isinstance(payload, dict):
            raise MCPDiscoveryError("transport returned non-object discovery")
        return parse_discovery(server, protocol_version, payload)


class LoopbackTransport(MCPTransport):
    """In-memory transport for tests and offline development. Serves a
    canned discovery payload; labeled simulated so it is never mistaken
    for a live server."""

    kind = "loopback"
    simulated = True

    def __init__(self, payload: dict[str, Any]):
        self._payload = payload

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method != "discovery":
            raise MCPError(f"loopback serves discovery only, got {method}")
        return self._payload


class _UnavailableTransport(MCPTransport):
    """Declared transport kind with no live backend on this workstation."""

    def __init__(self, kind: str, reason: str):
        self.kind = kind
        self._reason = reason

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        raise MCPUnavailable(f"{self.kind} transport: {self._reason}")


def stdio_transport() -> MCPTransport:
    return _UnavailableTransport("stdio", "no MCP server subprocess registered (owner-authorized runtime work)")


def websocket_transport() -> MCPTransport:
    return _UnavailableTransport("websocket", "no MCP websocket endpoint configured (owner-authorized runtime work)")


def sse_transport() -> MCPTransport:
    return _UnavailableTransport("sse", "no MCP SSE endpoint configured (owner-authorized runtime work)")
