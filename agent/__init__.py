"""DefaultAgent orchestration system (v0.7). Runtime-owned agent orchestration.

The DefaultAgent is the built-in agent orchestration that makes the runtime
independent of external IDE agents (OpenCode, Devin, etc.). It provides:

- Task understanding and planning
- Model selection via ModelRouter
- Tool discovery and selection
- Step-by-step execution
- Result verification
- Milestone tracking
- Fallback strategies

The reasoning model is replaceable - the orchestration is built into the runtime.
"""
from __future__ import annotations

from agent.default_agent import DefaultAgent
from agent.agent_core import AgentCore
from agent.agent_session import AgentSession
from agent.agent_loop import AgentLoop

__all__ = [
    "DefaultAgent",
    "AgentCore",
    "AgentSession", 
    "AgentLoop",
]