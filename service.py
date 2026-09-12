"""Local /v1 HTTP service (v0.5, stdlib http.server only).

Binds 127.0.0.1 by default — never 0.0.0.0 unless explicitly configured.
Guards: bearer token (optional), request size caps, per-IP rate limiting,
timeouts, CORS disabled, no bypass endpoints (everything flows through
session -> protocol -> policy -> approval -> executor -> verification).
Adds: model inventory, session listing, diff/manifest/export/scorecard/
timeline, final-gate resolution, revision requests, diagnostics,
self-check, and SSE event streaming with Last-Event-ID recovery.
"""
from __future__ import annotations

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from runtime import AgentRuntime, RuntimeConfig
from versions import API_VERSION


class _State:
    def __init__(self, runtime: AgentRuntime, cfg: RuntimeConfig):
        self.runtime = runtime
        self.cfg = cfg
        self.hits: dict[str, list[float]] = {}
        self.lock = threading.Lock()


def _rate_ok(state: _State, ip: str) -> bool:
    now = time.time()
    with state.lock:
        lst = [t for t in state.hits.get(ip, []) if now - t < 60]
        lst.append(now)
        state.hits[ip] = lst[-300:]
        return len(lst) <= state.runtime.cfg.rate_limit_per_min


class Handler(BaseHTTPRequestHandler):
    state: _State  # set by serve()
    server_version = "AgentRuntime/0.5"

    # -- helpers ----------------------------------------------------------
    def _send(self, code: int, obj: Any) -> None:
        body = json.dumps(obj, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        # CORS disabled by default: no Access-Control-Allow-Origin header.
        self.end_headers()
        self.wfile.write(body)

    def _guard(self) -> str | None:
        if not _rate_ok(self.state, self.client_address[0]):
            self._send(429, {"ok": False, "error": "rate limited"})
            return None
        token = self.state.runtime.cfg.token
        if token:
            auth = self.headers.get("Authorization", "")
            if auth != f"Bearer {token}":
                self._send(401, {"ok": False, "error": "invalid token"})
                return None
        return self.client_address[0]

    def _body(self) -> dict | None:
        try:
            n = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            n = 0
        if n > self.state.runtime.cfg.max_request_bytes:
            self._drain(n)  # avoid RST race: consume before refusing
            self._send(413, {"ok": False, "error": "request too large"})
            return None
        try:
            raw = self.rfile.read(n) if n else b"{}"
            obj = json.loads(raw.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            self._send(400, {"ok": False, "error": "malformed JSON"})
            return None
        return obj if isinstance(obj, dict) else None

    def log_message(self, *args: Any) -> None:  # keep quiet; bridge logs instead
        pass

    def _drain(self, n: int) -> None:
        try:
            left = n
            while left > 0:
                chunk = self.rfile.read(min(left, 65536))
                if not chunk:
                    break
                left -= len(chunk)
        except (OSError, ValueError):
            pass

    # -- routes -------------------------------------------------------------
    def _q(self) -> dict[str, str]:
        q = parse_qs(urlparse(self.path).query)
        return {k: v[0] for k, v in q.items() if v}

    def do_GET(self):
        if self._guard() is None:
            return
        url = urlparse(self.path)
        parts = [p for p in url.path.split("/") if p]
        rt = self.state.runtime
        q = self._q()
        try:
            if parts == ["health"]:
                return self._send(200, rt.health())
            if parts == [API_VERSION, "capabilities"]:
                return self._send(200, rt.capabilities())
            if parts == [API_VERSION, "caps"]:
                return self._send(200, rt.machine_inventory())
            if parts == [API_VERSION, "models"]:
                return self._send(200, rt.model_inventory())
            if parts == [API_VERSION, "diagnostics"]:
                return self._send(200, rt.diagnostics())
            if parts == [API_VERSION, "selfcheck"]:
                return self._send(200, {"checks": rt.self_check()})
            if parts == [API_VERSION, "schema"]:
                return self._send(200, api_schema())
            if parts == [API_VERSION, "sessions"]:
                return self._send(200, {"sessions": rt.list_sessions(
                    status=q.get("status", ""), workspace=q.get("workspace", ""),
                    since_ts=float(q.get("since", "0") or 0))})
            if len(parts) == 3 and parts[:2] == [API_VERSION, "sessions"]:
                s = rt.get_session(parts[2])
                with s.lock:
                    return self._send(200, {"session_id": s.session_id,
                                            "status": s.status, "mode": s.mode,
                                            "tasks": {t: {"status": r.status}
                                                      for t, r in s.tasks.items()}})
            if len(parts) == 4 and parts[:2] == [API_VERSION, "sessions"] \
                    and parts[3] == "status":
                s = rt.get_session(parts[2])
                return self._send(200, s.status_dashboard())
            if len(parts) == 4 and parts[:2] == [API_VERSION, "sessions"] \
                    and parts[3] == "events":
                s = rt.get_session(parts[2])
                try:
                    since = int(q.get("since", "0") or 0)
                except ValueError:
                    since = 0
                return self._send(200, s.events_since(since))
            if len(parts) == 5 and parts[:2] == [API_VERSION, "sessions"] \
                    and parts[3] == "events" and parts[4] == "stream":
                return self._sse(parts[2])
            if len(parts) == 4 and parts[:2] == [API_VERSION, "sessions"] \
                    and parts[3] == "diff":
                s = rt.get_session(parts[2])
                return self._send(200, rt.session_diff(
                    parts[2], target=q.get("target", "session"),
                    path=q.get("path", ""), label=q.get("label", "")))
            if len(parts) == 4 and parts[:2] == [API_VERSION, "sessions"] \
                    and parts[3] == "manifest":
                return self._send(200, rt.session_manifest(parts[2]))
            if len(parts) == 4 and parts[:2] == [API_VERSION, "sessions"] \
                    and parts[3] == "scorecard":
                return self._send(200, rt.session_scorecard(parts[2]))
            if len(parts) == 4 and parts[:2] == [API_VERSION, "sessions"] \
                    and parts[3] == "timeline":
                return self._send(200, rt.session_timeline(parts[2]))
            if len(parts) == 4 and parts[:2] == [API_VERSION, "sessions"] \
                    and parts[3] == "export":
                fmt = q.get("format", "json")
                if fmt not in ("json", "markdown", "jsonl"):
                    return self._send(400, {"ok": False, "error": "bad format"})
                s = rt.get_session(parts[2])
                body = rt.export_result(parts[2], q.get("task", ""), fmt)
                payload = body.encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json"
                                 if fmt != "markdown" else "text/markdown")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return None
            return self._send(404, {"ok": False, "error": "unknown route"})
        except KeyError as e:
            return self._send(404, {"ok": False, "error": str(e)})
        except PermissionError as e:
            return self._send(403, {"ok": False, "error": str(e)})
        except Exception as e:
            return self._send(500, {"ok": False, "error": f"{type(e).__name__}"})

    def _sse(self, session_id: str):
        """Server-Sent Events with Last-Event-ID recovery and polling fallback."""
        rt = self.state.runtime
        try:
            s = rt.get_session(session_id)
        except KeyError as e:
            return self._send(404, {"ok": False, "error": str(e)})
        last = self.headers.get("Last-Event-ID", "")
        q = self._q()
        try:
            index = int(last or q.get("since", "0") or 0)
        except ValueError:
            index = 0
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        # close-delimited framing (no Content-Length on a stream)
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            deadline = time.time() + 120  # bounded stream window
            it = 0
            while time.time() < deadline:
                it += 1
                chunk = s.events_since(index)
                for e in chunk["events"]:
                    index += 1
                    line = f"id: {index}\nevent: {e.get('event', 'message')}\n" \
                           f"data: {json.dumps(e, default=str)[:4000]}\n\n"
                    self.wfile.write(line.encode())
                try:
                    self.wfile.flush()
                except (OSError, ValueError):
                    break
                with s.lock:
                    terminal = s.status in ("COMPLETED", "FAILED", "CANCELLED",
                                            "ROLLED_BACK", "INTERRUPTED")
                    pending = bool(s.pending_approvals) or bool(
                        getattr(s, "_gate", None))
                    nevents = len(s.events)
                if terminal and not pending and index >= nevents:
                    break
                time.sleep(0.5)  # no busy waiting; client may poll instead
        except (OSError, ValueError, ConnectionError):
            pass
        finally:
            self.close_connection = True
        return None

    def do_POST(self):
        if self._guard() is None:
            return
        url = urlparse(self.path)
        parts = [p for p in url.path.split("/") if p]
        rt = self.state.runtime
        body = self._body()
        if body is None:
            return self._send(400, {"ok": False, "error": "malformed JSON"})
        try:
            if parts == [API_VERSION, "sessions"]:
                ws = body.get("workspace", "")
                if not ws:
                    return self._send(400, {"ok": False, "error": "workspace required"})
                try:
                    s = rt.create_session(
                        ws, mode=body.get("mode", ""),
                        approval=body.get("approval", ""),
                        model=body.get("model", ""),
                        roles=body.get("roles"),
                        profile=body.get("profile", ""),
                        owner_authorized=bool(body.get("owner_authorized", False)),
                        network_policy=body.get("network_policy", ""))
                except PermissionError as e:
                    return self._send(403, {"ok": False, "error": str(e)})
                return self._send(201, {"session_id": s.session_id, "mode": s.mode})
            if len(parts) == 4 and parts[:2] == [API_VERSION, "sessions"] \
                    and parts[3] == "tasks":
                s = rt.get_session(parts[2])
                text = body.get("text", "")
                if not text:
                    return self._send(400, {"ok": False, "error": "text required"})
                tid = s.submit_task(text, body.get("idempotency_key", ""),
                                    parent_task_id=body.get("parent_task_id", ""))
                return self._send(202, {"task_id": tid,
                                        "status": s.tasks[tid].status,
                                        "deduped": bool(s.last_submit_deduped)})
            if len(parts) == 4 and parts[:2] == [API_VERSION, "sessions"] \
                    and parts[3] == "revise":
                s = rt.get_session(parts[2])
                instruction = body.get("instruction", "")
                if not instruction:
                    return self._send(400, {"ok": False, "error": "instruction required"})
                try:
                    child = s.request_revision(body.get("task_id", ""), instruction)
                except KeyError as e:
                    return self._send(404, {"ok": False, "error": str(e)})
                return self._send(202, {"child_task_id": child})
            if len(parts) == 4 and parts[:2] == [API_VERSION, "sessions"] \
                    and parts[3] == "final":
                s = rt.get_session(parts[2])
                try:
                    return self._send(200, s.resolve_final(
                        body.get("task_id", ""), body.get("decision", ""),
                        body.get("note", "")))
                except (KeyError, ValueError) as e:
                    return self._send(404 if isinstance(e, KeyError) else 400,
                                      {"ok": False, "error": str(e)})
            if len(parts) == 4 and parts[:2] == [API_VERSION, "sessions"] \
                    and parts[3] == "cancel":
                s = rt.get_session(parts[2])
                tids = body.get("task_id", "")
                return self._send(200, s.cancel_task(tids))
            if len(parts) == 5 and parts[:2] == [API_VERSION, "sessions"] \
                    and parts[3] == "approvals":
                s = rt.get_session(parts[2])
                try:
                    return self._send(200, s.resolve_approval(
                        parts[4], body.get("decision", "")))
                except (KeyError, ValueError) as e:
                    return self._send(404 if isinstance(e, KeyError) else 400,
                                      {"ok": False, "error": str(e)})
            if len(parts) == 4 and parts[:2] == [API_VERSION, "sessions"] \
                    and parts[3] == "rollback":
                s = rt.get_session(parts[2])
                return self._send(200, s.rollback(body.get("label", "")))
            if parts == [API_VERSION, "stop"]:
                reason = body.get("reason", "operator stop")
                return self._send(200, rt.emergency_stop(reason))
            if parts == [API_VERSION, "caps"]:
                return self._send(200, rt.machine_inventory())
            return self._send(404, {"ok": False, "error": "unknown route"})
        except PermissionError as e:
            return self._send(403, {"ok": False, "error": str(e)})
        except (KeyError, ValueError) as e:
            return self._send(400, {"ok": False, "error": str(e)})
        except Exception:
            return self._send(500, {"ok": False, "error": "internal error"})

    def do_DELETE(self):
        if self._guard() is None:
            return
        parts = [p for p in urlparse(self.path).path.split("/") if p]
        if len(parts) == 3 and parts[:2] == [API_VERSION, "sessions"]:
            try:
                return self._send(200, self.state.runtime.delete_session(parts[2]))
            except (KeyError, ValueError) as e:
                code = 404 if isinstance(e, KeyError) else 409
                return self._send(code, {"ok": False, "error": str(e)})
        return self._send(404, {"ok": False, "error": "unknown route"})

    def do_PUT(self):
        return self._send(405, {"ok": False, "error": "method not allowed"})

    def do_PATCH(self):
        return self._send(405, {"ok": False, "error": "method not allowed"})


def api_schema() -> dict[str, Any]:
    """Lightweight machine-readable API description (no framework)."""
    from versions import API_VERSION as _V, COMPATIBILITY as _C
    return {
        "api": _V, "compat": _C,
        "auth": "optional Bearer token; 401 on mismatch",
        "errors": {"400": "malformed JSON / bad value", "401": "invalid token",
                   "403": "workspace outside roots", "404": "unknown route/id",
                   "405": "method not allowed", "409": "conflict (active tasks)",
                   "413": "request too large", "429": "rate limited",
                   "500": "internal error"},
        "routes": [
            {"method": "GET", "path": "/health"},
            {"method": "GET", "path": "/v1/capabilities"},
            {"method": "GET", "path": "/v1/models"},
            {"method": "GET", "path": "/v1/diagnostics"},
            {"method": "GET", "path": "/v1/selfcheck"},
            {"method": "GET", "path": "/v1/schema"},
            {"method": "GET", "path": "/v1/sessions?status=&workspace=&since="},
            {"method": "POST", "path": "/v1/sessions",
             "body": "{workspace*, mode, approval, model, roles, profile, "
                     "owner_authorized, network_policy}"},
            {"method": "GET", "path": "/v1/sessions/{id}"},
            {"method": "GET", "path": "/v1/sessions/{id}/status"},
            {"method": "POST", "path": "/v1/sessions/{id}/tasks",
             "body": "{text*, idempotency_key, parent_task_id}"},
            {"method": "POST", "path": "/v1/sessions/{id}/revise",
             "body": "{task_id*, instruction*}"},
            {"method": "POST", "path": "/v1/sessions/{id}/cancel",
             "body": "{task_id*}"},
            {"method": "POST", "path": "/v1/sessions/{id}/final",
             "body": "{task_id*, decision: accept|revise|rollback|cancel, note}"},
            {"method": "GET", "path": "/v1/sessions/{id}/events?since="},
            {"method": "GET", "path": "/v1/sessions/{id}/events/stream",
             "notes": "SSE, Last-Event-ID recovery, polling fallback"},
            {"method": "POST", "path": "/v1/sessions/{id}/approvals/{aid}",
             "body": "{decision: approve-once|approve-session|deny}"},
            {"method": "POST", "path": "/v1/sessions/{id}/rollback",
             "body": "{label}"},
            {"method": "GET", "path": "/v1/sessions/{id}/diff?target=&path=&label="},
            {"method": "GET", "path": "/v1/sessions/{id}/manifest"},
            {"method": "GET", "path": "/v1/sessions/{id}/scorecard"},
            {"method": "GET", "path": "/v1/sessions/{id}/timeline"},
            {"method": "GET", "path": "/v1/sessions/{id}/export?format=json|markdown|jsonl"},
            {"method": "DELETE", "path": "/v1/sessions/{id}"},
            {"method": "POST", "path": "/v1/stop",
             "body": "{reason}"},
            {"method": "GET", "path": "/v1/caps"},
        ],
        "transitions": ["QUEUED", "PLANNING", "EXECUTING", "WAITING_APPROVAL",
                        "TESTING", "REVIEWING", "REVISING", "COMPLETED",
                        "FAILED", "CANCELLED", "ROLLED_BACK", "INTERRUPTED",
                        "WAITING_FINAL_APPROVAL"],
    }


def serve(runtime: AgentRuntime, host: str = "", port: int = 0) -> ThreadingHTTPServer:
    host = host or runtime.cfg.host or "127.0.0.1"
    if host == "0.0.0.0" and not getattr(runtime.cfg, "_public_ok", False):
        raise ValueError("refusing public bind: host must stay 127.0.0.1 unless explicitly approved")
    port = port or runtime.cfg.port
    Handler.state = _State(runtime, runtime.cfg)
    srv = ThreadingHTTPServer((host, port), Handler)
    srv.daemon_threads = True
    return srv


def main(argv: list[str] | None = None) -> int:
    import argparse
    p = argparse.ArgumentParser(description="Agent runtime local service")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8471)
    p.add_argument("--root", action="append", default=[],
                   help="allowed workspace root (repeatable)")
    p.add_argument("--token", default="")
    p.add_argument("--profile", default="",
                   choices=["", "SAFE_EXPLORATION", "ASSISTED_BUILD",
                            "AUTONOMOUS_SANDBOX", "PRECIOUS_PROJECT",
                            "OWNER_FULL_ACCESS"])
    p.add_argument("--owner-authorized", action="store_true",
                   help="explicit machine-owner authorization (with --profile OWNER_FULL_ACCESS)")
    p.add_argument("--network", default="",
                   choices=["", "LOCAL_MODEL_NETWORK", "EXTERNAL_NETWORK",
                            "NO_NETWORK"])
    args = p.parse_args(argv)
    from runtime import RuntimeConfig
    cfg = RuntimeConfig(host=args.host, port=args.port,
                        allowed_workspace_roots=args.root or
                        [os.getenv("AGENT_BRIDGE_ROOT", ".")],
                        token=args.token,
                        profile=args.profile,
                        owner_authorized=args.owner_authorized,
                        network_policy=args.network or "LOCAL_MODEL_NETWORK")
    if cfg.profile == "OWNER_FULL_ACCESS" and not cfg.owner_authorized:
        p.error("--profile OWNER_FULL_ACCESS requires --owner-authorized")
    rt = AgentRuntime(cfg)
    srv = serve(rt, args.host, args.port)
    print(f"serving /v1 on http://{args.host}:{srv.server_address[1]}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
