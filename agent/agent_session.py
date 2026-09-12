"""AgentSession (v0.7). Agent session management.

AgentSession manages the lifecycle of an agent session:
- Session creation and initialization
- Task submission and execution
- State management
- Resource cleanup
- Session persistence
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from agent.agent_core import AgentCore, AgentPlan


@dataclass
class SessionConfig:
    workspace: str = ""
    profile: str = "GENERAL_DESKTOP_PROFILE"
    privacy_policy: str = "LOCAL_FIRST"
    max_steps: int = 100
    timeout_s: int = 3600
    enable_milestones: bool = True
    enable_verification: bool = True
    enable_review: bool = True
    owner_authorized: bool = False
    admin_active: bool = False
    
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SessionState:
    session_id: str
    status: str = "idle"  # "idle", "running", "paused", "completed", "failed", "cancelled"
    current_task: str = ""
    current_plan_id: str = ""
    steps_completed: int = 0
    steps_total: int = 0
    error: str = ""
    start_time: float = field(default_factory=time.monotonic)
    end_time: float = 0.0
    metadata: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AgentSession:
    """Agent session management."""
    
    def __init__(self, session_id: str, config: SessionConfig,
                 agent_core: AgentCore, workspace: str = ""):
        self.session_id = session_id
        self.config = config
        self.agent_core = agent_core
        self.workspace = workspace or config.workspace
        self.state = SessionState(session_id=session_id)
        self.session_dir = Path(self.workspace) / ".bridge" / "sessions" / session_id
        self._ensure_session_dir()
    
    def _ensure_session_dir(self) -> None:
        """Ensure session directory exists."""
        self.session_dir.mkdir(parents=True, exist_ok=True)
    
    def submit_task(self, task: str, context: dict[str, Any] | None = None) -> AgentPlan:
        """Submit a task for execution.
        
        Args:
            task: The task to execute.
            context: Additional execution context.
            
        Returns:
            AgentPlan for the task.
        """
        context = dict(context or {})
        
        # Add session context
        context.update({
            "session_id": self.session_id,
            "workspace": self.workspace,
            "profile": self.config.profile,
            "privacy_policy": self.config.privacy_policy,
            "owner_authorized": self.config.owner_authorized,
            "admin_active": self.config.admin_active
        })
        
        # Create plan
        plan = self.agent_core.create_plan(task, context)
        
        # Update session state
        self.state.current_task = task
        self.state.current_plan_id = plan.plan_id
        self.state.status = "running"
        self.state.steps_total = plan.total_steps
        
        # Save session state
        self._save_state()
        
        return plan
    
    def execute_plan(self, plan: AgentPlan,
                    context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a plan step by step.
        
        Args:
            plan: The plan to execute.
            context: Execution context.
            
        Returns:
            Final execution result.
        """
        context = dict(context or {})
        context.update({
            "session_id": self.session_id,
            "workspace": self.workspace,
            "profile": self.config.profile,
            "privacy_policy": self.config.privacy_policy,
            "owner_authorized": self.config.owner_authorized,
            "admin_active": self.config.admin_active
        })
        
        results = []
        failed = False
        
        for i in range(len(plan.steps)):
            if self.state.status == "cancelled":
                break
            
            if i >= self.config.max_steps:
                plan.status = "failed"
                plan.metadata["error"] = "max steps reached"
                failed = True
                break
            
            # Execute step
            result = self.agent_core.execute_step(plan, i, context)
            results.append(result)
            
            # Update session state
            self.state.steps_completed = i + 1
            
            # Check for failure
            if not result.get("ok"):
                # Determine if we should continue or stop
                if context.get("stop_on_error", True):
                    plan.status = "failed"
                    plan.metadata["error"] = result.get("error", "step failed")
                    failed = True
                    break
            
            # Save state periodically
            if i % 5 == 0:
                self._save_state()
        
        # Update final state
        if failed:
            self.state.status = "failed"
            self.state.error = plan.metadata.get("error", "execution failed")
        elif self.state.status == "cancelled":
            self.state.status = "cancelled"
        else:
            self.state.status = "completed"
        
        self.state.end_time = time.monotonic()
        self._save_state()
        
        return {
            "ok": not failed,
            "session_id": self.session_id,
            "plan_id": plan.plan_id,
            "steps_completed": self.state.steps_completed,
            "steps_total": self.state.steps_total,
            "duration_s": self.state.end_time - self.state.start_time,
            "results": results,
            "plan": plan.to_dict()
        }
    
    def pause(self) -> dict[str, Any]:
        """Pause the current session."""
        if self.state.status == "running":
            self.state.status = "paused"
            self._save_state()
            return {"ok": True, "session_id": self.session_id, "status": "paused"}
        return {"ok": False, "error": "session not running"}
    
    def resume(self) -> dict[str, Any]:
        """Resume a paused session."""
        if self.state.status == "paused":
            self.state.status = "running"
            self._save_state()
            return {"ok": True, "session_id": self.session_id, "status": "running"}
        return {"ok": False, "error": "session not paused"}
    
    def cancel(self) -> dict[str, Any]:
        """Cancel the current session."""
        if self.state.status in ("running", "paused"):
            self.state.status = "cancelled"
            self.state.end_time = time.monotonic()
            self._save_state()
            return {"ok": True, "session_id": self.session_id, "status": "cancelled"}
        return {"ok": False, "error": "session not active"}
    
    def get_state(self) -> SessionState:
        """Get current session state."""
        return self.state
    
    def get_plan(self, plan_id: str) -> AgentPlan:
        """Get a plan by ID."""
        return self.agent_core.get_plan(plan_id)
    
    def _save_state(self) -> None:
        """Save session state to disk."""
        state_file = self.session_dir / "state.json"
        with open(state_file, "w") as f:
            json.dump({
                "config": self.config.to_dict(),
                "state": self.state.to_dict()
            }, f, indent=2)
    
    def _load_state(self) -> None:
        """Load session state from disk."""
        state_file = self.session_dir / "state.json"
        if state_file.exists():
            with open(state_file) as f:
                data = json.load(f)
                config_data = data.get("config", {})
                state_data = data.get("state", {})
                
                # Update config
                for key, value in config_data.items():
                    if hasattr(self.config, key):
                        setattr(self.config, key, value)
                
                # Update state
                for key, value in state_data.items():
                    if hasattr(self.state, key):
                        setattr(self.state, key, value)
    
    def cleanup(self) -> None:
        """Clean up session resources."""
        # Mark session as complete if still running
        if self.state.status == "running":
            self.state.status = "cancelled"
            self.state.end_time = time.monotonic()
            self._save_state()


def create_session_id() -> str:
    """Create a unique session ID."""
    return f"session-{uuid.uuid4().hex[:12]}"