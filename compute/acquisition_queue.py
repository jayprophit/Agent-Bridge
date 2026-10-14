"""§7/§11 — External Worker Commissioning Loop + Acquisition Queue.

Every external AI application that shows up on the machine enters as
UNASSESSED.  It only becomes a routable WorkerRecord after it has flowed
through the full pipeline:

    DISCOVER -> LAUNCH -> IDENTIFY_ACCOUNT -> PLAN -> MODELS ->
    QUOTA -> TEST_AGENT_MODE -> VERIFY_RESULT -> REGISTER_CAPABILITY

A shortcut that claims "commissioned" without registered capability is a
false claim (§15).  The queue is append-only and durable so a partial
commissioning survives a power cut (§37) and resumes where it left off.

The runtime imports this lazily (check_invariants calls it, then wires the
result into the invariants snapshot under `unassessed_apps`), so the
constitution can flag stale unassessed apps as §7 violations.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

# --- commissioning stages (§7) -----------------------------------------------
DISCOVERED = "DISCOVERED"
LAUNCHED = "LAUNCHED"
ACCOUNT_IDENTIFIED = "ACCOUNT_IDENTIFIED"
PLAN_DETERMINED = "PLAN_DETERMINED"
MODELS_ENUMERATED = "MODELS_ENUMERATED"
QUOTA_PROFILED = "QUOTA_PROFILED"
AGENT_MODE_TESTED = "AGENT_MODE_TESTED"
BOUNDARY_TASK_SUBMITTED = "BOUNDARY_TASK_SUBMITTED"
RESULT_VERIFIED = "RESULT_VERIFIED"
# only CAPABILITY_REGISTERED makes a worker routable (§2 installed != controllable)
CAPABILITY_REGISTERED = "CAPABILITY_REGISTERED"
REJECTED = "REJECTED"          # e.g. archived upstream, licence-incompatible

FINAL_STATES = {CAPABILITY_REGISTERED, REJECTED}

STAGES = [DISCOVERED, LAUNCHED, ACCOUNT_IDENTIFIED, PLAN_DETERMINED,
          MODELS_ENUMERATED, QUOTA_PROFILED, AGENT_MODE_TESTED,
          BOUNDARY_TASK_SUBMITTED, RESULT_VERIFIED,
          CAPABILITY_REGISTERED, REJECTED]

VERIFICATION_REQUIRED = (BOUNDARY_TASK_SUBMITTED, RESULT_VERIFIED)

# control-channel priority (owner directive 10:08:17)
CONTROL_LEVELS = [
    "native_api",         # highest — A2A, OpenHands agent, CLI
    "mcp_a2a",            # MCP server / A2A
    "cli",                # opencode run, codex exec, goose CLI, aider CLI
    "scripting",          # plugin/extension scripting
    "workspace_files",    # direct write-set access
    "accessibility",      # UIA / AX
    "browser_automation", # web UI
    "mouse_keyboard",     # fallback
]

# resource cost tiers for the governor (§11)
APP_RESOURCE_COST = {
    "electron": "MEDIUM",     # OpenCode/Cursor/Antigravity — ~500MB+
    "web": "LIGHT",           # browser-automation agents
    "cli": "LIGHT",           # goose CLI, codex CLI, aider CLI
    "native": "HEAVY",        # compiled native agents
}


@dataclass
class AppRecord:
    """One discovered candidate AI-agent application (§7)."""
    app_id: str
    source: str = "unknown"                 # desktop-shortcut | start-menu | repo-fork | github-discovery
    name: str = ""
    category: str = "agent-app"
    discovered_at: float = field(default_factory=time.time)
    last_action_at: float = field(default_factory=time.time)
    current_stage: str = DISCOVERED
    control_channel: str = "unknown"
    verification_status: str = "UNCOMMISSIONED"  # §2 honesty gate
    model_requirements: list[str] = field(default_factory=list)
    free_available: bool = False
    quota_observed: dict = field(default_factory=dict)
    agent_mode_confirmed: bool = False
    test_task_id: str = ""
    test_result_evidence: list[str] = field(default_factory=list)
    routable_worker_id: str = ""              # set at CAPABILITY_REGISTERED
    resource_cost: str = "MEDIUM"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "AppRecord":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class AcquisitionQueue:
    """§7: the unassessed AI apps queue.  Append-only, durable."""

    def __init__(self, persistence_path: Optional[str] = None) -> None:
        self._apps: dict[str, AppRecord] = {}
        self._path = Path(persistence_path) if persistence_path else None
        self._load()

    def _load(self) -> None:
        if not self._path or not self._path.exists():
            return
        try:
            for line in self._path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                rec = AppRecord.from_dict(json.loads(line))
                self._apps[rec.app_id] = rec
        except (OSError, json.JSONDecodeError):
            pass   # honest: start empty rather than crash on corrupt trail

    def _persist(self, rec: AppRecord) -> None:
        if not self._path:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self._path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec.to_dict()) + "\n")
        except OSError:
            pass   # §15 honesty: never block the cycle on persistence failure

    def discover(self, app_id: str, **attrs: Any) -> AppRecord:
        """Enter a candidate. Idempotent on app_id (§5 permanent IDs)."""
        if app_id not in self._apps:
            rec = AppRecord(app_id=app_id, **attrs)
        else:
            rec = self._apps[app_id]
            for k, v in attrs.items():
                if hasattr(rec, k):
                    setattr(rec, k, v)
        rec.last_action_at = time.time()
        self._apps[app_id] = rec
        self._persist(rec)
        return rec

    def advance(self, app_id: str, stage: str,
                evidence: Optional[list[str]] = None) -> AppRecord:
        """Move a candidate forward in the pipeline (recorded durably)."""
        rec = self._apps.get(app_id)
        if rec is None:
            raise KeyError(f"unknown app {app_id}")
        if stage not in STAGES:
            raise ValueError(f"unknown stage {stage!r}")
        if rec.current_stage in FINAL_STATES:
            raise ValueError(f"{app_id} is {rec.current_stage} — locked")
        rec.current_stage = stage
        rec.last_action_at = time.time()
        rec.notes.append(f"-> {stage} @ {time.time():.0f}")
        if evidence:
            rec.test_result_evidence.extend(evidence)
        # AGENT_MODE_TESTED with evidence => agent mode confirmed
        if stage == AGENT_MODE_TESTED and evidence:
            rec.agent_mode_confirmed = True
        self._persist(rec)
        return rec

    def register_capability(self, app_id: str, worker_id: str,
                            control_channel: str,
                            free_available: bool) -> AppRecord:
        """§2/§5: promote to a routable worker record."""
        rec = self.advance(app_id, CAPABILITY_REGISTERED)
        rec.verification_status = "AUTOPILOT_READY"
        rec.routable_worker_id = worker_id
        rec.control_channel = control_channel
        rec.free_available = free_available
        rec.last_action_at = time.time()
        self._persist(rec)
        return rec

    def unassessed(self, now: Optional[float] = None) -> list[dict]:
        """Apps not yet in a FINAL state — for the §7 invariant snapshot."""
        now = now or time.time()
        return [{"app_id": r.app_id,
                 "last_action_epoch": r.last_action_at,
                 "stage": r.current_stage,
                 "control_channel": r.control_channel,
                 "free_available": r.free_available,
                 "resource_cost": r.resource_cost}
                for r in self._apps.values()
                if r.current_stage not in FINAL_STATES]

    def ready_workers(self) -> list[dict]:
        """Commissioned workers that are routable (CAPABILITY_REGISTERED)."""
        return [r.to_dict() for r in self._apps.values()
                if r.current_stage == CAPABILITY_REGISTERED]

    def count(self) -> int:
        return len(self._apps)

    def __len__(self) -> int:
        return len(self._apps)
