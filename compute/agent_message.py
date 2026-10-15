"""Aetherius Agent Communications Bridge — canonical message schema (v1).

This module defines the FIRST-PARTY TYPED MESSAGE CONTRACT (§5) that all
worker adapters (OpenCode, Codex, Hermes subagents, GUI apps, cloud workers)
speak. Hermes and OpenCode are clients of this bridge; neither owns it.

Schema: aetherius.agent-message.v1

Key rules:
- Every message has a unique message_id + idempotency_key (§16).
- Every task lifecycle transition is a typed intent (§4) with evidence (§6).
- SENT != RECEIVED != ACKNOWLEDGED != RUNNING (each is a separate state).
- Messages carry credential_ref, never plaintext secrets (§40).
- Worker messages distinguish claim types (§21): OBSERVATION, SOURCE_QUOTE,
  CLAIM, INFERENCE, HYPOTHESIS, CONTRADICTION, VERIFIED_CONCLUSION.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# --- schema version ------------------------------------------------------------

SCHEMA_VERSION = "aetherius.agent-message.v1"


# --- message intents (§4) ------------------------------------------------------

class Intent(str, Enum):
    """Typed message intents (§4)."""
    # Task lifecycle
    TASK_ASSIGN = "TASK_ASSIGN"
    TASK_ACK = "TASK_ACK"
    TASK_START = "TASK_START"
    TASK_PROGRESS = "TASK_PROGRESS"
    TASK_CHECKPOINT = "TASK_CHECKPOINT"
    TASK_COMPLETE = "TASK_COMPLETE"
    TASK_FAILED = "TASK_FAILED"
    # Control commands
    CONTINUE = "CONTINUE"
    CORRECT = "CORRECT"
    PAUSE = "PAUSE"
    RESUME = "RESUME"
    CANCEL = "CANCEL"
    RECALL = "RECALL"
    REVOKE = "REVOKE"                # §23: revoke capability/provider
    REVOKE_CAPABILITY = "REVOKE_CAPABILITY"  # §23: capability-specific
    REVOKE_PROVIDER = "REVOKE_PROVIDER"      # §23: provider-specific
    REASSIGN = "REASSIGN"
    EMERGENCY_HALT = "EMERGENCY_HALT"   # §23: distinct from RECALL
    # Handoff + QA
    HANDOFF = "HANDOFF"
    HANDOFF_ACK = "HANDOFF_ACK"
    QA_REQUEST = "QA_REQUEST"
    QA_RESULT = "QA_RESULT"
    # Messaging
    DM = "DM"
    TEAM_MESSAGE = "TEAM_MESSAGE"
    MEETING_MESSAGE = "MEETING_MESSAGE"
    # State announcements
    CAPABILITY_ADVERTISE = "CAPABILITY_ADVERTISE"
    MODEL_CHANGED = "MODEL_CHANGED"
    QUOTA_UPDATE = "QUOTA_UPDATE"
    RESOURCE_UPDATE = "RESOURCE_UPDATE"
    # Approval
    APPROVAL_REQUEST = "APPROVAL_REQUEST"
    APPROVAL_RESULT = "APPROVAL_RESULT"
    # Skill communication
    SKILL_CANDIDATE = "SKILL_CANDIDATE"
    SKILL_APPROVED = "SKILL_APPROVED"
    # Liveness
    HEARTBEAT = "HEARTBEAT"
    HEALTH = "HEALTH"


# --- delivery lifecycle states (§6) --------------------------------------------

class DeliveryState(str, Enum):
    """Task delivery lifecycle. SENT is NOT ACKNOWLEDGED is NOT RUNNING."""
    PENDING = "PENDING"           # created, not yet sent
    DELIVERED = "DELIVERED"       # sent to transport, no ACK yet
    ACKNOWLEDGED = "ACKNOWLEDGED" # worker sent TASK_ACK
    RUNNING_VERIFIED = "RUNNING_VERIFIED"  # worker sent TASK_START or evidence
    PROGRESSING = "PROGRESSING"   # worker sent TASK_PROGRESS/CHECKPOINT
    COMPLETED = "COMPLETED"       # worker sent TASK_COMPLETE
    HANDED_OFF = "HANDED_OFF"     # worker sent HANDOFF
    QA_PASSED = "QA_PASSED"       # supervisor QA passed
    DELIVERY_FAILED = "DELIVERY_FAILED"  # no ACK within timeout
    PAUSED = "PAUSED"             # worker paused
    CANCELLED = "CANCELLED"       # supervisor cancelled
    RECALLED = "RECALLED"         # authority revoked (§25)
    FAILED = "FAILED"             # task failed


# --- evidence claim types (§21) --------------------------------------------------

class ClaimType(str, Enum):
    """Workers must distinguish what kind of statement they're making."""
    OBSERVATION = "OBSERVATION"           # directly observed fact
    SOURCE_QUOTE = "SOURCE_QUOTE"         # quoted from a cited source
    CLAIM = "CLAIM"                       # a claim that needs verification
    INFERENCE = "INFERENCE"               # derived from evidence
    HYPOTHESIS = "HYPOTHESIS"             # unverified proposal
    CONTRADICTION = "CONTRADICTION"       # conflicts with another claim
    VERIFIED_CONCLUSION = "VERIFIED_CONCLUSION"  # independently verified


# --- worker capabilities (§34) ---------------------------------------------------

class Capability(str, Enum):
    """Advertised worker capabilities (§34)."""
    CODING = "coding"
    RESEARCH = "research"
    BROWSER = "browser"
    VISION = "vision"
    FILES = "files"
    TERMINAL = "terminal"
    COMPUTER_USE = "computer-use"
    SUBAGENTS = "subagents"
    MODELS = "models"
    MODEL_SWITCH = "model-switch"
    TOOL_CALLS = "tool-calls"
    STREAMING = "streaming"
    PERSISTENT_JOBS = "persistent-jobs"


# --- cost policy (§26) ------------------------------------------------------------

DEFAULT_COST_POLICY = "ZERO_INCREMENTAL_SPEND"


# --- message envelope ---------------------------------------------------------------

@dataclass
class AgentMessage:
    """The canonical message envelope (§5).

    Every field is typed and inspectable. No opaque fields.
    """
    # Identity (§5)
    schema: str = SCHEMA_VERSION
    message_id: str = field(default_factory=lambda: f"msg_{uuid.uuid4().hex[:16]}")
    correlation_id: str = ""       # groups messages for one task
    causation_id: str = ""         # which message caused this one

    # Sender/receiver (§5)
    sender_agent: str = ""         # e.g. "hermes", "opencode"
    sender_worker: str = ""        # e.g. "supervisor", "opencode-01"
    receiver_agent: str = ""
    receiver_worker: str = ""

    # Task context (§5)
    project_id: str = ""
    task_id: str = ""

    # Intent + payload (§5)
    intent: Intent = Intent.DM
    objective: str = ""
    constraints: dict[str, Any] = field(default_factory=dict)
    evidence_refs: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    requested_actions: list[str] = field(default_factory=list)

    # Priority + expiry (§5)
    priority: int = 50             # 0-100
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None

    # Delivery (§16)
    required_ack: bool = True
    idempotency_key: str = ""
    retry_count: int = 0
    delivery_timeout_s: float = 120.0

    # Claims (§21) — for TASK_COMPLETE/HANDOFF/QA_RESULT
    claim_type: Optional[ClaimType] = None
    claim_confidence: Optional[str] = None  # VERIFIED/OBSERVED/ESTIMATED/UNKNOWN

    # Payload (free-form but typed) — for details not in the envelope
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.idempotency_key:
            self.idempotency_key = self._compute_idempotency_key()
        if self.intent not in Intent.__members__.values():
            raise ValueError(f"unknown intent: {self.intent}")

    def _compute_idempotency_key(self) -> str:
        """Deterministic key: task_id + intent + sender (§16 dedup).

        Deliberately EXCLUDES created_at: two messages for the same task
        with the same intent from the same sender are the same message
        (§16), even if sent at different times.
        """
        parts = [self.task_id, self.intent.value, self.sender_agent,
                 self.sender_worker]
        raw = ":".join(parts)
        return f"idem_{hashlib.sha256(raw.encode()).hexdigest()[:16]}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "message_id": self.message_id,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "sender": {"agent_id": self.sender_agent, "worker_id": self.sender_worker},
            "receiver": {"agent_id": self.receiver_agent, "worker_id": self.receiver_worker},
            "project_id": self.project_id,
            "task_id": self.task_id,
            "intent": self.intent.value,
            "objective": self.objective,
            "constraints": self.constraints,
            "evidence_refs": self.evidence_refs,
            "dependencies": self.dependencies,
            "requested_actions": self.requested_actions,
            "priority": self.priority,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "delivery": {
                "required_ack": self.required_ack,
                "idempotency_key": self.idempotency_key,
                "retry_count": self.retry_count,
                "delivery_timeout_s": self.delivery_timeout_s,
            },
            "claim_type": self.claim_type.value if self.claim_type else None,
            "claim_confidence": self.claim_confidence,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentMessage":
        """Reconstruct from dict. Validates schema version."""
        if data.get("schema") != SCHEMA_VERSION:
            raise ValueError(f"unknown schema: {data.get('schema')}")
        sender = data.get("sender", {})
        receiver = data.get("receiver", {})
        delivery = data.get("delivery", {})
        claim_type_str = data.get("claim_type")
        return cls(
            schema=data["schema"],
            message_id=data["message_id"],
            correlation_id=data.get("correlation_id", ""),
            causation_id=data.get("causation_id", ""),
            sender_agent=sender.get("agent_id", ""),
            sender_worker=sender.get("worker_id", ""),
            receiver_agent=receiver.get("agent_id", ""),
            receiver_worker=receiver.get("worker_id", ""),
            project_id=data.get("project_id", ""),
            task_id=data.get("task_id", ""),
            intent=Intent(data["intent"]),
            objective=data.get("objective", ""),
            constraints=data.get("constraints", {}),
            evidence_refs=data.get("evidence_refs", []),
            dependencies=data.get("dependencies", []),
            requested_actions=data.get("requested_actions", []),
            priority=data.get("priority", 50),
            created_at=data.get("created_at", time.time()),
            expires_at=data.get("expires_at"),
            required_ack=delivery.get("required_ack", True),
            idempotency_key=delivery.get("idempotency_key", ""),
            retry_count=delivery.get("retry_count", 0),
            delivery_timeout_s=delivery.get("delivery_timeout_s", 120.0),
            claim_type=ClaimType(claim_type_str) if claim_type_str else None,
            claim_confidence=data.get("claim_confidence"),
            payload=data.get("payload", {}),
        )

    def is_duplicate(self, other: "AgentMessage") -> bool:
        """Check idempotency: same key = same message (§16)."""
        return self.idempotency_key == other.idempotency_key


# --- task assignment builder (§5) ---------------------------------------------------

def build_task_assign(
    task_id: str,
    objective: str,
    sender_agent: str = "hermes",
    sender_worker: str = "supervisor",
    receiver_agent: str = "",
    receiver_worker: str = "",
    project_id: str = "",
    cost_policy: str = DEFAULT_COST_POLICY,
    permissions: list[str] | None = None,
    write_set: list[str] | None = None,
    branch: str = "",
    worktree: str = "",
    priority: int = 50,
    evidence_refs: list[str] | None = None,
    dependencies: list[str] | None = None,
) -> AgentMessage:
    """Build a TASK_ASSIGN message with the standard §5 envelope."""
    return AgentMessage(
        correlation_id=f"task_{task_id}",
        sender_agent=sender_agent,
        sender_worker=sender_worker,
        receiver_agent=receiver_agent,
        receiver_worker=receiver_worker,
        project_id=project_id,
        task_id=task_id,
        intent=Intent.TASK_ASSIGN,
        objective=objective,
        constraints={
            "cost_policy": cost_policy,
            "permissions": permissions or [],
            "write_set": write_set or [],
            "branch": branch,
            "worktree": worktree,
        },
        evidence_refs=evidence_refs or [],
        dependencies=dependencies or [],
        priority=priority,
        required_ack=True,
    )


def build_ack(
    original: AgentMessage,
    sender_agent: str,
    sender_worker: str,
    accepted: bool = True,
    current_model: str = "",
    repo: str = "",
    worktree: str = "",
    branch: str = "",
    baseline_sha: str = "",
    expected_write_set: list[str] | None = None,
    reason: str = "",
) -> AgentMessage:
    """Build a TASK_ACK responding to a TASK_ASSIGN (§7)."""
    return AgentMessage(
        correlation_id=original.correlation_id,
        causation_id=original.message_id,
        sender_agent=sender_agent,
        sender_worker=sender_worker,
        receiver_agent=original.sender_agent,
        receiver_worker=original.sender_worker,
        project_id=original.project_id,
        task_id=original.task_id,
        intent=Intent.TASK_ACK,
        payload={
            "accepted": accepted,
            "current_model": current_model,
            "repo": repo,
            "worktree": worktree,
            "branch": branch,
            "baseline_sha": baseline_sha,
            "expected_write_set": expected_write_set or [],
            "reason": reason,
        },
        required_ack=False,
    )


def build_task_start(
    original: AgentMessage,
    sender_agent: str,
    sender_worker: str,
    phase: str = "implementing",
) -> AgentMessage:
    """Build a TASK_START confirming work has begun (§8)."""
    return AgentMessage(
        correlation_id=original.correlation_id,
        causation_id=original.message_id,
        sender_agent=sender_agent,
        sender_worker=sender_worker,
        receiver_agent=original.sender_agent,
        receiver_worker=original.sender_worker,
        project_id=original.project_id,
        task_id=original.task_id,
        intent=Intent.TASK_START,
        payload={"phase": phase, "started_at": time.time()},
        required_ack=False,
    )


def build_task_complete(
    original: AgentMessage,
    sender_agent: str,
    sender_worker: str,
    claim_type: ClaimType = ClaimType.VERIFIED_CONCLUSION,
    files_changed: list[str] | None = None,
    repo: str = "",
    branch: str = "",
    baseline_sha: str = "",
    final_sha: str = "",
    tests_passed: int = 0,
    tests_failed: int = 0,
    evidence: list[str] | None = None,
    decisions: list[str] | None = None,
    known_gaps: list[str] | None = None,
    recommended_next: str = "",
) -> AgentMessage:
    """Build a TASK_COMPLETE with structured handoff data (§11)."""
    return AgentMessage(
        correlation_id=original.correlation_id,
        causation_id=original.message_id,
        sender_agent=sender_agent,
        sender_worker=sender_worker,
        receiver_agent=original.sender_agent,
        receiver_worker=original.sender_worker,
        project_id=original.project_id,
        task_id=original.task_id,
        intent=Intent.TASK_COMPLETE,
        claim_type=claim_type,
        claim_confidence="VERIFIED" if claim_type == ClaimType.VERIFIED_CONCLUSION else "OBSERVED",
        payload={
            "files_changed": files_changed or [],
            "repo": repo,
            "branch": branch,
            "baseline_sha": baseline_sha,
            "final_sha": final_sha,
            "tests_passed": tests_passed,
            "tests_failed": tests_failed,
            "evidence": evidence or [],
            "decisions": decisions or [],
            "known_gaps": known_gaps or [],
            "recommended_next": recommended_next,
        },
        required_ack=False,
    )


def build_heartbeat(
    worker_agent: str,
    worker_id: str,
    task_id: str = "",
    phase: str = "",
    last_progress_at: float = 0.0,
    current_operation: str = "",
    repo: str = "",
    branch: str = "",
    resource_state: str = "",
    quota_state: str = "",
) -> AgentMessage:
    """Build a lightweight HEARTBEAT (§9)."""
    return AgentMessage(
        correlation_id=f"task_{task_id}" if task_id else "",
        sender_agent=worker_agent,
        sender_worker=worker_id,
        intent=Intent.HEARTBEAT,
        task_id=task_id,
        payload={
            "phase": phase,
            "last_progress_at": last_progress_at or time.time(),
            "current_operation": current_operation,
            "repo": repo,
            "branch": branch,
            "resource_state": resource_state,
            "quota_state": quota_state,
        },
        required_ack=False,
    )


def build_handoff(
    original: AgentMessage,
    sender_agent: str,
    sender_worker: str,
    completed_work: str = "",
    remaining_work: str = "",
    files_changed: list[str] | None = None,
    repo: str = "",
    branch: str = "",
    baseline_sha: str = "",
    final_sha: str = "",
    tests_results: str = "",
    evidence: list[str] | None = None,
    research_used: list[str] | None = None,
    decisions: list[str] | None = None,
    known_gaps: list[str] | None = None,
    blockers: list[str] | None = None,
    recommended_next: str = "",
) -> AgentMessage:
    """Build a HANDOFF message (§11) — the canonical completion handoff."""
    return AgentMessage(
        correlation_id=original.correlation_id,
        causation_id=original.message_id,
        sender_agent=sender_agent,
        sender_worker=sender_worker,
        receiver_agent=original.sender_agent,
        receiver_worker=original.sender_worker,
        project_id=original.project_id,
        task_id=original.task_id,
        intent=Intent.HANDOFF,
        claim_type=ClaimType.VERIFIED_CONCLUSION,
        claim_confidence="VERIFIED",
        payload={
            "completed_work": completed_work,
            "remaining_work": remaining_work,
            "files_changed": files_changed or [],
            "repo": repo,
            "branch": branch,
            "baseline_sha": baseline_sha,
            "final_sha": final_sha,
            "tests_results": tests_results,
            "evidence": evidence or [],
            "research_used": research_used or [],
            "decisions": decisions or [],
            "known_gaps": known_gaps or [],
            "blockers": blockers or [],
            "recommended_next": recommended_next,
        },
        required_ack=True,
    )
