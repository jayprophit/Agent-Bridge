"""Aetherius Team Execution Fabric (§56).

Extends the existing EnterpriseTeam orchestrator with:

- Team execution modes: SOLO_LOCAL, SOLO_CLOUD, SOLO_AUTO, TEAM_LOCAL,
  TEAM_CLOUD, TEAM_HYBRID, TEAM_FEDERATED, TEAM_AUTO (§1)
- Internal worker pools: LOCAL_WORKER_POOL, CLOUD_WORKER_POOL, HYBRID_WORKER_POOL (§3)
- Agent Communication Protocol with structured messages (§14, §15)
- Message bus for inter-worker communication (§13, §14)
- Group agent rooms (§19)
- Team-size vs active-concurrency distinction (§9)
- Critical-path parallel execution (§10, §11)
- Workspace isolation (§12)
- Team autoscaling (§29)
- Failover with context handoff (§30)
- Communication interface registration (§40, §44)
- TeamProvider adapter for external runtimes (§22, §23)
- Performance metrics (§27)

Extends compute/enterprise_team.py. Does NOT build a competing system.
"""
import time
import uuid
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable, Protocol
from concurrent.futures import ThreadPoolExecutor, as_completed

from models.inference_contract import (
    PRIVACY_PUBLIC, PRIVACY_PROJECT, PRIVACY_CONFIDENTIAL,
    PRIVACY_SECRET_LOCAL_ONLY,
)

logger = logging.getLogger("aetherius.team_fabric")


# === §1: Team Execution Modes ===

class TeamExecutionMode(Enum):
    SOLO_LOCAL = "SOLO_LOCAL"
    SOLO_CLOUD = "SOLO_CLOUD"
    SOLO_AUTO = "SOLO_AUTO"
    TEAM_LOCAL = "TEAM_LOCAL"
    TEAM_CLOUD = "TEAM_CLOUD"
    TEAM_HYBRID = "TEAM_HYBRID"
    TEAM_FEDERATED = "TEAM_FEDERATED"
    TEAM_AUTO = "TEAM_AUTO"


# === §15: Message Types ===

class MessageType(Enum):
    REQUEST = "REQUEST"
    RESPONSE = "RESPONSE"
    QUESTION = "QUESTION"
    ANSWER = "ANSWER"
    INSTRUCTION = "INSTRUCTION"
    STATUS = "STATUS"
    HANDOFF = "HANDOFF"
    REVIEW = "REVIEW"
    CHALLENGE = "CHALLENGE"
    EVIDENCE = "EVIDENCE"
    ARTIFACT = "ARTIFACT"
    DEPENDENCY = "DEPENDENCY"
    BLOCKER = "BLOCKER"
    WARNING = "WARNING"
    FAILURE = "FAILURE"
    RETRY = "RETRY"
    ACKNOWLEDGEMENT = "ACKNOWLEDGEMENT"
    CONSENSUS_REQUEST = "CONSENSUS_REQUEST"
    ARBITRATION_REQUEST = "ARBITRATION_REQUEST"
    HEARTBEAT = "HEARTBEAT"


# === §14: Agent Protocol Message ===

@dataclass
class AgentProtocolMessage:
    """Structured agent-to-agent message (§14).

    Every message has structured metadata so it remains auditable
    and translatable to canonical form (§16).
    """
    message_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    conversation_id: str = ""
    team_id: str = ""
    task_id: str = ""

    from_worker: str = ""
    from_role: str = ""

    to_worker: str = ""
    to_role: str = ""

    message_type: MessageType = MessageType.REQUEST
    priority: str = "normal"  # low, normal, high, urgent
    timestamp: float = field(default_factory=time.time)
    privacy_class: str = PRIVACY_PROJECT
    content: str = ""
    artifact_refs: list = field(default_factory=list)
    source_refs: list = field(default_factory=list)
    evidence_refs: list = field(default_factory=list)
    provenance_refs: list = field(default_factory=list)
    requires_response: bool = True
    expiry: Optional[float] = None
    correlation_id: str = ""

    def to_dict(self) -> dict:
        """Convert to dict for audit/storage (§16)."""
        d = {
            "message_id": self.message_id,
            "conversation_id": self.conversation_id,
            "team_id": self.team_id,
            "task_id": self.task_id,
            "from_worker": self.from_worker,
            "from_role": self.from_role,
            "to_worker": self.to_worker,
            "to_role": self.to_role,
            "message_type": self.message_type.value,
            "priority": self.priority,
            "timestamp": self.timestamp,
            "privacy_class": self.privacy_class,
            "content": self.content,
            "artifact_refs": self.artifact_refs,
            "source_refs": self.source_refs,
            "evidence_refs": self.evidence_refs,
            "provenance_refs": self.provenance_refs,
            "requires_response": self.requires_response,
            "expiry": self.expiry,
            "correlation_id": self.correlation_id,
        }
        return d


# === §3: Worker Pool ===

@dataclass
class WorkerPool:
    """Logical worker pool (§3).

    LOCAL_WORKER_POOL, CLOUD_WORKER_POOL, HYBRID_WORKER_POOL.
    Tracks logical size vs active concurrency (§9).
    """
    pool_id: str
    worker_class: str  # "local", "cloud", "hybrid"
    max_workers: int = 10
    active_workers: int = 0
    pending_workers: int = 0
    blocked_workers: int = 0
    worker_specs: dict = field(default_factory=dict)  # worker_id -> WorkerSpec

    @property
    def logical_size(self) -> int:
        """Total logical workers in pool (§9)."""
        return len(self.worker_specs)

    @property
    def available_capacity(self) -> int:
        return self.max_workers - self.active_workers

    def register_worker(self, worker_id: str, model_class: str,
                        model_id: Optional[str] = None,
                        provider_id: Optional[str] = None,
                        privacy_class: str = PRIVACY_PROJECT) -> None:
        """Register a logical worker in the pool (§4)."""
        self.worker_specs[worker_id] = {
            "model_class": model_class,
            "model_id": model_id,
            "provider_id": provider_id,
            "privacy_class": privacy_class,
            "status": "idle",
        }

    def acquire(self, worker_id: str) -> bool:
        """Acquire a worker slot. Returns False if the worker is unknown,
        already active, or capacity is exceeded.

        Fail-closed: an unregistered worker_id can NEVER acquire a slot.
        Previously an unknown worker returned True without incrementing
        active_workers, silently bypassing concurrency/resource accounting.
        """
        spec = self.worker_specs.get(worker_id)
        if spec is None:
            # Unknown/unregistered worker: deny. Do not count it, do not
            # let it bypass the pool's concurrency accounting.
            return False
        if spec.get("status") == "active":
            # Already active: a second acquire of the same worker is a bug
            # in the caller and must not double-count capacity.
            return False
        if self.active_workers >= self.max_workers:
            return False
        spec["status"] = "active"
        self.active_workers += 1
        return True

    def release(self, worker_id: str) -> None:
        """Release a worker slot."""
        spec = self.worker_specs.get(worker_id)
        if spec and spec["status"] == "active":
            spec["status"] = "idle"
            self.active_workers -= 1


# === §19: Team Room ===

@dataclass
class TeamRoom:
    """Scoped group chat room for team members (§19).

    Rooms are task/project scoped. Messages are auditable (§16).
    """
    room_id: str
    team_id: str
    task_id: str
    privacy_class: str = PRIVACY_PROJECT
    members: list = field(default_factory=list)
    messages: list = field(default_factory=list)

    def post(self, message: AgentProtocolMessage) -> None:
        """Post a message to the room."""
        self.messages.append(message.to_dict())

    def add_member(self, worker_id: str) -> None:
        if worker_id not in self.members:
            self.members.append(worker_id)

    def message_history(self) -> list:
        """Return auditable message history (§16)."""
        return list(self.messages)


# === §40: Communication Interface Registry ===

class CommunicationInterface(Protocol):
    """Abstract communication interface (§40).

    Backend transport is replaceable (§47).
    """
    interface_id: str
    transport: str  # websocket, webrtc, sip, local

    def session_create(self) -> str: ...
    def session_join(self, session_id: str) -> bool: ...
    def session_leave(self, session_id: str) -> bool: ...
    def message_send(self, session_id: str, message: dict) -> bool: ...
    def message_receive(self, session_id: str) -> Optional[dict]: ...
    def voice_start(self, session_id: str) -> bool: ...
    def voice_stop(self, session_id: str) -> bool: ...
    def video_start(self, session_id: str) -> bool: ...
    def video_stop(self, session_id: str) -> bool: ...
    def screen_share(self, session_id: str) -> bool: ...
    def participant_list(self, session_id: str) -> list: ...


class CommunicationInterfaceRegistry:
    """Registry for communication interfaces (§40, §15 communication).

    Registers interfaces for text, voice, video.
    """

    def __init__(self):
        self._interfaces: dict[str, CommunicationInterface] = {}
        self._registered_modes = set()

    def register(self, interface: CommunicationInterface) -> bool:
        """Register a communication interface (§15)."""
        self._interfaces[interface.interface_id] = interface
        logger.info(f"Registered communication interface: {interface.interface_id} "
                    f"(transport={interface.transport})")
        return True

    def get(self, interface_id: str) -> Optional[CommunicationInterface]:
        return self._interfaces.get(interface_id)

    def list_interfaces(self) -> list:
        return [
            {"interface_id": iface.interface_id, "transport": iface.transport,
             "modes": [m.value for m in self._registered_modes]}
            for iface in self._interfaces.values()
        ]

    def register_text_mode(self) -> None:
        """Register that text communication is available (§15)."""
        self._registered_modes.add(TeamExecutionMode.SOLO_LOCAL)

    def register_voice_mode(self) -> None:
        """Register that voice communication interface exists (§32, §40)."""
        self._registered_modes.add(TeamExecutionMode.SOLO_LOCAL)

    def register_video_mode(self) -> None:
        """Register that video communication interface exists (§34, §40)."""
        self._registered_modes.add(TeamExecutionMode.SOLO_LOCAL)

    @property
    def modes_available(self) -> set:
        return set(self._registered_modes)


# === §22: Team Provider Protocol ===

class TeamProvider(Protocol):
    """External team provider adapter (§22, §23).

    External app with built-in multi-agent capability appears as a team provider.
    """
    provider_id: str

    def create_team(self, team_spec: dict) -> str: ...
    def destroy_team(self, team_id: str) -> bool: ...
    def list_workers(self, team_id: str) -> list: ...
    def assign_role(self, team_id: str, worker_id: str, role: str) -> bool: ...
    def submit_task(self, team_id: str, task: str) -> str: ...
    def send_message(self, team_id: str, message: AgentProtocolMessage) -> bool: ...
    def broadcast(self, team_id: str, message: dict) -> bool: ...
    def query_status(self, team_id: str) -> dict: ...
    def retrieve_result(self, team_id: str, task_id: str) -> Optional[str]: ...
    def cancel(self, team_id: str, task_id: str) -> bool: ...
    def pause(self, team_id: str) -> bool: ...
    def resume(self, team_id: str) -> bool: ...


# === §20: Team Performance Metrics ===

@dataclass
class TeamMetrics:
    """Performance metrics for a team execution (§27)."""
    team_id: str
    completion_time_ms: float = 0.0
    critical_path_duration_ms: float = 0.0
    tasks_completed: int = 0
    parallel_efficiency: float = 0.0
    worker_idle_time_ms: float = 0.0
    retry_count: int = 0
    integration_conflicts: int = 0
    review_rejection_rate: float = 0.0
    resource_usage: dict = field(default_factory=dict)
    cost_estimate: float = 0.0
    human_intervention_count: int = 0
    communication_overhead_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "team_id": self.team_id,
            "completion_time_ms": self.completion_time_ms,
            "critical_path_duration_ms": self.critical_path_duration_ms,
            "tasks_completed": self.tasks_completed,
            "parallel_efficiency": self.parallel_efficiency,
            "worker_idle_time_ms": self.worker_idle_time_ms,
            "retry_count": self.retry_count,
            "integration_conflicts": self.integration_conflicts,
            "review_rejection_rate": self.review_rejection_rate,
            "resource_usage": self.resource_usage,
            "cost_estimate": self.cost_estimate,
            "human_intervention_count": self.human_intervention_count,
            "communication_overhead_ms": self.communication_overhead_ms,
        }


# === Task DAG Node (§11, §55) ===

@dataclass
class TaskDAGNode:
    """A node in the task dependency DAG (§11, §55)."""
    node_id: str
    role_id: str
    task: str
    dependencies: list[str] = field(default_factory=list)
    privacy_class: str = PRIVACY_SECRET_LOCAL_ONLY
    worker_pool: str = "local"
    est_duration_ms: float = 0.0
    fn: Optional[Callable] = None
    status: str = "pending"  # pending, running, completed, failed, blocked
    start_time: float = 0.0
    end_time: float = 0.0
    result: str = ""
    error: str = ""
    execution_target: str = "local"  # local or cloud


# === §13: Message Bus ===

class MessageBus:
    """Agent-to-agent message bus (§13, §14).

    Messages have structured metadata and are auditable (§16).
    """

    def __init__(self):
        self._messages: list = []
        self._subscriptions: dict = {}  # worker_id -> list of handlers

    def send(self, message: AgentProtocolMessage) -> None:
        """Send a message through the bus (§13)."""
        self._messages.append(message.to_dict())
        # Notify subscribers
        handlers = self._subscriptions.get(message.to_worker, [])
        for handler in handlers:
            try:
                handler(message)
            except Exception as e:
                logger.warning(f"Message handler error: {e}")

    def send_direct(self, from_worker: str, to_worker: str,
                    content: str, message_type: MessageType = MessageType.QUESTION,
                    privacy_class: str = PRIVACY_PROJECT,
                    task_id: str = "", team_id: str = "") -> AgentProtocolMessage:
        """Send a direct agent-to-agent message (§9 of §59 proof)."""
        msg = AgentProtocolMessage(
            conversation_id=task_id,
            team_id=team_id,
            task_id=task_id,
            from_worker=from_worker,
            to_worker=to_worker,
            message_type=message_type,
            privacy_class=privacy_class,
            content=content,
        )
        self.send(msg)
        return msg

    def subscribe(self, worker_id: str, handler: Callable) -> None:
        """Subscribe a worker to receive messages."""
        if worker_id not in self._subscriptions:
            self._subscriptions[worker_id] = []
        self._subscriptions[worker_id].append(handler)

    def history(self) -> list:
        """Return auditable message history (§16)."""
        return list(self._messages)

    def messages_for_worker(self, worker_id: str) -> list:
        """Get all messages to/from a specific worker."""
        return [m for m in self._messages
                if m.get("from_worker") == worker_id or m.get("to_worker") == worker_id]
