"""Node network transport + pairing/security foundation (v0.7).

Stdlib-only (http.client/urllib + ssl + secrets + hmac). The legacy
in-memory transport in task_delegator.py is preserved for deterministic unit
tests; this module adds real network adapters and the pairing state machine.

Security posture:
- Plain HTTP is allowed ONLY for 127.0.0.1/localhost (or explicit
  allow_insecure_dev development override). Anything else returns
  REMOTE_PLAINTEXT_DENIED before any task content is sent.
- TLS uses Python's ssl module (TLS 1.2 minimum). No custom crypto.
- Pairing tokens/challenges come from secrets; HMAC is message
  authentication only, never a substitute for TLS confidentiality.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any

# -- transport types ---------------------------------------------------------
TRANSPORT_IN_MEMORY = "IN_MEMORY"
TRANSPORT_HTTP = "HTTP"
TRANSPORT_HTTPS = "HTTPS"
TRANSPORT_SSE = "SSE"
TRANSPORT_WEBSOCKET = "WEBSOCKET"
WEBSOCKET_STATUS = "NOT_INSTALLED"  # no websocket backend installed; do not add one

# -- security modes ----------------------------------------------------------
SECURITY_MODE_IN_MEMORY = "IN_MEMORY"
SECURITY_MODE_PLAINTEXT_LOOPBACK = "PLAINTEXT_LOOPBACK"
SECURITY_MODE_TLS = "TLS"

# -- node protocol -----------------------------------------------------------
PROTOCOL_NAME = "agent-bridge-node"
PROTOCOL_VERSION = "1.0"
PROTOCOL_MIN_SUPPORTED = "1.0"
PROTOCOL_MAX_SUPPORTED = "1.0"

# -- error codes -------------------------------------------------------------
ERR_NODE_OFFLINE = "NODE_OFFLINE"
ERR_NODE_UNTRUSTED = "NODE_UNTRUSTED"
ERR_NODE_NOT_PAIRED = "NODE_NOT_PAIRED"
ERR_AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
ERR_PAIRING_REQUIRED = "PAIRING_REQUIRED"
ERR_PAIRING_REJECTED = "PAIRING_REJECTED"
ERR_PAIRING_EXPIRED = "PAIRING_EXPIRED"
ERR_PROTOCOL_VERSION_UNSUPPORTED = "PROTOCOL_VERSION_UNSUPPORTED"
ERR_TLS_REQUIRED = "TLS_REQUIRED"
ERR_REMOTE_PLAINTEXT_DENIED = "REMOTE_PLAINTEXT_DENIED"
ERR_PRIVACY_DENIED = "PRIVACY_DENIED"
ERR_CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"
ERR_TOOL_DENIED = "TOOL_DENIED"
ERR_DELEGATION_TIMEOUT = "DELEGATION_TIMEOUT"
ERR_DELEGATION_CANCELLED = "DELEGATION_CANCELLED"
ERR_REMOTE_EXECUTION_FAILED = "REMOTE_EXECUTION_FAILED"
ERR_REPLAY_REJECTED = "REPLAY_REJECTED"
ERR_EMERGENCY_STOP_ACTIVE = "EMERGENCY_STOP_ACTIVE"
ERR_REMOTE_OWNER_POLICY_DENIED = "REMOTE_OWNER_POLICY_DENIED"
ERR_REMOTE_OWNER_APPROVAL_REQUIRED = "REMOTE_OWNER_APPROVAL_REQUIRED"

# remote owner authorization policy (local OWNER_FULL_ACCESS never implies these)
REMOTE_OWNER_DISABLED = "REMOTE_OWNER_DISABLED"
REMOTE_OWNER_APPROVAL_REQUIRED = "REMOTE_OWNER_APPROVAL_REQUIRED"
REMOTE_OWNER_ENABLED = "REMOTE_OWNER_ENABLED"

REMOTE_OWNER_POLICIES = (
    REMOTE_OWNER_DISABLED,
    REMOTE_OWNER_APPROVAL_REQUIRED,
    REMOTE_OWNER_ENABLED,
)

# -- pairing states ----------------------------------------------------------
PAIR_UNPAIRED = "UNPAIRED"
PAIR_REQUESTED = "PAIRING_REQUESTED"
PAIR_AWAITING_OWNER = "AWAITING_OWNER_APPROVAL"
PAIR_CHALLENGE_SENT = "CHALLENGE_SENT"
PAIR_CHALLENGE_VERIFIED = "CHALLENGE_VERIFIED"
PAIR_PAIRED = "PAIRED"
PAIR_REJECTED = "REJECTED"
PAIR_REVOKED = "REVOKED"
PAIR_EXPIRED = "EXPIRED"

PAIRING_STATES = (
    PAIR_UNPAIRED, PAIR_REQUESTED, PAIR_AWAITING_OWNER,
    PAIR_CHALLENGE_SENT, PAIR_CHALLENGE_VERIFIED, PAIR_PAIRED,
    PAIR_REJECTED, PAIR_REVOKED, PAIR_EXPIRED,
)

PAIRING_TOKEN_TTL_S = 300
REPLAY_WINDOW_S = 300


@dataclass
class NodeProtocolInfo:
    """Advertised protocol metadata (no secrets)."""
    node_id: str = ""
    protocol_name: str = PROTOCOL_NAME
    protocol_version: str = PROTOCOL_VERSION
    min_supported_version: str = PROTOCOL_MIN_SUPPORTED
    max_supported_version: str = PROTOCOL_MAX_SUPPORTED
    runtime_version: str = "0.7.0"
    capabilities_schema_version: str = "1.0"
    transport: str = TRANSPORT_HTTP
    security_mode: str = SECURITY_MODE_PLAINTEXT_LOOPBACK

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def negotiate_protocol(local: NodeProtocolInfo,
                       remote: dict[str, Any]) -> tuple[bool, str]:
    """Negotiate protocol versions. Returns (compatible, code)."""
    if remote.get("protocol_name") != PROTOCOL_NAME:
        return False, ERR_PROTOCOL_VERSION_UNSUPPORTED
    rv = str(remote.get("protocol_version", ""))
    try:
        lo = tuple(int(p) for p in PROTOCOL_MIN_SUPPORTED.split("."))
        hi = tuple(int(p) for p in PROTOCOL_MAX_SUPPORTED.split("."))
        got = tuple(int(p) for p in rv.split("."))
    except ValueError:
        return False, ERR_PROTOCOL_VERSION_UNSUPPORTED
    if not (lo <= got <= hi):
        return False, ERR_PROTOCOL_VERSION_UNSUPPORTED
    return True, "OK"


@dataclass
class TaskEnvelope:
    """JSON-safe network task envelope (minimum necessary context)."""
    protocol_version: str = PROTOCOL_VERSION
    delegation_id: str = ""
    task_id: str = ""
    session_id: str = ""
    source_node: str = ""
    target_node: str = ""
    task_type: str = ""
    requirements: dict[str, Any] = field(default_factory=dict)
    privacy_policy: str = "LOCAL_FIRST"
    requested_agent: str = ""
    requested_model: str = ""
    requested_provider: str = ""
    requested_ide: str = ""
    required_tools: list[str] = field(default_factory=list)
    context_reference: str = ""
    artifact_references: list[str] = field(default_factory=list)
    deadline_s: int = 300
    nonce: str = ""
    timestamp: float = 0.0
    # Remote owner scope: local OWNER_FULL_ACCESS never implies this.
    owner_scope_requested: bool = False
    owner_scope: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResultEnvelope:
    """JSON-safe result envelope (references, not giant bodies)."""
    protocol_version: str = PROTOCOL_VERSION
    delegation_id: str = ""
    status: str = ""
    source_node: str = ""
    target_node: str = ""
    agent: str = ""
    model: str = ""
    provider: str = ""
    ide: str = ""
    tools_used: list[str] = field(default_factory=list)
    result_summary: str = ""
    artifact_references: list[dict[str, Any]] = field(default_factory=list)
    verification: dict[str, Any] = field(default_factory=dict)
    started_at: float = 0.0
    completed_at: float = 0.0
    error_code: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def privacy_allows_send(privacy_policy: str, source_node: str,
                        target_node: str, trusted: bool) -> tuple[bool, str]:
    """Decide BEFORE serializing private content. Returns (allowed, code)."""
    if privacy_policy in ("LOCAL_ONLY", "CURRENT_DEVICE_ONLY"):
        if target_node != source_node:
            return False, ERR_PRIVACY_DENIED
        return True, "OK"
    if privacy_policy in ("LOCAL_FIRST", "TRUSTED_NODES"):
        if target_node != source_node and not trusted:
            return False, ERR_PRIVACY_DENIED
        return True, "OK"
    return True, "OK"


def ensure_loopback_or_raise(url: str, allow_insecure_dev: bool = False) -> str:
    """Enforce plaintext safety. Returns security mode or raises."""
    parts = urllib.parse.urlparse(url)
    if parts.scheme == "https":
        return SECURITY_MODE_TLS
    if parts.scheme != "http":
        raise ValueError(f"unsupported scheme: {parts.scheme}")
    host = (parts.hostname or "").lower()
    if host in ("127.0.0.1", "localhost", "::1"):
        return SECURITY_MODE_PLAINTEXT_LOOPBACK
    if allow_insecure_dev:
        return SECURITY_MODE_PLAINTEXT_LOOPBACK
    raise PermissionError(ERR_REMOTE_PLAINTEXT_DENIED)


class ReplayGuard:
    """Nonce/timestamp/request-ID replay protection."""

    def __init__(self, window_s: int = REPLAY_WINDOW_S):
        self.window_s = window_s
        self._seen: dict[str, float] = {}

    def verify(self, nonce: str, timestamp: float, request_id: str) -> tuple[bool, str]:
        now = time.time()
        if not nonce or not request_id:
            return False, ERR_REPLAY_REJECTED
        if abs(now - timestamp) > self.window_s:
            return False, ERR_REPLAY_REJECTED
        key = f"{nonce}:{request_id}"
        self._prune(now)
        if key in self._seen:
            return False, ERR_REPLAY_REJECTED
        self._seen[key] = now
        return True, "OK"

    def _prune(self, now: float) -> None:
        expired = [k for k, t in self._seen.items() if now - t > self.window_s]
        for k in expired:
            del self._seen[k]


@dataclass
class PairingAttempt:
    attempt_id: str
    remote_node_id: str
    state: str = PAIR_REQUESTED
    token_hash: str = ""
    challenge: str = ""
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    used: bool = False
    trust_level: str = "LIMITED_NODE"


class PairingManager:
    """Pairing state machine with secrets-based tokens and HMAC challenge."""

    def __init__(self, local_node_id: str, token_ttl_s: int = PAIRING_TOKEN_TTL_S):
        self.local_node_id = local_node_id
        self.token_ttl_s = token_ttl_s
        self._attempts: dict[str, PairingAttempt] = {}
        self._revoked: set[str] = set()

    def request_pairing(self, remote_node_id: str) -> tuple[str, str]:
        """Create a pairing attempt. Returns (attempt_id, one_time_token).

        The token is returned ONCE to the caller; only its hash is stored.
        """
        attempt_id = f"pair-{secrets.token_hex(8)}"
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        now = time.time()
        self._attempts[attempt_id] = PairingAttempt(
            attempt_id=attempt_id,
            remote_node_id=remote_node_id,
            state=PAIR_AWAITING_OWNER,
            token_hash=token_hash,
            created_at=now,
            expires_at=now + self.token_ttl_s,
        )
        return attempt_id, token

    def approve(self, attempt_id: str, approved: bool,
              trust_level: str = "LIMITED_NODE") -> tuple[bool, str, str]:
        """Owner approval step. Returns (ok, code, challenge)."""
        attempt = self._attempts.get(attempt_id)
        if attempt is None or attempt.used:
            return False, ERR_PAIRING_REJECTED, ""
        if time.time() > attempt.expires_at:
            attempt.state = PAIR_EXPIRED
            return False, ERR_PAIRING_EXPIRED, ""
        if not approved:
            attempt.state = PAIR_REJECTED
            attempt.used = True
            return False, ERR_PAIRING_REJECTED, ""
        attempt.state = PAIR_CHALLENGE_SENT
        attempt.trust_level = trust_level
        attempt.challenge = secrets.token_hex(16)
        return True, "OK", attempt.challenge

    def verify_challenge(self, attempt_id: str, token: str, response: str) -> tuple[bool, str]:
        """Verify HMAC challenge response. Token is single-use."""
        attempt = self._attempts.get(attempt_id)
        if attempt is None or attempt.used:
            return False, ERR_AUTHENTICATION_FAILED
        if time.time() > attempt.expires_at:
            attempt.state = PAIR_EXPIRED
            return False, ERR_PAIRING_EXPIRED
        if attempt.remote_node_id in self._revoked:
            attempt.state = PAIR_REVOKED
            return False, ERR_PAIRING_REJECTED
        if hashlib.sha256(token.encode()).hexdigest() != attempt.token_hash:
            return False, ERR_AUTHENTICATION_FAILED
        expected = hmac.new(
            token.encode(),
            f"{attempt_id}:{attempt.challenge}".encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, response):
            return False, ERR_AUTHENTICATION_FAILED
        attempt.used = True
        attempt.state = PAIR_CHALLENGE_VERIFIED
        return True, "OK"

    def mark_paired(self, attempt_id: str) -> bool:
        attempt = self._attempts.get(attempt_id)
        if attempt and attempt.state == PAIR_CHALLENGE_VERIFIED:
            attempt.state = PAIR_PAIRED
            return True
        return False

    def revoke(self, remote_node_id: str) -> None:
        self._revoked.add(remote_node_id)
        for attempt in self._attempts.values():
            if attempt.remote_node_id == remote_node_id and \
                    attempt.state not in (PAIR_PAIRED, PAIR_REVOKED):
                attempt.state = PAIR_REVOKED

    def is_revoked(self, remote_node_id: str) -> bool:
        return remote_node_id in self._revoked

    def state_of(self, attempt_id: str) -> str:
        attempt = self._attempts.get(attempt_id)
        if attempt is None:
            return PAIR_UNPAIRED
        if attempt.state not in (PAIR_PAIRED, PAIR_REJECTED, PAIR_REVOKED,
                                 PAIR_EXPIRED) and time.time() > attempt.expires_at:
            attempt.state = PAIR_EXPIRED
        return attempt.state


def challenge_response(token: str, attempt_id: str, challenge: str) -> str:
    """Client-side HMAC response computation (message auth only)."""
    return hmac.new(
        token.encode(),
        f"{attempt_id}:{challenge}".encode(),
        hashlib.sha256,
    ).hexdigest()


class CredentialStore:
    """Credential-storage abstraction. Never logs secrets."""

    def put(self, key: str, secret: str) -> None:
        raise NotImplementedError

    def get(self, key: str) -> str | None:
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError


class DevFileCredentialStore(CredentialStore):
    """Development-only file store with restrictive permissions.

    Refuses to operate unless explicitly marked development-only.
    """

    def __init__(self, path: str, development_only: bool = False):
        if not development_only:
            raise PermissionError("DevFileCredentialStore requires development_only=True")
        import os
        self.path = path
        self._data: dict[str, str] = {}
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                self._data = json.load(f)

    def _save(self) -> None:
        import os
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._data, f)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def put(self, key: str, secret: str) -> None:
        self._data[key] = secret
        self._save()

    def get(self, key: str) -> str | None:
        return self._data.get(key)

    def delete(self, key: str) -> None:
        self._data.pop(key, None)
        self._save()


class WindowsCredentialManagerStore(CredentialStore):
    """Windows Credential Manager / DPAPI adapter (INTERFACE_ONLY in v0.7)."""

    def put(self, key: str, secret: str) -> None:
        raise NotImplementedError("Windows Credential Manager adapter is INTERFACE_ONLY in v0.7")

    def get(self, key: str) -> str | None:
        raise NotImplementedError("Windows Credential Manager adapter is INTERFACE_ONLY in v0.7")

    def delete(self, key: str) -> None:
        raise NotImplementedError("Windows Credential Manager adapter is INTERFACE_ONLY in v0.7")


@dataclass
class TlsConfig:
    """HTTPS configuration. Missing material => CONFIGURATION_REQUIRED."""
    certfile: str = ""
    keyfile: str = ""
    cafile: str = ""
    fingerprint: str = ""
    min_version: Any = None

    def status(self) -> str:
        if not self.certfile or not self.keyfile:
            return "CONFIGURATION_REQUIRED"
        return "CONFIGURED"

    def server_context(self) -> ssl.SSLContext:
        if self.status() != "CONFIGURED":
            raise ValueError("HTTPS CONFIGURATION_REQUIRED: certfile/keyfile missing")
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        try:
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        except AttributeError:
            ctx.options |= getattr(ssl, "OP_NO_TLSv1", 0) | getattr(ssl, "OP_NO_TLSv1_1", 0)
        ctx.load_cert_chain(self.certfile, self.keyfile)
        if self.cafile:
            ctx.load_verify_locations(self.cafile)
            ctx.verify_mode = ssl.CERT_REQUIRED
        return ctx


REDACT_KEYS = {"token", "challenge", "response", "secret", "private_key",
               "authorization", "pairing_token", "api_key"}


def audit_event(event: dict[str, Any]) -> dict[str, Any]:
    """Return a redacted copy of an audit event (never log secrets)."""
    redacted = dict(event)
    for key in list(redacted.keys()):
        if key.lower() in REDACT_KEYS:
            redacted[key] = "[REDACTED]"
    return redacted


class HttpNodeTransport:
    """Real HTTP(S) node transport (stdlib urllib).

    Mirrors the in-memory NodeTransport method names where practical and adds
    handshake/health/pairing/delegation endpoints. Streaming uses SSE-style
    polling of the events endpoint (no websocket dependency).
    """

    def __init__(self, local_node_id: str, timeout_s: float = 30.0,
                 allow_insecure_dev: bool = False,
                 tls_config: TlsConfig | None = None,
                 cafile: str = ""):
        self.local_node_id = local_node_id
        self.timeout_s = timeout_s
        self.allow_insecure_dev = allow_insecure_dev
        self.tls_config = tls_config or TlsConfig()
        self.cafile = cafile
        self.transport = TRANSPORT_HTTP

    def _context_for(self, url: str):
        """TLS client context: verify against explicit CA or system CAs.

        Self-signed development CAs are only trusted when their cafile is
        explicitly provided. There is no verify-skipping flag.
        """
        if urllib.parse.urlparse(url).scheme != "https":
            return None
        if self.cafile:
            ctx = ssl.create_default_context(cafile=self.cafile)
        else:
            ctx = ssl.create_default_context()
        try:
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        except AttributeError:
            pass
        return ctx

    def _post(self, url: str, payload: dict[str, Any],
              token: str = "") -> dict[str, Any]:
        ensure_loopback_or_raise(url, self.allow_insecure_dev)
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"})
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s,
                                        context=self._context_for(url)) as resp:
                return json.loads(resp.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            try:
                return json.loads(e.read().decode() or "{}")
            except Exception:
                return {"ok": False, "error_code": f"HTTP_{e.code}"}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error_code": ERR_NODE_OFFLINE,
                    "error": str(e)[:200]}

    def _get(self, url: str, token: str = "") -> dict[str, Any]:
        ensure_loopback_or_raise(url, self.allow_insecure_dev)
        req = urllib.request.Request(url)
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s,
                                        context=self._context_for(url)) as resp:
                ctype = resp.headers.get("Content-Type", "")
                body = resp.read().decode()
                if "text/event-stream" in ctype:
                    return {"ok": True, "events_text": body}
                return json.loads(body or "{}")
        except urllib.error.HTTPError as e:
            try:
                return json.loads(e.read().decode() or "{}")
            except Exception:
                return {"ok": False, "error_code": f"HTTP_{e.code}"}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error_code": ERR_NODE_OFFLINE,
                    "error": str(e)[:200]}

    # -- node protocol endpoints -------------------------------------------
    def health(self, base_url: str) -> dict[str, Any]:
        return self._get(f"{base_url.rstrip('/')}/v1/node/health")

    def get_descriptor(self, base_url: str) -> dict[str, Any]:
        return self._get(f"{base_url.rstrip('/')}/v1/node/descriptor")

    def handshake(self, base_url: str, local: NodeProtocolInfo) -> dict[str, Any]:
        return self._post(f"{base_url.rstrip('/')}/v1/node/handshake", local.to_dict())

    def heartbeat(self, base_url: str, node_id: str, load: float = 0.0) -> dict[str, Any]:
        return self._post(f"{base_url.rstrip('/')}/v1/node/heartbeat",
                          {"node_id": node_id, "load": load})

    def refresh_capabilities(self, base_url: str, capabilities: dict[str, Any]) -> dict[str, Any]:
        return self._post(f"{base_url.rstrip('/')}/v1/node/capabilities/refresh", capabilities)

    # -- pairing endpoints ---------------------------------------------------
    def pairing_request(self, base_url: str, source_node: str) -> dict[str, Any]:
        return self._post(f"{base_url.rstrip('/')}/v1/node/pairing/request",
                          {"source_node": source_node})

    def pairing_approve(self, base_url: str, attempt_id: str, approved: bool,
                        trust_level: str = "LIMITED_NODE") -> dict[str, Any]:
        return self._post(f"{base_url.rstrip('/')}/v1/node/pairing/approve",
                          {"attempt_id": attempt_id, "approved": approved,
                           "trust_level": trust_level})

    def pairing_challenge(self, base_url: str, attempt_id: str,
                          response: str) -> dict[str, Any]:
        return self._post(f"{base_url.rstrip('/')}/v1/node/pairing/challenge",
                          {"attempt_id": attempt_id, "response": response})

    # -- delegation endpoints --------------------------------------------------
    def send_envelope(self, base_url: str, envelope: TaskEnvelope) -> dict[str, Any]:
        return self._post(f"{base_url.rstrip('/')}/v1/node/delegations", envelope.to_dict())

    def delegation_status(self, base_url: str, delegation_id: str) -> dict[str, Any]:
        return self._get(f"{base_url.rstrip('/')}/v1/node/delegations/{delegation_id}")

    def delegation_events(self, base_url: str, delegation_id: str) -> dict[str, Any]:
        return self._get(f"{base_url.rstrip('/')}/v1/node/delegations/{delegation_id}/events")

    def cancel_delegation(self, base_url: str, delegation_id: str) -> dict[str, Any]:
        return self._post(
            f"{base_url.rstrip('/')}/v1/node/delegations/{delegation_id}/cancel", {})

    def artifact_metadata(self, base_url: str, ref: str) -> dict[str, Any]:
        return self._get(f"{base_url.rstrip('/')}/v1/node/artifacts/{ref}")
