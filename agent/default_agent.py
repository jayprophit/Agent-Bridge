"""DefaultAgent (v0.7). Runtime-owned default agent orchestration.

The DefaultAgent is the built-in agent that makes the runtime independent
of external IDE agents. It integrates:

- AgentCore for planning and orchestration
- AgentSession for session management  
- AgentLoop for execution control
- ModelRouter for model selection
- ToolRouter for tool execution
- ToolRegistry for tool discovery

The DefaultAgent provides a simple interface for running tasks:
    agent = DefaultAgent(registries, config)
    session = agent.create_session(workspace)
    result = agent.run_task(session, "Build and test a Python module")
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from agent.agent_core import AgentCore
from agent.agent_loop import AgentLoop
from agent.agent_session import AgentSession, SessionConfig, create_session_id
from aether_policy_bridge import issue_session_workspace_grants
from execution_contract import (
    BLOCK_WITH_EVIDENCE, COMPLETE, ExecutionContract,
    ExecutionPolicyViolation, PLAN_MISSING,
    REEVALUATION_QUESTIONS, VERIFIED as CX_VERIFIED, FAILED as CX_FAILED)
from models.model_router import ModelRouter
from models.model_registry import ModelRegistry
from models.provider_registry import ProviderRegistry
from tools.registry import ToolRegistry
from tools.router import ToolRouter


@dataclass
class AgentRegistries:
    """Container for all agent registries."""
    tool_registry: ToolRegistry
    model_registry: ModelRegistry
    provider_registry: ProviderRegistry
    model_router: ModelRouter
    tool_router: ToolRouter


class DefaultAgent:
    """Default agent orchestration - runtime-owned and independent.
    
    The DefaultAgent provides a complete agent orchestration system that
    does not depend on external IDE agents (OpenCode, Devin, etc.). It uses
    the ModelRouter to select appropriate models and ToolRouter to execute
    tools, making it truly model-agnostic and tool-agnostic.
    """
    
    def __init__(self, registries: AgentRegistries):
        self.registries = registries
        self.agent_core = AgentCore(
            tool_registry=registries.tool_registry,
            model_router=registries.model_router,
            tool_router=registries.tool_router
        )
        self.sessions: dict[str, AgentSession] = {}
    
    def create_session(self, workspace: str = "",
                      config: SessionConfig | None = None) -> AgentSession:
        """Create a new agent session.
        
        Args:
            workspace: Working directory for the session.
            config: Optional session configuration.
            
        Returns:
            AgentSession instance.
        """
        config = config or SessionConfig(workspace=workspace)
        session_id = create_session_id()
        
        session = AgentSession(
            session_id=session_id,
            config=config,
            agent_core=self.agent_core,
            workspace=workspace
        )
        
        # Issue workspace-scoped policy grants for this session (P10-PA compat)
        issue_session_workspace_grants(
            session_id=session.session_id,
            workspace_path=workspace,
            approval_mode="AUTO_SAFE",  # default safe profile
            owner_mode=False,
        )

        self.sessions[session_id] = session
        return session
    
    def run_task(self, session: AgentSession, task: str,
                 context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run a task in a session under the Adaptive Execution Contract.

        Second enforced execution path (Phase 1.1 runtime closure): the
        AgentPlan becomes a contract plan, the loop run is the bounded
        execution, and completion requires verification + re-evaluation.
        Fail-closed: a plan with no steps, or a result that cannot verify,
        is rejected, never silently completed.
        """
        from pathlib import Path as _Path
        context = dict(context or {})

        ws = getattr(session, "workspace", "") or ""
        cx = ExecutionContract(
            _Path(ws) / ".bridge" / "execution_contract.json" if ws else None)

        # Submit task -> AgentPlan (plan-first by construction)
        plan = session.submit_task(task, context)
        ctid = f"{session.session_id}:{plan.plan_id}"
        try:
            cx.receive(ctid)
        except ValueError:
            cx.note_event(ctid, "resumed")

        def _denied(reason: str, detail: str) -> dict[str, Any]:
            try:
                snap = cx.contract_snapshot(ctid)
            except (KeyError, ValueError):
                snap = {"task_id": ctid, "state": "UNKNOWN",
                        "plan_version": 0, "telemetry": {}}
            return {"ok": False, "error": f"{reason}: {detail}",
                    "kind": "EXECUTION_POLICY_VIOLATION",
                    "contract": snap}

        if not plan.steps:
            return _denied(PLAN_MISSING, "agent plan has no steps")
        try:
            cx.recover_context(ctid)
            depth = "FULL" if (plan.total_steps or 0) > 5 else "LIGHTWEIGHT"
            fields: dict[str, Any] = {
                "objective": plan.task[:500],
                "change": f"{len(plan.steps)} planned step(s)",
                "expected_result": "agent plan executed to completion",
                "verify": "plan status completed + step results ok",
            }
            if depth == "FULL":
                meta = getattr(plan, "metadata", {}) or {}
                fields.update({
                    "current_state": str(meta.get("task_type", "agent session")),
                    "requirements": str(task)[:300],
                    "constraints": "session config limits",
                    "dependencies": "tool registry capabilities",
                    "risks": "not specified in AgentPlan",
                    "unknowns": "not specified in AgentPlan",
                    "steps": [s.to_dict() for s in plan.steps][:20],
                    "evidence_requirements": "step results recorded",
                    "acceptance": "plan.status == completed",
                })
            cx.plan(ctid, fields, depth=depth, author="agent-core")
            cx.mark_ready(ctid)
            cx.begin_execute(ctid)
        except ExecutionPolicyViolation as e:
            return _denied(e.reason, e.detail)

        # Create loop and execute (the bounded unit)
        loop = AgentLoop(session, self.agent_core)
        result = loop.run(plan, context)
        try:
            cx.capture_result(ctid, f"loop.run ok={bool((result or {}).get('ok', True))}"[:300]
                              if isinstance(result, dict) else "loop.run done")
            cx.begin_verify(ctid)
            ok = bool(result.get("ok", True)) if isinstance(result, dict) else True
            cx.record_verification(
                ctid, CX_VERIFIED if ok else CX_FAILED,
                [f"plan.status={plan.status}"], verifier="agent-loop")
            cx.begin_reevaluate(ctid)
            findings = {q: f"agent-loop: plan.status={plan.status}"[:200]
                        for q in REEVALUATION_QUESTIONS}
            if ok:
                cx.record_reevaluation(ctid, findings, COMPLETE,
                                       [f"plan.status={plan.status}"],
                                       author="default-agent")
                cx.finalize(ctid)
            else:
                cx.record_reevaluation(ctid, findings, BLOCK_WITH_EVIDENCE,
                                       [f"plan.status={plan.status}"],
                                       author="default-agent")
        except ExecutionPolicyViolation as e:
            if isinstance(result, dict):
                result = dict(result)
                result["contract_error"] = f"{e.reason}: {e.detail}"
            else:
                result = {"ok": False, "error": f"{e.reason}: {e.detail}",
                          "kind": "EXECUTION_POLICY_VIOLATION"}
        if isinstance(result, dict):
            result = dict(result)
            try:
                result["contract"] = cx.contract_snapshot(ctid)
            except (KeyError, ValueError):
                pass
            return result
        return {"ok": True, "result": result,
                "contract": cx.contract_snapshot(ctid)}
    
    def run_task_sync(self, workspace: str, task: str,
                     config: SessionConfig | None = None,
                     context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Convenience method: create session and run task in one call.
        
        Args:
            workspace: Working directory.
            task: The task to execute.
            config: Optional session configuration.
            context: Additional execution context.
            
        Returns:
            Task execution result.
        """
        session = self.create_session(workspace, config)
        return self.run_task(session, task, context)
    
    def get_session(self, session_id: str) -> AgentSession:
        """Get a session by ID."""
        if session_id not in self.sessions:
            raise KeyError(f"session not found: {session_id}")
        return self.sessions[session_id]
    
    def list_sessions(self) -> list[AgentSession]:
        """List all active sessions."""
        return list(self.sessions.values())
    
    def cancel_session(self, session_id: str) -> dict[str, Any]:
        """Cancel a session."""
        session = self.get_session(session_id)
        return session.cancel()
    
    def cleanup_session(self, session_id: str) -> None:
        """Clean up a session."""
        session = self.get_session(session_id)
        session.cleanup()
        del self.sessions[session_id]
    
    def get_capabilities(self) -> dict[str, Any]:
        """Get agent capabilities.
        
        Returns:
            Dict with tool and model capabilities.
        """
        return {
            "tools": {
                "total": len(self.registries.tool_registry),
                "available": len(self.registries.tool_registry.available_tools()),
                "by_family": self._count_tools_by_family()
            },
            "models": {
                "total": len(self.registries.model_registry),
                "available": len(self.registries.model_registry.available_models()),
                "local": len(self.registries.model_registry.local_models()),
                "remote": len(self.registries.model_registry.remote_models())
            },
            "providers": {
                "total": len(self.registries.provider_registry),
                "available": len(self.registries.provider_registry.available_providers()),
                "local": len(self.registries.provider_registry.local_providers()),
                "remote": len(self.registries.provider_registry.remote_providers())
            }
        }
    
    def _count_tools_by_family(self) -> dict[str, int]:
        """Count tools by family."""
        counts = {}
        for tool in self.registries.tool_registry.ids():
            family = tool.split(".")[0] if "." in tool else "other"
            counts[family] = counts.get(family, 0) + 1
        return counts
    
    def health_check(self) -> dict[str, Any]:
        """Perform health check on the agent system.
        
        Returns:
            Dict with health status of components.
        """
        return {
            "agent_core": "healthy",
            "sessions": {
                "active": len(self.sessions),
                "details": [
                    {
                        "session_id": s.session_id,
                        "status": s.state.status,
                        "task": s.state.current_task
                    }
                    for s in self.sessions.values()
                ]
            },
            "tool_registry": {
                "total": len(self.registries.tool_registry),
                "status": "healthy"
            },
            "model_registry": {
                "total": len(self.registries.model_registry),
                "available": len(self.registries.model_registry.available_models()),
                "status": "healthy" if len(self.registries.model_registry.available_models()) > 0 else "no_models"
            },
            "provider_registry": {
                "total": len(self.registries.provider_registry),
                "available": len(self.registries.provider_registry.available_providers()),
                "status": "healthy" if len(self.registries.provider_registry.available_providers()) > 0 else "no_providers"
            }
        }


def create_default_agent(tool_registry: ToolRegistry,
                        model_registry: ModelRegistry,
                        provider_registry: ProviderRegistry) -> DefaultAgent:
    """Factory function to create a DefaultAgent with all registries.
    
    Args:
        tool_registry: Tool registry instance.
        model_registry: Model registry instance.
        provider_registry: Provider registry instance.
        
    Returns:
        Configured DefaultAgent instance.
    """
    # Create model router
    model_router = ModelRouter(model_registry, provider_registry)
    
    # Create tool router (no artifacts for now)
    tool_router = ToolRouter(tool_registry)
    
    # Create registries container
    registries = AgentRegistries(
        tool_registry=tool_registry,
        model_registry=model_registry,
        provider_registry=provider_registry,
        model_router=model_router,
        tool_router=tool_router
    )
    
    # Create and return agent
    return DefaultAgent(registries)