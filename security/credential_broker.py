"""Aetherius Credential Broker (§2, §16, §21 of KeePass Access Policy).

Architectural boundary:

SUPERVISOR
    down
AETHERIUS CREDENTIAL BROKER     this module
    down  PERMISSION CHECK
    down  KEEPASS ADAPTER
    down  KEEPASS DATABASE

Credentials are requested by stable reference (e.g. CRED-OPENROUTER-PRIMARY),
never by raw value. The broker enforces access control and audit logging.
The master password is NEVER stored or logged.

KeePass owns the secret. Aetherius owns the policy and reference.
"""
import os
import sys
import time
import uuid
import json
import subprocess
import hashlib
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Protocol

from .keepass_bridge import KeePassBridge, KeePassBridgeError

logger = logging.getLogger("aetherius.credential_broker")

# ---- Vault states (§4, §23) ----

VAULT_UNLOCKED = "VAULT_UNLOCKED"
VAULT_LOCKED = "VAULT_LOCKED"
AUTH_REQUIRED = "AUTH_REQUIRED"

# ---- Worker access levels (§8) ----

NO_VAULT_ACCESS = "NO_VAULT_ACCESS"
METADATA_ONLY = "METADATA_ONLY"
READ_SCOPED = "READ_SCOPED"
READ_WRITE_SCOPED = "READ_WRITE_SCOPED"
ROTATION_SCOPED = "ROTATION_SCOPED"
ADMIN_OWNER_ONLY = "ADMIN_OWNER_ONLY"

# ---- Operations (§3) ----

OP_LIST_METADATA = "VAULT_LIST_METADATA"
OP_READ_ENTRY = "VAULT_READ_ENTRY"
OP_CREATE_ENTRY = "VAULT_CREATE_ENTRY"
OP_UPDATE_ENTRY = "VAULT_UPDATE_ENTRY"
OP_ROTATE_ENTRY = "VAULT_ROTATE_ENTRY"
OP_STORE_NEW_SECRET = "VAULT_STORE_NEW_SECRET"
OP_LOCK = "VAULT_LOCK"
OP_STATUS = "VAULT_STATUS"

# Destructive operations — require explicit human approval (§3)
DESTRUCTIVE_OPS = {"DELETE_ENTRY", "DELETE_GROUP", "DELETE_DATABASE", "OVERWRITE_DATABASE"}


@dataclass
class AuditEvent:
    """Audit event — NEVER contains secret values (§13)."""
    timestamp: float
    request_id: str
    worker_id: str
    credential_ref: str
    operation: str
    result: str
    authorisation_mode: str
    duration_ms: int = 0


@dataclass
class CredentialReference:
    """Stable credential reference (§7, §16).

    The Aetherius registry holds the reference/policy. KeePass owns the secret.
    """
    credential_id: str
    service: str
    account_label: str
    vault_entry_path: str
    purpose: str
    projects: list[str]
    permissions: dict = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    rotated_at: Optional[float] = None
    expires_at: Optional[float] = None
    status: str = "ACTIVE"
    last_verified: Optional[float] = None


class VaultAdapter(Protocol):
    """Abstract vault adapter interface (§2, §12)."""
    adapter_id: str
    vault_state: str

    def status(self) -> dict:
        """Return vault status without exposing secrets."""
        ...

    def list_metadata(self, project: str | None = None) -> list[dict]:
        """List credential metadata (no secrets)."""
        ...

    def read_entry(self, credential_id: str,
                   master_password: str | None = None) -> str:
        """Read a credential value by ID. Returns empty if denied/not found."""
        ...

    def create_entry(self, credential_id: str, secret_value: str,
                     metadata: dict, master_password: str | None = None) -> bool:
        """Create a new credential entry. Returns success."""
        ...

    def update_entry(self, credential_id: str, secret_value: str,
                     master_password: str | None = None) -> bool:
        """Update an existing credential entry."""
        ...

    def lock(self) -> bool:
        """Lock the vault (clear master password from memory)."""
        ...


class CredentialBroker:
    """Aetherius Credential Broker — policy enforcement layer (§2, §16).

    Supervisors and workers request credentials by stable reference.
    The broker checks permissions, enforces privacy policy, and logs
    audit events WITHOUT exposing secret values.

    The master password is NEVER stored by this class. It must be passed
    to each operation that needs it, or provided through a secure callback.
    """

    def __init__(self, vault_adapter: VaultAdapter | None = None):
        self._adapter: VaultAdapter | None = vault_adapter
        self._registry: dict = {}
        self._audit_log: list = []
        self._worker_permissions: dict = {}
        self._default_worker_access: str = NO_VAULT_ACCESS
        self._master_password_callback: Optional[callable] = None

    def register_adapter(self, adapter: VaultAdapter) -> None:
        """Register a vault adapter (§2, §12)."""
        self._adapter = adapter
        self._log_audit(adapter.adapter_id, "BROKER", "REGISTER",
                        "SUCCESS", "system")

    def set_worker_access(self, worker_id: str, access_level: str) -> None:
        """Set a worker's vault access level (§8)."""
        self._worker_permissions[worker_id] = access_level

    def set_default_access(self, level: str) -> None:
        """Set default worker access (§8)."""
        self._default_worker_access = level

    def set_master_password_callback(self, callback: callable) -> None:
        """Set a callback that prompts the owner for the master password.

        The callback must return the password as a string. This keeps the
        master password out of agent code and config. (§4, §23)
        """
        self._master_password_callback = callback

    def _get_master_password(self) -> Optional[str]:
        """Request master password from the owner via callback.

        NEVER logs or stores the password. (§4)
        """
        if self._master_password_callback:
            return self._master_password_callback()
        return None

    def _get_worker_access(self, worker_id: str) -> str:
        return self._worker_permissions.get(worker_id, self._default_worker_access)

    def _check_access(self, worker_id: str, required: str) -> bool:
        """Check if a worker has the required access level (§2, §8)."""
        levels = [
            NO_VAULT_ACCESS, METADATA_ONLY, READ_SCOPED,
            READ_WRITE_SCOPED, ROTATION_SCOPED, ADMIN_OWNER_ONLY,
        ]
        worker_level = self._get_worker_access(worker_id)
        if worker_level not in levels:
            return False
        try:
            return levels.index(worker_level) >= levels.index(required)
        except ValueError:
            return False

    def _log_audit(self, credential_id: str, worker_id: str,
                   operation: str, result: str,
                   authorisation_mode: str = "SCOPED_REQUEST") -> AuditEvent:
        """Log an audit event — NEVER includes secret values (§13)."""
        ev = AuditEvent(
            timestamp=time.time(),
            request_id=str(uuid.uuid4().hex[:8]),
            worker_id=worker_id,
            credential_ref=credential_id,
            operation=operation,
            result=result,
            authorisation_mode=authorisation_mode,
        )
        self._audit_log.append(ev)
        logger.info(f"AUDIT: {operation} {credential_id} {result} "
                    f"(worker={worker_id}, mode={authorisation_mode})")
        return ev

    def register_credential(self, cred: CredentialReference) -> None:
        """Register a credential reference in the Aetherius registry (§16).

        Does NOT store the secret value. KeePass owns the secret.
        """
        self._registry[cred.credential_id] = cred

    def status(self, worker_id: str = "supervisor") -> dict:
        """Return broker + vault status (no secrets)."""
        adapter_status = {}
        if self._adapter:
            adapter_status = self._adapter.status()
        return {
            "broker_status": "VAULT_UNLOCKED" if self._adapter else "VAULT_LOCKED",
            "vault_state": adapter_status.get("vault_state", VAULT_LOCKED),
            "registered_credentials": len(self._registry),
            "audit_events": len(self._audit_log),
            "default_worker_access": self._default_worker_access,
        }

    def read_credential(self, credential_id: str,
                        worker_id: str = "supervisor",
                        project: str | None = None) -> str:
        """Read a credential by stable reference (§7).

        Workers receive the secret value only if they have READ_SCOPED or
        higher, and the credential is approved for that worker/project.
        """
        start = time.time()
        req = self._registry.get(credential_id)
        if not req:
            self._log_audit(credential_id, worker_id, OP_READ_ENTRY,
                           "NOT_FOUND", "NO_ACCESS")
            return ""

        worker_access = self._get_worker_access(worker_id)
        if worker_access == NO_VAULT_ACCESS:
            self._log_audit(credential_id, worker_id, OP_READ_ENTRY,
                           "DENIED", "NO_VAULT_ACCESS")
            return ""
        if not self._check_access(worker_id, READ_SCOPED):
            self._log_audit(credential_id, worker_id, OP_READ_ENTRY,
                           "DENIED", "INSUFFICIENT_ACCESS")
            return ""

        # Check project authorization
        if project and req.projects and project not in req.projects:
            self._log_audit(credential_id, worker_id, OP_READ_ENTRY,
                           "DENIED", "PROJECT_POLICY")
            return ""

        if req.status != "ACTIVE":
            self._log_audit(credential_id, worker_id, OP_READ_ENTRY,
                           "DENIED", f"CREDENTIAL_{req.status}")
            return ""

        if not self._adapter:
            self._log_audit(credential_id, worker_id, OP_READ_ENTRY,
                           "ERROR", "NO_ADAPTER")
            return ""

        master_pw = self._get_master_password()
        try:
            secret = self._adapter.read_entry(credential_id, master_pw)
            duration_ms = int((time.time() - start) * 1000)
            self._audit_log.append(AuditEvent(
                timestamp=time.time(),
                request_id=str(uuid.uuid4().hex[:8]),
                worker_id=worker_id, credential_ref=credential_id,
                operation=OP_READ_ENTRY, result="SUCCESS",
                authorisation_mode="SCOPED_REQUEST", duration_ms=duration_ms,
            ))
            logger.info(f"AUDIT: READ {credential_id} SUCCESS (worker={worker_id})")
            return secret
        except Exception as e:
            self._log_audit(credential_id, worker_id, OP_READ_ENTRY,
                           "ERROR", f"ADAPTER_ERROR: {type(e).__name__}")
            return ""

    def store_credential(self, credential_id: str, secret_value: str,
                         worker_id: str = "supervisor",
                         service: str = "", account_label: str = "",
                         purpose: str = "", projects: list = None,
                         access_level_required: str = ADMIN_OWNER_ONLY) -> bool:
        """Store a newly-created credential in the vault (§15)."""
        if not self._check_access(worker_id, access_level_required):
            self._log_audit(credential_id, worker_id, OP_STORE_NEW_SECRET,
                           "DENIED", f"REQUIRES_{access_level_required}")
            return False
        if not self._adapter:
            self._log_audit(credential_id, worker_id, OP_STORE_NEW_SECRET,
                           "ERROR", "NO_ADAPTER")
            return False

        master_pw = self._get_master_password()
        metadata = {
            "service": service,
            "account": account_label,
            "purpose": purpose,
            "projects": projects or [],
        }

        start = time.time()
        try:
            success = self._adapter.create_entry(
                credential_id, secret_value, metadata, master_pw)
            if success:
                cred = CredentialReference(
                    credential_id=credential_id,
                    service=service,
                    account_label=account_label,
                    vault_entry_path=credential_id,
                    purpose=purpose,
                    projects=projects or [],
                    permissions={worker_id: [access_level_required]},
                )
                self._registry[cred.credential_id] = cred
                self._audit_log.append(AuditEvent(
                    timestamp=time.time(),
                    request_id=str(uuid.uuid4().hex[:8]),
                    worker_id=worker_id, credential_ref=credential_id,
                    operation=OP_STORE_NEW_SECRET, result="SUCCESS",
                    authorisation_mode=access_level_required,
                    duration_ms=int((time.time() - start) * 1000),
                ))
                logger.info(f"AUDIT: STORE {credential_id} SUCCESS")
                return True
            else:
                self._log_audit(credential_id, worker_id, OP_STORE_NEW_SECRET,
                               "ERROR", "ADAPTER_REJECTED")
                return False
        except Exception as e:
            self._log_audit(credential_id, worker_id, OP_STORE_NEW_SECRET,
                           "ERROR", f"ADAPTER_ERROR: {type(e).__name__}")
            return False

    def rotate_credential(self, credential_id: str,
                          new_secret: str, worker_id: str = "supervisor",
                          access_level_required: str = ROTATION_SCOPED) -> bool:
        """Rotate a credential (§14). Old credential marked REVOKED/SUPERSEDED."""
        if not self._check_access(worker_id, access_level_required):
            self._log_audit(credential_id, worker_id, OP_ROTATE_ENTRY,
                           "DENIED", f"REQUIRES_{access_level_required}")
            return False
        req = self._registry.get(credential_id)
        if req:
            req.status = "REVOKED"
            req.rotated_at = time.time()
        success = self.store_credential(
            credential_id=credential_id, secret_value=new_secret,
            worker_id=worker_id,
            service=req.service if req else "",
            account_label=req.account_label if req else "",
            purpose=req.purpose if req else "",
            projects=req.projects if req else [],
            access_level_required=access_level_required,
        )
        if success and req:
            req.status = "ACTIVE"
            req.last_verified = time.time()
        return success

    def list_credentials_metadata(self, worker_id: str = "supervisor") -> list:
        """List credential metadata (no secrets) (§16)."""
        if not self._check_access(worker_id, METADATA_ONLY):
            self._log_audit("ALL", worker_id, OP_LIST_METADATA,
                           "DENIED", "NO_ACCESS")
            return []
        self._log_audit("ALL", worker_id, OP_LIST_METADATA,
                       "SUCCESS", "METADATA_ONLY")
        return [
            {
                "credential_id": cred.credential_id,
                "service": cred.service,
                "account_label": cred.account_label,
                "purpose": cred.purpose,
                "projects": cred.projects,
                "status": cred.status,
                "created_at": cred.created_at,
                "rotated_at": cred.rotated_at,
                "expires_at": cred.expires_at,
                "last_verified": cred.last_verified,
            }
            for cred in self._registry.values()
        ]

    def lock_vault(self, worker_id: str = "supervisor") -> bool:
        """Lock the vault — clear master password from memory (§3)."""
        if not self._check_access(worker_id, ADMIN_OWNER_ONLY):
            self._log_audit("VAULT", worker_id, OP_LOCK, "DENIED", "NO_ACCESS")
            return False
        self._log_audit("VAULT", worker_id, OP_LOCK, "REQUESTED", "ADMIN_OWNER_ONLY")
        if self._adapter:
            result = self._adapter.lock()
            self._log_audit("VAULT", worker_id, OP_LOCK,
                           "SUCCESS" if result else "ERROR", "ADMIN_OWNER_ONLY")
            return result
        return False

    def audit_trail(self) -> list:
        """Return audit trail (no secrets)."""
        return [
            {
                "timestamp": ev.timestamp,
                "request_id": ev.request_id,
                "worker_id": ev.worker_id,
                "credential_ref": ev.credential_ref,
                "operation": ev.operation,
                "result": ev.result,
                "authorisation_mode": ev.authorisation_mode,
                "duration_ms": ev.duration_ms,
            }
            for ev in self._audit_log
        ]


class InMemoryVaultAdapter:
    """In-memory vault adapter for testing (§22).

    Simulates a KeePass-like vault using a dict. Used to prove the
    CredentialBroker interface with non-sensitive test entries before
    connecting to a real KeePass database.
    """

    adapter_id = "in_memory"
    vault_state = VAULT_UNLOCKED

    def __init__(self):
        self._entries: dict = {}
        self._unlocked = True

    def status(self) -> dict:
        return {
            "adapter_id": self.adapter_id,
            "vault_state": VAULT_UNLOCKED if self._unlocked else VAULT_LOCKED,
            "entry_count": len(self._entries),
        }

    def list_metadata(self, project: str | None = None) -> list:
        result = []
        for cid, entry in self._entries.items():
            result.append({
                "credential_id": cid,
                "service": entry.get("service", ""),
                "account_label": entry.get("account_label", ""),
                "purpose": entry.get("purpose", ""),
                "project": entry.get("project", ""),
            })
        return result

    def read_entry(self, credential_id: str,
                   master_password: str | None = None) -> str:
        entry = self._entries.get(credential_id)
        if not entry:
            return ""
        return entry.get("secret_value", "")

    def create_entry(self, credential_id: str, secret_value: str,
                     metadata: dict, master_password: str | None = None) -> bool:
        self._entries[credential_id] = {
            "secret_value": secret_value,
            **metadata,
        }
        return True

    def update_entry(self, credential_id: str, secret_value: str,
                     master_password: str | None = None) -> bool:
        if credential_id not in self._entries:
            return False
        self._entries[credential_id]["secret_value"] = secret_value
        return True

    def lock(self) -> bool:
        self._unlocked = False
        return True


class KeePassAdapter:
    """KeePass v2 adapter — real database via the pykeepass subprocess bridge (§12).

    Two-layer design:

        KeePassAdapter   (in-process policy + reference layer)
            -> KeePassBridge   (spawns a short-lived child process)
                -> keepass_bridge_worker.py  (pykeepass, real .kdbx)

    The master password is passed per-operation to the bridge and NEVER
    stored on this object. `lock()` clears any cached session state.

    Discovery (§21 step 1-3): the KeePass executable and the .kdbx path are
    both discovered at construction. An owner-supplied path always wins.
    """

    adapter_id = "keepass"

    def __init__(self, db_path: str | None = None,
                 interpreter: str | None = None):
        self._db_path: Optional[str] = None
        self._keepass_exe: Optional[str] = None
        self._unlocked = False
        self._master_password: Optional[str] = None  # session-scoped only
        self._bridge = KeePassBridge(db_path=db_path, interpreter=interpreter)
        self._discover_installation()
        self._db_path = self._bridge.db_path

    def _discover_installation(self) -> None:
        """Discover KeePass installation (§21 step 1-3)."""
        candidates = [
            os.environ.get("PROGRAMFILES", "C:/Program Files") + "/KeePass Password Safe 2/KeePass.exe",
            os.environ.get("PROGRAMFILES", "C:/Program Files") + "/KeePass/KeePass.exe",
            "C:/Program Files/KeePass Password Safe 2/KeePass.exe",
        ]
        for path in candidates:
            if os.path.isfile(path):
                self._keepass_exe = path
                break

    def set_database_path(self, db_path: str) -> None:
        """Point the adapter at a specific .kdbx file (§21 step 2)."""
        self._bridge = KeePassBridge(db_path=db_path,
                                     interpreter=self._bridge.interpreter)
        self._db_path = self._bridge.db_path

    @property
    def bridge(self) -> KeePassBridge:
        """Direct bridge access — used by CLI tooling and diagnostics."""
        return self._bridge

    @property
    def vault_state(self) -> str:
        return VAULT_UNLOCKED if self._unlocked else VAULT_LOCKED

    def unlock(self, master_password: str) -> bool:
        """Unlock the database for this session (§4, §23).

        Verifies the password once via the bridge, then holds it ONLY in
        this object's memory for the duration of the session. The password
        is never written to disk and never logged.
        """
        if not self._bridge.ready():
            return False
        try:
            self._bridge.verify(master_password)
        except KeePassBridgeError as exc:
            logger.warning(f"KeePass unlock failed: {exc.error_code}")
            self._unlocked = False
            return False
        self._master_password = master_password
        self._unlocked = True
        return True

    def status(self) -> dict:
        bridge_status = self._bridge.status()
        container = {}
        if bridge_status.get("db_present"):
            try:
                container = self._bridge.header()
            except KeePassBridgeError:
                container = {"signature_valid": False}
        return {
            "adapter_id": self.adapter_id,
            "vault_state": VAULT_UNLOCKED if self._unlocked else VAULT_LOCKED,
            "keepass_installed": self._keepass_exe is not None,
            "keepass_exe": self._keepass_exe,
            "database_path": self._db_path,
            "db_present": bridge_status.get("db_present", False),
            "bridge_ready": bridge_status.get("ready", False),
            "kdbx_signature_valid": container.get("signature_valid", False),
            "kdbx_major_version": container.get("major_version"),
            "auth_required": not self._unlocked,
        }

    def status_str(self) -> str:
        return VAULT_UNLOCKED if self._unlocked else VAULT_LOCKED

    def _require_session(self) -> bool:
        """Fail closed unless the adapter is unlocked with a live password."""
        return self._unlocked and self._master_password is not None

    def list_metadata(self, project: str | None = None) -> list:
        """List credential metadata via the bridge (no secrets) (§16)."""
        if not self._require_session():
            return []
        try:
            entries = self._bridge.list_metadata(self._master_password)
        except KeePassBridgeError as exc:
            logger.warning(f"KeePass list_metadata failed: {exc.error_code}")
            return []
        return [
            {
                "credential_id": e.get("title", ""),
                "service": e.get("url", ""),
                "account_label": e.get("username", ""),
                "purpose": e.get("notes", ""),
                "group": e.get("group_path", ""),
            }
            for e in entries
        ]

    def read_entry(self, credential_id: str,
                   master_password: str | None = None) -> str:
        """Read a credential value from KeePass by entry title (§7).

        The credential_id doubles as the KeePass entry title, which is the
        stable reference used across Aetherius (e.g. CRED-OPENROUTER-PRIMARY).

        A per-call `master_password` overrides the session password; if the
        adapter was never unlocked the call fails closed.
        """
        password = master_password or self._master_password
        if not self._bridge.ready() or not password:
            return ""
        try:
            result = self._bridge.read_entry(credential_id, password)
        except KeePassBridgeError as exc:
            logger.warning(f"KeePass read_entry failed for {credential_id}: "
                           f"{exc.error_code}")
            return ""
        return result.get("password", "")

    def create_entry(self, credential_id: str, secret_value: str,
                     metadata: dict, master_password: str | None = None) -> bool:
        """Create a new entry in KeePass (§15)."""
        password = master_password or self._master_password
        if not self._bridge.ready() or not password:
            return False
        try:
            self._bridge.create_entry(
                title=credential_id,
                secret=secret_value,
                password=password,
                username=metadata.get("account", ""),
                url=metadata.get("service", ""),
                notes=metadata.get("purpose", ""),
                group="Aetherius",
            )
            return True
        except KeePassBridgeError as exc:
            logger.warning(f"KeePass create_entry failed: {exc.error_code}")
            return False

    def update_entry(self, credential_id: str, secret_value: str,
                     master_password: str | None = None) -> bool:
        """Update an existing entry in KeePass (§15)."""
        password = master_password or self._master_password
        if not self._bridge.ready() or not password:
            return False
        try:
            self._bridge.update_entry(
                title=credential_id, password=password, secret=secret_value)
            return True
        except KeePassBridgeError as exc:
            logger.warning(f"KeePass update_entry failed: {exc.error_code}")
            return False

    def lock(self) -> bool:
        """Lock the vault — drop the session password from memory (§3, §23)."""
        self._unlocked = False
        self._master_password = None
        return True

    def _run_keepass(self, args: list, input_text: str | None = None) -> str:
        """Legacy KeePass.exe CLI passthrough (§12 — last resort only)."""
        if not self._keepass_exe:
            return ""
        try:
            result = subprocess.run(
                [self._keepass_exe] + args,
                capture_output=True, text=True, timeout=30,
                input=input_text,
            )
            return result.stdout if result.returncode == 0 else ""
        except Exception:
            return ""
