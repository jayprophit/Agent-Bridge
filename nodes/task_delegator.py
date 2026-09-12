"""TaskDelegator (v0.7). Cross-device task execution and delegation.

Handles delegating tasks to remote nodes and receiving results.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from nodes.node_descriptor import NodeDescriptor
from nodes.node_registry import NodeRegistry
from nodes.node_router import NodeRouter, TaskRequirements, RoutingDecision
from nodes.trust_registry import TrustRegistry


# Delegation statuses
DELEGATION_PENDING = "PENDING"
DELEGATION_ACCEPTED = "ACCEPTED"
DELEGATION_RUNNING = "RUNNING"
DELEGATION_COMPLETED = "COMPLETED"
DELEGATION_FAILED = "FAILED"
DELEGATION_CANCELLED = "CANCELLED"
DELEGATION_TIMEOUT = "TIMEOUT"
DELEGATION_REJECTED = "REJECTED"
DELEGATION_NODE_OFFLINE = "NODE_OFFLINE"

DELEGATION_STATUSES = (
    DELEGATION_PENDING,
    DELEGATION_ACCEPTED,
    DELEGATION_RUNNING,
    DELEGATION_COMPLETED,
    DELEGATION_FAILED,
    DELEGATION_CANCELLED,
    DELEGATION_TIMEOUT,
    DELEGATION_REJECTED,
    DELEGATION_NODE_OFFLINE,
)


@dataclass
class DelegationRequest:
    """Request to delegate a task to a node."""
    delegation_id: str
    task_id: str
    source_node_id: str
    target_node_id: str
    
    # Task specification
    task_type: str = ""
    prompt: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    requirements: TaskRequirements | None = None
    
    # Execution
    selected_agent_id: str = ""
    selected_model_id: str = ""
    selected_provider_id: str = ""
    selected_ide_id: str = ""
    tool_ids: list[str] = field(default_factory=list)
    
    # Privacy
    privacy_policy: str = "LOCAL_FIRST"
    data_locality: str = "local"
    
    # Timing
    created_at: float = field(default_factory=time.monotonic)
    timeout_s: int = 300
    
    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.requirements:
            data["requirements"] = self.requirements.to_dict()
        return data


@dataclass
class DelegationResult:
    """Result of a delegated task execution."""
    delegation_id: str
    task_id: str
    source_node_id: str
    target_node_id: str
    
    # Execution details
    selected_agent: str = ""
    selected_model: str = ""
    selected_provider: str = ""
    selected_ide: str = ""
    tools_used: list[str] = field(default_factory=list)
    
    # Timing
    started_at: float = 0.0
    completed_at: float = 0.0
    duration_ms: int = 0
    
    # Status
    status: str = DELEGATION_PENDING
    error: str = ""
    
    # Result
    result_reference: str = ""  # ArtifactRegistry reference
    result_summary: str = ""
    result_metadata: dict[str, Any] = field(default_factory=dict)
    
    # Verification
    verified: bool = False
    verification_notes: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DelegationStatus:
    """Status update for a delegation."""
    delegation_id: str
    status: str
    progress: float = 0.0
    message: str = ""
    timestamp: float = field(default_factory=time.monotonic)
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class NodeTransport:
    """Abstract transport for node-to-node communication.
    
    For v0.7, provides an in-memory transport for testing.
    Real implementations would use HTTP, WebSocket, etc.
    """
    
    def __init__(self, local_node_id: str):
        self.local_node_id = local_node_id
        self._pending_requests: dict[str, DelegationRequest] = {}
        self._results: dict[str, DelegationResult] = {}
        self._status_callbacks: dict[str, list[callable]] = {}
    
    def send_delegation(self, request: DelegationRequest) -> bool:
        """Send a delegation request to the target node.
        
        For in-memory transport, stores locally for processing.
        """
        self._pending_requests[request.delegation_id] = request
        return True
    
    def get_pending_request(self, delegation_id: str) -> DelegationRequest | None:
        """Get a pending delegation request."""
        return self._pending_requests.get(delegation_id)
    
    def complete_delegation(self, result: DelegationResult) -> None:
        """Mark a delegation as complete with result."""
        self._results[result.delegation_id] = result
        # Notify callbacks
        if result.delegation_id in self._status_callbacks:
            for callback in self._status_callbacks[result.delegation_id]:
                callback(result)
    
    def get_result(self, delegation_id: str) -> DelegationResult | None:
        """Get delegation result."""
        return self._results.get(delegation_id)
    
    def register_status_callback(self, delegation_id: str, callback: callable) -> None:
        """Register a callback for status updates."""
        if delegation_id not in self._status_callbacks:
            self._status_callbacks[delegation_id] = []
        self._status_callbacks[delegation_id].append(callback)
    
    def cancel_delegation(self, delegation_id: str) -> bool:
        """Cancel a pending delegation."""
        if delegation_id in self._pending_requests:
            del self._pending_requests[delegation_id]
            return True
        return False


class TaskDelegator:
    """Manages task delegation across nodes.
    
    Coordinates with NodeRouter for node selection, NodeTransport for
    communication, and tracks delegation lifecycle.
    """
    
    def __init__(
        self,
        node_registry: NodeRegistry,
        trust_registry: TrustRegistry,
        node_router: NodeRouter,
        transport: NodeTransport | None = None,
        local_node_id: str = "",
    ):
        self.node_registry = node_registry
        self.trust_registry = trust_registry
        self.node_router = node_router
        self.transport = transport or NodeTransport(local_node_id)
        self.local_node_id = local_node_id
        
        self._active_delegations: dict[str, DelegationRequest] = {}
        self._delegation_results: dict[str, DelegationResult] = {}
        self._delegation_history: list[DelegationResult] = []
    
    def delegate(
        self,
        task_id: str,
        task_type: str,
        prompt: str,
        requirements: TaskRequirements,
        context: dict[str, Any] | None = None,
        selected_agent: str = "",
        selected_model: str = "",
        selected_provider: str = "",
        selected_ide: str = "",
        tool_ids: list[str] | None = None,
    ) -> DelegationResult:
        """Delegate a task to the best available node.
        
        This is the main entry point for task delegation.
        """
        # Route to find best node
        routing_decision = self.node_router.route(task_id, requirements)
        
        if not routing_decision.selected_node_id:
            # No eligible node
            return DelegationResult(
                delegation_id=f"del-{uuid.uuid4().hex[:10]}",
                task_id=task_id,
                source_node_id=self.local_node_id,
                target_node_id="",
                status=DELEGATION_FAILED,
                error=routing_decision.reasoning or "No eligible node found",
            )
        
        target_node_id = routing_decision.selected_node_id
        
        # Check if local execution
        if target_node_id == self.local_node_id:
            return self._execute_locally(
                task_id=task_id,
                task_type=task_type,
                prompt=prompt,
                requirements=requirements,
                context=context,
                selected_agent=selected_agent,
                selected_model=selected_model,
                selected_provider=selected_provider,
                selected_ide=selected_ide,
                tool_ids=tool_ids,
            )
        
        # Remote delegation
        return self._delegate_remote(
            task_id=task_id,
            task_type=task_type,
            prompt=prompt,
            requirements=requirements,
            context=context,
            target_node_id=target_node_id,
            routing_decision=routing_decision,
            selected_agent=selected_agent,
            selected_model=selected_model,
            selected_provider=selected_provider,
            selected_ide=selected_ide,
            tool_ids=tool_ids,
        )
    
    def _execute_locally(
        self,
        task_id: str,
        task_type: str,
        prompt: str,
        requirements: TaskRequirements,
        context: dict[str, Any] | None,
        selected_agent: str,
        selected_model: str,
        selected_provider: str,
        selected_ide: str,
        tool_ids: list[str] | None,
    ) -> DelegationResult:
        """Execute task locally (placeholder for actual execution)."""
        delegation_id = f"del-{uuid.uuid4().hex[:10]}"
        
        result = DelegationResult(
            delegation_id=delegation_id,
            task_id=task_id,
            source_node_id=self.local_node_id,
            target_node_id=self.local_node_id,
            selected_agent=selected_agent,
            selected_model=selected_model,
            selected_provider=selected_provider,
            selected_ide=selected_ide,
            tools_used=tool_ids or [],
            status=DELEGATION_COMPLETED,
            started_at=time.monotonic(),
            completed_at=time.monotonic(),
            duration_ms=0,
            result_summary="Local execution completed (placeholder)",
        )
        
        self._delegation_results[delegation_id] = result
        self._delegation_history.append(result)
        
        return result
    
    def _delegate_remote(
        self,
        task_id: str,
        task_type: str,
        prompt: str,
        requirements: TaskRequirements,
        context: dict[str, Any] | None,
        target_node_id: str,
        routing_decision,
        selected_agent: str,
        selected_model: str,
        selected_provider: str,
        selected_ide: str,
        tool_ids: list[str] | None,
    ) -> DelegationResult:
        """Delegate task to a remote node."""
        delegation_id = f"del-{uuid.uuid4().hex[:10]}"
        
        request = DelegationRequest(
            delegation_id=delegation_id,
            task_id=task_id,
            source_node_id=self.local_node_id,
            target_node_id=target_node_id,
            task_type=task_type,
            prompt=prompt,
            context=context or {},
            requirements=requirements,
            selected_agent_id=selected_agent,
            selected_model_id=selected_model,
            selected_provider_id=selected_provider,
            selected_ide_id=selected_ide,
            tool_ids=tool_ids or [],
            privacy_policy=requirements.privacy_policy,
            data_locality=requirements.data_locality,
            timeout_s=requirements.timeout_s if hasattr(requirements, 'timeout_s') else 300,
        )
        
        # Send via transport
        self.transport.send_delegation(request)
        self._active_delegations[delegation_id] = request
        
        # For in-memory transport, simulate remote execution
        # In real implementation, this would be async with callbacks
        result = self._simulate_remote_execution(request)
        
        # Update tracking
        self._active_delegations.pop(delegation_id, None)
        self._delegation_results[delegation_id] = result
        self._delegation_history.append(result)
        
        return result
    
    def _simulate_remote_execution(self, request: DelegationRequest) -> DelegationResult:
        """Simulate remote execution for in-memory transport."""
        delegation_id = request.delegation_id
        
        # For testing, create a result immediately
        # Real implementation would wait for transport callback
        result = DelegationResult(
            delegation_id=delegation_id,
            task_id=request.task_id,
            source_node_id=request.source_node_id,
            target_node_id=request.target_node_id,
            selected_agent=request.selected_agent_id,
            selected_model=request.selected_model_id,
            selected_provider=request.selected_provider_id,
            selected_ide=request.selected_ide_id,
            tools_used=request.tool_ids,
            status=DELEGATION_COMPLETED,
            started_at=time.monotonic(),
            completed_at=time.monotonic(),
            duration_ms=100,
            result_summary=f"Remote execution on {request.target_node_id} (simulated)",
            result_metadata={"simulated": True, "transport": "in_memory"},
        )
        
        return result
    
    def get_delegation_status(self, delegation_id: str) -> DelegationResult | None:
        """Get status/result of a delegation."""
        return self._delegation_results.get(delegation_id)
    
    def cancel_delegation(self, delegation_id: str) -> bool:
        """Cancel a pending delegation."""
        if delegation_id in self._active_delegations:
            self.transport.cancel_delegation(delegation_id)
            self._active_delegations.pop(delegation_id, None)
            return True
        return False
    
    def get_delegation_history(self, limit: int = 100) -> list[DelegationResult]:
        """Get recent delegation history."""
        return self._delegation_history[-limit:]
    
    def wait_for_result(self, delegation_id: str, timeout_s: int = 300) -> DelegationResult | None:
        """Wait for delegation result (blocking)."""
        start = time.monotonic()
        
        while time.monotonic() - start < timeout_s:
            result = self.get_delegation_status(delegation_id)
            if result and result.status in (DELEGATION_COMPLETED, DELEGATION_FAILED, DELEGATION_CANCELLED):
                return result
            time.sleep(0.1)
        
        # Timeout
        return DelegationResult(
            delegation_id=delegation_id,
            task_id="",
            source_node_id=self.local_node_id,
            target_node_id="",
            status=DELEGATION_TIMEOUT,
            error=f"Delegation timed out after {timeout_s}s",
        )


def create_task_delegator(
    node_registry: NodeRegistry,
    trust_registry: TrustRegistry,
    node_router: NodeRouter,
    local_node_id: str,
    transport: NodeTransport | None = None,
) -> TaskDelegator:
    """Factory to create a TaskDelegator."""
    return TaskDelegator(
        node_registry=node_registry,
        trust_registry=trust_registry,
        node_router=node_router,
        transport=transport,
        local_node_id=local_node_id,
    )