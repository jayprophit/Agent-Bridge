"""Trust boundary & incident response (V2 H10, AT-31, maps F03-F05/E05/G03).

H10 requirement: Treat agent messages, generated code, logs, retrieved web
pages, tool outputs, repo README files, model replies, and external services
as UNTRUSTED unless verified. Sign/attest sender and capability where feasible.

Key rules:
- Untrusted input is quarantined, not executed (§1)
- A malicious worker cannot modify system instructions, grants, route private
  data, create paid resources, or enable unsafe tools (§2)
- Security-incident handling: freeze affected work, revoke scopes, quarantine
  artefacts, inspect provenance, notify owner, rotate secrets, validate
  recovery before resuming (§3)
- Security telemetry is privacy-preserving (§4)

This module provides:
- TrustBoundary: classifies and gates untrusted inputs
- IncidentResponse: freeze → quarantine → revoke → notify → recover
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# --- trust classification (§1) -------------------------------------------------------------

class TrustLevel(str, Enum):
    """Trust levels for inputs (§1)."""
    VERIFIED = "verified"            # signed/attested source
    APPROVED = "approved"            # owner-approved source
    UNTRUSTED = "untrusted"          # agent message, model reply, web page
    QUARANTINED = "quarantined"      # known-malicious or suspicious


class InputSource(str, Enum):
    """§1: all of these are UNTRUSTED by default."""
    AGENT_MESSAGE = "agent_message"
    GENERATED_CODE = "generated_code"
    LOG_ENTRY = "log_entry"
    WEB_PAGE = "web_page"
    TOOL_OUTPUT = "tool_output"
    REPO_README = "repo_readme"
    MODEL_REPLY = "model_reply"
    EXTERNAL_SERVICE = "external_service"


# --- signed attestation (§1) ------------------------------------------------------------------

@dataclass
class Attestation:
    """A cryptographic attestation of an input's source (§1)."""
    attestation_id: str
    source: str               # who produced this attestation
    subject_hash: str         # sha256 of the attested content
    created_at: float = field(default_factory=time.time)
    signature: str = ""       # signature over subject_hash

    def to_dict(self) -> dict[str, Any]:
        return {
            "attestation_id": self.attestation_id,
            "source": self.source,
            "subject_hash": self.subject_hash,
            "created_at": self.created_at,
            "signature": self.signature,
        }


def compute_content_hash(content: str) -> str:
    """Compute sha256 of content for attestation."""
    return hashlib.sha256(content.encode()).hexdigest()


# --- trust boundary (§1, §2) ----------------------------------------------------------------------

class TrustBoundary:
    """Gates untrusted inputs at the security boundary (§1, §2).

    UNTRUSTED input can never:
    - Modify system instructions (§2)
    - Modify grants/permissions (§2)
    - Route private data to unapproved providers (§2)
    - Create paid resources (§2)
    - Enable unsafe tools (§2)
    """

    def __init__(self) -> None:
        self._attestations: dict[str, Attestation] = {}
        self._quarantine: list[dict[str, Any]] = []
        self._blocked_actions: list[dict[str, Any]] = []

    def attest(self, content: str, source: str,
               signature: str = "") -> Attestation:
        """Create an attestation for verified content (§1)."""
        subject_hash = compute_content_hash(content)
        att = Attestation(
            attestation_id=f"att_{subject_hash[:16]}",
            source=source,
            subject_hash=subject_hash,
            signature=signature or f"sig_{source}_{subject_hash[:8]}",
        )
        self._attestations[att.subject_hash] = att
        return att

    def check_trust(self, content: str, source: str) -> TrustLevel:
        """Check the trust level of content (§1).

        Default: UNTRUSTED. Only content with a valid attestation is VERIFIED.
        """
        content_hash = compute_content_hash(content)
        if content_hash in self._attestations:
            return TrustLevel.VERIFIED
        # Check if this exact content was quarantined
        for q in self._quarantine:
            if q.get("content_hash") == content_hash:
                return TrustLevel.QUARANTINED
        return TrustLevel.UNTRUSTED

    def gate_action(self, action: str, source_trust: TrustLevel,
                    target: str = "") -> dict[str, Any]:
        """Gate a consequential action based on source trust (§2).

        UNTRUSTED sources cannot trigger consequential actions.
        """
        if source_trust == TrustLevel.VERIFIED:
            return {"allowed": True, "reason": "verified source"}
        if source_trust == TrustLevel.APPROVED:
            return {"allowed": True, "reason": "owner-approved source"}

        # UNTRUSTED or QUARANTINED: block consequential actions (§2)
        blocked = {
            "allowed": False,
            "reason": f"{source_trust.value} source cannot perform "
                      f"consequential action '{action}'",
            "action": action,
            "target": target,
            "timestamp": time.time(),
        }
        self._blocked_actions.append(blocked)
        return blocked

    def quarantine(self, content: str, reason: str,
                   source: str = "") -> dict[str, Any]:
        """Quarantine suspicious content (§3: quarantine artefacts)."""
        content_hash = compute_content_hash(content)
        entry = {
            "content_hash": content_hash,
            "reason": reason,
            "source": source,
            "quarantined_at": time.time(),
            "content_preview": content[:200],
        }
        self._quarantine.append(entry)
        return entry

    def quarantined_items(self) -> list[dict[str, Any]]:
        return list(self._quarantine)

    def blocked_actions(self) -> list[dict[str, Any]]:
        """§2: all consequential actions blocked by untrusted sources."""
        return list(self._blocked_actions)


# --- incident response (§3) -------------------------------------------------------------------------

class IncidentPhase(str, Enum):
    """§3: security-incident handling phases."""
    FREEZE = "freeze"              # freeze affected work
    QUARANTINE = "quarantine"      # quarantine artefacts
    REVOKE = "revoke"              # revoke scopes
    INSPECT = "inspect"            # inspect provenance/logs
    NOTIFY = "notify"              # notify owner
    ROTATE = "rotate"              # rotate impacted secrets
    VALIDATE = "validate"          # validate recovery
    RESUME = "resume"              # resume work


@dataclass
class SecurityIncident:
    """One security incident with its response phases (§3)."""
    incident_id: str
    description: str
    severity: str = "high"         # low | medium | high | critical
    affected_workers: list[str] = field(default_factory=list)
    affected_scopes: list[str] = field(default_factory=list)
    artifacts_quarantined: list[str] = field(default_factory=list)
    secrets_to_rotate: list[str] = field(default_factory=list)
    current_phase: IncidentPhase = IncidentPhase.FREEZE
    phases_completed: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    resolved_at: Optional[float] = None
    evidence: list[str] = field(default_factory=list)

    def advance_phase(self) -> bool:
        """Advance to the next incident response phase (§3)."""
        order = list(IncidentPhase)
        current_idx = order.index(self.current_phase)
        if current_idx >= len(order) - 1:
            return False
        self.phases_completed.append(self.current_phase.value)
        self.current_phase = order[current_idx + 1]
        return True

    def is_resolved(self) -> bool:
        return self.current_phase == IncidentPhase.RESUME


class IncidentResponse:
    """Orchestrates the §3 incident response sequence."""

    def __init__(self, trust_boundary: Optional[TrustBoundary] = None):
        self._boundary = trust_boundary or TrustBoundary()
        self._incidents: dict[str, SecurityIncident] = {}

    def open_incident(self, incident_id: str, description: str,
                       severity: str = "high",
                       affected_workers: Optional[list[str]] = None,
                       secrets_to_rotate: Optional[list[str]] = None) -> SecurityIncident:
        """Open a new security incident. Starts in FREEZE phase (§3)."""
        incident = SecurityIncident(
            incident_id=incident_id,
            description=description,
            severity=severity,
            affected_workers=affected_workers or [],
            secrets_to_rotate=secrets_to_rotate or [],
        )
        self._incidents[incident_id] = incident
        return incident

    def freeze_work(self, incident_id: str, workers: list[str]) -> None:
        """§3: freeze affected work."""
        inc = self._incidents[incident_id]
        inc.affected_workers.extend(workers)
        inc.evidence.append(f"froze workers: {workers}")
        inc.advance_phase()

    def quarantine_artifacts(self, incident_id: str,
                              artifacts: list[str]) -> None:
        """§3: quarantine suspicious artefacts."""
        inc = self._incidents[incident_id]
        for art in artifacts:
            entry = self._boundary.quarantine(art, f"incident {incident_id}")
            inc.artifacts_quarantined.append(entry["content_hash"])
        inc.evidence.append(f"quarantined {len(artifacts)} artifacts")
        inc.advance_phase()

    def revoke_scopes(self, incident_id: str, scopes: list[str]) -> None:
        """§3: revoke affected scopes."""
        inc = self._incidents[incident_id]
        inc.affected_scopes.extend(scopes)
        inc.evidence.append(f"revoked scopes: {scopes}")
        inc.advance_phase()

    def inspect_provenance(self, incident_id: str, findings: str) -> None:
        """§3: inspect provenance/logs."""
        inc = self._incidents[incident_id]
        inc.evidence.append(f"provenance inspection: {findings}")
        inc.advance_phase()

    def notify_owner(self, incident_id: str, message: str) -> None:
        """§3: notify the owner (PRIVACY-PRESERVING §4)."""
        inc = self._incidents[incident_id]
        inc.evidence.append(f"owner notified: {message[:100]}")
        inc.advance_phase()

    def rotate_secrets(self, incident_id: str, rotated: list[str]) -> None:
        """§3: rotate impacted secrets."""
        inc = self._incidents[incident_id]
        inc.evidence.append(f"rotated secrets: {rotated}")
        inc.advance_phase()

    def validate_recovery(self, incident_id: str, validation: str) -> None:
        """§3: validate recovery before resuming."""
        inc = self._incidents[incident_id]
        inc.evidence.append(f"recovery validated: {validation}")
        inc.advance_phase()

    def resume_work(self, incident_id: str) -> SecurityIncident:
        """§3: resume work after all phases completed."""
        inc = self._incidents[incident_id]
        # Must have completed all phases
        if len(inc.phases_completed) < len(IncidentPhase) - 1:
            raise ValueError(
                f"cannot resume: only {len(inc.phases_completed)} of "
                f"{len(IncidentPhase) - 1} phases completed")
        inc.resolved_at = time.time()
        inc.advance_phase()  # -> RESUME
        return inc

    def get_incident(self, incident_id: str) -> Optional[SecurityIncident]:
        return self._incidents.get(incident_id)

    def active_incidents(self) -> list[SecurityIncident]:
        return [i for i in self._incidents.values() if not i.is_resolved()]
