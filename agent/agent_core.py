"""AgentCore (v0.7). Core agent orchestration logic.

AgentCore provides the fundamental orchestration capabilities:
- Task planning and decomposition
- Model selection
- Tool discovery and selection
- Step execution and verification
- Progress tracking
- Error handling and recovery
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from models.model_router import ModelRouter
from tools.registry import ToolRegistry
from tools.router import ToolRouter


@dataclass
class AgentStep:
    step_id: str
    step_type: str  # "plan", "execute", "verify", "reflect"
    description: str
    tool_id: str = ""
    model_id: str = ""
    arguments: dict = field(default_factory=dict)
    status: str = "pending"  # "pending", "running", "completed", "failed"
    result: dict = field(default_factory=dict)
    error: str = ""
    duration_s: float = 0.0
    timestamp: float = field(default_factory=time.monotonic)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "step_type": self.step_type,
            "description": self.description,
            "tool_id": self.tool_id,
            "model_id": self.model_id,
            "arguments": self.arguments,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "duration_s": self.duration_s,
            "timestamp": self.timestamp
        }


@dataclass
class AgentPlan:
    plan_id: str
    task: str
    steps: list[AgentStep] = field(default_factory=list)
    status: str = "planning"  # "planning", "ready", "executing", "completed", "failed"
    current_step_index: int = 0
    total_steps: int = 0
    metadata: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "task": self.task,
            "steps": [s.to_dict() for s in self.steps],
            "status": self.status,
            "current_step_index": self.current_step_index,
            "total_steps": self.total_steps,
            "metadata": self.metadata
        }


class AgentCore:
    """Core agent orchestration logic."""
    
    def __init__(self, tool_registry: ToolRegistry, model_router: ModelRouter,
                 tool_router: ToolRouter):
        self.tool_registry = tool_registry
        self.model_router = model_router
        self.tool_router = tool_router
        self.plans: dict[str, AgentPlan] = {}
        self.execution_log: list[dict] = []
    
    def create_plan(self, task: str, context: dict[str, Any] | None = None) -> AgentPlan:
        """Create an execution plan for a task.
        
        Args:
            task: The task to plan for.
            context: Additional context for planning.
            
        Returns:
            AgentPlan with planned steps.
        """
        context = dict(context or {})
        plan_id = f"plan-{uuid.uuid4().hex[:10]}"
        
        # Analyze task and determine approach
        task_type = self._classify_task(task, context)
        
        # Create initial plan
        steps = self._generate_initial_steps(task, task_type, context)
        
        plan = AgentPlan(
            plan_id=plan_id,
            task=task,
            steps=steps,
            status="ready",
            total_steps=len(steps),
            metadata={
                "task_type": task_type,
                "created_at": time.monotonic()
            }
        )
        
        self.plans[plan_id] = plan
        return plan
    
    def _classify_task(self, task: str, context: dict[str, Any]) -> str:
        """Classify the task type for routing."""
        task_lower = task.lower()
        
        # Simple keyword-based classification
        if any(word in task_lower for word in ["code", "program", "function", "debug", "fix"]):
            return "coding"
        elif any(word in task_lower for word in ["image", "picture", "visual", "screenshot"]):
            return "vision"
        elif any(word in task_lower for word in ["review", "check", "verify", "validate"]):
            return "review"
        elif any(word in task_lower for word in ["data", "analyze", "statistics", "calculate"]):
            return "analytics"
        elif any(word in task_lower for word in ["file", "directory", "folder", "read", "write"]):
            return "filesystem"
        elif any(word in task_lower for word in ["web", "http", "download", "fetch"]):
            return "network"
        else:
            return "general"
    
    def _generate_initial_steps(self, task: str, task_type: str,
                                context: dict[str, Any]) -> list[AgentStep]:
        """Generate initial steps for the plan."""
        steps = []
        
        # Step 1: Understand and plan
        steps.append(AgentStep(
            step_id=f"step-{uuid.uuid4().hex[:8]}",
            step_type="plan",
            description=f"Understand task: {task}",
            status="pending"
        ))
        
        # Step 2: Select model
        model_decision = self.model_router.route(
            task_type=task_type,
            requirements=context.get("requirements", {}),
            privacy_policy=context.get("privacy_policy", "LOCAL_FIRST"),
            context=context
        )
        
        steps.append(AgentStep(
            step_id=f"step-{uuid.uuid4().hex[:8]}",
            step_type="execute",
            description=f"Select model for {task_type} task",
            model_id=model_decision.selected_model,
            status="pending",
            result={"routing_decision": model_decision.to_dict()}
        ))
        
        # Step 3: Discover relevant tools
        relevant_tools = self._discover_relevant_tools(task, task_type, context)
        
        steps.append(AgentStep(
            step_id=f"step-{uuid.uuid4().hex[:8]}",
            step_type="execute",
            description=f"Discover {len(relevant_tools)} relevant tools",
            status="pending",
            result={"tool_count": len(relevant_tools), "tools": relevant_tools[:5]}
        ))
        
        # Task-specific steps
        if task_type == "coding":
            steps.extend(self._generate_coding_steps(task, context))
        elif task_type == "filesystem":
            steps.extend(self._generate_filesystem_steps(task, context))
        elif task_type == "network":
            steps.extend(self._generate_network_steps(task, context))
        else:
            steps.extend(self._generate_general_steps(task, context))
        
        # Final step: Verify and report
        steps.append(AgentStep(
            step_id=f"step-{uuid.uuid4().hex[:8]}",
            step_type="verify",
            description="Verify results and generate report",
            status="pending"
        ))
        
        return steps
    
    def _discover_relevant_tools(self, task: str, task_type: str,
                                context: dict[str, Any]) -> list[str]:
        """Discover tools relevant to the task."""
        # Search for tools by task keywords
        search_results = self.tool_registry.search(task, limit=10)
        return [t.tool_id for t in search_results]
    
    def _generate_coding_steps(self, task: str, context: dict[str, Any]) -> list[AgentStep]:
        """Generate steps for coding tasks."""
        return [
            AgentStep(
                step_id=f"step-{uuid.uuid4().hex[:8]}",
                step_type="execute",
                description="Analyze code structure",
                tool_id="code.project_detect",
                status="pending"
            ),
            AgentStep(
                step_id=f"step-{uuid.uuid4().hex[:8]}",
                step_type="execute",
                description="Read relevant files",
                tool_id="filesystem.read",
                status="pending"
            ),
            AgentStep(
                step_id=f"step-{uuid.uuid4().hex[:8]}",
                step_type="execute",
                description="Generate or modify code",
                tool_id="code.generate",
                status="pending"
            ),
            AgentStep(
                step_id=f"step-{uuid.uuid4().hex[:8]}",
                step_type="execute",
                description="Run tests",
                tool_id="test.run",
                status="pending"
            )
        ]
    
    def _generate_filesystem_steps(self, task: str, context: dict[str, Any]) -> list[AgentStep]:
        """Generate steps for filesystem tasks."""
        return [
            AgentStep(
                step_id=f"step-{uuid.uuid4().hex[:8]}",
                step_type="execute",
                description="List directory contents",
                tool_id="filesystem.list",
                status="pending"
            ),
            AgentStep(
                step_id=f"step-{uuid.uuid4().hex[:8]}",
                step_type="execute",
                description="Read file contents",
                tool_id="filesystem.read",
                status="pending"
            ),
            AgentStep(
                step_id=f"step-{uuid.uuid4().hex[:8]}",
                step_type="execute",
                description="Write or modify files",
                tool_id="filesystem.write",
                status="pending"
            )
        ]
    
    def _generate_network_steps(self, task: str, context: dict[str, Any]) -> list[AgentStep]:
        """Generate steps for network tasks."""
        return [
            AgentStep(
                step_id=f"step-{uuid.uuid4().hex[:8]}",
                step_type="execute",
                description="Make HTTP request",
                tool_id="http.get",
                status="pending"
            ),
            AgentStep(
                step_id=f"step-{uuid.uuid4().hex[:8]}",
                step_type="execute",
                description="Process response",
                tool_id="data.json",
                status="pending"
            )
        ]
    
    def _generate_general_steps(self, task: str, context: dict[str, Any]) -> list[AgentStep]:
        """Generate steps for general tasks."""
        return [
            AgentStep(
                step_id=f"step-{uuid.uuid4().hex[:8]}",
                step_type="execute",
                description="Execute task with available tools",
                tool_id="shell.run",
                status="pending"
            )
        ]
    
    def execute_step(self, plan: AgentPlan, step_index: int,
                    context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a single step from the plan.
        
        Args:
            plan: The plan containing the step.
            step_index: Index of the step to execute.
            context: Execution context.
            
        Returns:
            Execution result.
        """
        if step_index >= len(plan.steps):
            return {"ok": False, "error": "step index out of range"}
        
        step = plan.steps[step_index]
        context = dict(context or {})
        t0 = time.monotonic()
        
        step.status = "running"
        plan.current_step_index = step_index
        plan.status = "executing"
        
        try:
            if step.step_type == "plan":
                result = {"ok": True, "note": "planning step"}
            elif step.step_type == "execute":
                if step.tool_id:
                    result = self.tool_router.call(
                        step.tool_id,
                        step.arguments,
                        context
                    )
                else:
                    result = {"ok": True, "note": "no tool execution needed"}
            elif step.step_type == "verify":
                result = {"ok": True, "note": "verification step"}
            else:
                result = {"ok": False, "error": f"unknown step type: {step.step_type}"}
            
            step.result = result
            step.status = "completed" if result.get("ok") else "failed"
            step.error = result.get("error", "")
            
        except Exception as e:
            step.result = {"ok": False, "error": str(e)}
            step.status = "failed"
            step.error = str(e)
        
        step.duration_s = time.monotonic() - t0
        
        # Update plan status
        if step.status == "failed":
            plan.status = "failed"
        elif step_index == len(plan.steps) - 1:
            plan.status = "completed"
        
        # Log execution
        self.execution_log.append({
            "plan_id": plan.plan_id,
            "step_id": step.step_id,
            "step_index": step_index,
            "status": step.status,
            "duration_s": step.duration_s,
            "timestamp": time.monotonic()
        })
        
        return step.result
    
    def get_plan(self, plan_id: str) -> AgentPlan:
        """Get a plan by ID."""
        if plan_id not in self.plans:
            raise KeyError(f"plan not found: {plan_id}")
        return self.plans[plan_id]
    
    def list_plans(self) -> list[AgentPlan]:
        """List all plans."""
        return list(self.plans.values())
    
    def get_execution_log(self, limit: int = 100) -> list[dict]:
        """Get recent execution log entries."""
        return self.execution_log[-limit:]