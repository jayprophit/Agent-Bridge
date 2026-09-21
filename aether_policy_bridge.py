"""Aether Policy Bridge — Integrates aether-boot-logic policy engine with Agent Bridge.

This module provides the integration layer between the aether-boot-logic
policy engine (RBAC/ABAC) and the Agent Bridge's existing approval system.
"""
from __future__ import annotations

import json
import uuid
import time
from typing import Any, Optional, Dict, List, Set
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# Import the aether-boot-logic policy types
# These would ideally come from a compiled Rust library via FFI
# For now we redefine the necessary types on the Python side

@dataclass
class PermissionId:
    """Unique permission identifier. Namespaced by service."""
    service: str
    action: str
    
    def __str__(self) -> str:
        return f"{self.service}:{self.action}"
    
    @classmethod
    def new(cls, service: str, action: str) -> "PermissionId":
        return cls(service=service, action=action)
    
    def __str__(self) -> str:
        return f"{self.service}:{self.action}"
    
    def __eq__(self, other):
        if not isinstance(other, PermissionId):
            return False
        return self.service == other.service and self.action == other.action
    
    def __hash__(self):
        return hash((self.service, self.action))


@dataclass
class RoleId:
    """Role identifier. Composed of permission sets."""
    value: str
    
    def __str__(self) -> str:
        return self.value


@dataclass
class Subject:
    """Subject (user, service, device) that can be granted permissions."""
    kind: str  # "identity", "service", "device", "anonymous"
    value: str
    
    @classmethod
    def identity(cls, identity_id: str) -> "Subject":
        return cls(kind="identity", value=identity_id)
    
    @classmethod
    def service(cls, service: str) -> "Subject":
        return cls(kind="service", value=service)
    
    @classmethod
    def device(cls, device: str) -> "Subject":
        return cls(kind="device", value=device)
    
    @classmethod
    def anonymous(cls) -> "Subject":
        return cls(kind="anonymous", value="")


@dataclass
class ResourceId:
    """Resource that can be accessed. Namespaced by service."""
    value: str


@dataclass
class Grant:
    """Permission grant: subject -> permission on resource."""
    subject: "Subject"
    permission: "PermissionId"
    resource: "ResourceId"
    conditions: list
    granted_by: str
    granted_at: int
    expires_at: Optional[int] = None


@dataclass
class RoleId:
    value: str


@dataclass
class Role:
    id: str
    name: str
    description: str
    permissions: set
    implied_roles: set


from dataclasses import dataclass, field
from typing import Any, Optional, Dict, List, Set, Optional
from datetime import datetime
import uuid
import time

# Decision enum
class Decision:
    ALLOW = "allow"
    DENY = "deny"
    NOT_APPLICABLE = "not_applicable"


@dataclass
class EvalContext:
    subject: "Subject"
    resource: str  # ResourceId
    action: "PermissionId"
    attributes: Dict[str, str] = field(default_factory=dict)
    timestamp: int = 0
    network_origin: Optional[str] = None
    device_trust: Optional[int] = None


@dataclass
class Grant:
    subject: "Subject"
    permission: "PermissionId"
    resource: str  # ResourceId
    conditions: list
    granted_by: str
    granted_at: int
    expires_at: Optional[int] = None


@dataclass
class Role:
    id: str
    name: str
    description: str
    permissions: Set[PermissionId]
    implied_roles: Set[str]


class Decision:
    ALLOW = "allow"
    DENY = "deny"
    NOT_APPLICABLE = "not_applicable"


@dataclass
class EvalContext:
    subject: "Subject"
    resource: str  # ResourceId
    action: "PermissionId"
    attributes: Dict[str, str] = field(default_factory=dict)
    timestamp: int = 0
    network_origin: Optional[str] = None
    device_trust: Optional[int] = None


# Import the aether-boot-logic policy engine
# In a real implementation, this would be an FFI call to the Rust library
# For now, we implement a compatible Python version

class PermissionId:
    def __init__(self, service: str, action: str):
        self.service = service
        self.action = action
    
    def __str__(self):
        return f"{self.service}:{self.action}"
    
    @classmethod
    def new(cls, service: str, action: str):
        return PermissionId(service, action)
    
    def __str__(self):
        return f"{self.service}:{self.action}"
    
    def __eq__(self, other):
        if not isinstance(other, PermissionId):
            return False
        return self.service == other.service and self.action == other.action
    
    def __hash__(self):
        return hash((self.service, self.action))


class RoleId:
    def __init__(self, value: str):
        self.value = value
    
    def __str__(self):
        return self.value


class Subject:
    def __init__(self, kind: str, value: str):
        self.kind = kind
        self.value = value

    def __str__(self):
        return f"{self.kind}:{self.value}"

    def __eq__(self, other):
        if not isinstance(other, Subject):
            return False
        return self.kind == other.kind and self.value == other.value

    def __hash__(self):
        return hash((self.kind, self.value))

    @classmethod
    def identity(cls, identity_id: str):
        return cls(kind="identity", value=identity_id)

    @classmethod
    def service(cls, service: str):
        return cls(kind="service", value=service)

    @classmethod
    def device(cls, device: str):
        return cls(kind="device", value=device)

    @classmethod
    def anonymous(cls):
        return cls(kind="anonymous", value="")


@dataclass
class ResourceId:
    value: str


class Decision:
    ALLOW = "allow"
    DENY = "deny"
    NOT_APPLICABLE = "not_applicable"


@dataclass
class EvalContext:
    subject: "Subject"
    resource: str
    action: "PermissionId"
    attributes: dict = field(default_factory=dict)
    timestamp: int = 0
    network_origin: Optional[str] = None
    device_trust: Optional[int] = None


@dataclass
class Grant:
    subject: "Subject"
    permission: "PermissionId"
    resource: str
    conditions: list
    granted_by: str
    granted_at: int
    expires_at: Optional[int] = None


@dataclass
class Role:
    id: str
    name: str
    description: str
    permissions: set
    implied_roles: set


class Decision:
    ALLOW = "allow"
    DENY = "deny"
    NOT_APPLICABLE = "not_applicable"


class EvalContext:
    def __init__(self, subject: "Subject", resource: str, action: "PermissionId",
                 attributes: dict = None, timestamp: int = 0,
                 network_origin: str = None, device_trust: int = None):
        self.subject = subject
        self.resource = resource
        self.action = action
        self.attributes = {} if attributes is None else attributes
        self.timestamp = timestamp or int(time.time())
        self.network_origin = None
        self.device_trust = None


# Simple PolicyEngine implementation
class PolicyEngine:
    def __init__(self):
        self.grants = {}
        self.roles = {}
        self.subject_roles = {}
        self.default_decision = "deny"
    
    def add_grant(self, grant):
        subject_key = str(grant.subject)
        if subject_key not in self.grants:
            self.grants[subject_key] = []
        self.grants[subject_key].append(grant)
    
    def evaluate(self, ctx) -> str:
        # Check explicit grants
        subject_key = str(ctx.subject)
        if subject_key in self.grants:
            for grant in self.grants.get(subject_key, []):
                if grant.permission == ctx.action and grant.resource == ctx.resource:
                    return "allow"
        
        return "deny"


# Global policy engine instance (P10-PA: single default-deny engine shared
# by every bridge-facing evaluation so grants persist across calls).
_policy_engine = None

def get_policy_engine():
    global _policy_engine
    if _policy_engine is None:
        _policy_engine = PolicyEngine()
    return _policy_engine


def reset_policy_engine():
    """Test/reset hook: drop all grants and restore default-deny."""
    global _policy_engine
    _policy_engine = PolicyEngine()
    return _policy_engine


def _parse_subject(subject: str) -> "Subject":
    if isinstance(subject, Subject):
        return subject
    if isinstance(subject, str) and ":" in subject:
        kind, _, value = subject.partition(":")
        if kind in ("identity", "service", "device", "anonymous"):
            return Subject(kind=kind, value=value)
    return Subject(kind="service", value=str(subject))


def evaluate_capability_request(
    subject: str,
    capability: str,
    resource: str,
    context: dict = None
) -> dict:
    """
    Evaluate a capability request through the shared policy engine
    (P10-PA gate: default-deny; explicit grants allow).

    Returns: {"allowed": bool, "decision": str, "reason": str, "policy_id": str}
    """
    engine = get_policy_engine()

    # Parse capability
    if ":" in capability:
        service, action = capability.split(":", 1)
    else:
        service, action = "unknown", capability

    ctx = EvalContext(
        subject=_parse_subject(subject),
        resource=str(resource),
        action=PermissionId(service, action),
        attributes=(context or {}).get("attributes", {}) if isinstance(context, dict) else {},
        timestamp=(context or {}).get("timestamp", 0) if isinstance(context, dict) else 0,
        network_origin=(context or {}).get("network_origin") if isinstance(context, dict) else None,
        device_trust=(context or {}).get("device_trust") if isinstance(context, dict) else None,
    )
    decision = engine.evaluate(ctx)
    allowed = (decision == "allow")
    return {
        "allowed": allowed,
        "decision": decision,
        "reason": "grant matched" if allowed else f"denied by default-deny: no grant for {ctx.subject} {service}:{action} on {resource}",
        "policy_id": str(uuid.uuid4()),
        "timestamp": int(time.time()),
    }


def check_capability(subject: str, capability: str, resource: str, context: dict = None) -> dict:
    """Check if a subject has a capability on a resource."""
    return evaluate_capability_request(subject, capability, resource, context)


# Integration with Agent Bridge protocol
def create_policy_evaluation_result(
    action: dict,
    context: dict,
    decision: str,
    reason: str
) -> dict:
    """Create a standardized policy evaluation result for Agent Bridge."""
    return {
        "policy_decision": {
            "allowed": decision == "allow",
            "decision": decision,
            "reason": reason,
            "policy_id": str(uuid.uuid4()),
            "timestamp": int(time.time()),
        },
        "action": action,
        "context": context,
    }


__all__ = [
    "PermissionId",
    "RoleId",
    "Subject",
    "ResourceId",
    "Condition",
    "Grant",
    "Role",
    "Decision",
    "EvalContext",
    "PolicyEngine",
    "get_policy_engine",
    "reset_policy_engine",
    "evaluate_capability_request",
    "check_capability",
    "create_policy_evaluation_result",
]