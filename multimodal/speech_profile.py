"""Replaceable speech backend profile (P21, REQ-p21-speech-profile).

Additive leaf over the multimodal router (multimodal/router.py): describes
what a speech backend can do and under what privacy/deployment/consent
conditions. Reuses router status vocabulary (INSTALLED/NOT_INSTALLED/
AVAILABLE/UNAVAILABLE/UNKNOWN) and presence-only probes. Never a second
router, never a provider system, never an audio application.

Honesty rules (tested):
- PROFILE EXISTS != BACKEND INSTALLED (declared profiles for absent
  backends stay NOT_INSTALLED).
- BACKEND INSTALLED != AUTHORIZED (P25 decides use).
- NOT_INSTALLED != UNSUPPORTED; UNKNOWN != FALSE.
- CLONING SUPPORTED != CONSENT PRESENT; CONSENT REQUIRED != CONSENT
  PRESENT (profiles state requirements, never possession).
- No credential fields exist on the profile (validated).
- Missing backends are never auto-installed, downloaded, or fabricated.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from . import probes
from .router import MODALITIES, STT, TTS

SPEECH_MODALITIES = ("STT", "TTS", "STS")

STATUSES = ("INSTALLED", "NOT_INSTALLED", "AVAILABLE", "UNAVAILABLE", "UNKNOWN")

PROVENANCES = (
    "LOCAL_EMPIRICAL",
    "BACKEND_METADATA",
    "OFFICIAL_DOCUMENTATION",
    "CONFIGURATION",
    "EXTERNAL_REFERENCE",
    "USER_SUPPLIED",
    "UNVERIFIED",
)

# Field names that must never appear on a profile (credential boundary).
BANNED_FIELDS = (
    "api_key", "apikey", "access_token", "token", "password",
    "secret", "private_key", "privatekey", "credential", "credentials",
)


class SpeechProfileError(Exception):
    """Malformed profile or registry violation."""


@dataclass
class SpeechPrivacy:
    """Factual processing metadata. Never a compliance claim."""
    processes_locally: bool | None = None
    network_required: bool | None = None
    retention_known: bool = False
    retention_detail: str = ""

    def validate(self) -> list[str]:
        problems = []
        for name in ("processes_locally", "network_required"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, bool):
                problems.append(f"privacy.{name} must be bool or absent")
        if not isinstance(self.retention_detail, str):
            problems.append("privacy.retention_detail must be text")
        return problems


@dataclass
class SpeechLicence:
    identifier: str = ""
    url: str = ""
    commercial_use: bool | None = None

    def validate(self) -> list[str]:
        problems = []
        if not isinstance(self.identifier, str) or not isinstance(self.url, str):
            problems.append("licence identifier/url must be text")
        if self.commercial_use is not None and not isinstance(self.commercial_use, bool):
            problems.append("licence.commercial_use must be bool or absent")
        return problems


@dataclass
class SpeechBackendProfile:
    """One replaceable speech backend, described — not provided."""
    backend_profile_id: str
    backend_id: str
    version: str = "1.0.0"
    status: str = "UNKNOWN"
    capabilities: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    streaming_in: bool = False
    streaming_out: bool = False
    offline_capable: bool = False
    installed: bool = False
    privacy: SpeechPrivacy = field(default_factory=SpeechPrivacy)
    licence: SpeechLicence = field(default_factory=SpeechLicence)
    consent_required: list[str] = field(default_factory=list)
    provenance: str = "UNVERIFIED"
    evidence_ref: str = ""


def validate_profile(profile: SpeechBackendProfile) -> list[str]:
    """Structural validation. Returns problems (empty = registrable)."""
    problems: list[str] = []
    if not profile.backend_profile_id.strip():
        problems.append("backend_profile_id is required")
    if not profile.backend_id.strip():
        problems.append("backend_id is required")
    if not profile.version.strip():
        problems.append("version is required")
    if profile.status not in STATUSES:
        problems.append(f"status must be one of {STATUSES}")
    for cap in profile.capabilities:
        if cap not in ("STT", "TTS", "STS"):
            problems.append(f"unknown speech capability {cap}")
    for lang in profile.languages:
        if not isinstance(lang, str) or not lang.strip():
            problems.append("languages must be explicit non-empty identifiers")
    for name in ("streaming_in", "streaming_out", "offline_capable", "installed"):
        if not isinstance(getattr(profile, name), bool):
            problems.append(f"{name} must be bool")
    problems.extend(profile.privacy.validate())
    problems.extend(profile.licence.validate())
    for item in profile.consent_required:
        if not isinstance(item, str) or not item.strip():
            problems.append("consent_required must list non-empty feature names")
    if profile.provenance not in PROVENANCES:
        problems.append(f"provenance must be one of {PROVENANCES}")
    # Credential boundary: profile dicts must not smuggle secret fields.
    for key in asdict(profile):
        if key.lower() in BANNED_FIELDS:
            problems.append(f"banned credential field {key}")
    # installed without INSTALLED/AVAILABLE status is incoherent.
    if profile.installed and profile.status not in ("INSTALLED", "AVAILABLE"):
        problems.append("installed backends must report INSTALLED or AVAILABLE")
    return sorted(set(problems))


class SpeechProfileRegistry:
    """Smallest suitable registry: validated profiles, deterministic list."""

    def __init__(self) -> None:
        self._profiles: dict[str, SpeechBackendProfile] = {}

    def register(self, profile: SpeechBackendProfile) -> SpeechBackendProfile:
        problems = validate_profile(profile)
        if problems:
            raise SpeechProfileError(f"invalid speech profile: {'; '.join(problems)}")
        if profile.backend_profile_id in self._profiles:
            existing = self._profiles[profile.backend_profile_id]
            if asdict(existing) == asdict(profile):
                return existing
            raise SpeechProfileError(
                f"conflicting speech profile {profile.backend_profile_id}: versions are immutable")
        self._profiles[profile.backend_profile_id] = profile
        return profile

    def lookup(self, backend_profile_id: str) -> SpeechBackendProfile | None:
        return self._profiles.get(backend_profile_id)

    def list(self) -> list[SpeechBackendProfile]:
        return [self._profiles[k] for k in sorted(self._profiles)]

    def to_dicts(self) -> list[dict[str, Any]]:
        return [asdict(p) for p in self.list()]


def attach_profiles(route: Any, profiles: list[SpeechBackendProfile]) -> dict[str, Any]:
    """Enrich a router ModalityRoute with matching profile facts without
    changing routing behaviour. UNKNOWN when nothing matches."""
    matched = [p for p in profiles if p.backend_id == getattr(route, "backend_id", "")]
    return {
        "modality": getattr(route, "modality", ""),
        "backend_id": getattr(route, "backend_id", ""),
        "status": getattr(route, "status", "UNKNOWN"),
        "reasons": list(getattr(route, "reasons", []) or []),
        "profiles": [asdict(p) for p in matched],
    }


def detect_sapi_profile() -> SpeechBackendProfile:
    """Bounded local detection: list installed Windows SAPI voices only
    (no synthesis, no downloads). Present → INSTALLED offline-capable
    TTS leaf with unknown languages; absent → honest NOT_INSTALLED."""
    probe = probes.probe_sapi_voices()
    if probe.get("present"):
        return SpeechBackendProfile(
            backend_profile_id="sapi-local-tts",
            backend_id="sapi",
            status="INSTALLED",
            capabilities=["TTS"],
            languages=[],
            streaming_in=False,
            streaming_out=False,
            offline_capable=True,
            installed=True,
            privacy=SpeechPrivacy(processes_locally=True, network_required=False),
            licence=SpeechLicence(identifier="OS-bundled"),
            consent_required=[],
            provenance="LOCAL_EMPIRICAL",
            evidence_ref="multimodal.probes.probe_sapi_voices",
        )
    return SpeechBackendProfile(
        backend_profile_id="sapi-local-tts",
        backend_id="sapi",
        status="NOT_INSTALLED",
        capabilities=["TTS"],
        provenance="LOCAL_EMPIRICAL",
        evidence_ref="multimodal.probes.probe_sapi_voices",
    )
