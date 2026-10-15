"""Thin Genesis → Agent Bridge action integration.

Genesis = persistent identity / digital organism
Agent Bridge = external tool/control bus / security authority

This module is the minimal bridge between Genesis's ActionProposal and the
Agent Bridge action intake (POST /v1/actions). It does NOT reimplement
validation, policy, execution, or journaling — those are owned by
actions.py, aether_policy_bridge.py, executor.py, and the session journal.

All Genesis actions pass through:
    Genesis proposal
    → AgentBridgeClient (this module)
    → POST /v1/actions
    → protocol.validate_action
    → authority / policy evaluation (P25)
    → cost policy (£0 guard)
    → execution adapter (executor.py)
    → journal

No direct privileged bypass. Genesis cannot authorize itself.

Derived from: genesis_bridge.py (abstract contracts), client.py (AgentRuntimeClient)
Permanent ID: GENESIS-ACTION-BRIDGE-v1
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from client import AgentRuntimeClient
from genesis_bridge import GenesisIdentity


# ---- Action proposal (Genesis-side contract) ----

@dataclass
class GenesisActionProposal:
    """A Genesis-proposed action, ready for Agent Bridge intake.

    Maps to client.submit_action() fields 1:1. The Agent Bridge, not Genesis,
    decides whether the action is authorized.
    """
    action: str                          # e.g. "shell:bash", "write", "finish"
    resource: str                        # target path or command
    workspace: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    session_id: str = ""
    action_id: str = ""
    principal: Any = None
    owner_mode: str = ""
    approval: str = ""
    interactive: bool = False
    wait_ms: int = 30000

    def to_submit_payload(self) -> dict[str, Any]:
        """Convert to the dict expected by client.submit_action()."""
        return {
            "action_id": self.action_id,
            "action": self.action,
            "resource": self.resource,
            "workspace": self.workspace,
            "session_id": self.session_id,
            "payload": self.payload,
            "principal": self.principal,
            "owner_mode": self.owner_mode,
            "approval": self.approval,
            "interactive": self.interactive,
            "wait_ms": self.wait_ms,
        }


# ---- Thin client (Genesis-side, delegates to existing SDK) ----

class AgentBridgeClient:
    """Thin client: GenesisActionProposal → AgentRuntimeClient.submit_action.

    Does NOT invent an 'authorized' field. Does NOT bypass P25 authority.
    The principal is mapped to the existing 'genesis' principal kind.
    """

    def __init__(self, base: str = "http://127.0.0.1:8471",
                 token: str = "", timeout: int = 30):
        self._runtime = AgentRuntimeClient(base=base, token=token, timeout=timeout)
        self._genesis: Optional[GenesisIdentity] = None

    def bind_identity(self, genesis: GenesisIdentity) -> None:
        """Bind this client to a Genesis identity (principal kind: genesis)."""
        self._genesis = genesis

    def _resolve_principal(self, proposal: GenesisActionProposal) -> Any:
        """Map GenesisActionProposal.principal to existing 'genesis' principal kind.

        If the caller already supplied a principal, use it. Otherwise derive
        from the bound GenesisIdentity (principal kind: 'genesis'). Never
        invents an 'authorized' field.
        """
        if proposal.principal is not None:
            return proposal.principal
        if self._genesis is not None and self._genesis.genesis_id:
            # Map to existing 'genesis' principal kind — do not invent kinds.
            return {"kind": "genesis", "id": self._genesis.genesis_id}
        return None

    def execute(self, proposal: GenesisActionProposal) -> dict[str, Any]:
        """Submit a Genesis action proposal to Agent Bridge.

        POST /v1/actions → protocol.validate_action → P25 authority →
        £0 cost policy → executor.

        Returns the raw Agent Bridge response dict. Never authorizes
        anything on its own — authorization lives in P25/aether_policy_bridge.
        """
        payload = proposal.to_submit_payload()
        payload["principal"] = self._resolve_principal(proposal)
        return self._runtime.submit_action(**payload)

    def status(self, action_id: str) -> dict[str, Any]:
        """Poll the status of a submitted action."""
        return self._runtime.action_status(action_id)
