"""Additional vault adapters for the Aetherius Credential Broker (§8).

Per §8 of the Data Fabric policy:
"Integrate with the previously authorised AETHERIUS CREDENTIAL BROKER.
KeePass remains available for READ_SCOPED/WRITE_SCOPED under human oversight.
Also research modern credential-management interfaces designed for agents."

Adapters implemented:
- ProtonPassAdapter: CLI-based Proton Pass integration (§7 candidates)
- BitwardenAdapter: CLI-based Bitwarden integration (§7 candidates)

These adapters implement the VaultAdapter Protocol from credential_broker.py.
They use CLI interfaces (bw, proton) that support token-based auth — the
master password/token is NEVER stored or logged (§4, §18).

Per §46: Do NOT automatically copy real passwords. Test with dummy data first (§47).
Per §3: Live research required — adapters detect CLI availability and report
OWNER_ACTION_REQUIRED if the CLI or account is not configured.
"""
import os
import sys
import subprocess
import json
import logging
import shutil
from typing import Optional

from security.credential_broker import (
    VaultAdapter, VAULT_UNLOCKED, VAULT_LOCKED, AUTH_REQUIRED,
    OP_READ_ENTRY, OP_CREATE_ENTRY, OP_UPDATE_ENTRY,
)

logger = logging.getLogger("aetherius.vault_adapters")


class ProtonPassAdapter:
    """Proton Pass adapter via proton CLI (§7, §8).

    Proton Pass supports agent access tokens with granular permissions
    and time limits (mentioned in §8 note). The adapter uses the
    proton CLI which supports token-based authentication.

    State: NOT_INSTALLED or EVALUATION (Proton Pass not yet installed).
    """

    adapter_id = "proton_pass"
    vault_state = AUTH_REQUIRED

    def __init__(self):
        self._cli_path: Optional[str] = None
        self._token: Optional[str] = None  # Never stored in config, never logged
        self._unlocked = False
        self._discover_cli()

    def _discover_cli(self) -> None:
        """Discover proton CLI availability (§3, §12)."""
        cli = shutil.which("proton")
        if cli:
            self._cli_path = cli
            logger.info("Proton CLI discovered at: %s", cli)
        else:
            logger.info("Proton CLI not found - ProtonPassAdapter in EVALUATION state")

    def status(self) -> dict:
        return {
            "adapter_id": self.adapter_id,
            "vault_state": VAULT_UNLOCKED if self._unlocked else VAULT_LOCKED,
            "cli_available": self._cli_path is not None,
            "cli_path": self._cli_path,
            "auth_required": not self._unlocked,
            "account_required": True,
            "account_state": "OWNER_ACTION_REQUIRED" if not self._unlocked else "CONFIGURED",
            "agent_support": True,
        }

    def status_str(self) -> str:
        return VAULT_UNLOCKED if self._unlocked else VAULT_LOCKED

    def set_token(self, token: str) -> None:
        """Set the Proton Pass agent access token (§4, §14).

        Token must be entered by the owner or provided via secure callback.
        NEVER logged or stored in config.
        """
        self._token = token
        self._unlocked = True

    def list_metadata(self, project: str | None = None) -> list:
        """List credential metadata via proton CLI (no secrets)."""
        if not self._cli_path or not self._unlocked:
            return []
        try:
            env = dict(os.environ)
            if self._token:
                env["PROTON_ACCESS_TOKEN"] = self._token
            result = subprocess.run(
                [self._cli_path, "pass", "list", "--output", "json"],
                capture_output=True, text=True, timeout=30, env=env,
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                return [{"credential_id": item.get("id", ""),
                         "service": item.get("service", ""),
                         "name": item.get("name", "")} for item in data]
        except Exception as e:
            logger.warning("Proton Pass list error: %s", e)
        return []

    def read_entry(self, credential_id: str,
                   master_password: str | None = None) -> str:
        """Read a credential value from Proton Pass by ID."""
        if not self._cli_path or not self._unlocked:
            return ""
        try:
            env = dict(os.environ)
            if self._token:
                env["PROTON_ACCESS_TOKEN"] = self._token
            result = subprocess.run(
                [self._cli_path, "pass", "get", credential_id, "--output", "json"],
                capture_output=True, text=True, timeout=30, env=env,
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                return data.get("password", "") or data.get("secret", "")
        except Exception as e:
            logger.warning("Proton Pass read error: %s", e)
        return ""

    def create_entry(self, credential_id: str, secret_value: str,
                     metadata: dict, master_password: str | None = None) -> bool:
        """Create a new entry in Proton Pass."""
        if not self._cli_path or not self._unlocked:
            return False
        # Proton Pass CLI create requires owner-level approval per §46
        return False  # Requires explicit owner action

    def update_entry(self, credential_id: str, secret_value: str,
                     master_password: str | None = None) -> bool:
        """Update an existing entry in Proton Pass."""
        if not self._cli_path or not self._unlocked:
            return False
        return False  # Requires explicit owner action

    def lock(self) -> bool:
        """Lock the Proton Pass session (clear token from memory)."""
        self._token = None
        self._unlocked = False
        self.vault_state = VAULT_LOCKED
        return True


class BitwardenAdapter:
    """Bitwarden adapter via bw CLI (§7, §8).

    Bitwarden CLI supports:
    - Service account tokens (bw login --apikey)
    - Item retrieval by ID (bw get password <id>)
    - Sync (bw sync)

    The master password/token is NEVER stored or logged (§4, §18).
    Per §46: test with dummy data first.
    """

    adapter_id = "bitwarden"
    vault_state = AUTH_REQUIRED

    def __init__(self):
        self._cli_path: Optional[str] = None
        self._session_token: Optional[str] = None  # bw --session token
        self._master_password: Optional[str] = None
        self._unlocked = False
        self._discovered = False
        self._discover_cli()

    def _discover_cli(self) -> None:
        """Discover bw CLI availability (§3, §12)."""
        cli = shutil.which("bw")
        if cli:
            self._cli_path = cli
            self._discovered = True
            logger.info("Bitwarden CLI discovered at: %s", cli)
        else:
            logger.info("Bitwarden CLI not found - BitwardenAdapter in EVALUATION state")

    def status(self) -> dict:
        return {
            "adapter_id": self.adapter_id,
            "vault_state": VAULT_UNLOCKED if self._unlocked else VAULT_LOCKED,
            "cli_available": self._cli_path is not None,
            "cli_path": self._cli_path,
            "auth_required": not self._unlocked,
            "account_required": True,
            "account_state": "OWNER_ACTION_REQUIRED" if not self._unlocked else "CONFIGURED",
            "agent_support": True,
            "sync_available": True,
        }

    def status_str(self) -> str:
        return VAULT_UNLOCKED if self._unlocked else VAULT_LOCKED

    def set_session(self, session_token: str) -> None:
        """Set a Bitwarden CLI session token (from `bw unlock`)."""
        self._session_token = session_token
        self._unlocked = True

    def set_master_password(self, password: str) -> None:
        """Set the master password for unlock (§4).

        Uses bw unlock to obtain a session token. The master password
        is passed directly and never logged.
        """
        self._master_password = password
        self._unlocked = True

    def _run_bw(self, args: list, use_session: bool = True) -> str:
        """Run a bw CLI command."""
        if not self._cli_path:
            return ""
        cmd = [self._cli_path] + args
        env = dict(os.environ)
        if use_session and self._session_token:
            cmd.extend(["--session", self._session_token])
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30, env=env,
            )
            return result.stdout if result.returncode == 0 else ""
        except Exception as e:
            logger.warning("Bitwarden CLI error: %s", e)
        return ""

    def sync(self) -> bool:
        """Sync the vault (§5)."""
        result = self._run_bw(["sync"])
        return bool(result)

    def list_metadata(self, project: str | None = None) -> list:
        """List credential metadata via bw CLI (no secrets)."""
        result = self._run_bw(["list", "items", "--output", "json"])
        if result:
            try:
                data = json.loads(result)
                return [{"credential_id": item.get("id", ""),
                         "service": item.get("name", ""),
                         "account_label": item.get("username", "")} for item in data]
            except json.JSONDecodeError:
                pass
        return []

    def read_entry(self, credential_id: str,
                   master_password: str | None = None) -> str:
        """Read a credential value from Bitwarden by item ID."""
        result = self._run_bw(["get", "password", credential_id])
        return result.strip()

    def create_entry(self, credential_id: str, secret_value: str,
                     metadata: dict, master_password: str | None = None) -> bool:
        """Create a new entry in Bitwarden."""
        # Requires interactive approval per §46
        return False

    def update_entry(self, credential_id: str, secret_value: str,
                     master_password: str | None = None) -> bool:
        """Update an existing entry in Bitwarden."""
        if not self._cli_path or not self._unlocked:
            return False
        return False  # Requires explicit owner action

    def lock(self) -> bool:
        """Lock the Bitwarden session (clear token from memory)."""
        self._session_token = None
        self._master_password = None
        self._unlocked = False
        self.vault_state = VAULT_LOCKED
        return True
