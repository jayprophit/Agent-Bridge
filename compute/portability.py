"""Portability & disaster recovery (V2 H08, AT-28).

H08 requirement: Migrate Aetherius to another machine/cloud provider without
losing Genesis identity, history, work. Document reversible cloud offboarding.

Key rules:
- Export/import: canonical tasks, agent IDs, knowledge/provenance, artifacts,
  provider metadata, policies, audit records (§3)
- No hidden provider-specific IDs become permanent project identities (§3)
- Reversible offboarding: revoke keys/tokens, disable workers, remove
  resources/permissions, confirm deletion (§4)
- Recovery material stored only in trusted user-controlled systems (§5)

This module provides:
- AetheriusStatePackage: the exportable, portable state container
- OffboardingPlan: the reversible cloud offboarding sequence
- Export/import with integrity verification (hash-checked)
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


# --- portable state package (§3) -------------------------------------------------

# State categories that must be exportable (§3)
STATE_CATEGORIES = (
    "canonical_tasks",       # task graph + task records
    "agent_ids",             # worker/agent identity (NOT provider IDs)
    "knowledge_provenance",  # knowledge index + claim registry
    "artifacts",             # generated files/reports
    "provider_metadata",     # provider config (NEVER credentials)
    "policies",              # invariants + cost policies
    "audit_records",         # append-only audit trail
    "skills",                # published skill registry
)


@dataclass
class StateSection:
    """One section of the portable state package."""
    category: str
    data: dict[str, Any]
    sha256: str = ""
    item_count: int = 0

    def __post_init__(self) -> None:
        if self.category not in STATE_CATEGORIES:
            raise ValueError(f"unknown state category: {self.category}")
        self.item_count = len(self.data) if isinstance(self.data, dict) else 0
        if not self.sha256:
            self.sha256 = self._compute_hash()

    def _compute_hash(self) -> str:
        raw = json.dumps(self.data, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "data": self.data,
            "sha256": self.sha256,
            "item_count": self.item_count,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "StateSection":
        return cls(
            category=d["category"],
            data=d["data"],
            sha256=d.get("sha256", ""),
            item_count=d.get("item_count", 0),
        )

    def verify_integrity(self) -> bool:
        """Verify the section data matches its stored hash."""
        return self._compute_hash() == self.sha256


class AetheriusStatePackage:
    """The exportable, portable Aetherius-owned state (§3, §5).

    This is what gets backed up, migrated, and restored. It contains
    ONLY Aetherius-owned data — never plaintext credentials, never
    provider master keys, never personal secrets.
    """

    def __init__(self, version: str = "1.0.0") -> None:
        self.version = version
        self.created_at: float = time.time()
        self.sections: dict[str, StateSection] = {}

    def add_section(self, category: str, data: dict[str, Any]) -> StateSection:
        """Add a state section (hash-verified)."""
        section = StateSection(category=category, data=data)
        self.sections[category] = section
        return section

    def get_section(self, category: str) -> Optional[StateSection]:
        return self.sections.get(category)

    def verify_all_integrity(self) -> dict[str, bool]:
        """Verify integrity of ALL sections."""
        return {cat: sec.verify_integrity()
                for cat, sec in self.sections.items()}

    def export(self, path: Path) -> Path:
        """Export the package to a single JSON file (§3)."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        package = {
            "format": "aetherius-state-package",
            "version": self.version,
            "created_at": self.created_at,
            "categories": list(STATE_CATEGORIES),
            "sections": {cat: sec.to_dict()
                         for cat, sec in self.sections.items()},
        }
        path.write_text(json.dumps(package, indent=1), encoding="utf-8")
        return path

    @classmethod
    def import_package(cls, path: Path) -> "AetheriusStatePackage":
        """Import a package from disk, verifying integrity (§3)."""
        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("format") != "aetherius-state-package":
            raise ValueError(f"not an Aetherius state package: {data.get('format')}")
        pkg = cls(version=data.get("version", "1.0.0"))
        pkg.created_at = data.get("created_at", time.time())
        for cat, sec_dict in data.get("sections", {}).items():
            section = StateSection.from_dict(sec_dict)
            if not section.verify_integrity():
                raise ValueError(
                    f"integrity check failed for section {cat} — "
                    f"package may be corrupt")
            pkg.sections[cat] = section
        return pkg

    def summary(self) -> dict[str, Any]:
        """Honest summary of what's in the package."""
        return {
            "version": self.version,
            "created_at": self.created_at,
            "sections": {
                cat: {"items": sec.item_count, "sha256": sec.sha256[:16]}
                for cat, sec in self.sections.items()
            },
            "missing_categories": [c for c in STATE_CATEGORIES
                                   if c not in self.sections],
        }


# --- offboarding plan (§4) ------------------------------------------------------

class OffboardingStep(str):
    pass


@dataclass
class OffboardingStep:
    """One step in the reversible cloud offboarding sequence (§4)."""
    step_id: str
    description: str
    action_type: str           # "revoke", "disable", "remove", "verify"
    provider: str = ""
    completed: bool = False
    completed_at: Optional[float] = None
    evidence: str = ""
    reversible: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "description": self.description,
            "action_type": self.action_type,
            "provider": self.provider,
            "completed": self.completed,
            "completed_at": self.completed_at,
            "evidence": self.evidence,
            "reversible": self.reversible,
        }


class OffboardingPlan:
    """The reversible cloud offboarding sequence (§4).

    AT-28 acceptance: revoke provider credentials, disable workers, remove
    remote deployment while preserving exportable Aetherius-owned state;
    test restore elsewhere.
    """

    def __init__(self, provider: str = "") -> None:
        self.provider = provider
        self.steps: list[OffboardingStep] = []
        self._build_default_steps()

    def _build_default_steps(self) -> None:
        """Build the default offboarding sequence (§4)."""
        self.steps = [
            OffboardingStep(
                step_id="export-state",
                description="Export Aetherius-owned state package BEFORE offboarding",
                action_type="verify", provider=self.provider),
            OffboardingStep(
                step_id="disable-remote-workers",
                description="Disable all remote workers for this provider",
                action_type="disable", provider=self.provider),
            OffboardingStep(
                step_id="revoke-keys",
                description="Revoke API keys/tokens for this provider",
                action_type="revoke", provider=self.provider),
            OffboardingStep(
                step_id="remove-resources",
                description="Remove cloud resources/deployments",
                action_type="remove", provider=self.provider),
            OffboardingStep(
                step_id="confirm-deletion",
                description="Confirm user-requested data deletion to the extent "
                            "the provider supports it",
                action_type="verify", provider=self.provider),
            OffboardingStep(
                step_id="test-restore",
                description="Test restore of exported state to a clean environment",
                action_type="verify", provider=self.provider),
        ]

    def complete_step(self, step_id: str, evidence: str = "") -> bool:
        """Mark a step as completed with evidence."""
        for s in self.steps:
            if s.step_id == step_id:
                s.completed = True
                s.completed_at = time.time()
                s.evidence = evidence
                return True
        return False

    def is_complete(self) -> bool:
        return all(s.completed for s in self.steps)

    def remaining_steps(self) -> list[OffboardingStep]:
        return [s for s in self.steps if not s.completed]

    def summary(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "total_steps": len(self.steps),
            "completed_steps": len([s for s in self.steps if s.completed]),
            "remaining": [s.step_id for s in self.remaining_steps()],
            "is_complete": self.is_complete(),
        }


# --- provider ID hygiene (§3) ------------------------------------------------------

# Fields that must NOT leak as permanent identity (§3: "avoid hidden
# managed-provider-specific IDs becoming permanent project identities")
_PROVIDER_SPECIFIC_ID_FIELDS = frozenset({
    "openai_org_id", "anthropic_org_id", "groq_org_id",
    "openrouter_account_id", "provider_session_id",
    "managed_deployment_id", "provider_account_uuid",
})


def scrub_provider_ids(data: dict[str, Any]) -> dict[str, Any]:
    """Remove provider-specific IDs from an export (§3).

    Provider-specific IDs are transport details, not Aetherius identity.
    The export contains Aetherius-owned IDs only.
    """
    cleaned = {}
    for key, value in data.items():
        if key in _PROVIDER_SPECIFIC_ID_FIELDS:
            continue  # drop provider-specific ID
        if isinstance(value, dict):
            cleaned[key] = scrub_provider_ids(value)
        elif isinstance(value, list):
            cleaned[key] = [scrub_provider_ids(v) if isinstance(v, dict) else v
                            for v in value]
        else:
            cleaned[key] = value
    return cleaned
