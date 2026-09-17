"""Genesis integration contracts (Phase 2 preparation, not implementation).

Defines the clean interfaces by which Genesis becomes the persistent
logical AI above Agent Bridge WITHOUT merging ownership boundaries:

  USER -> GENESIS (identity/state/memory) -> AGENT BRIDGE (execution,
  policy, tools, environments) -> MODELS / WORKERS / COMPUTE / DEVICES.

Genesis identity/state must never depend on one vendor model. Native
Genesis workers are first-class participants, never disposable plugins.
Contracts only; no runtime behavior here. Additive only.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any

# Import avatar interface from genesis_avatar
from genesis_avatar import (
    AvatarUIMode,
    AvatarState,
    AvatarCapabilities,
    AvatarConfig,
    AvatarBinding,
    AvatarInterface,
)


@dataclass
class GenesisIdentity:
    """Stable logical identity, independent of underlying models."""
    genesis_id: str = ""
    display_name: str = "Genesis"
    created_at: str = ""
    active_model: str = ""
    model_history: list[str] = field(default_factory=list)

    def rotate_model(self, new_model: str) -> dict[str, Any]:
        previous = self.active_model
        if new_model and new_model != previous:
            if previous:
                self.model_history.append(previous)
            self.active_model = new_model
        return {"genesis_id": self.genesis_id, "active_model": self.active_model,
                "previous": previous, "identity_preserved": True}

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GenesisSession:
    session_id: str = ""
    genesis_id: str = ""
    bridge_session_id: str = ""
    objective: str = ""
    memory_refs: list[str] = field(default_factory=list)
    state: str = "OPEN"


class GenesisMemory(ABC):
    """Meaning/origin/lineage/permissions/retention/provenance. Not a cache."""

    @abstractmethod
    def remember(self, entry: dict[str, Any]) -> str: ...

    @abstractmethod
    def recall(self, query: str, limit: int = 10) -> list[dict[str, Any]]: ...


class GenesisBridge(ABC):
    """The narrow interface Genesis uses to drive Agent Bridge."""

    @abstractmethod
    def submit_objective(self, objective: str, budget: dict[str, Any] | None = None) -> str: ...

    @abstractmethod
    def delegate(self, handoff: dict[str, Any]) -> str: ...

    @abstractmethod
    def observe(self, task_id: str) -> dict[str, Any]: ...

    @abstractmethod
    def integrate(self, task_id: str) -> dict[str, Any]: ...


# Re-export avatar types for consumers
__all__ = [
    "GenesisIdentity",
    "GenesisSession",
    "GenesisMemory",
    "GenesisBridge",
    "AvatarUIMode",
    "AvatarState",
    "AvatarCapabilities",
    "AvatarConfig",
    "AvatarBinding",
    "AvatarInterface",
]
