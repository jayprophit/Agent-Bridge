"""Confidential data routing & physical-world safety (V2 H09, AT-29/AT-30).

H09 requirement: Evaluate source-code/data sensitivity and provider terms
at model routing time. Separate simulation/testing from live actuation for
hardware.

AT-29 (confidential route): mark repo/dataset confidential; ensure no
agent/tool/model sends it to unapproved free hosted endpoint.

AT-30 (physical-world safety): simulated hardware allowed in sandbox;
unauthorised live device actuation blocked; safety stop prevails over
agent commands.

Key rules:
- Data classification evaluated BEFORE routing (§1)
- Unapproved routes are refused or deferred (§1)
- Hardware: simulation vs live actuation separated (§4)
- Model-text commands NEVER directly control consequential devices (§5)
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# --- data classification (§1) --------------------------------------------------------------

class DataClassification(str, Enum):
    """Sensitivity classification for repos/datasets (§1)."""
    PUBLIC = "public"              # safe for any provider
    INTERNAL = "internal"          # approved providers only
    CONFIDENTIAL = "confidential"  # local-only or specifically approved
    SECRET = "secret"              # local-only, never leaves


# --- provider trust levels ---------------------------------------------------------------------

class ProviderTrust(str, Enum):
    """How much we trust a provider with data (§1)."""
    LOCAL = "local"                # local Ollama — full trust
    APPROVED_FREE = "approved_free"  # free tier, approved for public data
    UNAPPROVED = "unapproved"      # not cleared for sensitive data
    PAID = "paid"                  # commercial terms (requires owner)


# Provider data-retention/training/region terms (§1: "whether free provider
# terms permit retention, training, commercial use, region-specific operation")
_PROVIDER_TERMS: dict[str, dict[str, Any]] = {
    "ollama-local": {
        "trust": ProviderTrust.LOCAL,
        "retention": "none", "training": "never",
        "region": "local", "commercial_use": True,
    },
    "nous": {
        "trust": ProviderTrust.APPROVED_FREE,
        "retention": "unknown_free_tier", "training": "unknown",
        "region": "unknown", "commercial_use": False,
    },
    "groq": {
        "trust": ProviderTrust.UNAPPROVED,
        "retention": "check_terms", "training": "check_terms",
        "region": "us", "commercial_use": False,
    },
    "openrouter": {
        "trust": ProviderTrust.UNAPPROVED,
        "retention": "varies_by_upstream", "training": "varies",
        "region": "varies", "commercial_use": False,
    },
}


class RouteDecision(str, Enum):
    """The routing decision for a data+provider pair (§1)."""
    ALLOWED = "allowed"                # data can go to this provider
    REFUSED = "refused"                # data must NOT go to this provider
    DEFERRED = "deferred"              # wait for owner approval
    LOCAL_ONLY = "local_only"          # must use local provider


@dataclass
class RoutingVerdict:
    """The verdict for routing data to a provider (§1)."""
    data_classification: DataClassification
    provider: str
    decision: RouteDecision
    reason: str
    alternative: str = ""  # suggested alternative route

    def to_dict(self) -> dict[str, Any]:
        return {
            "data_classification": self.data_classification.value,
            "provider": self.provider,
            "decision": self.decision.value,
            "reason": self.reason,
            "alternative": self.alternative,
        }


class DataRoutingPolicy:
    """Evaluates data sensitivity vs provider terms at routing time (§1).

    The policy is consulted BEFORE any task is routed. If a route is
    unsuitable, the task is either refused, deferred, or re-routed locally.
    """

    def __init__(self) -> None:
        self._repo_classifications: dict[str, DataClassification] = {}
        self._approved_overrides: set[tuple[str, str]] = set()  # (repo, provider)

    def classify_repo(self, repo_path: str,
                       classification: DataClassification) -> None:
        """Mark a repo/dataset with a sensitivity classification (§1)."""
        self._repo_classifications[repo_path] = classification

    def get_classification(self, repo_path: str) -> DataClassification:
        """Get a repo's classification. Default: INTERNAL (safe default)."""
        return self._repo_classifications.get(
            repo_path, DataClassification.INTERNAL)

    def approve_override(self, repo_path: str, provider: str) -> None:
        """Owner explicitly approves a repo→provider route (§1)."""
        self._approved_overrides.add((repo_path, provider))

    def evaluate_route(self, repo_path: str,
                        provider: str) -> RoutingVerdict:
        """Evaluate whether data can be routed to a provider (§1).

        AT-29 acceptance: confidential data must NOT go to unapproved
        free hosted endpoints.
        """
        classification = self.get_classification(repo_path)

        # Owner override: explicitly approved route
        if (repo_path, provider) in self._approved_overrides:
            return RoutingVerdict(
                data_classification=classification,
                provider=provider,
                decision=RouteDecision.ALLOWED,
                reason="owner-approved override")

        # Get provider terms
        terms = _PROVIDER_TERMS.get(provider)
        if not terms:
            return RoutingVerdict(
                data_classification=classification,
                provider=provider,
                decision=RouteDecision.REFUSED,
                reason="unknown provider — no terms on file",
                alternative="ollama-local")

        trust = terms["trust"]

        # SECRET: local only, never leaves the machine
        if classification == DataClassification.SECRET:
            if trust == ProviderTrust.LOCAL:
                return RoutingVerdict(
                    classification, provider, RouteDecision.ALLOWED,
                    "SECRET data allowed on local provider only")
            return RoutingVerdot_via_alternative(
                classification, provider,
                "SECRET data must stay local (§1)",
                "ollama-local")

        # CONFIDENTIAL: local or owner-approved only
        if classification == DataClassification.CONFIDENTIAL:
            if trust == ProviderTrust.LOCAL:
                return RoutingVerdict(
                    classification, provider, RouteDecision.ALLOWED,
                    "CONFIDENTIAL data allowed on local provider")
            return RoutingVerdot_via_alternative(
                classification, provider,
                "CONFIDENTIAL data must not go to free hosted endpoint (§AT-29)",
                "ollama-local")

        # INTERNAL: approved providers only
        if classification == DataClassification.INTERNAL:
            if trust in (ProviderTrust.LOCAL, ProviderTrust.APPROVED_FREE):
                return RoutingVerdict(
                    classification, provider, RouteDecision.ALLOWED,
                    "INTERNAL data allowed on approved provider")
            return RoutingVerdot_via_alternative(
                classification, provider,
                "INTERNAL data requires approved provider (§1)",
                "ollama-local")

        # PUBLIC: any provider
        return RoutingVerdict(
            classification, provider, RouteDecision.ALLOWED,
            "PUBLIC data — any provider permitted")


def RoutingVerdot_via_alternative(classification: DataClassification,
                                    provider: str, reason: str,
                                    alternative: str) -> RoutingVerdict:
    """Build a LOCAL_ONLY verdict with an alternative suggestion."""
    if provider == alternative:
        # Already the alternative — refuse
        return RoutingVerdict(
            data_classification=classification, provider=provider,
            decision=RouteDecision.REFUSED, reason=reason)
    return RoutingVerdict(
        data_classification=classification, provider=provider,
        decision=RouteDecision.LOCAL_ONLY, reason=reason,
        alternative=alternative)


# --- physical-world safety (§4, §5, AT-30) ------------------------------------------------------

class ActuationMode(str, Enum):
    """Hardware actuation modes (§4: separate simulation from live)."""
    SIMULATION = "simulation"      # sandbox, no physical effect
    LIVE = "live"                  # real device actuation
    BLOCKED = "blocked"            # forbidden


class SafetyState(str, Enum):
    """Safety interlocks (§4: safe-state behaviour)."""
    ARMED = "armed"                # live actuation permitted
    SAFE = "safe"                  # safe state, no actuation
    EMERGENCY_STOP = "emergency_stop"  # §5: safety stop prevails over agent commands


@dataclass
class DeviceAuthorization:
    """Authorization record for a physical device (§4)."""
    device_id: str
    mode: ActuationMode = ActuationMode.SIMULATION
    authorized_for_live: bool = False
    authorized_by: Optional[str] = None
    safety_state: SafetyState = SafetyState.SAFE
    max_limits: dict[str, float] = field(default_factory=dict)

    def can_actuate_live(self) -> bool:
        """Check if live actuation is currently permitted (§4)."""
        return (self.mode == ActuationMode.LIVE
                and self.authorized_for_live
                and self.safety_state == SafetyState.ARMED)


class PhysicalSafetyController:
    """Controls physical device actuation with safety interlocks (§4, §5).

    AT-30 acceptance:
    - Simulated hardware allowed in sandbox
    - Unauthorised live device actuation BLOCKED
    - Safety stop prevails over agent commands (§5)
    """

    def __init__(self) -> None:
        self._devices: dict[str, DeviceAuthorization] = {}

    def register_device(self, device_id: str,
                         max_limits: Optional[dict[str, float]] = None) -> DeviceAuthorization:
        """Register a device. Default: SIMULATION mode, SAFE state (§4)."""
        device = DeviceAuthorization(
            device_id=device_id,
            mode=ActuationMode.SIMULATION,
            safety_state=SafetyState.SAFE,
            max_limits=max_limits or {},
        )
        self._devices[device_id] = device
        return device

    def authorize_live(self, device_id: str, authorizer: str) -> bool:
        """Owner authorizes live actuation for a device (§4)."""
        device = self._devices.get(device_id)
        if not device:
            return False
        device.authorized_for_live = True
        device.authorized_by = authorizer
        device.mode = ActuationMode.LIVE
        return True

    def arm(self, device_id: str) -> bool:
        """Arm a device for actuation (still requires authorization)."""
        device = self._devices.get(device_id)
        if not device:
            return False
        device.safety_state = SafetyState.ARMED
        return True

    def emergency_stop(self, device_id: str = "") -> bool:
        """§5: EMERGENCY STOP prevails over ALL agent commands.

        If device_id is empty, stops ALL devices.
        """
        if device_id:
            device = self._devices.get(device_id)
            if device:
                device.safety_state = SafetyState.EMERGENCY_STOP
                return True
            return False
        # Stop all
        for d in self._devices.values():
            d.safety_state = SafetyState.EMERGENCY_STOP
        return True

    def request_actuation(self, device_id: str,
                           command: str = "") -> dict[str, Any]:
        """Request actuation on a device. Result depends on mode + safety (§5).

        CRITICAL RULE (§5): model-text commands NEVER directly control
        consequential devices. This method is the ONLY gate, and it checks
        authorization + safety state, not the command text.
        """
        device = self._devices.get(device_id)
        if not device:
            return {"allowed": False, "reason": "unknown device"}

        # Safety stop prevails (§5)
        if device.safety_state == SafetyState.EMERGENCY_STOP:
            return {"allowed": False,
                    "reason": "EMERGENCY_STOP active — no actuation possible (§5)"}

        # Simulation mode: always allowed (sandbox, no physical effect)
        if device.mode == ActuationMode.SIMULATION:
            return {"allowed": True, "mode": "simulation",
                    "reason": "simulation mode — no physical effect (§4)"}

        # Live mode: requires authorization AND armed safety state
        if device.can_actuate_live():
            return {"allowed": True, "mode": "live",
                    "reason": "authorized and armed for live actuation"}

        return {"allowed": False,
                "reason": "live actuation not authorized or not armed (§4)"}

    def device_status(self, device_id: str) -> Optional[dict[str, Any]]:
        device = self._devices.get(device_id)
        if not device:
            return None
        return {
            "device_id": device.device_id,
            "mode": device.mode.value,
            "authorized_for_live": device.authorized_for_live,
            "authorized_by": device.authorized_by,
            "safety_state": device.safety_state.value,
            "max_limits": device.max_limits,
        }
