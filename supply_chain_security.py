"""Supply-chain security contracts (v0.9.0).

Pre-installation security gate architecture for everything Agent Bridge
may one day acquire externally: skills, MCP servers/tools, plugins,
extensions, packages, repositories, scripts, workflows, adapters,
binaries, installers, model helpers, automation bundles.

Pipeline:
  REQUEST -> DISCOVER -> PROVENANCE -> LICENSE -> SCAN -> SUPPLY-CHAIN
  -> POLICY -> ALLOW/BLOCK -> STAGE -> INSTALL -> VERIFY -> REGISTER.

Locked principle: AUTOMATION POWER REQUIRES PROPORTIONAL VERIFICATION
AND POLICY CONTROL. Popularity, stars, successful install, or AI
recommendation NEVER confer trust.

Scope of THIS module (architecture-mapping, not Phase 4 runtime):
  trust-state machine, scanner adapter contract, permission manifest and
  least-privilege check, supply-chain record, skill registry skeleton,
  MCP inspector, update-review rule. No staging/sandbox execution, no
  bundled scanners, no mutations. Additive only; no import side effects.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


AUTOMATION_PRINCIPLE = (
    "AUTOMATION POWER REQUIRES PROPORTIONAL VERIFICATION AND POLICY CONTROL."
)


class TrustState(str, Enum):
    UNKNOWN = "UNKNOWN"
    DISCOVERED = "DISCOVERED"
    SCANNED = "SCANNED"
    WARNINGS = "WARNINGS"
    BLOCKED = "BLOCKED"
    STAGED = "STAGED"
    VERIFIED = "VERIFIED"
    APPROVED = "APPROVED"
    TRUSTED_VERSION = "TRUSTED_VERSION"
    REVOKED = "REVOKED"


# Allowed transitions (anything else is rejected; trust never jumps).
TRUST_TRANSITIONS: dict[str, tuple[str, ...]] = {
    TrustState.UNKNOWN: (TrustState.DISCOVERED,),
    TrustState.DISCOVERED: (TrustState.SCANNED, TrustState.BLOCKED),
    TrustState.SCANNED: (TrustState.WARNINGS, TrustState.STAGED,
                         TrustState.BLOCKED),
    TrustState.WARNINGS: (TrustState.STAGED, TrustState.BLOCKED),
    TrustState.STAGED: (TrustState.VERIFIED, TrustState.BLOCKED),
    TrustState.VERIFIED: (TrustState.APPROVED, TrustState.BLOCKED),
    TrustState.APPROVED: (TrustState.TRUSTED_VERSION, TrustState.REVOKED),
    TrustState.TRUSTED_VERSION: (TrustState.REVOKED,),
    TrustState.BLOCKED: (),
    TrustState.REVOKED: (),
}


def advance_trust(current: TrustState, nxt: TrustState) -> TrustState:
    if nxt.value not in TRUST_TRANSITIONS[current.value]:
        raise ValueError(f"illegal trust transition: {current} -> {nxt}")
    return nxt


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


FINDING_CATEGORIES: tuple[str, ...] = (
    "PROMPT_INJECTION", "DATA_EXFILTRATION_RISK", "PRIVILEGE_ESCALATION_RISK",
    "DANGEROUS_CODE", "SUPPLY_CHAIN_RISK", "TOOL_POISONING",
    "SUSPICIOUS_NETWORK_BEHAVIOUR", "UNSAFE_INSTALL_INSTRUCTION",
    "UNKNOWN_BINARY", "UNVERIFIED_SOURCE",
)

SEVERITY_ACTION: dict[str, str] = {
    Severity.LOW: "ALLOW",
    Severity.MEDIUM: "REQUIRE_APPROVAL",
    Severity.HIGH: "BLOCK",
    Severity.CRITICAL: "BLOCK",
}


@dataclass
class SecurityFinding:
    category: str = ""
    severity: Severity = Severity.LOW
    evidence: str = ""
    recommended_action: str = ""


class SecurityScannerAdapter(ABC):
    """Generic scanner contract (skills, MCP, code, deps, containers...)."""
    scanner_id: str = ""
    specialises: tuple[str, ...] = ()

    @abstractmethod
    def scan(self, target: dict[str, Any]) -> list[SecurityFinding]: ...


@dataclass
class PermissionManifest:
    component: str = ""
    permissions: tuple[str, ...] = ()


# Least privilege: sensitive permissions default-deny unless policy allows.
SENSITIVE_PERMISSIONS = frozenset({
    "shell.execute", "process.spawn", "admin.request", "secrets.request",
    "filesystem.write", "network.outbound", "screen.control",
    "device.control", "camera.read", "microphone.read",
})


class PermissionPolicy:
    def __init__(self, allowed: set[str] | None = None):
        self.allowed = set(allowed or {"filesystem.read"})

    def check(self, manifest: PermissionManifest) -> dict[str, Any]:
        denied = [p for p in manifest.permissions
                  if p in SENSITIVE_PERMISSIONS and p not in self.allowed]
        if denied:
            return {"component": manifest.component, "decision": "REQUIRE_APPROVAL",
                    "denied": denied}
        unknown = [p for p in manifest.permissions
                   if p not in SENSITIVE_PERMISSIONS and p not in self.allowed]
        if unknown:
            return {"component": manifest.component, "decision": "REQUIRE_APPROVAL",
                    "denied": unknown}
        return {"component": manifest.component, "decision": "ALLOW", "denied": []}


@dataclass
class SupplyChainRecord:
    upstream: str = ""
    canonical_url: str = ""
    version: str = ""
    commit: str = ""
    licence: str = ""
    download_source: str = ""
    checksum: str = ""
    scan_result: str = ""
    install_time: str = ""
    permissions: tuple[str, ...] = ()
    verification_result: str = ""
    update_history: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SkillRecord:
    skill_id: str = ""
    name: str = ""
    version: str = ""
    commit: str = ""
    source: str = ""
    publisher: str = ""
    licence: str = ""
    required_tools: tuple[str, ...] = ()
    required_permissions: tuple[str, ...] = ()
    trust: TrustState = TrustState.UNKNOWN

    def needs_rescan(self, new_version: str, new_commit: str) -> bool:
        """Trust binds to an exact version/commit; anything new rescans."""
        return (new_version != self.version) or (new_commit != self.commit)


class SkillRegistry:
    """Version-pinned trust registry. Popularity never confers trust."""

    def __init__(self):
        self._skills: dict[str, SkillRecord] = {}

    def register(self, record: SkillRecord) -> None:
        self._skills[record.skill_id] = record

    def get(self, skill_id: str) -> SkillRecord | None:
        return self._skills.get(skill_id)

    def set_trust(self, skill_id: str, nxt: TrustState) -> SkillRecord:
        rec = self._skills[skill_id]
        rec.trust = advance_trust(rec.trust, nxt)
        return rec

    def trusted(self, skill_id: str, version: str, commit: str) -> bool:
        rec = self._skills.get(skill_id)
        if rec is None:
            return False
        if rec.trust != TrustState.TRUSTED_VERSION:
            return False
        return not rec.needs_rescan(version, commit)


class MCPInspector:
    """Inspect MCP tool definitions -> BLOCK / SANDBOX / REQUIRE_APPROVAL."""

    RISKY_KEYS = ("shell", "filesystem_write", "network", "secrets",
                  "remote_endpoint", "environment")

    @staticmethod
    def inspect(tool: dict[str, Any]) -> dict[str, Any]:
        flags = [k for k in MCPInspector.RISKY_KEYS if tool.get(k)]
        if tool.get("shell") or tool.get("secrets"):
            return {"tool": tool.get("name", ""), "decision": "BLOCK",
                    "flags": flags}
        if flags:
            return {"tool": tool.get("name", ""), "decision": "SANDBOX",
                    "flags": flags}
        return {"tool": tool.get("name", ""), "decision": "REQUIRE_APPROVAL",
                "flags": flags}


def review_update(old: SupplyChainRecord, new: dict[str, Any]) -> dict[str, Any]:
    """A trusted version does not authorise its updates. Renew on change."""
    changed = []
    if new.get("version") != old.version:
        changed.append("version")
    if set(new.get("permissions", ())) - set(old.permissions):
        changed.append("permissions")
    if set(new.get("endpoints", ())) - set(
            (old.to_dict().get("endpoints", ()) or ())):
        changed.append("endpoints")
    if new.get("dependencies") != old.to_dict().get("dependencies"):
        changed.append("dependencies")
    if new.get("binaries") != old.to_dict().get("binaries"):
        changed.append("binaries")
    if not changed:
        return {"decision": "KEEP_TRUST", "changed": []}
    if "permissions" in changed or "endpoints" in changed:
        return {"decision": "RENEW_APPROVAL", "changed": changed}
    return {"decision": "RESCAN", "changed": changed}


import os as _os
import re as _re


class StaticSkillScanner(SecurityScannerAdapter):
    """Real static checks over a skill directory (no execution).

    Flags: shell exfil patterns, credential reads, broad rm -rf, curl|sh
    installers, embedded secrets, unknown binaries. Deterministic output.
    """
    scanner_id = "static-skill"
    specialises = ("skills",)

    PATTERNS: tuple[tuple[str, str, str], ...] = (
        (r"curl\s+[^|\n]*\|\s*(ba)?sh", "UNSAFE_INSTALL_INSTRUCTION", "HIGH"),
        (r"rm\s+-rf\s+(/|~|\$HOME)", "DANGEROUS_CODE", "HIGH"),
        (r"(sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{16})",
         "UNVERIFIED_SOURCE", "CRITICAL"),
        (r"(passwd|shadow|\.ssh/id_)",
         "DATA_EXFILTRATION_RISK", "MEDIUM"),
        (r"(exfiltrate|phone[_-]?home|keylog)",
         "DATA_EXFILTRATION_RISK", "HIGH"),
    )

    def scan(self, target: dict[str, Any]) -> list[SecurityFinding]:
        root = str(target.get("path", ""))
        findings: list[SecurityFinding] = []
        if not root or not _os.path.isdir(root):
            return [SecurityFinding("UNVERIFIED_SOURCE", Severity.MEDIUM,
                                    "not a directory", "BLOCK")]
        for base, _dirs, files in _os.walk(root):
            for name in files:
                if not name.endswith((".md", ".py", ".sh", ".js", ".json", ".yaml", ".yml")):
                    findings.append(SecurityFinding(
                        "UNKNOWN_BINARY", Severity.LOW,
                        f"unscanned file type: {name}", "REQUIRE_APPROVAL"))
                    continue
                try:
                    with open(_os.path.join(base, name), encoding="utf-8",
                              errors="replace") as f:
                        text = f.read(200000)
                except OSError:
                    continue
                for pattern, category, severity in self.PATTERNS:
                    m = _re.search(pattern, text)
                    if m:
                        findings.append(SecurityFinding(
                            category, Severity(severity),
                            f"{name}: {m.group(0)[:80]}",
                            "BLOCK" if severity in ("HIGH", "CRITICAL")
                            else "REQUIRE_APPROVAL"))
        return findings


PIPELINE_STAGES: tuple[str, ...] = (
    "REQUEST", "DISCOVER", "PROVENANCE", "LICENSE", "SCAN", "SUPPLY_CHAIN",
    "POLICY", "ALLOW_OR_BLOCK", "STAGE", "INSTALL", "VERIFY", "REGISTER",
)


def gate_pipeline(candidate: dict[str, Any],
                  scanners: list[SecurityScannerAdapter],
                  policy: PermissionPolicy) -> dict[str, Any]:
    """Run the gate over injected scanners. Pure orchestration, no I/O."""
    findings: list[SecurityFinding] = []
    for scanner in scanners:
        findings.extend(scanner.scan(candidate))
    worst = max((f.severity for f in findings), default=Severity.LOW,
                key=lambda s: ("LOW", "MEDIUM", "HIGH", "CRITICAL").index(s))
    gate = SEVERITY_ACTION[worst]
    manifest = PermissionManifest(
        component=str(candidate.get("id", "")),
        permissions=tuple(candidate.get("permissions", ()) or ()))
    perm = policy.check(manifest)
    if gate == "BLOCK" or perm["decision"] == "REQUIRE_APPROVAL" and worst in (
            Severity.HIGH, Severity.CRITICAL):
        decision = "BLOCK"
    elif perm["decision"] == "REQUIRE_APPROVAL" or gate == "REQUIRE_APPROVAL":
        decision = "REQUIRE_APPROVAL"
    else:
        decision = "ALLOW"
    return {"stages": list(PIPELINE_STAGES), "decision": decision,
            "worst_severity": worst.value,
            "findings": [asdict(f) for f in findings],
            "permission_check": perm}
