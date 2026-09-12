"""Stable ToolAdapter interface (v0.7). All adapters implement this shape.

Future external plugins implement the same class and register themselves —
no runtime-core modification needed. Adapters can never bypass policy:
the router enforces mode/profile/admin/network/model/owner checks before
execute() is ever called.
"""
from __future__ import annotations

from typing import Any


class ToolAdapter:
    tool_id: str = ""
    family: str = ""

    # -- introspection ------------------------------------------------------
    def probe(self) -> dict[str, Any]:
        """Lightweight availability probe. MUST NOT mutate user data."""
        return {"available": False, "status": "UNAVAILABLE",
                "reason": "not implemented"}

    def describe(self) -> dict[str, Any]:
        from tools.registry import ToolRegistry  # noqa: F401
        return {"tool_id": self.tool_id, "family": self.family}

    def health(self) -> dict[str, Any]:
        p = self.probe()
        return {"healthy": bool(p.get("available")), **p}

    # -- execution ------------------------------------------------------------
    def validate(self, arguments: dict[str, Any]) -> tuple[bool, str]:
        return True, ""

    def execute(self, arguments: dict[str, Any],
                context: dict[str, Any] | None = None) -> dict[str, Any]:
        raise NotImplementedError

    def verify(self, result: dict[str, Any]) -> tuple[bool, str]:
        return bool(result.get("ok", False)), ""

    def cancel(self) -> dict[str, Any]:
        return {"ok": True, "note": "nothing cancellable"}

    def rollback(self, call_id: str) -> dict[str, Any]:
        return {"ok": False, "error": "rollback not supported by this tool"}
