"""AgentLoop (v0.7). Agent execution loop with control flow.

AgentLoop provides the main execution loop for agent sessions:
- Step-by-step execution
- Error handling and recovery
- Progress tracking
- Cancellation support
- Milestone checking
- Verification integration
"""
from __future__ import annotations

import time
from typing import Any

from agent.agent_core import AgentCore, AgentPlan
from agent.agent_session import AgentSession


class AgentLoop:
    """Agent execution loop with control flow."""
    
    def __init__(self, session: AgentSession, agent_core: AgentCore):
        self.session = session
        self.agent_core = agent_core
        self._cancelled = False
        self._paused = False
    
    def run(self, plan: AgentPlan, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run the agent loop for a plan.
        
        Args:
            plan: The plan to execute.
            context: Execution context.
            
        Returns:
            Final execution result.
        """
        context = dict(context or {})
        self._cancelled = False
        self._paused = False
        
        result = self.session.execute_plan(plan, context)
        
        return result
    
    def run_single_step(self, plan: AgentPlan, step_index: int,
                       context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run a single step from the plan.
        
        Args:
            plan: The plan containing the step.
            step_index: Index of the step to execute.
            context: Execution context.
            
        Returns:
            Step execution result.
        """
        context = dict(context or {})
        
        if self._cancelled:
            return {"ok": False, "error": "loop cancelled"}
        
        if self._paused:
            return {"ok": False, "error": "loop paused"}
        
        result = self.agent_core.execute_step(plan, step_index, context)
        
        # Check for cancellation after each step
        if self.session.state.status == "cancelled":
            self._cancelled = True
        
        return result
    
    def cancel(self) -> dict[str, Any]:
        """Cancel the running loop."""
        self._cancelled = True
        return self.session.cancel()
    
    def pause(self) -> dict[str, Any]:
        """Pause the running loop."""
        self._paused = True
        return self.session.pause()
    
    def resume(self) -> dict[str, Any]:
        """Resume the paused loop."""
        self._paused = False
        return self.session.resume()
    
    def is_cancelled(self) -> bool:
        """Check if the loop is cancelled."""
        return self._cancelled
    
    def is_paused(self) -> bool:
        """Check if the loop is paused."""
        return self._paused
    
    def get_progress(self) -> dict[str, Any]:
        """Get current progress information."""
        state = self.session.get_state()
        return {
            "session_id": state.session_id,
            "status": state.status,
            "current_task": state.current_task,
            "steps_completed": state.steps_completed,
            "steps_total": state.steps_total,
            "progress_percent": (
                (state.steps_completed / state.steps_total * 100)
                if state.steps_total > 0 else 0
            ),
            "duration_s": time.monotonic() - state.start_time if state.end_time == 0 else state.end_time - state.start_time
        }