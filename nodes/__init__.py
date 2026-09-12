"""Cross-device node architecture (v0.7).

This module provides the foundation for cross-device agent coordination:
- NodeRegistry: Catalog of available nodes/devices
- NodeDescriptor: Normalized node capability representation
- NodeRouter: Task delegation across nodes
- TaskDelegator: Cross-device task execution
- TrustRegistry: Node trust and pairing management
"""
from __future__ import annotations

from nodes.node_registry import NodeRegistry, NodeDescriptor
from nodes.node_factory import node_from_device_profile
from nodes.node_router import NodeRouter, RoutingDecision, TaskRequirements, create_node_router
from nodes.task_delegator import TaskDelegator, DelegationRequest, DelegationResult, NodeTransport, create_task_delegator
from nodes.trust_registry import TrustRegistry, TrustRecord, create_trust_registry
from nodes.node_transport import (
    TRANSPORT_IN_MEMORY, TRANSPORT_HTTP, TRANSPORT_HTTPS, TRANSPORT_SSE,
    TRANSPORT_WEBSOCKET, WEBSOCKET_STATUS,
    SECURITY_MODE_IN_MEMORY, SECURITY_MODE_PLAINTEXT_LOOPBACK, SECURITY_MODE_TLS,
    PROTOCOL_NAME, PROTOCOL_VERSION, PROTOCOL_MIN_SUPPORTED, PROTOCOL_MAX_SUPPORTED,
    NodeProtocolInfo, TaskEnvelope, ResultEnvelope,
    PairingManager, ReplayGuard, CredentialStore, DevFileCredentialStore,
    WindowsCredentialManagerStore, TlsConfig, HttpNodeTransport,
    ERR_REMOTE_OWNER_POLICY_DENIED, ERR_REMOTE_OWNER_APPROVAL_REQUIRED,
    REMOTE_OWNER_DISABLED, REMOTE_OWNER_APPROVAL_REQUIRED, REMOTE_OWNER_ENABLED,
    REMOTE_OWNER_POLICIES,
    challenge_response, negotiate_protocol, privacy_allows_send,
    ensure_loopback_or_raise, audit_event,
)
from nodes.node_server import NodeServerState, build_capability_summary, serve_node, node_api_schema

__all__ = [
    "NodeRegistry",
    "NodeDescriptor",
    "node_from_device_profile",
    "NodeRouter",
    "RoutingDecision",
    "TaskRequirements",
    "TaskDelegator",
    "DelegationRequest",
    "DelegationResult",
    "NodeTransport",
    "TrustRegistry",
    "TrustRecord",
    "create_trust_registry",
    "create_node_router",
    "create_task_delegator",
    "TRANSPORT_IN_MEMORY",
    "TRANSPORT_HTTP",
    "TRANSPORT_HTTPS",
    "TRANSPORT_SSE",
    "TRANSPORT_WEBSOCKET",
    "WEBSOCKET_STATUS",
    "SECURITY_MODE_IN_MEMORY",
    "SECURITY_MODE_PLAINTEXT_LOOPBACK",
    "SECURITY_MODE_TLS",
    "PROTOCOL_NAME",
    "PROTOCOL_VERSION",
    "PROTOCOL_MIN_SUPPORTED",
    "PROTOCOL_MAX_SUPPORTED",
    "NodeProtocolInfo",
    "TaskEnvelope",
    "ResultEnvelope",
    "PairingManager",
    "ReplayGuard",
    "CredentialStore",
    "DevFileCredentialStore",
    "WindowsCredentialManagerStore",
    "TlsConfig",
    "HttpNodeTransport",
    "ERR_REMOTE_OWNER_POLICY_DENIED",
    "ERR_REMOTE_OWNER_APPROVAL_REQUIRED",
    "REMOTE_OWNER_DISABLED",
    "REMOTE_OWNER_APPROVAL_REQUIRED",
    "REMOTE_OWNER_ENABLED",
    "REMOTE_OWNER_POLICIES",
    "challenge_response",
    "negotiate_protocol",
    "privacy_allows_send",
    "ensure_loopback_or_raise",
    "audit_event",
    "NodeServerState",
    "build_capability_summary",
    "serve_node",
    "node_api_schema",
]