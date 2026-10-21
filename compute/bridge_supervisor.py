"""Aetherius Agent Communications Bridge — supervisor (§6, §30).

The bridge supervisor orchestrates the task lifecycle:
  TASK_ASSIGN → DELIVERED → ACKNOWLEDGED → RUNNING_VERIFIED →
  PROGRESSING → COMPLETED → HANDED_OFF → QA_PASSED → NEXT_TASK.

Each transition requires evidence (§6). SENT != RECEIVED != ACKNOWLEDGED
!= RUNNING. The supervisor NEVER claims a worker is IMPLEMENTING based on
activity proxies (§44: OWNER_MANUAL_RELAY_REQUIRED if manual relay needed).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from compute.agent_message import (
    AgentMessage,
    ClaimType,
    DeliveryState,
    Intent,
    build_ack,
    build_heartbeat,
    build_task_assign,
    build_task_complete,
    build_task_start,
)
from compute.agent_message_bus import AgentMessageBus, DeliveryError
from compute.worker_bridge_adapters import WorkerAdapterInterface


@dataclass
class TaskLifecycle:
    """Tracks one task's delivery lifecycle with evidence (§6)."""
    task_id: str
    assign_msg_id: str = ""
    delivery_state: DeliveryState = DeliveryState.PENDING
    ack_msg_id: str = ""
    start_msg_id: str = ""
    complete_msg_id: str = ""
    handoff_msg_id: str = ""
    evidence: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    owner_manual_relay: bool = False  # §44: was manual intervention needed?

    def add_evidence(self, evidence: str) -> None:
        self.evidence.append(evidence)
        self.updated_at = time.time()


class BridgeSupervisor:
    """The supervisor that manages worker task delivery via the bridge (§6).

    Key contract: the supervisor NEVER marks a task as RUNNING based on
    activity proxies. It requires:
    - TASK_ACK from the worker (§7) before ACKNOWLEDGED
    - TASK_START from the worker (§8) before RUNNING_VERIFIED
    - Task-specific evidence (transcript contains task_id) for verification (§15)
    """

    def __init__(self, bus: AgentMessageBus):
        self._bus = bus
        self._lifecycles: dict[str, TaskLifecycle] = {}
        self._adapters: dict[str, WorkerAdapterInterface] = {}

    # -- adapter management (§12) --------------------------------------------------

    def register_adapter(self, adapter: WorkerAdapterInterface) -> None:
        """Register a worker adapter (§12)."""
        self._adapters[adapter.worker_id] = adapter

    def get_adapter(self, worker_id: str) -> Optional[WorkerAdapterInterface]:
        return self._adapters.get(worker_id)

    def list_workers(self) -> list[dict[str, Any]]:
        """List all registered workers with status (§43 dashboard)."""
        workers = []
        for wid, adapter in self._adapters.items():
            status = adapter.status()
            workers.append({
                "worker_id": wid,
                "agent_id": adapter.agent_id,
                "status": status.get("status", "UNKNOWN"),
                "capabilities": [c.value for c in adapter.capabilities],
                "delivery_state": adapter.delivery_state.value,
                "current_model": adapter.current_model,
            })
        return workers

    # -- task assignment (§6, §7) -----------------------------------------------------

    def assign_task(self, task_id: str, objective: str,
                    worker_id: str, project_id: str = "",
                    cost_policy: str = "ZERO_INCREMENTAL_SPEND",
                    permissions: list[str] | None = None,
                    write_set: list[str] | None = None,
                    branch: str = "",
                    worktree: str = "",
                    priority: int = 50) -> dict[str, Any]:
        """Assign a task to a worker. Returns delivery result with evidence.

        This is the CORE operation. It:
        1. Builds a TASK_ASSIGN message (§5)
        2. Persists it to the durable bus (§3)
        3. Sends it via the adapter's transport (§13)
        4. Marks DELIVERED (§6)
        5. Returns honest delivery status — NOT "IMPLEMENTING"
        """
        adapter = self._adapters.get(worker_id)
        if not adapter:
            return {"task_id": task_id, "delivered": False,
                    "error": f"unknown worker: {worker_id}"}

        # Build the TASK_ASSIGN message
        msg = build_task_assign(
            task_id=task_id,
            objective=objective,
            sender_agent="hermes",
            sender_worker="bridge-supervisor",
            receiver_agent=adapter.agent_id,
            receiver_worker=worker_id,
            project_id=project_id,
            cost_policy=cost_policy,
            permissions=permissions,
            write_set=write_set,
            branch=branch,
            worktree=worktree,
            priority=priority,
        )

        # Persist BEFORE delivery (§3 crash-safe)
        self._bus.submit(msg)

        # Track lifecycle
        lc = TaskLifecycle(task_id=task_id, assign_msg_id=msg.message_id)
        self._lifecycles[task_id] = lc

        # Send via adapter transport (§13)
        result = adapter.send_message(msg)

        if result.get("delivered"):
            # Mark DELIVERED (§6: DELIVERED, not ACKNOWLEDGED)
            self._bus.mark_delivered(msg.message_id)
            lc.delivery_state = DeliveryState.DELIVERED
            lc.add_evidence(f"delivered via {result.get('channel', 'unknown')}")
            for ev in result.get("evidence", []):
                lc.add_evidence(ev)
        else:
            lc.delivery_state = DeliveryState.DELIVERY_FAILED
            lc.add_evidence(f"delivery failed: {result.get('evidence', ['unknown'])}")
            self._bus.mark_delivery_failed(
                msg.message_id,
                reason=str(result.get("evidence", ["unknown"])))

        return {
            "task_id": task_id,
            "message_id": msg.message_id,
            "delivery_state": lc.delivery_state.value,
            "channel": result.get("channel", ""),
            "evidence": lc.evidence,
            # CRITICAL: NOT "IMPLEMENTING" — just DELIVERED (§44)
        }

    # -- ACK verification (§7) ---------------------------------------------------------

    def verify_ack(self, task_id: str) -> dict[str, Any]:
        """Verify that the worker has ACKed the task (§7).

        Searches the worker's transcript for the task_id (§15).
        Only after this may we classify DELIVERY_VERIFIED (§7).
        """
        lc = self._lifecycles.get(task_id)
        if not lc:
            return {"task_id": task_id, "acknowledged": False,
                    "error": "unknown task"}

        adapter = self._adapters.get(lc.worker_id) if hasattr(lc, 'worker_id') else None
        # Find the adapter from the assign message
        msg = self._bus.get_messages_for_task(task_id)
        if not msg:
            return {"task_id": task_id, "acknowledged": False,
                    "error": "no messages for task"}

        # Find the worker from the assign message
        assign = msg[0]
        worker_id = assign.get("receiver_worker", "")
        adapter = self._adapters.get(worker_id)

        if not adapter:
            return {"task_id": task_id, "acknowledged": False,
                    "error": f"no adapter for worker {worker_id}"}

        # Reconstruct the assign message for the adapter's acknowledge()
        from compute.agent_message import AgentMessage
        assign_msg = AgentMessage(
            task_id=task_id,
            intent=Intent.TASK_ASSIGN,
            sender_agent=assign.get("sender_agent", ""),
            sender_worker=assign.get("sender_worker", ""),
            receiver_agent=assign.get("receiver_agent", ""),
            receiver_worker=assign.get("receiver_worker", ""),
        )

        acked = adapter.acknowledge(assign_msg)
        if acked:
            self._bus.mark_acknowledged(lc.assign_msg_id, assign_msg)
            lc.delivery_state = DeliveryState.ACKNOWLEDGED
            lc.add_evidence("worker ACKed (task_id found in transcript)")
            return {"task_id": task_id, "acknowledged": True,
                    "delivery_state": "ACKNOWLEDGED"}
        else:
            return {"task_id": task_id, "acknowledged": False,
                    "delivery_state": "DELIVERED (no ACK yet)",
                    "note": "SENT != ACKNOWLEDGED (§7)"}

    # -- start verification (§8) ---------------------------------------------------------

    def verify_start(self, task_id: str) -> dict[str, Any]:
        """Verify that the worker has STARTED the task (§8).

        SESSION_ACTIVE or PROCESS_ALIVE alone is NOT sufficient (§8).
        Requires task-specific evidence.
        """
        lc = self._lifecycles.get(task_id)
        if not lc:
            return {"task_id": task_id, "started": False,
                    "error": "unknown task"}

        if lc.delivery_state != DeliveryState.ACKNOWLEDGED:
            return {"task_id": task_id, "started": False,
                    "error": f"cannot verify start from {lc.delivery_state.value}"}

        # The worker must have sent TASK_START or we observe task-specific
        # evidence. For CLI adapters, we check if the worker's output
        # contains task-specific activity.
        # For now: mark as RUNNING_VERIFIED if ACK was received and
        # the adapter reports the task is active.
        msg = self._bus.get_messages_for_task(task_id)
        if not msg:
            return {"task_id": task_id, "started": False,
                    "error": "no messages for task"}

        # Check for TASK_START or equivalent evidence in the bus
        for m in msg:
            if m.get("intent") == Intent.TASK_START.value:
                self._bus.mark_started(lc.assign_msg_id, AgentMessage(
                    task_id=task_id, intent=Intent.TASK_START))
                lc.delivery_state = DeliveryState.RUNNING_VERIFIED
                lc.add_evidence("TASK_START received from worker")
                return {"task_id": task_id, "started": True,
                        "delivery_state": "RUNNING_VERIFIED"}

        # No explicit TASK_START — honest: not verified started
        return {"task_id": task_id, "started": False,
                "delivery_state": "ACKNOWLEDGED (no TASK_START yet)",
                "note": "PROCESS_ALIVE alone is insufficient (§8)"}

    # -- completion + handoff (§11) --------------------------------------------------------

    def receive_handoff(self, task_id: str, handoff_msg: AgentMessage) -> dict[str, Any]:
        """Receive a HANDOFF from a worker (§11)."""
        lc = self._lifecycles.get(task_id)
        if not lc:
            return {"task_id": task_id, "received": False,
                    "error": "unknown task"}

        self._bus.submit(handoff_msg)
        self._bus.mark_completed(lc.assign_msg_id, handoff_msg)
        lc.delivery_state = DeliveryState.HANDED_OFF
        lc.handoff_msg_id = handoff_msg.message_id
        lc.add_evidence(f"handoff received: {handoff_msg.payload.get('completed_work', '')[:100]}")

        return {
            "task_id": task_id,
            "received": True,
            "delivery_state": "HANDED_OFF",
            "files_changed": handoff_msg.payload.get("files_changed", []),
            "evidence": lc.evidence,
        }

    # -- lifecycle query (§43) ---------------------------------------------------------------

    def get_lifecycle(self, task_id: str) -> Optional[dict[str, Any]]:
        """Get the full lifecycle state for a task (§43 dashboard)."""
        lc = self._lifecycles.get(task_id)
        if not lc:
            return None
        return {
            "task_id": lc.task_id,
            "delivery_state": lc.delivery_state.value,
            "evidence": lc.evidence,
            "owner_manual_relay": lc.owner_manual_relay,
            "created_at": lc.created_at,
            "updated_at": lc.updated_at,
        }

    def record_owner_manual_relay(self, task_id: str) -> None:
        """Record that the owner had to manually relay a task (§44).

        This is a SUPERVISOR FAILURE. It must be recorded, not hidden.
        """
        lc = self._lifecycles.get(task_id)
        if lc:
            lc.owner_manual_relay = True
            lc.add_evidence("OWNER_MANUAL_RELAY_REQUIRED — supervisor failed to deliver (§44)")

    # -- supervisor failure detection (§44) ---------------------------------------------------

    def detect_manual_relay(self, task_id: str) -> bool:
        """Detect if the owner manually relayed a task that the supervisor
        was supposed to deliver (§44).

        Heuristic: if the task was assigned but the worker's session shows
        the prompt was entered manually (not via the adapter's transport),
        record OWNER_MANUAL_RELAY_REQUIRED.
        """
        lc = self._lifecycles.get(task_id)
        if not lc:
            return False
        # If delivery failed but the task appears in the worker's transcript,
        # the owner manually relayed it
        if lc.delivery_state == DeliveryState.DELIVERY_FAILED:
            msg = self._bus.get_messages_for_task(task_id)
            if msg:
                assign = msg[0]
                worker_id = assign.get("receiver_worker", "")
                adapter = self._adapters.get(worker_id)
                if adapter:
                    from compute.agent_message import AgentMessage
                    check_msg = AgentMessage(
                        task_id=task_id, intent=Intent.TASK_ASSIGN)
                    if adapter.acknowledge(check_msg):
                        self.record_owner_manual_relay(task_id)
                        return True
        return False
