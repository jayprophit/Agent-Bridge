"""Live Supervisor Dashboard — backend read-model + loopback API (V1 slice).

WHY THIS MODULE EXISTS
======================

The owner needs to SEE the Aetherius/Genesis workforce while it runs — Hermes,
subagents, OpenCode, models, projects, tasks, tests, repos — as real operational
state, not a mockup. This module is the data half of that dashboard.

DESIGN LAW (§49 of the supervisor constitution)
===============================================

This module does NOT invent a parallel event bus, worker registry, or transport.
It is an ADAPTER + NORMALISER + READ-MEL over systems that already exist:

  - events.py::EventBus        -> the canonical pub/sub; we subscribe("*").
  - compute/team_registry.py   -> canonical worker/team/RACI identity.
  - nodes/node_server.py       -> the stdlib HTTP + SSE framing pattern we mirror.

We add only what genuinely has no existing equivalent:
  - git telemetry adapter (subprocess, read-only)
  - Ollama model adapter (loopback HTTP)
  - the normalised supervisor snapshot + a loopback SSE stream

HONESTY (§29, §34, §1 of the dashboard brief)
=============================================

Every value carries a source-state. We never fabricate:
  LIVE_VERIFIED  we executed/observed the real thing this cycle
  LIVE           a real, currently-connected source reported it
  STALE          a real source reported it, but it has aged past freshness
  DEGRADED       source reachable but partially failing
  OFFLINE        source known but not reachable right now
  FIXTURE        demo/sample data, never shown as live
  UNKNOWN        no source could determine it
  BLOCKED        a real source exists but is gated (creds/permission)
  NOT_EXPOSED    the backend interface does not exist yet (honest placeholder)
  DEFERRED_BACKEND_INTERFACE  same, explicitly deferred

An unreachable runtime produces an honest empty/unknown view, never a
convincing fabricated one. Secrets are never placed on the wire (the EventLogger
already strips them; adapters add no secret fields).
"""
from __future__ import annotations

import json
import subprocess
import threading
import time
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Optional
from urllib.parse import urlparse

# --- source-state vocabulary (single source of truth) -----------------------
LIVE_VERIFIED = "LIVE_VERIFIED"
LIVE = "LIVE"
STALE = "STALE"
DEGRADED = "DEGRADED"
OFFLINE = "OFFLINE"
FIXTURE = "FIXTURE"
UNKNOWN = "UNKNOWN"
BLOCKED = "BLOCKED"
NOT_EXPOSED = "NOT_EXPOSED"
DEFERRED_BACKEND_INTERFACE = "DEFERRED_BACKEND_INTERFACE"

SOURCE_STATES = frozenset({
    LIVE_VERIFIED, LIVE, STALE, DEGRADED, OFFLINE, FIXTURE,
    UNKNOWN, BLOCKED, NOT_EXPOSED, DEFERRED_BACKEND_INTERFACE,
})

# Freshness window: a source-reported value older than this is STALE, not LIVE.
FRESHNESS_WINDOW_S = 30.0

SCHEMA_VERSION = 1


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _now() -> float:
    return time.time()


class SourceFact:
    """A single observed value tagged with its honesty state.

    `observed_at` is when the real source produced it. `state` is computed by
    the caller (or defaulted LIVE for a fresh observation). The dashboard
    renders the state; it never upgrades a value's honesty on its own.
    """

    __slots__ = ("value", "state", "observed_at", "source", "note")

    def __init__(self, value: Any, state: str, source: str,
                 observed_at: Optional[float] = None, note: str = ""):
        if state not in SOURCE_STATES:
            raise ValueError(f"unknown source-state: {state!r}")
        self.value = value
        self.state = state
        self.source = source
        self.observed_at = observed_at if observed_at is not None else _now()
        self.note = note

    def age_s(self) -> float:
        return max(0.0, _now() - self.observed_at)

    def effective_state(self) -> str:
        """A fresh LIVE/LIVE_VERIFIED stays; an aged one degrades to STALE.
        Non-live states are never upgraded by time."""
        if self.state in (LIVE, LIVE_VERIFIED) and self.age_s() > FRESHNESS_WINDOW_S:
            return STALE
        return self.state

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "state": self.effective_state(),
            "source": self.source,
            "observed_at": datetime.fromtimestamp(
                self.observed_at, timezone.utc).isoformat(timespec="seconds"),
            "age_s": round(self.age_s(), 2),
            "note": self.note,
        }


def fact(value: Any, state: str, source: str, note: str = "") -> SourceFact:
    return SourceFact(value, state, source, note=note)


def not_exposed(what: str, source: str = "backend") -> SourceFact:
    """Honest placeholder for a backend interface that does not exist yet."""
    return SourceFact(None, NOT_EXPOSED, source, note=f"{what} not exposed by backend")


def deferred(what: str, source: str = "backend") -> SourceFact:
    return SourceFact(None, DEFERRED_BACKEND_INTERFACE, source,
                      note=f"{what} deferred backend interface")


# --- git telemetry adapter (read-only, stdlib subprocess) -------------------
def read_git_state(repo_path: str) -> dict[str, SourceFact]:
    """Real git state for a repo. Every field is a SourceFact. Read-only."""
    def _git(*args: str) -> tuple[int, str]:
        try:
            p = subprocess.run(
                ["git", "-C", repo_path, *args],
                capture_output=True, text=True, timeout=10,
            )
            return p.returncode, (p.stdout or "").strip()
        except (OSError, subprocess.SubprocessError):
            return 1, ""

    rc_head, head = _git("rev-parse", "--short", "HEAD")
    rc_branch, branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    rc_ab, ab = _git("rev-list", "--left-right", "--count", "@{u}...HEAD")
    rc_status, status = _git("status", "--porcelain")
    rc_log, logline = _git("log", "-1", "--pretty=%h %s")

    if rc_head != 0:
        return {"repo": fact(repo_path, OFFLINE, "git",
                             note="git rev-parse failed (not a repo or git missing)")}

    facts: dict[str, SourceFact] = {
        "head": fact(head, LIVE_VERIFIED, "git"),
        "branch": fact(branch, LIVE_VERIFIED, "git"),
    }
    if rc_ab == 0 and ab:
        # "behind<TAB>ahead" from @{u}...HEAD
        parts = ab.replace("\t", " ").split()
        if len(parts) == 2:
            facts["behind"] = fact(int(parts[0]), LIVE_VERIFIED, "git")
            facts["ahead"] = fact(int(parts[1]), LIVE_VERIFIED, "git")
        else:
            facts["ahead_behind"] = fact(ab, LIVE_VERIFIED, "git")
    else:
        facts["upstream"] = fact(None, UNKNOWN, "git", note="no upstream configured")
    dirty = [ln for ln in status.splitlines() if ln.strip()] if rc_status == 0 else []
    facts["dirty_count"] = fact(len(dirty), LIVE_VERIFIED, "git")
    facts["dirty_files"] = fact(dirty[:50], LIVE_VERIFIED, "git")
    if rc_log == 0:
        facts["last_commit"] = fact(logline, LIVE_VERIFIED, "git")
    return facts


# --- Ollama model adapter (loopback HTTP) -----------------------------------
def read_ollama_state(base_url: str = "http://127.0.0.1:11434",
                      timeout: float = 4.0) -> dict[str, SourceFact]:
    """Real Ollama runtime state. Read-only loopback GET."""
    def _get(path: str) -> tuple[Optional[dict], str]:
        try:
            with urllib.request.urlopen(base_url + path, timeout=timeout) as r:
                return json.loads(r.read().decode()), ""
        except Exception as e:  # noqa: BLE001
            return None, f"{type(e).__name__}: {e}"

    ver, ver_err = _get("/api/version")
    if ver is None:
        return {"ollama": fact(None, OFFLINE, "ollama", note=ver_err or "unreachable")}
    facts: dict[str, SourceFact] = {
        "version": fact(ver.get("version"), LIVE_VERIFIED, "ollama"),
    }
    ps, _ = _get("/api/ps")
    if ps is not None:
        resident = [m.get("name") for m in ps.get("models", [])]
        facts["resident_models"] = fact(resident, LIVE_VERIFIED, "ollama")
    else:
        facts["resident_models"] = fact([], DEGRADED, "ollama", note="/api/ps failed")
    return facts


# --- normaliser -------------------------------------------------------------
class SupervisorState:
    """The normalised read-model. Holds the latest snapshot and an event ring.

    Subscribes to an EventBus via "*" and folds each event into a bounded
    history. Adapters refresh the snapshot on demand. Thread-safe.
    """

    def __init__(self, bus: Any = None, event_ring: int = 500):
        self._lock = threading.RLock()
        self.schema_version = SCHEMA_VERSION
        self.started_at = _now_iso()
        self.supervisor = "hermes"
        self.session_id = ""
        self._snapshot: dict[str, Any] = {}
        self._events: list[dict[str, Any]] = []
        self._event_ring = event_ring
        self._seq = 0
        self._bus = bus
        if bus is not None:
            try:
                bus.subscribe("*", self._on_bus_event)
            except Exception:  # noqa: BLE001
                pass

    # -- event ingestion ----------------------------------------------------
    def _on_bus_event(self, evt: dict[str, Any]) -> None:
        with self._lock:
            self._seq += 1
            self._events.append({
                "seq": self._seq,
                "received_at": _now_iso(),
                "event": evt,
            })
            if len(self._events) > self._event_ring:
                self._events = self._events[-self._event_ring:]

    def ingest(self, evt: dict[str, Any]) -> None:
        """Manual ingestion (for sources not on the bus, e.g. node_server)."""
        self._on_bus_event(evt)

    def events_since(self, last_seq: int = 0) -> list[dict[str, Any]]:
        with self._lock:
            return [e for e in self._events if e["seq"] > last_seq]

    @property
    def last_seq(self) -> int:
        with self._lock:
            return self._seq

    # -- snapshot -----------------------------------------------------------
    def set_section(self, name: str, data: dict[str, Any]) -> None:
        with self._lock:
            self._snapshot[name] = data

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "schema_version": self.schema_version,
                "supervisor": self.supervisor,
                "session_id": self.session_id,
                "generated_at": _now_iso(),
                "last_event_seq": self._seq,
                "sections": json.loads(json.dumps(self._snapshot, default=str)),
            }


# --- refresh wiring ---------------------------------------------------------
def refresh_snapshot(state: SupervisorState, repos: dict[str, str],
                     ollama_url: str = "http://127.0.0.1:11434") -> None:
    """Pull real adapter data into the snapshot. Call on a timer or per-request.

    `repos` maps a project label -> absolute repo path. This is read-only.
    TeamRegistry workers are read via an optional injected reader (see
    build_supervisor_server) to avoid a hard import cycle.
    """
    git_section: dict[str, Any] = {}
    for label, path in repos.items():
        git_section[label] = {k: v.to_dict() for k, v in read_git_state(path).items()}
    state.set_section("repositories", git_section)

    oll = {k: v.to_dict() for k, v in read_ollama_state(ollama_url).items()}
    state.set_section("local_models", oll)

    workers_reader: Any = getattr(state, "_workers_reader", None)
    if callable(workers_reader):
        try:
            state.set_section("workers", workers_reader())
        except Exception as e:  # noqa: BLE001
            state.set_section("workers", {"error": fact(str(e), DEGRADED, "team_registry").to_dict()})
    else:
        state.set_section("workers", {
            "note": fact("team_registry reader not wired", NOT_EXPOSED,
                         "team_registry").to_dict()})


# --- loopback HTTP + SSE server (mirrors node_server framing) ---------------
class _SupHandler(BaseHTTPRequestHandler):
    state: SupervisorState
    server_version = "AetheriusSupervisor/0.1"

    def _send(self, code: int, obj: Any) -> None:
        body = json.dumps(obj, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_sse(self, events: list[dict[str, Any]]) -> None:
        # Same framing as node_server._send_sse so clients share one parser.
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        for i, e in enumerate(events):
            line = f"id: {e.get('seq', i)}\nevent: supervisor\n" \
                   f"data: {json.dumps(e, default=str)[:4000]}\n\n"
            self.wfile.write(line.encode())

    def do_GET(self) -> None:  # noqa: N802
        url = urlparse(self.path)
        parts = [p for p in url.path.split("/") if p]
        st = self.state
        try:
            if parts == ["v1", "supervisor", "health"]:
                return self._send(200, {"ok": True, "supervisor": st.supervisor,
                                        "schema_version": st.schema_version,
                                        "last_event_seq": st.last_seq})
            if parts == ["v1", "supervisor", "state"]:
                return self._send(200, {"ok": True, "snapshot": st.snapshot()})
            if parts == ["v1", "supervisor", "events"]:
                # Cursor via ?since=<seq>; default 0 = full ring.
                q = url.query
                since = 0
                for kv in q.split("&"):
                    if kv.startswith("since="):
                        try:
                            since = int(kv.split("=", 1)[1])
                        except ValueError:
                            since = 0
                return self._send_sse(st.events_since(since))
            return self._send(404, {"ok": False, "error_code": "UNKNOWN_ROUTE"})
        except Exception as e:  # noqa: BLE001
            return self._send(500, {"ok": False, "error_code": "SUPERVISOR_ERROR",
                                    "detail": type(e).__name__})

    def log_message(self, *args: Any) -> None:
        pass


def build_supervisor_server(state: SupervisorState, host: str = "127.0.0.1",
                            port: int = 0) -> ThreadingHTTPServer:
    """Bind the supervisor API. Loopback-only, same rule as node_server."""
    if host == "0.0.0.0":
        raise ValueError("refusing public bind: supervisor API stays on 127.0.0.1")
    _SupHandler.state = state
    srv = ThreadingHTTPServer((host, port), _SupHandler)
    srv.daemon_threads = True
    return srv

