"""Human notifications & approvals (V2 H07, AT-27, maps D05/C07/F02).

H07 requirement: User-configurable notification priority and delivery
channels. Support pause-only-the-blocked-branch while unrelated teams
continue.

Key rules:
- Notification priority is user-configurable (§2)
- Approval checkpoints record who approved what, under which scope, with
  what expiry (§3)
- NEVER reinterpret silence as approval (§3)
- Return-to-session delta report: actions completed, artifacts, failures,
  model/provider usage, changed files, pending approvals (§4)
- Notifications contain NO secrets (§5)

This module provides:
- NotificationRouter: priority-based, channel-based, secret-free
- ApprovalGate: scope-bound approval checkpoints with expiry
- DeltaReport: return-to-session summary
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# --- secret hygiene (§5) ------------------------------------------------------------------

# Patterns that must NEVER appear in a notification (§5)
_SECRET_PATTERNS = [
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "openai-api-key"),
    (re.compile(r"sk-ant-[A-Za-z0-9-]{15,}"), "anthropic-api-key"),
    (re.compile(r"gsk_[A-Za-z0-9]{20,}"), "groq-api-key"),
    (re.compile(r"AIza[A-Za-z0-9_-]{35}"), "google-api-key"),
    (re.compile(r"hf_[A-Za-z0-9]{34,}"), "hf-token"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private-key"),
    (re.compile(r"Bearer\s+[A-Za-z0-9._-]{20,}"), "bearer-token"),
    (re.compile(r"password\s*[:=]\s*\S+", re.I), "password"),
]


def contains_secret(text: str) -> Optional[str]:
    """Check if text contains a secret. Returns the secret type or None."""
    for pattern, secret_type in _SECRET_PATTERNS:
        if pattern.search(text):
            return secret_type
    return None


def redact_secrets(text: str) -> str:
    """Redact any secrets from notification text (§5)."""
    result = text
    for pattern, secret_type in _SECRET_PATTERNS:
        result = pattern.sub(f"[REDACTED-{secret_type}]", result)
    return result


# --- notification priority + categories (§1, §2) -------------------------------------------------

class NotificationPriority(str, Enum):
    """User-configurable notification priority (§1)."""
    CRITICAL = "critical"        # security incident, credential compromise
    URGENT = "urgent"            # approval needed, quota exhausted
    HIGH = "high"                # task failed
    NORMAL = "normal"            # task completed
    LOW = "low"                  # routine progress


class NotificationCategory(str, Enum):
    """§2: notification categories."""
    TASK_COMPLETION = "task_completion"
    URGENT_FAULT = "urgent_fault"
    APPROVAL_REQUEST = "approval_request"
    CREDENTIAL_COMPROMISE = "credential_compromise"
    QUOTA_EXHAUSTED = "quota_exhausted"
    RESEARCH_FINDING = "research_finding"
    SECURITY_INCIDENT = "security_incident"


class NotificationChannel(str, Enum):
    """§2: delivery channels."""
    DESKTOP = "desktop"        # Hermes desktop app
    LOG = "log"                # append-only log
    KANBAN = "kanban"          # kanban comment
    TELEGRAM = "telegram"      # if configured
    EMAIL = "email"            # if configured


# Default priority per category
_DEFAULT_PRIORITY = {
    NotificationCategory.SECURITY_INCIDENT: NotificationPriority.CRITICAL,
    NotificationCategory.CREDENTIAL_COMPROMISE: NotificationPriority.CRITICAL,
    NotificationCategory.APPROVAL_REQUEST: NotificationPriority.URGENT,
    NotificationCategory.QUOTA_EXHAUSTED: NotificationPriority.URGENT,
    NotificationCategory.URGENT_FAULT: NotificationPriority.HIGH,
    NotificationCategory.TASK_COMPLETION: NotificationPriority.NORMAL,
    NotificationCategory.RESEARCH_FINDING: NotificationPriority.LOW,
}


# --- notification -----------------------------------------------------------------------

@dataclass
class Notification:
    """One notification, secret-checked (§5)."""
    notification_id: str
    category: NotificationCategory
    message: str
    priority: NotificationPriority = NotificationPriority.NORMAL
    channels: list[NotificationChannel] = field(
        default_factory=lambda: [NotificationChannel.DESKTOP,
                                  NotificationChannel.LOG])
    task_id: str = ""
    worker_id: str = ""
    created_at: float = field(default_factory=time.time)
    delivered: bool = False
    delivered_at: Optional[float] = None
    _original_message: str = ""

    def __post_init__(self) -> None:
        # §5: store the ORIGINAL for secret checking, then redact
        self._original_message = self.message
        self.message = redact_secrets(self.message)
        if self.priority == NotificationPriority.NORMAL:
            self.priority = _DEFAULT_PRIORITY.get(
                self.category, NotificationPriority.NORMAL)

    @property
    def original_message(self) -> str:
        """The message as originally provided, for secret detection."""
        return self._original_message


class NotificationRouter:
    """Routes notifications by priority and channel (§1, §2).

    User-configurable: priorities and channels can be overridden.
    Secret-free: every message is checked before delivery (§5).
    """

    def __init__(self, min_priority: NotificationPriority = NotificationPriority.LOW):
        self._min_priority = min_priority
        self._channel_overrides: dict[NotificationCategory, list[NotificationChannel]] = {}
        self._delivered: list[Notification] = []
        self._blocked: list[tuple[Notification, str]] = []

    def configure_category(self, category: NotificationCategory,
                           channels: list[NotificationChannel]) -> None:
        """User-configurable: override channels for a category (§1)."""
        self._channel_overrides[category] = channels

    def set_min_priority(self, priority: NotificationPriority) -> None:
        """User-configurable: only notify at or above this priority (§1)."""
        self._min_priority = priority

    def notify(self, notification: Notification) -> dict[str, Any]:
        """Route a notification. Returns delivery status.

        §5: if a secret is detected in the ORIGINAL message, the notification
        is BLOCKED (not delivered).
        """
        # Secret check on ORIGINAL message (§5)
        secret_type = contains_secret(notification.original_message)
        if secret_type:
            self._blocked.append((notification, f"secret detected: {secret_type}"))
            return {"delivered": False, "blocked": True,
                    "reason": f"notification contains secret ({secret_type})"}

        # Priority filter (§1): lower index = higher priority.
        # Notification passes if its index is <= min_priority's index
        # (i.e. it's at least as urgent as the minimum).
        priority_order = list(NotificationPriority)
        if priority_order.index(notification.priority) > \
                priority_order.index(self._min_priority):
            return {"delivered": False, "blocked": False,
                    "reason": "below minimum priority"}

        # Channel routing (§1: user-configurable)
        if notification.category in self._channel_overrides:
            notification.channels = self._channel_overrides[notification.category]

        # Deliver (log always; others as configured)
        notification.delivered = True
        notification.delivered_at = time.time()
        self._delivered.append(notification)
        return {"delivered": True, "blocked": False,
                "channels": [c.value for c in notification.channels]}

    def delivered_notifications(self) -> list[Notification]:
        return list(self._delivered)

    def blocked_notifications(self) -> list[tuple[Notification, str]]:
        """§5: notifications blocked for containing secrets."""
        return list(self._blocked)


# --- approval gate (§3) ------------------------------------------------------------------------

class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"


@dataclass
class ApprovalRequest:
    """One approval checkpoint (§3)."""
    request_id: str
    scope: str                     # what is being approved
    requested_by: str
    task_id: str = ""
    status: ApprovalStatus = ApprovalStatus.PENDING
    approved_by: Optional[str] = None
    approved_at: Optional[float] = None
    expires_at: Optional[float] = None
    scope_details: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def is_expired(self) -> bool:
        """Check if the request's expiry has passed (regardless of status)."""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at


class ApprovalGate:
    """Approval checkpoints with scope, expiry, and audit (§3).

    Key rule: SILENCE IS NOT APPROVAL (§3). An approval must be explicitly
    granted by a named approver within a defined scope and expiry.
    """

    def __init__(self) -> None:
        self._requests: dict[str, ApprovalRequest] = {}

    def request_approval(self, scope: str, requested_by: str,
                         task_id: str = "",
                         expires_in_s: Optional[float] = None,
                         scope_details: Optional[dict[str, Any]] = None) -> ApprovalRequest:
        """Create an approval request. Status starts PENDING (§3)."""
        req_id = f"apr_{abs(hash((scope, requested_by, time.time())))}"
        req = ApprovalRequest(
            request_id=req_id,
            scope=scope,
            requested_by=requested_by,
            task_id=task_id,
            expires_at=(time.time() + expires_in_s) if expires_in_s else None,
            scope_details=scope_details or {},
        )
        self._requests[req_id] = req
        return req

    def approve(self, request_id: str, approver: str) -> ApprovalRequest:
        """Explicitly approve a request (§3: named approver required)."""
        req = self._requests.get(request_id)
        if not req:
            raise ValueError(f"unknown request: {request_id}")
        if req.is_expired():
            raise ValueError(f"request {request_id} has expired")
        req.status = ApprovalStatus.APPROVED
        req.approved_by = approver
        req.approved_at = time.time()
        return req

    def deny(self, request_id: str, denier: str) -> ApprovalRequest:
        """Explicitly deny a request."""
        req = self._requests.get(request_id)
        if not req:
            raise ValueError(f"unknown request: {request_id}")
        req.status = ApprovalStatus.DENIED
        req.approved_by = denier
        req.approved_at = time.time()
        return req

    def check_expired(self) -> list[ApprovalRequest]:
        """Mark expired approvals and return them."""
        expired = []
        for req in self._requests.values():
            if req.is_expired():
                req.status = ApprovalStatus.EXPIRED
                expired.append(req)
        return expired

    def is_approved(self, request_id: str) -> bool:
        """Check if a request is currently approved (not expired)."""
        req = self._requests.get(request_id)
        if not req:
            return False
        if req.is_expired():
            return False
        return req.status == ApprovalStatus.APPROVED

    def pending_requests(self) -> list[ApprovalRequest]:
        """All pending approval requests (§3: silence is not approval)."""
        return [r for r in self._requests.values()
                if r.status == ApprovalStatus.PENDING]


# --- delta report (§4) ---------------------------------------------------------------------------

@dataclass
class DeltaReport:
    """Return-to-session delta report (§4)."""
    generated_at: float = field(default_factory=time.time)
    since_timestamp: float = 0.0
    actions_completed: list[str] = field(default_factory=list)
    artifacts_produced: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    model_usage: dict[str, dict[str, Any]] = field(default_factory=dict)
    files_changed: list[str] = field(default_factory=list)
    pending_approvals: list[str] = field(default_factory=list)
    worker_status: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "since_timestamp": self.since_timestamp,
            "actions_completed": self.actions_completed,
            "artifacts_produced": self.artifacts_produced,
            "failures": self.failures,
            "model_usage": self.model_usage,
            "files_changed": self.files_changed,
            "pending_approvals": self.pending_approvals,
            "worker_status": self.worker_status,
        }
