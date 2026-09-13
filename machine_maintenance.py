"""Machine Maintenance / Improvement Manager (v0.9.0).

Reusable, headless-capable Agent Bridge capability for keeping a development
machine HEALTHY, COMPATIBLE, PROJECT-READY and RESOURCE-EFFICIENT.

Design rules (enforced by this module, not by convention alone):
  - ADDITIVE ONLY: reuses Phase 1 registries, never duplicates them.
  - NO import-time side effects; NOTHING mutates on import.
  - Every mutation goes through MaintenancePolicy + a manager execute()
    with dry_run=True by default; OFF mode refuses all mutations.
  - Firmware, drivers, OS upgrades and destructive actions ALWAYS require
    explicit owner approval, in every mode.
  - Trusted sources only (official package managers / vendor releases).
  - History is written to gitignored local storage, never the repo.

Modes: OFF | ASK | AUTO_SAFE | AUTO_MANAGED | PROJECT_READY.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable


# --------------------------------------------------------------------------
# Modes, states, decisions
# --------------------------------------------------------------------------

class MaintenanceMode(str, Enum):
    OFF = "OFF"
    ASK = "ASK"
    AUTO_SAFE = "AUTO_SAFE"
    AUTO_MANAGED = "AUTO_MANAGED"
    PROJECT_READY = "PROJECT_READY"


class HealthState(str, Enum):
    HEALTHY = "HEALTHY"
    OUTDATED_BUT_WORKING = "OUTDATED_BUT_WORKING"
    DEGRADED = "DEGRADED"
    MISCONFIGURED = "MISCONFIGURED"
    PARTIALLY_WORKING = "PARTIALLY_WORKING"
    BROKEN = "BROKEN"
    MISSING = "MISSING"
    INCOMPATIBLE = "INCOMPATIBLE"
    UNVERIFIED = "UNVERIFIED"


class PolicyDecision(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


class ActionKind(str, Enum):
    REPAIR = "REPAIR"
    UPDATE = "UPDATE"
    INSTALL = "INSTALL"
    CONFIGURE = "CONFIGURE"
    SERVICE_RESTART = "SERVICE_RESTART"
    CACHE_CLEANUP = "CACHE_CLEANUP"


# Risk classes that ALWAYS require explicit owner approval.
ALWAYS_REQUIRE_APPROVAL = frozenset({
    "firmware", "bios", "uefi", "driver", "os_upgrade", "boot_config",
    "partition", "disk_format", "wsl_distro_delete", "docker_volume_delete",
    "docker_image_delete", "app_remove", "security_disable", "destructive",
})


@dataclass
class MaintenanceSettings:
    """Conceptual equivalent of machine_maintenance.* user settings."""
    enabled: bool = True
    mode: MaintenanceMode = MaintenanceMode.ASK
    allow_installs: bool = True
    allow_updates: bool = True
    allow_repairs: bool = True
    allow_configuration_changes: bool = True
    allow_cache_cleanup: bool = True
    allow_service_restart: bool = True
    allow_admin_operations: bool = False
    require_driver_approval: bool = True
    require_firmware_approval: bool = True
    require_os_upgrade_approval: bool = True
    require_destructive_approval: bool = True
    prefer_existing_tools: bool = True
    avoid_duplicate_tools: bool = True
    verify_after_change: bool = True
    rollback_when_possible: bool = True

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["mode"] = self.mode.value
        return d


# --------------------------------------------------------------------------
# Findings, plan steps, rollback, history
# --------------------------------------------------------------------------

@dataclass
class CapabilityFinding:
    capability: str = ""
    state: HealthState = HealthState.UNVERIFIED
    evidence: str = ""
    required_by: list[str] = field(default_factory=list)
    root_cause: str = ""
    recommended_action: str = ""


@dataclass
class PlanStep:
    action: ActionKind = ActionKind.REPAIR
    tool: str = ""
    reason: str = ""
    command: list[str] = field(default_factory=list)
    source: str = ""  # winget | pip | uv | npm | cargo | apt | official | none
    risk_class: str = "safe_local"
    admin_required: bool = False
    rollback: str = ""  # rollback command or "" when not available
    verification: str = ""  # how to verify after the change


@dataclass
class RollbackMetadata:
    tool: str = ""
    previous_version: str = ""
    previous_config: str = ""
    previous_path: str = ""
    package_source: str = ""
    command_executed: str = ""
    rollback_command: str = ""
    backup_path: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class AuditRecord:
    timestamp: float = field(default_factory=time.time)
    requested_action: str = ""
    reason: str = ""
    policy_decision: str = ""
    commands: list[str] = field(default_factory=list)
    package_source: str = ""
    previous_state: str = ""
    new_state: str = ""
    verification: str = ""
    failure: str = ""
    rollback_available: bool = False
    admin_used: bool = False
    reboot_required: bool = False


class MaintenanceHistory:
    """Append-only JSONL audit log under gitignored local storage."""

    def __init__(self, path: str | Path | None = None):
        if path is None:
            try:
                from localdirs import local_subdir
                base = Path(local_subdir("maintenance"))
            except Exception:
                base = Path("local") / "maintenance"
            path = base / "history.jsonl"
        self.path = Path(path)

    def record(self, entry: AuditRecord) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(entry)) + "\n")
        return self.path

    def read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        out = []
        with open(self.path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        continue
        return out


# --------------------------------------------------------------------------
# Policy
# --------------------------------------------------------------------------

class MaintenancePolicy:
    """Decides ALLOW / DENY / REQUIRE_APPROVAL for a proposed PlanStep."""

    def __init__(self, settings: MaintenanceSettings | None = None):
        self.settings = settings or MaintenanceSettings()

    def decide(self, step: PlanStep) -> PolicyDecision:
        s = self.settings
        if not s.enabled or s.mode == MaintenanceMode.OFF:
            return PolicyDecision.DENY
        if step.risk_class in ALWAYS_REQUIRE_APPROVAL:
            return PolicyDecision.REQUIRE_APPROVAL
        if "firmware" in step.tool.lower() or "driver" in step.tool.lower():
            return PolicyDecision.REQUIRE_APPROVAL
        if step.admin_required and not s.allow_admin_operations:
            return PolicyDecision.REQUIRE_APPROVAL
        if s.mode == MaintenanceMode.ASK:
            return PolicyDecision.REQUIRE_APPROVAL
        # Gate categories by settings in AUTO_* / PROJECT_READY modes.
        if step.action == ActionKind.INSTALL and not s.allow_installs:
            return PolicyDecision.REQUIRE_APPROVAL
        if step.action == ActionKind.UPDATE and not s.allow_updates:
            return PolicyDecision.REQUIRE_APPROVAL
        if step.action == ActionKind.REPAIR and not s.allow_repairs:
            return PolicyDecision.REQUIRE_APPROVAL
        if step.action == ActionKind.CONFIGURE and not s.allow_configuration_changes:
            return PolicyDecision.REQUIRE_APPROVAL
        if step.action == ActionKind.SERVICE_RESTART and not s.allow_service_restart:
            return PolicyDecision.REQUIRE_APPROVAL
        if step.action == ActionKind.CACHE_CLEANUP and not s.allow_cache_cleanup:
            return PolicyDecision.REQUIRE_APPROVAL
        return PolicyDecision.ALLOW


# --------------------------------------------------------------------------
# Analyzer (reuses Phase 1 registries; read-only)
# --------------------------------------------------------------------------

def _tool_state(tool: Any) -> HealthState:
    """Map a Phase 1 ToolInfo to a HealthState (pure function)."""
    working = bool(getattr(tool, "working", False))
    version = str(getattr(tool, "version", "") or "")
    if working and version:
        return HealthState.HEALTHY
    if working:
        return HealthState.DEGRADED
    if getattr(tool, "executable", ""):
        return HealthState.PARTIALLY_WORKING
    return HealthState.MISSING


class MachineHealthAnalyzer:
    """Read-only analysis over a Phase 1 machine capability snapshot."""

    def __init__(self, machine: Any = None):
        self.machine = machine

    def _ensure_machine(self) -> Any:
        if self.machine is None:
            from machine_capability import discover_machine_capability
            self.machine = discover_machine_capability()
        return self.machine

    def analyze(self, required_by: dict[str, list[str]] | None = None) -> list[CapabilityFinding]:
        machine = self._ensure_machine()
        required_by = required_by or {}
        findings = []
        for tool in getattr(machine, "tools", []) or []:
            name = getattr(tool, "name", "")
            state = _tool_state(tool)
            findings.append(CapabilityFinding(
                capability=name, state=state,
                evidence=str(getattr(tool, "probe_output", "") or "")[:300],
                required_by=list(required_by.get(name, [])),
                root_cause="" if state == HealthState.HEALTHY else "see probe output",
            ))
        return sorted(findings, key=lambda f: f.capability)


# --------------------------------------------------------------------------
# Planner (smallest sufficient set, no duplicates)
# --------------------------------------------------------------------------

TRUSTED_SOURCES = frozenset({"winget", "pip", "uv", "npm", "cargo", "rustup",
                              "dotnet", "apt", "official", "none"})


class MachineImprovementPlanner:
    """Turns findings (+ optional project requirements) into an ordered plan."""

    def plan(self, findings: list[CapabilityFinding],
             project_needs: list[str] | None = None) -> list[PlanStep]:
        project_needs = set(project_needs or [])
        steps: list[PlanStep] = []
        seen: set[str] = set()
        # Only plan for capabilities the project needs (or all if unspecified),
        # skipping healthy ones; dedupe by tool.
        for f in findings:
            if project_needs and f.capability not in project_needs:
                continue
            if f.state == HealthState.HEALTHY:
                continue
            if f.capability in seen:
                continue
            seen.add(f.capability)
            step = self._step_for(f)
            if step is not None:
                steps.append(step)
        # Deterministic order: repairs before installs, then tool name.
        order = {ActionKind.REPAIR: 0, ActionKind.CONFIGURE: 1,
                 ActionKind.SERVICE_RESTART: 2, ActionKind.UPDATE: 3,
                 ActionKind.INSTALL: 4, ActionKind.CACHE_CLEANUP: 5}
        steps.sort(key=lambda s: (order.get(s.action, 9), s.tool))
        return steps

    def _step_for(self, finding: CapabilityFinding) -> PlanStep | None:
        if finding.state == HealthState.MISSING:
            return PlanStep(action=ActionKind.INSTALL, tool=finding.capability,
                            reason=finding.root_cause or "missing capability",
                            source="winget",
                            verification=f"re-probe {finding.capability}")
        if finding.state in (HealthState.BROKEN, HealthState.MISCONFIGURED,
                             HealthState.PARTIALLY_WORKING, HealthState.DEGRADED):
            return PlanStep(action=ActionKind.REPAIR, tool=finding.capability,
                            reason=finding.root_cause or "repair root cause first",
                            source="none",
                            verification=f"functional test {finding.capability}")
        if finding.state == HealthState.OUTDATED_BUT_WORKING:
            return PlanStep(action=ActionKind.UPDATE, tool=finding.capability,
                            reason="update only if security/compat/feature requires it",
                            source="winget",
                            verification=f"re-probe {finding.capability}")
        return None


# --------------------------------------------------------------------------
# Managers (plan = pure; execute = gated, verified)
# --------------------------------------------------------------------------

def _run(cmd: list[str], timeout: float = 300.0) -> dict[str, Any]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout, shell=False)
        return {"ok": r.returncode == 0, "exit_code": r.returncode,
                "stdout": (r.stdout or "")[:2000],
                "stderr": (r.stderr or "")[:2000]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "TIMEOUT"}
    except OSError as e:
        return {"ok": False, "error": f"launch failed: {e}"}


class _BaseManager:
    def __init__(self, policy: MaintenancePolicy | None = None,
                 history: MaintenanceHistory | None = None,
                 runner: Callable[[list[str]], dict[str, Any]] | None = None):
        self.policy = policy or MaintenancePolicy()
        self.history = history or MaintenanceHistory()
        self._runner = runner or _run

    def execute(self, step: PlanStep, dry_run: bool = True) -> dict[str, Any]:
        decision = self.policy.decide(step)
        record = AuditRecord(requested_action=f"{step.action.value}:{step.tool}",
                             reason=step.reason,
                             policy_decision=decision.value,
                             commands=[" ".join(step.command)] if step.command else [],
                             package_source=step.source,
                             rollback_available=bool(step.rollback),
                             admin_used=step.admin_required)
        if decision != PolicyDecision.ALLOW:
            record.failure = "" if decision == PolicyDecision.REQUIRE_APPROVAL \
                else "denied by maintenance policy"
            self.history.record(record)
            return {"ok": False, "decision": decision.value, "dry_run": dry_run,
                    "note": "approval required" if decision == PolicyDecision.REQUIRE_APPROVAL
                            else "denied by policy"}
        if dry_run or not step.command:
            self.history.record(record)
            return {"ok": True, "decision": decision.value, "dry_run": True,
                    "command": step.command}
        if step.source not in TRUSTED_SOURCES:
            record.failure = f"untrusted source: {step.source}"
            self.history.record(record)
            return {"ok": False, "decision": decision.value,
                    "error": f"refused untrusted source: {step.source}"}
        res = self._runner(step.command)
        record.new_state = "ok" if res.get("ok") else "failed"
        record.verification = step.verification
        if not res.get("ok"):
            record.failure = str(res.get("stderr") or res.get("error") or "")[:300]
        self.history.record(record)
        return {"ok": bool(res.get("ok")), "decision": decision.value,
                "dry_run": False, "result": res}


class RepairManager(_BaseManager):
    """Root-cause repairs (PATH, config, services, caches, reinstalls)."""


class UpdateManager(_BaseManager):
    """Compatibility/security/feature-driven updates (never blind latest)."""


class InstallationManager(_BaseManager):
    """Trusted-source installs of genuinely missing tools."""


class ConfigurationManager(_BaseManager):
    """Compiler/SDK/service configuration amendments."""


# --------------------------------------------------------------------------
# Verification (pre/post, disposable artifacts only)
# --------------------------------------------------------------------------

class VerificationManager:
    """Functional checks with disposable artifacts, cleaned up afterwards."""

    def __init__(self, runner: Callable[[list[str]], dict[str, Any]] | None = None):
        self._runner = runner or _run

    def check_tool(self, name: str, probe: list[str]) -> dict[str, Any]:
        res = self._runner(probe)
        return {"tool": name, "ok": bool(res.get("ok")),
                "output": (res.get("stdout") or res.get("stderr") or "")[:300]}

    def verify_plan(self, steps: list[PlanStep]) -> list[dict[str, Any]]:
        results = []
        for step in steps:
            if step.verification.startswith("re-probe "):
                tool = step.verification.split("re-probe ", 1)[1].strip()
                exe = shutil.which(tool)
                results.append({"tool": tool, "ok": bool(exe),
                                "output": exe or "not on PATH"})
            else:
                results.append({"tool": step.tool, "ok": None,
                                "output": f"manual: {step.verification}"})
        return results


# --------------------------------------------------------------------------
# Scheduling contract (no daemon; triggers only)
# --------------------------------------------------------------------------

SUPPORTED_TRIGGERS = ("ON_DEMAND", "ON_PROJECT_OPEN", "ON_BUILD_FAILURE",
                      "ON_HEALTH_SCAN", "PERIODIC_CHECK")


def describe_schedule(trigger: str) -> dict[str, Any]:
    if trigger not in SUPPORTED_TRIGGERS:
        return {"ok": False, "error": f"unknown trigger: {trigger}"}
    return {"ok": True, "trigger": trigger,
            "read_only_checks": True,
            "mutations_governed_by": "MaintenancePolicy"}


# --------------------------------------------------------------------------
# PROJECT_READY flow
# --------------------------------------------------------------------------

def prepare_project(workspace: str,
                    settings: MaintenanceSettings | None = None,
                    machine: Any = None,
                    dry_run: bool = True) -> dict[str, Any]:
    """Detect project needs, diff against capabilities, plan smallest fix set.

    Never mutates when dry_run=True (default) or when policy denies.
    """
    from project_detector import inspect_project
    from project_model import build_project_model

    settings = settings or MaintenanceSettings(mode=MaintenanceMode.PROJECT_READY)
    policy = MaintenancePolicy(settings)
    profile = inspect_project(workspace)
    model = build_project_model(profile)
    needed: set[str] = set()
    for comp in model.components:
        needed.update(comp.languages)
    analyzer = MachineHealthAnalyzer(machine)
    if machine is None:
        # Read-only scan; callers may inject a cached snapshot instead.
        analyzer._ensure_machine()
    findings = analyzer.analyze()
    planner = MachineImprovementPlanner()
    steps = planner.plan(findings, sorted(needed))
    allowed = [s for s in steps if policy.decide(s) == PolicyDecision.ALLOW]
    return {"workspace": workspace,
            "project_languages": sorted(needed),
            "findings": [asdict(f) for f in findings if f.capability in needed],
            "plan": [asdict(s) for s in steps],
            "executable_now": [asdict(s) for s in allowed] if not dry_run else [],
            "dry_run": dry_run,
            "mode": settings.mode.value}
