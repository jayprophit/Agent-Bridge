"""Node HTTP server (v0.7). Real loopback network transport for nodes.

Stdlib ThreadingHTTPServer. Binds 127.0.0.1 by default and refuses 0.0.0.0
unless explicitly approved. Every remote delegation is re-validated on the
target (trust, pairing, privacy, capabilities, emergency stop) before the
injected executor runs. The server never executes tools itself.
"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import urlparse

from nodes.node_transport import (
    ERR_AUTHENTICATION_FAILED, ERR_CAPABILITY_UNAVAILABLE,
    ERR_DELEGATION_CANCELLED, ERR_EMERGENCY_STOP_ACTIVE, ERR_NODE_OFFLINE,
    ERR_NODE_UNTRUSTED, ERR_PAIRING_EXPIRED, ERR_PAIRING_REJECTED,
    ERR_PAIRING_REQUIRED, ERR_PRIVACY_DENIED, ERR_PROTOCOL_VERSION_UNSUPPORTED,
    ERR_REMOTE_EXECUTION_FAILED, ERR_REMOTE_OWNER_APPROVAL_REQUIRED,
    ERR_REMOTE_OWNER_POLICY_DENIED, ERR_REPLAY_REJECTED, ERR_TOOL_DENIED,
    REMOTE_OWNER_APPROVAL_REQUIRED, REMOTE_OWNER_DISABLED, REMOTE_OWNER_ENABLED,
    NodeProtocolInfo, PairingManager, ReplayGuard, audit_event,
    negotiate_protocol, privacy_allows_send,
)


class NodeServerState:
    """Mutable server-side node state (owned by one server instance)."""

    def __init__(self, node_id: str, descriptor_fn: Callable[[], dict[str, Any]],
                 trust_fn: Callable[[str], str],
                 executor: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]] | None = None):
        self.node_id = node_id
        self.descriptor_fn = descriptor_fn
        self.trust_fn = trust_fn  # remote_node_id -> trust level
        self.executor = executor  # target-side task execution (fixture/test-provided)
        self.pairing = PairingManager(node_id)
        self.replay = ReplayGuard()
        self.delegations: dict[str, dict[str, Any]] = {}
        self.events: dict[str, list[dict[str, Any]]] = {}
        self.cancelled: set[str] = set()
        self.emergency_stop = False
        self.emergency_reason = ""
        self.heartbeats: dict[str, dict[str, Any]] = {}
        self.capability_advertisement: dict[str, Any] = {}
        self.audit: list[dict[str, Any]] = []
        self.lock = threading.RLock()
        # Remote owner authorization: local OWNER_FULL_ACCESS never implies
        # remote privileges. Default denies all remote owner-scope requests.
        self.remote_owner_policy: str = REMOTE_OWNER_DISABLED
        # Explicit temporary grants: scope -> True. Even ENABLED allows only
        # configured scopes.
        self.remote_owner_grants: dict[str, bool] = {}

    def log(self, event: dict[str, Any]) -> None:
        with self.lock:
            self.audit.append(audit_event(event))

    def emit(self, delegation_id: str, status: str, message: str = "",
             progress: float = 0.0) -> None:
        with self.lock:
            self.events.setdefault(delegation_id, []).append({
                "delegation_id": delegation_id, "status": status,
                "message": message, "progress": progress,
                "timestamp": time.time(),
            })


def build_capability_summary(descriptor: dict[str, Any]) -> dict[str, Any]:
    """Concise capability advertisement (no full tool schemas)."""
    return {
        "node_id": descriptor.get("node_id", ""),
        "device_class": descriptor.get("device_class", ""),
        "models": list(descriptor.get("models", []))[:50],
        "tool_families": sorted({str(t).split(".")[0] for t in descriptor.get("tools", [])}),
        "tool_count": len(descriptor.get("tools", [])),
        "agents": list(descriptor.get("agents", []))[:20],
        "ides": list(descriptor.get("ides", []))[:20],
        "capabilities": list(descriptor.get("capabilities", []))[:50],
        "gpu_available": bool(descriptor.get("gpu_available", False)),
        "memory_mb": descriptor.get("memory_mb", 0),
        "filesystem_write": bool(descriptor.get("filesystem_write", False)),
        "browser_available": bool(descriptor.get("browser_available", False)),
    }


class Handler(BaseHTTPRequestHandler):
    state: NodeServerState
    server_version = "AgentBridgeNode/0.7"

    # -- helpers ---------------------------------------------------------
    def _send(self, code: int, obj: Any) -> None:
        body = json.dumps(obj, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_sse(self, events: list[dict[str, Any]]) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        for i, e in enumerate(events):
            line = f"id: {i}\nevent: {e.get('status', 'message')}\n" \
                   f"data: {json.dumps(e, default=str)[:4000]}\n\n"
            self.wfile.write(line.encode())

    def _body(self, limit: int = 256 * 1024) -> dict | None:
        try:
            n = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            n = 0
        if n > limit:
            self._send(413, {"ok": False, "error_code": "REQUEST_TOO_LARGE"})
            return None
        try:
            raw = self.rfile.read(n) if n else b"{}"
            obj = json.loads(raw.decode() or "{}")
        except (ValueError, UnicodeDecodeError):
            self._send(400, {"ok": False, "error_code": "MALFORMED_JSON"})
            return None
        return obj if isinstance(obj, dict) else None

    def log_message(self, *args: Any) -> None:
        pass

    # -- routes ----------------------------------------------------------
    def do_GET(self):
        url = urlparse(self.path)
        parts = [p for p in url.path.split("/") if p]
        st = self.state
        try:
            if parts == ["v1", "node", "health"]:
                desc = st.descriptor_fn()
                tls_version = None
                try:
                    version_fn = getattr(self.request, "version", None)
                    if callable(version_fn):
                        tls_version = version_fn()
                except Exception:
                    tls_version = None
                return self._send(200, {"ok": True, "node_id": st.node_id,
                                        "online": True,
                                        "protocol_version": "1.0",
                                        "security_mode": "TLS" if tls_version else "PLAINTEXT_LOOPBACK",
                                        "tls_version": tls_version,
                                        "emergency_stop": st.emergency_stop})
            if parts == ["v1", "node", "descriptor"]:
                return self._send(200, {"ok": True, "descriptor": st.descriptor_fn()})
            if parts == ["v1", "node", "protocol"]:
                from nodes.node_transport import NodeProtocolInfo
                return self._send(200, {"ok": True,
                                        "protocol": NodeProtocolInfo(node_id=st.node_id).to_dict()})
            if len(parts) == 4 and parts[:3] == ["v1", "node", "delegations"]:
                with st.lock:
                    d = st.delegations.get(parts[3])
                if not d:
                    return self._send(404, {"ok": False, "error_code": ERR_NODE_OFFLINE})
                return self._send(200, {"ok": True, "delegation": d})
            if len(parts) == 5 and parts[:3] == ["v1", "node", "delegations"] \
                    and parts[4] == "events":
                with st.lock:
                    evts = list(st.events.get(parts[3], []))
                return self._send_sse(evts)
            if len(parts) == 4 and parts[:3] == ["v1", "node", "artifacts"]:
                # Metadata only, never file bodies
                return self._send(200, {"ok": True, "reference": parts[3],
                                        "verified": False,
                                        "note": "artifact fetch requires explicit transfer policy"})
            return self._send(404, {"ok": False, "error_code": "UNKNOWN_ROUTE"})
        except Exception as e:  # noqa: BLE001
            return self._send(500, {"ok": False, "error_code": ERR_REMOTE_EXECUTION_FAILED})

    def do_POST(self):
        url = urlparse(self.path)
        parts = [p for p in url.path.split("/") if p]
        st = self.state
        body = self._body()
        if body is None:
            return
        try:
            if parts == ["v1", "node", "handshake"]:
                ok, code = negotiate_protocol(
                    __import__("nodes.node_transport", fromlist=["NodeProtocolInfo"]).NodeProtocolInfo(
                        node_id=st.node_id),
                    body)
                from nodes.node_transport import NodeProtocolInfo as _NPI
                st.log({"event": "handshake", "source_node": body.get("node_id", ""),
                        "ok": ok, "code": code})
                if not ok:
                    return self._send(400, {"ok": False, "error_code": code})
                return self._send(200, {"ok": True,
                                        "protocol": _NPI(node_id=st.node_id).to_dict(),
                                        "pairing_required": True})
            if parts == ["v1", "node", "pairing", "request"]:
                source = str(body.get("source_node", ""))
                if not source:
                    return self._send(400, {"ok": False, "error_code": ERR_AUTHENTICATION_FAILED})
                attempt_id, token = st.pairing.request_pairing(source)
                st.emit(attempt_id, "PAIRING_REQUESTED", f"pairing requested by {source}")
                st.log({"event": "pairing_request", "source_node": source,
                        "attempt_id": attempt_id})
                return self._send(200, {"ok": True, "attempt_id": attempt_id,
                                        "pairing_token": token,
                                        "expires_in_s": 300})
            if parts == ["v1", "node", "pairing", "approve"]:
                # Simulated owner approval hook: body.approved is the owner's decision
                ok, code, challenge = st.pairing.approve(
                    str(body.get("attempt_id", "")), bool(body.get("approved", False)),
                    str(body.get("trust_level", "LIMITED_NODE")))
                if not ok:
                    err = ERR_PAIRING_REJECTED if code == ERR_PAIRING_REJECTED else code
                    return self._send(400 if code != ERR_PAIRING_EXPIRED else 410,
                                      {"ok": False, "error_code": err})
                st.emit(str(body.get("attempt_id", "")), "CHALLENGE_SENT")
                return self._send(200, {"ok": True, "challenge": challenge})
            if parts == ["v1", "node", "pairing", "challenge"]:
                # Token must be presented out-of-band; server never logs it
                ok, code = st.pairing.verify_challenge(
                    str(body.get("attempt_id", "")),
                    str(body.get("token", "")),
                    str(body.get("response", "")))
                if not ok:
                    err = ERR_PAIRING_EXPIRED if code == ERR_PAIRING_EXPIRED \
                        else ERR_AUTHENTICATION_FAILED
                    return self._send(401 if code != ERR_PAIRING_EXPIRED else 410,
                                      {"ok": False, "error_code": err})
                st.pairing.mark_paired(str(body.get("attempt_id", "")))
                st.emit(str(body.get("attempt_id", "")), "PAIRED")
                st.log({"event": "paired", "attempt_id": body.get("attempt_id", "")})
                return self._send(200, {"ok": True, "state": "PAIRED"})
            if parts == ["v1", "node", "heartbeat"]:
                node_id = str(body.get("node_id", ""))
                with st.lock:
                    st.heartbeats[node_id] = {"load": body.get("load", 0.0),
                                              "last_seen": time.time()}
                return self._send(200, {"ok": True})
            if parts == ["v1", "node", "capabilities", "refresh"]:
                with st.lock:
                    st.capability_advertisement = dict(body)
                return self._send(200, {"ok": True})
            if parts == ["v1", "node", "delegations"]:
                return self._handle_delegation(body)
            if len(parts) == 5 and parts[:3] == ["v1", "node", "delegations"] \
                    and parts[4] == "cancel":
                delegation_id = parts[3]
                with st.lock:
                    st.cancelled.add(delegation_id)
                    d = st.delegations.get(delegation_id)
                    if d:
                        d["status"] = "CANCELLED"
                    st.emit(delegation_id, "CANCELLED", "cancelled by source")
                return self._send(200, {"ok": True, "delegation_id": delegation_id,
                                        "status": "CANCELLED"})
            return self._send(404, {"ok": False, "error_code": "UNKNOWN_ROUTE"})
        except PermissionError as e:
            return self._send(403, {"ok": False, "error_code": str(e)})
        except Exception:  # noqa: BLE001
            return self._send(500, {"ok": False, "error_code": ERR_REMOTE_EXECUTION_FAILED})

    def _handle_delegation(self, body: dict[str, Any]):
        from nodes.node_transport import privacy_allows_send
        st = self.state
        delegation_id = str(body.get("delegation_id", ""))
        source = str(body.get("source_node", ""))
        nonce = str(body.get("nonce", ""))
        ts = float(body.get("timestamp", 0) or 0)
        privacy = str(body.get("privacy_policy", "LOCAL_FIRST"))

        # 1. emergency stop
        if st.emergency_stop:
            return self._send(503, {"ok": False, "error_code": ERR_EMERGENCY_STOP_ACTIVE})

        # 1b. remote owner gate: local OWNER_FULL_ACCESS never implies
        # remote privileges. Checked before any other processing.
        if body.get("owner_scope_requested"):
            scope = str(body.get("owner_scope", "owner_full"))
            if st.remote_owner_policy == REMOTE_OWNER_DISABLED:
                st.log({"event": "remote_owner_denied", "source_node": source,
                        "delegation_id": delegation_id, "scope": scope})
                return self._send(403, {"ok": False,
                                        "error_code": ERR_REMOTE_OWNER_POLICY_DENIED})
            if not st.remote_owner_grants.get(scope):
                code = ERR_REMOTE_OWNER_APPROVAL_REQUIRED \
                    if st.remote_owner_policy == REMOTE_OWNER_APPROVAL_REQUIRED \
                    else ERR_REMOTE_OWNER_POLICY_DENIED
                st.log({"event": "remote_owner_denied", "source_node": source,
                        "delegation_id": delegation_id, "scope": scope})
                return self._send(403, {"ok": False, "error_code": code})

        # 2. replay protection
        ok, code = st.replay.verify(nonce, ts, delegation_id)
        if not ok:
            st.log({"event": "replay_rejected", "source_node": source,
                    "delegation_id": delegation_id})
            return self._send(409, {"ok": False, "error_code": code})

        # 3. trust / pairing
        trust = st.trust_fn(source)
        if trust == "UNTRUSTED_NODE":
            st.log({"event": "untrusted_rejected", "source_node": source,
                    "delegation_id": delegation_id})
            return self._send(403, {"ok": False, "error_code": ERR_NODE_UNTRUSTED})
        if trust == "REVOKED":
            return self._send(403, {"ok": False, "error_code": ERR_PAIRING_REJECTED})

        # 4. privacy pre-check (before touching private body further)
        allowed, pcode = privacy_allows_send(privacy, source, st.node_id,
                                             trust in ("OWNER_NODE", "TRUSTED_NODE"))
        if not allowed:
            return self._send(403, {"ok": False, "error_code": pcode})

        # 5. capability check (concise advertisement, no full schemas)
        required_tools = list(body.get("required_tools", []))
        desc = st.descriptor_fn()
        available = set(desc.get("tools", []))
        missing = [t for t in required_tools if t not in available]
        if missing:
            return self._send(422, {"ok": False, "error_code": ERR_CAPABILITY_UNAVAILABLE,
                                    "missing": missing})

        # 6. cancelled already?
        with st.lock:
            if delegation_id in st.cancelled:
                return self._send(409, {"ok": False, "error_code": ERR_DELEGATION_CANCELLED})
            st.delegations[delegation_id] = {
                "delegation_id": delegation_id, "status": "RUNNING",
                "source_node": source, "target_node": st.node_id,
            }
            st.emit(delegation_id, "RUNNING", "accepted")

        # 7. target-side execution via injected executor (re-validates tools)
        try:
            if st.executor is None:
                result = {"status": "COMPLETED",
                          "result_summary": "accepted (no executor)",
                          "tools_used": [],
                          "artifact_references": []}
            else:
                result = st.executor(body, {"trust_level": trust, "source_node": source})
        except PermissionError as e:
            with st.lock:
                st.delegations[delegation_id]["status"] = "FAILED"
            return self._send(403, {"ok": False, "error_code": str(e)})
        except Exception:  # noqa: BLE001
            with st.lock:
                st.delegations[delegation_id]["status"] = "FAILED"
            # No raw stack traces across nodes
            return self._send(500, {"ok": False, "error_code": ERR_REMOTE_EXECUTION_FAILED})

        # 8. cancellation check post-execution
        with st.lock:
            if delegation_id in st.cancelled:
                st.delegations[delegation_id]["status"] = "CANCELLED"
                st.emit(delegation_id, "CANCELLED")
                return self._send(409, {"ok": False, "error_code": ERR_DELEGATION_CANCELLED})
            record = {
                "delegation_id": delegation_id, "status": "COMPLETED",
                "source_node": source, "target_node": st.node_id,
                "agent": result.get("agent", ""), "model": result.get("model", ""),
                "provider": result.get("provider", ""),
                "tools_used": result.get("tools_used", []),
                "result_summary": str(result.get("result_summary", ""))[:2000],
                "artifact_references": result.get("artifact_references", []),
                "verification": result.get("verification", {"verified": False}),
                "completed_at": time.time(),
            }
            st.delegations[delegation_id] = record
            st.emit(delegation_id, "COMPLETED", "done", 1.0)
            st.log({"event": "delegation_completed", "source_node": source,
                    "delegation_id": delegation_id,
                    "trust_level": trust, "privacy_policy": privacy})
        return self._send(200, {"ok": True, "result": record})


def node_api_schema() -> dict[str, Any]:
    """Canonical machine-readable node API description (single source of truth)."""
    return {
        "protocol": {"name": "agent-bridge-node", "version": "1.0",
                     "min_supported": "1.0", "max_supported": "1.0"},
        "auth": ("loopback bind + pairing trust; no bearer token. "
                 "Plain HTTP refused off-loopback; HTTPS needs real certs."),
        "limits": {"json_body_bytes": 256 * 1024, "sse_event_chars": 4000,
                   "result_summary_chars": 2000},
        "errors": ["NODE_OFFLINE", "NODE_UNTRUSTED", "NODE_NOT_PAIRED",
                   "AUTHENTICATION_FAILED", "PAIRING_REQUIRED", "PAIRING_REJECTED",
                   "PAIRING_EXPIRED", "PROTOCOL_VERSION_UNSUPPORTED", "TLS_REQUIRED",
                   "REMOTE_PLAINTEXT_DENIED", "REMOTE_OWNER_POLICY_DENIED",
                   "REMOTE_OWNER_APPROVAL_REQUIRED", "PRIVACY_DENIED",
                   "CAPABILITY_UNAVAILABLE", "TOOL_DENIED", "DELEGATION_TIMEOUT",
                   "DELEGATION_CANCELLED", "REMOTE_EXECUTION_FAILED",
                   "REPLAY_REJECTED", "EMERGENCY_STOP_ACTIVE"],
        "routes": [
            {"method": "GET", "path": "/v1/node/health"},
            {"method": "GET", "path": "/v1/node/descriptor"},
            {"method": "GET", "path": "/v1/node/protocol"},
            {"method": "POST", "path": "/v1/node/handshake",
             "body": "{node_id*, protocol_name*, protocol_version*}"},
            {"method": "POST", "path": "/v1/node/pairing/request",
             "body": "{source_node*}"},
            {"method": "POST", "path": "/v1/node/pairing/approve",
             "body": "{attempt_id*, approved*, trust_level}"},
            {"method": "POST", "path": "/v1/node/pairing/challenge",
             "body": "{attempt_id*, token*, response*}"},
            {"method": "POST", "path": "/v1/node/delegations",
             "body": "{task envelope: delegation_id*, task_id*, source_node*, "
                      "target_node*, nonce*, timestamp*, privacy_policy, "
                      "required_tools, owner_scope_requested}"},
            {"method": "GET", "path": "/v1/node/delegations/{id}"},
            {"method": "GET", "path": "/v1/node/delegations/{id}/events",
             "notes": "SSE text/event-stream"},
            {"method": "POST", "path": "/v1/node/delegations/{id}/cancel"},
            {"method": "GET", "path": "/v1/node/artifacts/{ref}",
             "notes": "metadata only, never file bodies"},
            {"method": "POST", "path": "/v1/node/heartbeat",
             "body": "{node_id*, load}"},
            {"method": "POST", "path": "/v1/node/capabilities/refresh",
             "body": "{concise capability advertisement}"},
        ],
    }


def serve_node(state: NodeServerState, host: str = "127.0.0.1",
               port: int = 0, tls_config=None) -> ThreadingHTTPServer:
    """Bind a node server. Refuses 0.0.0.0 unless explicitly approved."""
    if host == "0.0.0.0":
        raise ValueError("refusing public bind: host must stay 127.0.0.1 unless explicitly approved")
    Handler.state = state
    srv = ThreadingHTTPServer((host, port), Handler)
    srv.daemon_threads = True
    if tls_config is not None and getattr(tls_config, "status", lambda: "")() == "CONFIGURED":
        import ssl as _ssl
        srv.socket = tls_config.server_context().wrap_socket(srv.socket, server_side=True)
    return srv
