"""Governed remote-desktop adapter (P21, REQ-p21-remote-desktop).

VNC-class remote desktop reach with authenticated transport, scoped
clipboard/file transfer and a saved-endpoint registry using vault
references. Reference: CrabFleet remote-desktop (v0.3.1, MIT, STUDY_ONLY)
— mechanics only. CrabFleet is a remote-desktop tool, not a fleet
controller; no fleet semantics exist here.

Boundaries:
- Endpoints carry vault REFERENCES ({ref: ...}), never raw credentials.
  Raw password/secret/token fields are rejected at registration.
- Transport without authentication is rejected, except the labeled
  simulated loopback used for tests.
- Clipboard and file transfer are scoped per session (direction allowlist
  + byte budget). Anything outside scope fails closed.
- No screen scraping, no input injection, no live backend in this unit:
  the loopback backend replays declared frames; the VNC backend is
  declared-unavailable. Session lifecycle and scope enforcement are real.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------

class RemoteDesktopError(Exception):
    """Base for adapter errors."""


class EndpointError(RemoteDesktopError):
    """Saved-endpoint validation failure."""


class AuthError(RemoteDesktopError):
    """Authentication required or failed."""


class ScopeError(RemoteDesktopError):
    """Clipboard/transfer outside the session scope."""


class SessionError(RemoteDesktopError):
    """Session lifecycle violation."""


class BackendUnavailable(RemoteDesktopError):
    """Declared backend with no live implementation here."""


# --------------------------------------------------------------------------
# Saved endpoints (vault references only)
# --------------------------------------------------------------------------

AUTH_METHODS = ("password-vault-ref", "key-vault-ref", "loopback-sim")
RAW_CREDENTIAL_FIELDS = ("password", "secret", "token", "private_key", "privateKey", "api_key")


@dataclass(frozen=True)
class SavedEndpoint:
    endpoint_id: str
    host: str
    port: int
    auth_method: str
    credential: dict[str, Any]
    label: str = ""


def validate_endpoint(data: dict[str, Any]) -> SavedEndpoint:
    """Validate a saved endpoint. Credentials must be a vault reference
    ({ref: <pointer>}); raw credential fields are rejected."""
    if not isinstance(data, dict):
        raise EndpointError("endpoint must be an object")
    endpoint_id = str(data.get("endpoint_id", "")).strip()
    if not endpoint_id:
        raise EndpointError("endpoint_id is required")
    host = str(data.get("host", "")).strip()
    if not host:
        raise EndpointError("host is required")
    port = data.get("port")
    if not isinstance(port, int) or port < 1 or port > 65535:
        raise EndpointError("port must be 1..65535")
    auth_method = str(data.get("auth_method", "")).strip()
    if auth_method not in AUTH_METHODS:
        raise EndpointError(f"auth_method must be one of {AUTH_METHODS}")
    credential = data.get("credential")
    if not isinstance(credential, dict):
        raise EndpointError("credential must be a vault reference object")
    for banned in RAW_CREDENTIAL_FIELDS:
        if banned in credential:
            raise EndpointError(f"credential must be a vault reference, not raw field {banned}")
    if "ref" not in credential or not str(credential["ref"]).strip():
        raise EndpointError("credential must carry a non-empty vault ref")
    return SavedEndpoint(
        endpoint_id=endpoint_id,
        host=host,
        port=port,
        auth_method=auth_method,
        credential={"ref": str(credential["ref"]).strip()},
        label=str(data.get("label", "")),
    )


class EndpointRegistry:
    """First-party saved-endpoint registry. Stores validated endpoints;
    never sees raw credentials (they cannot be registered)."""

    def __init__(self) -> None:
        self._endpoints: dict[str, SavedEndpoint] = {}

    def register(self, data: dict[str, Any]) -> SavedEndpoint:
        endpoint = validate_endpoint(data)
        if endpoint.endpoint_id in self._endpoints:
            raise EndpointError(f"duplicate endpoint {endpoint.endpoint_id}")
        self._endpoints[endpoint.endpoint_id] = endpoint
        return endpoint

    def get(self, endpoint_id: str) -> SavedEndpoint:
        try:
            return self._endpoints[endpoint_id]
        except KeyError:
            raise EndpointError(f"unknown endpoint {endpoint_id}") from None

    def list_ids(self) -> list[str]:
        return sorted(self._endpoints)


# --------------------------------------------------------------------------
# Sessions (scoped clipboard/file transfer, authenticated transport)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class TransferScope:
    clipboard_in: bool = False
    clipboard_out: bool = False
    file_upload: bool = False
    file_download: bool = False
    max_bytes: int = 0


@dataclass
class DesktopSession:
    session_id: str
    endpoint_id: str
    scope: TransferScope
    simulated: bool
    state: str = "DEFINED"
    clipboard_bytes: int = 0
    transfer_bytes: int = 0
    frames: int = 0

    VALID = ("DEFINED", "AUTH", "CONNECTED", "CLOSED")

    def _move(self, nxt: str) -> None:
        allowed = {
            "DEFINED": ("AUTH",),
            "AUTH": ("CONNECTED",),
            "CONNECTED": ("CLOSED",),
            "CLOSED": (),
        }[self.state]
        if nxt not in allowed:
            raise SessionError(f"session {self.session_id}: {self.state} -> {nxt} not allowed")
        self.state = nxt


class DesktopBackend(ABC):
    kind: str = "unknown"

    @abstractmethod
    def connect(self, session: DesktopSession, endpoint: SavedEndpoint) -> None:
        """Authenticate transport. Raises AuthError/BackendUnavailable."""

    @abstractmethod
    def frame(self, session: DesktopSession) -> dict[str, Any]:
        """Next declared frame descriptor (metadata only, never pixels)."""


class LoopbackBackend(DesktopBackend):
    """Labeled simulated backend for tests. Replays declared frame
    descriptors; performs no network, no capture, no input."""

    kind = "loopback"
    simulated = True

    def __init__(self, frames: list[dict[str, Any]] | None = None):
        self._frames = list(frames or [{"width": 0, "height": 0, "note": "simulated"}])
        self._cursor = 0

    def connect(self, session: DesktopSession, endpoint: SavedEndpoint) -> None:
        if endpoint.auth_method != "loopback-sim":
            raise AuthError("loopback serves loopback-sim endpoints only")
        session._move("AUTH")

    def frame(self, session: DesktopSession) -> dict[str, Any]:
        if session.state != "CONNECTED":
            raise SessionError("frames require a CONNECTED session")
        frame = self._frames[self._cursor % len(self._frames)]
        self._cursor += 1
        session.frames += 1
        return {"simulated": True, **frame}


class VncBackend(DesktopBackend):
    """Declared VNC backend with no live implementation on this
    workstation. Refuses work with a reason instead of pretending."""

    kind = "vnc"
    simulated = False

    def connect(self, session: DesktopSession, endpoint: SavedEndpoint) -> None:
        raise BackendUnavailable("no VNC client backend registered (owner-authorized runtime work)")

    def frame(self, session: DesktopSession) -> dict[str, Any]:
        raise BackendUnavailable("no VNC client backend registered (owner-authorized runtime work)")


class SessionManager:
    """Owns session lifecycle and scope enforcement for one backend."""

    def __init__(self, backend: DesktopBackend):
        self._backend = backend
        self._seq = 0

    def open(self, endpoint: SavedEndpoint, scope: TransferScope) -> DesktopSession:
        if endpoint.auth_method == "none":
            raise AuthError("transport without authentication is rejected")
        self._seq += 1
        session = DesktopSession(
            session_id=f"rdp-{self._seq}",
            endpoint_id=endpoint.endpoint_id,
            scope=scope,
            simulated=getattr(self._backend, "simulated", False),
        )
        self._backend.connect(session, endpoint)
        session._move("CONNECTED")
        return session

    def clipboard(self, session: DesktopSession, direction: str, data: bytes) -> int:
        self._require_connected(session)
        if direction == "in" and not session.scope.clipboard_in:
            raise ScopeError("clipboard-in not in session scope")
        if direction == "out" and not session.scope.clipboard_out:
            raise ScopeError("clipboard-out not in session scope")
        if direction not in ("in", "out"):
            raise ScopeError(f"unknown clipboard direction {direction}")
        return self._spend(session, len(data), clipboard=True)

    def transfer(self, session: DesktopSession, direction: str, size: int) -> int:
        self._require_connected(session)
        if direction == "upload" and not session.scope.file_upload:
            raise ScopeError("file upload not in session scope")
        if direction == "download" and not session.scope.file_download:
            raise ScopeError("file download not in session scope")
        if direction not in ("upload", "download"):
            raise ScopeError(f"unknown transfer direction {direction}")
        if size < 0:
            raise ScopeError("transfer size must be non-negative")
        return self._spend(session, size, clipboard=False)

    def _spend(self, session: DesktopSession, size: int, clipboard: bool) -> int:
        used = session.clipboard_bytes + session.transfer_bytes + size
        if used > session.scope.max_bytes:
            raise ScopeError(f"session byte budget exceeded ({session.scope.max_bytes})")
        if clipboard:
            session.clipboard_bytes += size
        else:
            session.transfer_bytes += size
        return size

    def frame(self, session: DesktopSession) -> dict[str, Any]:
        self._require_connected(session)
        return self._backend.frame(session)

    def close(self, session: DesktopSession) -> DesktopSession:
        session._move("CLOSED")
        return session

    @staticmethod
    def _require_connected(session: DesktopSession) -> None:
        if session.state != "CONNECTED":
            raise SessionError(f"session {session.session_id} is {session.state}, not CONNECTED")
