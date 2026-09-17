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
        self.terminals: dict[str, Any] = {}  # workspace -> TerminalManager

    def terminal_manager(self) -> Any:
        """Policy-gated terminal sessions rooted at the first allowed root."""
        from terminal import TerminalManager
        roots = list(getattr(self.cfg, "allowed_workspace_roots", []) or [])
        key = roots[0] if roots else "."
        with self.lock:
            mgr = self.terminals.get(key)
            if mgr is None:
                mgr = TerminalManager(key)
                self.terminals[key] = mgr
            return mgr


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
    def _cors_headers(self) -> dict[str, str]:
        """Owner-approved cross-origin exceptions (default: none).

        The service deliberately sends no ACAO header unless the request
        Origin is explicitly allowlisted (cfg.cors_origins, --cors-origin).
        This keeps arbitrary websites from driving the loopback API while
        letting the owner's IDE origin integrate. Never '*' (would combine
        with Bearer auth into a CSRF-equivalent hole).
        """
        try:
            allowed = list(getattr(self.state.runtime.cfg,
                                   "cors_origins", []) or [])
        except Exception:
            allowed = []
        origin = (self.headers.get("Origin", "") or "").strip()
        if origin and origin in allowed:
            return {"Access-Control-Allow-Origin": origin,
                    "Vary": "Origin"}
        return {}

    def _send_cors_headers(self) -> None:
        for k, v in self._cors_headers().items():
            self.send_header(k, v)

    def _send(self, code: int, obj: Any) -> None:
        body = json.dumps(obj, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        """CORS preflight: 204 with allowlisted origin only (else bare)."""
        self.send_response(204)
        self._send_cors_headers()
        self.send_header("Access-Control-Allow-Methods",
                         "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers",
                         "Authorization, Content-Type")
        self.send_header("Access-Control-Max-Age", "600")
        self.end_headers()

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
            if parts == [API_VERSION, "terminal", "sessions"]:
                return self._send(200, {"sessions": self.state.terminal_manager().list()})
            if len(parts) == 4 and parts[:2] == [API_VERSION, "terminal"] \
                    and parts[2] == "sessions":
                try:
                    return self._send(200, self.state.terminal_manager().get(
                        parts[3]).to_dict())
                except KeyError as e:
                    return self._send(404, {"ok": False, "error": str(e)})
            if parts == [API_VERSION, "models"]:
                return self._send(200, rt.model_inventory())
            if parts == [API_VERSION, "workspace", "files"]:
                from workspace_api import WorkspaceAPI
                api = WorkspaceAPI(list(getattr(
                    self.state.runtime.cfg, "allowed_workspace_roots", []) or []))
                try:
                    return self._send(200, api.list(
                        q.get("root", ""), q.get("path", "")))
                except (PermissionError, ValueError) as e:
                    return self._send(403, {"ok": False, "error": str(e)})
            if parts == [API_VERSION, "workspace", "file"]:
                from workspace_api import WorkspaceAPI
                api = WorkspaceAPI(list(getattr(
                    self.state.runtime.cfg, "allowed_workspace_roots", []) or []))
                try:
                    return self._send(200, api.read(
                        q.get("root", ""), q.get("path", "")))
                except (PermissionError, ValueError) as e:
                    return self._send(403, {"ok": False, "error": str(e)})
            if parts == [API_VERSION, "workspace", "search"]:
                from workspace_api import WorkspaceAPI
                api = WorkspaceAPI(list(getattr(
                    self.state.runtime.cfg, "allowed_workspace_roots", []) or []))
                if not q.get("pattern", ""):
                    return self._send(400, {"ok": False, "error": "pattern required"})
                try:
                    return self._send(200, api.search(
                        q.get("root", ""), q.get("pattern", ""),
                        q.get("path", ""), q.get("glob", "*")))
                except (PermissionError, ValueError) as e:
                    return self._send(403, {"ok": False, "error": str(e)})
            if parts == [API_VERSION, "git"]:
                from workspace_api import WorkspaceAPI
                api = WorkspaceAPI(list(getattr(
                    self.state.runtime.cfg, "allowed_workspace_roots", []) or []))
                try:
                    return self._send(200, api.git(
                        q.get("root", ""), q.get("op", "status")))
                except (PermissionError, ValueError) as e:
                    return self._send(403, {"ok": False, "error": str(e)})
            if parts == [API_VERSION, "runtime"]:
                from ide_bridge import build_runtime_snapshot
                return self._send(200, build_runtime_snapshot(
                    rt, None, getattr(rt, "genesis_runtime", None)))
            if parts == [API_VERSION, "taskcenter"]:
                tc = _taskcenter()
                prog = tc.progress()
                return self._send(200, {"progress": prog, "tree": tc.tree(),
                                        "adaptations": tc.adaptations,
                                        "problems": tc.problems,
                                        "loop_telemetry": _loop_telemetry()})
            if parts == [API_VERSION, "taskcenter", "view"]:
                tc = _taskcenter()
                task_id = q.get("task_id", "") or None
                body = tc.render_html(task_id).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(body)
                return None
            if parts == [API_VERSION, "chain"]:
                ob = _observer()
                task_id = q.get("task_id", "")
                if not task_id:
                    return self._send(400, {"ok": False,
                                            "error": "task_id required"})
                return self._send(200, {"chain": ob.chain(task_id),
                                        "current": ob.current_step(task_id),
                                        "summary": ob.summary(task_id)})
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
                self._send_cors_headers()
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
        self._send_cors_headers()
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
            if parts == [API_VERSION, "taskcenter", "tasks"]:
                tc = _taskcenter()
                if not body.get("objective", ""):
                    return self._send(400, {"ok": False,
                                            "error": "objective required"})
                try:
                    node = tc.add(
                        objective=str(body.get("objective", "")),
                        parent_id=str(body.get("parent_id", "") or ""),
                        status=str(body.get("status", "") or "PLANNED"),
                        supervisor=str(body.get("supervisor", "") or ""),
                        assigned_agent=str(body.get("assigned_agent", "") or ""),
                        assigned_model=str(body.get("assigned_model", "") or ""),
                        provider=str(body.get("provider", "") or ""),
                        execution_mode=str(body.get("execution_mode", "")
                                           or "DIRECT"),
                        sources=list(body.get("sources", []) or []),
                        next_action=str(body.get("next_action", "") or ""))
                except (KeyError, ValueError) as e:
                    return self._send(400, {"ok": False, "error": str(e)})
                return self._send(201, node.to_dict())
            if len(parts) == 5 and parts[:2] == [API_VERSION, "taskcenter"] \
                    and parts[2] == "tasks" and parts[4] == "edit":
                tc = _taskcenter()
                try:
                    node = tc.edit(
                        parts[3],
                        objective=body.get("objective"),
                        status=body.get("status"),
                        next_action=body.get("next_action"),
                        assigned_model=body.get("assigned_model"),
                        assigned_agent=body.get("assigned_agent"),
                        execution_mode=body.get("execution_mode"),
                        by=str(body.get("by", "") or ""),
                        reason=str(body.get("reason", "") or ""))
                except KeyError as e:
                    return self._send(404, {"ok": False, "error": str(e)})
                except ValueError as e:
                    return self._send(400, {"ok": False, "error": str(e)})
                return self._send(200, node.to_dict())
            if len(parts) == 5 and parts[:2] == [API_VERSION, "taskcenter"] \
                    and parts[2] == "tasks" and parts[4] == "copy":
                tc = _taskcenter()
                try:
                    if body.get("branch"):
                        node = tc.copy_branch(
                            parts[3],
                            str(body.get("new_parent_id", "") or ""),
                            str(body.get("by", "") or ""))
                    else:
                        node = tc.copy_task(
                            parts[3],
                            str(body.get("new_parent_id", "") or ""),
                            str(body.get("by", "") or ""))
                except KeyError as e:
                    return self._send(404, {"ok": False, "error": str(e)})
                return self._send(201, node.to_dict())
            if len(parts) == 5 and parts[:2] == [API_VERSION, "taskcenter"] \
                    and parts[2] == "tasks" and parts[4] == "status":
                tc = _taskcenter()
                try:
                    node = tc.set_status(
                        parts[3], str(body.get("status", "")),
                        str(body.get("by", "") or ""),
                        str(body.get("checkpoint", "") or ""),
                        str(body.get("next_action", "") or ""))
                except KeyError as e:
                    return self._send(404, {"ok": False, "error": str(e)})
                return self._send(200, node.to_dict())
            if parts == [API_VERSION, "caps"]:
                return self._send(200, rt.machine_inventory())
            if parts == [API_VERSION, "workspace", "file"]:
                from workspace_api import WorkspaceAPI
                api = WorkspaceAPI(list(getattr(
                    rt.cfg, "allowed_workspace_roots", []) or []))
                if not body.get("root", "") or "path" not in body \
                        or "content" not in body:
                    return self._send(400, {"ok": False,
                                            "error": "root, path, content required"})
                try:
                    res = api.write(body.get("root", ""), body.get("path", ""),
                                    body.get("content", ""))
                except (PermissionError, ValueError) as e:
                    return self._send(403, {"ok": False, "error": str(e)})
                return self._send(200 if res.get("ok") else 400, res)
            if parts == [API_VERSION, "workspace", "create"]:
                from workspace_api import WorkspaceAPI
                api = WorkspaceAPI(list(getattr(
                    rt.cfg, "allowed_workspace_roots", []) or []))
                root = body.get("root", "")
                path = body.get("path", "")
                is_dir = bool(body.get("is_dir", False))
                if not root or not path:
                    return self._send(400, {"ok": False,
                                            "error": "root, path required"})
                try:
                    res = api.create(root, path, is_dir)
                except (PermissionError, ValueError, FileExistsError) as e:
                    return self._send(403 if isinstance(e, PermissionError) else 409,
                                      {"ok": False, "error": str(e)})
                return self._send(201 if res.get("ok") else 400, res)
            if parts == [API_VERSION, "workspace", "rename"]:
                from workspace_api import WorkspaceAPI
                api = WorkspaceAPI(list(getattr(
                    rt.cfg, "allowed_workspace_roots", []) or []))
                root = body.get("root", "")
                old_path = body.get("old_path", "")
                new_path = body.get("new_path", "")
                if not root or not old_path or not new_path:
                    return self._send(400, {"ok": False,
                                            "error": "root, old_path, new_path required"})
                try:
                    res = api.rename(root, old_path, new_path)
                except (PermissionError, ValueError, FileNotFoundError) as e:
                    return self._send(403 if isinstance(e, PermissionError) else 404,
                                      {"ok": False, "error": str(e)})
                return self._send(200 if res.get("ok") else 400, res)
            if parts == [API_VERSION, "terminal", "sessions"]:
                mgr = self.state.terminal_manager()
                try:
                    s = mgr.create(body.get("cwd", ""))
                except (PermissionError, FileNotFoundError) as e:
                    return self._send(400, {"ok": False, "error": str(e)})
                return self._send(201, s.to_dict())
            if len(parts) == 5 and parts[:2] == [API_VERSION, "terminal"] \
                    and parts[2] == "sessions" and parts[4] == "exec":
                mgr = self.state.terminal_manager()
                command = body.get("command", "")
                if not command:
                    return self._send(400, {"ok": False, "error": "command required"})
                try:
                    timeout_s = float(body.get("timeout_s", 60) or 60)
                except (TypeError, ValueError):
                    return self._send(400, {"ok": False, "error": "bad timeout_s"})
                try:
                    res = mgr.exec(parts[3], command,
                                   timeout_s=min(timeout_s, 300),
                                   origin=body.get("origin", "user"))
                except KeyError as e:
                    return self._send(404, {"ok": False, "error": str(e)})
                return self._send(200, res)
            if len(parts) == 5 and parts[:2] == [API_VERSION, "terminal"] \
                    and parts[2] == "sessions" and parts[4] == "cancel":
                mgr = self.state.terminal_manager()
                try:
                    return self._send(200, mgr.cancel(parts[3]))
                except KeyError as e:
                    return self._send(404, {"ok": False, "error": str(e)})
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
        if parts == [API_VERSION, "workspace", "file"]:
            from workspace_api import WorkspaceAPI
            q = self._q()
            api = WorkspaceAPI(list(getattr(
                self.state.runtime.cfg, "allowed_workspace_roots", []) or []))
            root = q.get("root", "")
            path = q.get("path", "")
            if not root or not path:
                return self._send(400, {"ok": False,
                                        "error": "root, path required"})
            try:
                res = api.delete(root, path)
            except (PermissionError, ValueError, FileNotFoundError) as e:
                return self._send(403 if isinstance(e, PermissionError) else 404,
                                  {"ok": False, "error": str(e)})
            return self._send(200 if res.get("ok") else 400, res)
        return self._send(404, {"ok": False, "error": "unknown route"})

    def do_PUT(self):
        return self._send(405, {"ok": False, "error": "method not allowed"})

    def do_PATCH(self):
        return self._send(405, {"ok": False, "error": "method not allowed"})


def _taskcenter() -> Any:
    from pathlib import Path as _P
    from taskcenter import TaskCenter as _TC
    base = _P(__file__).resolve().parent / ".bridge" / "taskcenter.json"
    return _TC(base)


def _observer() -> Any:
    from pathlib import Path as _P
    from execution_observer import ExecutionObserver as _EO
    base = _P(__file__).resolve().parent / ".bridge" / "chain.json"
    return _EO(base)


def _loop_telemetry() -> dict[str, Any]:
    """Read-only violation/adaptation telemetry (§15). A missing or corrupt
    ledger yields zeros, never an error and never a state reset."""
    from pathlib import Path as _P
    import json as _json
    base = _P(__file__).resolve().parent / ".bridge" / "execution_contract.json"
    try:
        data = _json.loads(base.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"planned_ok": 0, "violations": {},
                "completions_without_verification": 0,
                "missing_reevaluations": 0, "adaptations": 0,
                "unchanged_continuations": 0, "reroutes": 0, "blocked": 0,
                "unresolved_bypasses": 0}
    tel = data.get("telemetry") or {}
    tel.setdefault("unresolved_bypasses",
                   sum((tel.get("violations") or {}).values()))
    return tel


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
            {"method": "GET", "path": "/v1/runtime"},
            {"method": "GET", "path": "/v1/taskcenter"},
            {"method": "GET", "path": "/v1/taskcenter/view?task_id="},
            {"method": "GET", "path": "/v1/chain?task_id="},
            {"method": "POST", "path": "/v1/taskcenter/tasks",
             "body": "{objective*, parent_id, status, supervisor, "
                     "assigned_agent, assigned_model, provider, "
                     "execution_mode, sources, next_action}"},
            {"method": "POST", "path": "/v1/taskcenter/tasks/{id}/edit",
             "body": "{objective, status, next_action, assigned_model, "
                     "assigned_agent, execution_mode, by, reason}"},
            {"method": "POST", "path": "/v1/taskcenter/tasks/{id}/copy",
             "body": "{branch: bool, new_parent_id, by}"},
            {"method": "POST", "path": "/v1/taskcenter/tasks/{id}/status",
             "body": "{status*, by, checkpoint, next_action}"},
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
            {"method": "GET", "path": "/v1/terminal/sessions"},
            {"method": "GET", "path": "/v1/terminal/sessions/{id}"},
            {"method": "POST", "path": "/v1/terminal/sessions",
             "body": "{cwd}"},
            {"method": "POST", "path": "/v1/terminal/sessions/{id}/exec",
             "body": "{command*, timeout_s, origin}"},
            {"method": "POST", "path": "/v1/terminal/sessions/{id}/cancel"},
            {"method": "GET", "path": "/v1/workspace/files?root=&path="},
            {"method": "GET", "path": "/v1/workspace/file?root=&path="},
            {"method": "POST", "path": "/v1/workspace/file",
             "body": "{root*, path*, content*}"},
            {"method": "POST", "path": "/v1/workspace/create",
             "body": "{root*, path*, is_dir?}"},
            {"method": "POST", "path": "/v1/workspace/rename",
             "body": "{root*, old_path*, new_path*}"},
            {"method": "DELETE", "path": "/v1/workspace/file?root=&path="},
            {"method": "GET", "path": "/v1/workspace/search?root=&pattern=&path=&glob="},
            {"method": "GET", "path": "/v1/git?root=&op=status|diff|branch|log"},
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
    # NOTE: port 0 means ephemeral (OS-assigned); only None falls back to cfg.
    # The old `port or cfg.port` silently redirected port 0 onto cfg.port,
    # colliding with live servers and contaminating tests.
    if port is None:
        port = runtime.cfg.port
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
    p.add_argument("--genesis-store", default="",
                   help="attach a Genesis identity store (JSON) so "
                        "/v1/runtime projects the live avatar state")
    p.add_argument("--cors-origin", action="append", default=[],
                   help="owner-approved browser origin for ACAO "
                        "(repeatable; default: none)")
    args = p.parse_args(argv)
    from runtime import RuntimeConfig
    cfg = RuntimeConfig(host=args.host, port=args.port,
                        allowed_workspace_roots=args.root or
                        [os.getenv("AGENT_BRIDGE_ROOT", ".")],
                        token=args.token,
                        cors_origins=list(args.cors_origin or []),
                        profile=args.profile,
                        owner_authorized=args.owner_authorized,
                        network_policy=args.network or "LOCAL_MODEL_NETWORK")
    if cfg.profile == "OWNER_FULL_ACCESS" and not cfg.owner_authorized:
        p.error("--profile OWNER_FULL_ACCESS requires --owner-authorized")
    rt = AgentRuntime(cfg)
    if args.genesis_store:
        from genesis_runtime import LocalGenesisRuntime
        rt.genesis_runtime = LocalGenesisRuntime(args.genesis_store)
    srv = serve(rt, args.host, args.port)
    print(f"serving /v1 on http://{args.host}:{srv.server_address[1]}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
