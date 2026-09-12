"""Role-based model routing (v0.3, real).

Roles: planner / coder / reviewer / general. Each resolves to a configured
model name; all roles may share one model (low-resource friendly, and the
bridge always logs which model actually handled each role — never pretends).
Single-model operation remains fully functional.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Route:
    role: str
    model: str
    shared_with: list[str]
    reason: str = ""


class RoleRouter:
    def __init__(self, default_model: str, roles: Any = None):
        self.default_model = default_model
        mapping = {"planner": "", "coder": "", "reviewer": "", "general": ""}
        if roles is not None:
            for r in mapping:
                mapping[r] = getattr(roles, r, "") or ""
        self.mapping = mapping

    def model_for(self, role: str) -> str:
        return self.mapping.get(role, "") or self.default_model

    def route(self, role: str) -> Route:
        model = self.model_for(role)
        shared = [r for r, m in self.mapping.items()
                  if r != role and (m or self.default_model) == model]
        reason = ("shared model for all roles (low-resource mode)"
                  if len(shared) == 3 else f"role '{role}' model")
        return Route(role=role, model=model, shared_with=shared, reason=reason)

    def phase_role(self, mode: str, action_name: str = "") -> str:
        """Which role owns one loop step (inspection=planner, mutation=coder)."""
        from protocol import READ_ONLY_ACTIONS
        if mode == "plan":
            return "planner"
        if action_name in READ_ONLY_ACTIONS or not action_name:
            return "planner" if mode == "hybrid" else "general"
        return "coder"

    def summary(self) -> dict[str, Any]:
        return {"default": self.default_model,
                "roles": {r: self.model_for(r) for r in self.mapping}}


# v0.2 name compat (single-model behaviour preserved)
class SingleModelRouter(RoleRouter):
    def __init__(self, default_model: str, planner_model: str = "",
                 coder_model: str = "", reviewer_model: str = "",
                 general_model: str = ""):
        class _R:
            pass
        r = _R()
        r.planner, r.coder, r.reviewer, r.general = (
            planner_model, coder_model, reviewer_model, general_model)
        super().__init__(default_model, r)
