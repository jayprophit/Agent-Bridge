"""Aetherius Personal + Business Data Fabric - Data Service Registry (§33).

Canonical registry for all personal/business data services.

Stores service metadata WITHOUT secrets. KeePass owns the secret.
This registry owns the reference/policy.

Follows §6 (APPLICATION STATES) and §33 (DATA SERVICE REGISTRY).
"""
import time
import uuid
import json
import logging
import hashlib
import os
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional

logger = logging.getLogger("aetherius.data_fabric")

# === §6: Application States ===

class AppState(Enum):
    PRIMARY = "PRIMARY"
    SECONDARY = "SECONDARY"
    FALLBACK = "FALLBACK"
    MIRROR = "MIRROR"
    SELF_HOSTED = "SELF_HOSTED"
    DECENTRALISED = "DECENTRALISED"
    EVALUATION = "EVALUATION"
    OPTIONAL = "OPTIONAL"
    PAID_DISABLED = "PAID_DISABLED"
    INCOMPATIBLE = "INCOMPATIBLE"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"
    OWNER_ACTION_REQUIRED = "OWNER_ACTION_REQUIRED"
    NOT_INSTALLED = "NOT_INSTALLED"
    INSTALLED = "INSTALLED"
    CONFIGURED = "CONFIGURED"
    VERIFIED = "VERIFIED"


# === §34: Data Classes ===

class DataClass(Enum):
    CREDENTIALS = "CREDENTIALS"
    TWO_FACTOR = "2FA"
    EMAIL = "EMAIL"
    CALENDAR = "CALENDAR"
    CONTACTS = "CONTACTS"
    FILES = "FILES"
    DOCUMENTS = "DOCUMENTS"
    NOTES = "NOTES"
    FINANCE = "FINANCE"
    BUSINESS = "BUSINESS"
    SOCIAL = "SOCIAL"
    MESSAGING = "MESSAGING"
    PHOTOS = "PHOTOS"
    VIDEO = "VIDEO"
    AUDIO = "AUDIO"
    IDENTITY = "IDENTITY"
    LEGAL = "LEGAL"
    HEALTH = "HEALTH"
    PROJECTS = "PROJECTS"
    SOURCE_CODE = "SOURCE_CODE"
    BACKUPS = "BACKUPS"
    RESEARCH = "RESEARCH"
    OTHER_PERSONAL = "OTHER_PERSONAL"

    @classmethod
    def from_string(cls, s: str) -> "DataClass":
        for dc in cls:
            if dc.value == s or dc.name == s:
                return dc
        return cls.OTHER_PERSONAL


# === §3, §6: Source Model ===

class SourceModel(Enum):
    LOCAL = "local"
    HOSTED = "hosted"
    SELF_HOSTED = "self_hosted"
    FEDERATED = "federated"
    PEER_TO_PEER = "peer_to_peer"
    DECENTRALISED = "decentralised"


class SourceType(Enum):
    OPEN_SOURCE = "open_source"
    SOURCE_AVAILABLE = "source_available"
    CLOSED_SOURCE = "closed_source"


# === §33: Data Service Registry Entry ===

@dataclass
class DataServiceEntry:
    """Canonical registry entry for a data service (§33).

    NEVER stores secret values. References credential IDs only.
    """
    service_id: str
    name: str
    category: str
    source_model: SourceModel = SourceModel.LOCAL
    source_type: SourceType = SourceType.OPEN_SOURCE
    pricing: str = "free"  # free, freemium, paid_optional, self_hosted
    state: AppState = AppState.NOT_INSTALLED
    installed_version: Optional[str] = None
    installation_path: Optional[str] = None
    account_required: bool = False
    account_state: str = "NONE"  # NONE, OWNER_ACTION_REQUIRED, CONFIGURED, VERIFIED
    primary_role: str = ""
    data_classes: list = field(default_factory=list)
    privacy_ceiling: str = "PRIVACY_PROJECT"
    encryption: str = "none"
    sync: str = "none"
    backup: str = "none"
    export_formats: list = field(default_factory=list)
    has_api: bool = False
    has_cli: bool = False
    automation_support: bool = False
    agent_support: bool = False
    credential_refs: list = field(default_factory=list)
    storage_location: Optional[str] = None
    backup_policy: dict = field(default_factory=dict)
    health: str = "UNKNOWN"
    last_verified: Optional[float] = None
    evidence: dict = field(default_factory=dict)
    download_source: Optional[str] = None
    installation_group: str = "DESKTOP_LIGHTWEIGHT"
    docker_compose_path: Optional[str] = None
    startup_command: Optional[str] = None
    shutdown_command: Optional[str] = None
    ports: list = field(default_factory=list)
    firewall_required: bool = False
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["source_model"] = self.source_model.value
        d["source_type"] = self.source_type.value
        d["state"] = self.state.value
        return d


# === §33: Data Service Registry ===

class DataServiceRegistry:
    """Canonical registry of all data services (§33).

    Single source of truth for what services exist, their state,
    and what data classes they cover. NEVER stores secrets.
    """

    def __init__(self):
        self._services: dict[str, DataServiceEntry] = {}
        self._data_class_map: dict[str, list[str]] = {}  # data_class -> [service_ids]
        self._category_map: dict[str, list[str]] = {}

    def register(self, entry: DataServiceEntry) -> None:
        """Register a data service (§33)."""
        entry.updated_at = time.time()
        self._services[entry.service_id] = entry
        # Index by data class
        for dc in entry.data_classes:
            if dc not in self._data_class_map:
                self._data_class_map[dc] = []
            if entry.service_id not in self._data_class_map[dc]:
                self._data_class_map[dc].append(entry.service_id)
        # Index by category
        if entry.category not in self._category_map:
            self._category_map[entry.category] = []
        if entry.service_id not in self._category_map[entry.category]:
            self._category_map[entry.category].append(entry.service_id)
        logger.info(f"Registered service: {entry.service_id} ({entry.name}) state={entry.state.value}")

    def get(self, service_id: str) -> Optional[DataServiceEntry]:
        return self._services.get(service_id)

    def set_state(self, service_id: str, state: AppState,
                  installed_version: Optional[str] = None,
                  installation_path: Optional[str] = None) -> bool:
        """Update a service's state (§6, §56 evidence)."""
        entry = self._services.get(service_id)
        if not entry:
            return False
        entry.state = state
        if installed_version:
            entry.installed_version = installed_version
        if installation_path:
            entry.installation_path = installation_path
        entry.updated_at = time.time()
        if state == AppState.VERIFIED:
            entry.last_verified = time.time()
            entry.health = "HEALTHY"
        return True

    def set_account_state(self, service_id: str, account_state: str) -> bool:
        """Update account state (§36)."""
        entry = self._services.get(service_id)
        if not entry:
            return False
        entry.account_state = account_state
        entry.updated_at = time.time()
        return True

    def add_credential_ref(self, service_id: str, credential_ref: str) -> None:
        """Link a service to a credential reference (§8, §42)."""
        entry = self._services.get(service_id)
        if entry and credential_ref not in entry.credential_refs:
            entry.credential_refs.append(credential_ref)

    def services_by_class(self, data_class: str) -> list[DataServiceEntry]:
        """Find services covering a data class (§33, §45)."""
        ids = self._data_class_map.get(data_class, [])
        return [self._services[sid] for sid in ids if sid in self._services]

    def services_by_category(self, category: str) -> list[DataServiceEntry]:
        """Find services by category."""
        ids = self._category_map.get(category, [])
        return [self._services[sid] for sid in ids if sid in self._services]

    def primary_for_class(self, data_class: str) -> Optional[DataServiceEntry]:
        """Get the PRIMARY service for a data class (§45)."""
        services = self.services_by_class(data_class)
        for s in services:
            if s.state == AppState.PRIMARY:
                return s
        return None

    def all_services(self) -> list[DataServiceEntry]:
        return list(self._services.values())

    def to_dict(self) -> dict:
        return {
            "services": {sid: entry.to_dict() for sid, entry in self._services.items()},
            "data_class_index": self._data_class_map,
            "category_index": self._category_map,
        }

    def to_json(self, path: str) -> None:
        """Export registry to JSON (§40 data portability)."""
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)

    @classmethod
    def from_json(cls, path: str) -> "DataServiceRegistry":
        """Load registry from JSON."""
        with open(path, "r") as f:
            data = json.load(f)
        reg = cls()
        for sid, entry_dict in data.get("services", {}).items():
            entry = DataServiceEntry(**{
                k: v for k, v in entry_dict.items()
                if k in DataServiceEntry.__dataclass_fields__
            })
            entry.source_model = SourceModel(entry_dict.get("source_model", "local"))
            entry.source_type = SourceType(entry_dict.get("source_type", "open_source"))
            entry.state = AppState(entry_dict.get("state", "NOT_INSTALLED"))
            reg._services[sid] = entry
        return reg

    def summary(self) -> dict:
        """Return registry summary without secrets (§33)."""
        states = {}
        credential_refs = []
        for s in self._services.values():
            state_val = s.state.value
            states[state_val] = states.get(state_val, 0) + 1
            credential_refs.extend(s.credential_refs)
        return {
            "total_services": len(self._services),
            "by_state": states,
            "data_classes_covered": len(self._data_class_map),
            "categories": len(self._category_map),
            "credential_refs": credential_refs,  # ref IDs only, never secrets
        }
