"""Universal ToolRegistry (v0.7). Central capability catalog.

Every record carries the full §1 field set. Statuses are computed by each
adapter's probe() — never advertised from concept alone.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# statuses
AVAILABLE = "AVAILABLE"
UNAVAILABLE = "UNAVAILABLE"
NOT_INSTALLED = "NOT_INSTALLED"
DISABLED = "DISABLED"
DEGRADED = "DEGRADED"
UNSUPPORTED_PLATFORM = "UNSUPPORTED_PLATFORM"
PROVIDER_REQUIRED = "PROVIDER_REQUIRED"
MODEL_REQUIRED = "MODEL_REQUIRED"
ADMIN_REQUIRED = "ADMIN_REQUIRED"

STATUSES = (AVAILABLE, UNAVAILABLE, NOT_INSTALLED, DISABLED, DEGRADED,
            UNSUPPORTED_PLATFORM, PROVIDER_REQUIRED, MODEL_REQUIRED,
            ADMIN_REQUIRED)

# risk classes
READ_ONLY = "READ_ONLY"
SAFE_LOCAL = "SAFE_LOCAL"
MUTATING_LOCAL = "MUTATING_LOCAL"
NETWORK = "NETWORK"
EXTERNAL_ACCOUNT = "EXTERNAL_ACCOUNT"
INSTALL = "INSTALL"
ADMIN = "ADMIN"
DESTRUCTIVE = "DESTRUCTIVE"
PHYSICAL = "PHYSICAL"
UNKNOWN = "UNKNOWN"

RISKS = (READ_ONLY, SAFE_LOCAL, MUTATING_LOCAL, NETWORK, EXTERNAL_ACCOUNT,
         INSTALL, ADMIN, DESTRUCTIVE, PHYSICAL, UNKNOWN)


@dataclass
class ToolRecord:
    tool_id: str
    tool_family: str = ""
    display_name: str = ""
    description: str = ""
    version: str = "0.7.0"
    status: str = UNAVAILABLE
    backend: str = ""
    provider: str = ""
    available: bool = False
    installed: bool = False
    enabled: bool = True
    requires_install: str = ""
    requires_admin: bool = False
    requires_network: str = ""  # "" | LOCAL_MODEL_NETWORK | EXTERNAL_NETWORK
    requires_external_service: str = ""
    requires_model_capability: str = ""
    input_schema: dict = field(default_factory=dict)
    output_schema: dict = field(default_factory=dict)
    risk_class: str = UNKNOWN
    supported_profiles: list = field(default_factory=list)
    supports_auto_approve: bool = False
    supports_cancel: bool = False
    supports_timeout: bool = True
    supports_rollback: bool = False
    supports_audit: bool = True
    supports_streaming: bool = False
    supports_progress: bool = False
    platforms: list = field(default_factory=lambda: ["windows", "linux", "darwin"])
    capability_tags: list = field(default_factory=list)
    limitations: str = ""

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"bad status {self.status!r} for {self.tool_id}")
        if self.risk_class not in RISKS:
            raise ValueError(f"bad risk {self.risk_class!r} for {self.tool_id}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ToolRegistry:
    """ID-keyed registry. Adapters self-register; duplicates rejected."""

    def __init__(self):
        self._tools: dict[str, ToolRecord] = {}
        self._adapters: dict[str, Any] = {}

    def register(self, record: ToolRecord, adapter: Any = None) -> None:
        if not record.tool_id or "." not in record.tool_id:
            raise ValueError(f"tool_id must be namespaced: {record.tool_id!r}")
        if record.tool_id in self._tools:
            raise ValueError(f"duplicate tool_id: {record.tool_id}")
        self._tools[record.tool_id] = record
        if adapter is not None:
            self._adapters[record.tool_id] = adapter

    def get(self, tool_id: str) -> ToolRecord:
        try:
            return self._tools[tool_id]
        except KeyError:
            raise KeyError(f"unknown tool: {tool_id!r}")

    def adapter_for(self, tool_id: str) -> Any:
        try:
            return self._adapters[tool_id]
        except KeyError:
            raise KeyError(f"no adapter registered: {tool_id!r}")

    def ids(self) -> list[str]:
        return sorted(self._tools)

    def __len__(self) -> int:
        return len(self._tools)

    def list(self, family: str = "", status: str = "",
             tag: str = "") -> list[ToolRecord]:
        out = []
        for rec in self._tools.values():
            if family and rec.tool_family != family:
                continue
            if status and rec.status != status:
                continue
            if tag and tag not in rec.capability_tags:
                continue
            out.append(rec)
        return sorted(out, key=lambda r: r.tool_id)

    def search(self, query: str, limit: int = 20) -> list[ToolRecord]:
        words = [w.lower() for w in query.split() if w]
        scored = []
        for rec in self._tools.values():
            hay = f"{rec.tool_id} {rec.display_name} {rec.description} " \
                  f"{' '.join(rec.capability_tags)}".lower()
            score = sum(2 for w in words if w in hay)
            if score:
                scored.append((score, rec))
        scored.sort(key=lambda t: (-t[0], t[1].tool_id))
        return [r for _, r in scored[:limit]]

    def describe(self, tool_id: str) -> dict[str, Any]:
        return self.get(tool_id).to_dict()

    def status_of(self, tool_id: str) -> dict[str, Any]:
        rec = self.get(tool_id)
        return {"tool_id": rec.tool_id, "status": rec.status,
                "available": rec.available, "backend": rec.backend,
                "limitations": rec.limitations}

    def health(self, tool_id: str) -> dict[str, Any]:
        rec = self.get(tool_id)
        adapter = self._adapters.get(tool_id)
        if adapter is None or not hasattr(adapter, "health"):
            return {"tool_id": tool_id, "status": rec.status,
                    "healthy": rec.available}
        try:
            return {"tool_id": tool_id, **adapter.health()}
        except Exception as e:  # noqa: BLE001  (health must never raise)
            return {"tool_id": tool_id, "status": rec.status,
                    "healthy": False, "error": str(e)[:200]}
