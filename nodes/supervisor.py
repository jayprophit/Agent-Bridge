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
import os
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


def read_team_registry(registry: Any) -> dict[str, SourceFact]:
    """Real worker/team identity from a TeamRegistry. Read-only.

    Uses list_workers()/list_teams(). Each worker is rendered with the fields
    the dashboard needs; counts are LIVE_VERIFIED because we just read them.
    An empty registry is honest (empty list), never a fabricated roster.
    """
    try:
        workers = registry.list_workers()
        teams = registry.list_teams()
    except Exception as e:  # noqa: BLE001
        return {"registry": fact(None, DEGRADED, "team_registry",
                                 note=f"list failed: {type(e).__name__}")}
    worker_rows = []
    for w in workers:
        worker_rows.append({
            "worker_id": getattr(w, "worker_id", None),
            "role_id": getattr(w, "role_id", None),
            "department": getattr(w, "department", None),
            "model_id": getattr(w, "model_id", None),
            "provider_id": getattr(w, "provider_id", None),
            "execution_target": getattr(w, "execution_target", None),
            "career_state": getattr(w, "career_state", None),
            "success_count": getattr(w, "success_count", None),
            "failure_count": getattr(w, "failure_count", None),
        })
    team_rows = []
    for t in teams:
        team_rows.append({
            "team_id": getattr(t, "team_id", None),
            "team_name": getattr(t, "team_name", None),
            "members": getattr(t, "members", []),
            "team_size": getattr(t, "team_size", None),
            "active_concurrency_limit": getattr(t, "active_concurrency_limit", None),
        })
    return {
        "worker_count": fact(len(workers), LIVE_VERIFIED, "team_registry"),
        "team_count": fact(len(teams), LIVE_VERIFIED, "team_registry"),
        "workers": fact(worker_rows, LIVE_VERIFIED, "team_registry"),
        "teams": fact(team_rows, LIVE_VERIFIED, "team_registry"),
    }


def _run_cli(cmd: list[str], timeout: float) -> subprocess.CompletedProcess:
    """Run a CLI robustly on Windows.

    `opencode`/`codex` are npm .cmd shims, not bare .exe, so subprocess.run
    raises FileNotFoundError even though the shell resolves them. Try the bare
    argv first; on FileNotFoundError retry through the shell. The shell retry
    uses subprocess.list2cmdline (Windows-native quoting) — NOT shlex.quote,
    whose single quotes cmd.exe does not interpret, which mangles SQL/flag
    arguments (verified: `opencode db "SELECT ..."` returned usage text).
    """
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return subprocess.run(subprocess.list2cmdline(cmd),
                              shell=True, capture_output=True, text=True, timeout=timeout)


def read_opencode_sessions(opencode_bin: str = "opencode",
                           timeout: float = 20.0) -> dict[str, SourceFact]:
    """Real OpenCode session inventory via `opencode session list`.

    This is the CLI telemetry verified in reconciliation §10 — structured,
    no auth, no screen-scraping. Returns honest OFFLINE if the CLI is missing
    or errors; never a fabricated session list.
    """
    try:
        p = _run_cli([opencode_bin, "session", "list"], timeout)
    except (OSError, subprocess.SubprocessError) as e:
        return {"opencode": fact(None, OFFLINE, "opencode-cli",
                                 note=f"{type(e).__name__}: {e}")}
    if p.returncode != 0:
        return {"opencode": fact(None, DEGRADED, "opencode-cli",
                                 note=f"exit {p.returncode}: {(p.stderr or '').strip()[:200]}")}
    lines = [ln for ln in (p.stdout or "").splitlines() if ln.strip()]
    # `opencode session list` prints a table; count non-empty data lines as a
    # real, honest lower-bound on sessions without over-parsing the table.
    return {
        "cli": fact("available", LIVE_VERIFIED, "opencode-cli"),
        "raw_line_count": fact(len(lines), LIVE_VERIFIED, "opencode-cli"),
        "listing": fact(lines[:60], LIVE_VERIFIED, "opencode-cli"),
    }


def read_opencode_session(opencode_bin: str = "opencode", session_id: str = "",
                          timeout: float = 30.0) -> dict[str, SourceFact]:
    """Real OpenCode session detail via `opencode export <id>` (JSON on stdout).

    Returns the session `info` fields the dashboard needs (id, title, agent,
    model, tokens, cost, time) as LIVE_VERIFIED. The 343-message `messages`
    array is NOT embedded in the snapshot (too large); we summarise counts.
    Honest OFFLINE/DEGRADED on CLI failure; never a fabricated session.
    """
    if not session_id:
        return {"opencode_session": fact(None, UNKNOWN, "opencode-cli",
                                         note="no session_id provided")}
    try:
        p = _run_cli([opencode_bin, "export", session_id], timeout)
    except (OSError, subprocess.SubprocessError) as e:
        return {"opencode_session": fact(None, OFFLINE, "opencode-cli",
                                         note=f"{type(e).__name__}: {e}")}
    if p.returncode != 0:
        return {"opencode_session": fact(None, DEGRADED, "opencode-cli",
                                         note=f"exit {p.returncode}")}
    try:
        data = json.loads(p.stdout)
    except (ValueError, TypeError):
        return {"opencode_session": fact(None, DEGRADED, "opencode-cli",
                                         note="export was not valid JSON")}
    info = data.get("info", {}) if isinstance(data, dict) else {}
    msgs = data.get("messages", []) if isinstance(data, dict) else []
    summary = {
        "id": info.get("id"),
        "title": info.get("title"),
        "agent": info.get("agent"),
        "model": info.get("model"),
        "version": info.get("version"),
        "tokens": info.get("tokens"),
        "cost": info.get("cost"),
    }
    return {
        "session": fact(summary, LIVE_VERIFIED, "opencode-cli"),
        "message_count": fact(len(msgs), LIVE_VERIFIED, "opencode-cli"),
    }


def read_opencode_liveness(opencode_bin: str = "opencode",
                           liveness_window_s: float = 600.0,
                           timeout: float = 20.0) -> dict[str, SourceFact]:
    """OpenCode heartbeat via the sanctioned `opencode db` SQLite channel.

    The app owns opencode.db's WAL, so a plain sqlite3.connect against the live
    file deadlocks (verified: 45-60s hangs). The `opencode db` CLI runs inside
    the app's own lock, so it is the only safe channel. We read the freshest
    session's time_updated (epoch ms) and derive an honest verdict:

      ACTIVE   session updated within liveness_window_s (the app is working)
      IDLE     CLI/process present but the session is stale
      OFFLINE  no CLI and no process
      DEGRADED any signal timed out or failed (never fabricated)

    The verdict never outranks its evidence: it names the composing signals.
    Reads only session rows; never touches the `credential` table (§14).
    """
    now = _now()
    signals: dict[str, SourceFact] = {}

    # process_present: is an OpenCode window/process alive at all?
    proc_alive = False
    try:
        p = _run_cli(["tasklist", "/FI", "IMAGENAME eq OpenCode.exe"], 15.0)
        proc_alive = "OpenCode.exe" in (p.stdout or "")
    except (OSError, subprocess.SubprocessError):
        proc_alive = False
    signals["process_present"] = fact(
        proc_alive, LIVE_VERIFIED if proc_alive else OFFLINE, "tasklist")

    # freshest session via opencode db (sanctioned channel, bounded query).
    cli_up = False
    freshest: dict[str, Any] = {}
    try:
        p = _run_cli([opencode_bin, "db",
                      "SELECT id,title,agent,time_updated FROM session "
                      "ORDER BY time_updated DESC LIMIT 3",
                      "--format", "json"], timeout)
        cli_up = p.returncode == 0
        if cli_up:
            rows = json.loads(p.stdout or "[]")
            if isinstance(rows, list) and rows:
                freshest = rows[0]
    except (OSError, subprocess.SubprocessError, ValueError, TypeError):
        cli_up = False
    signals["cli"] = fact("available" if cli_up else "unavailable",
                          LIVE_VERIFIED if cli_up else OFFLINE, "opencode-cli")
    if freshest:
        signals["freshest_session"] = fact(freshest, LIVE_VERIFIED, "opencode-db")

    # derive verdict from real signals only. The verdict VALUE is the
    # worker-lifecycle state (ACTIVE/IDLE/OFFLINE); its SourceFact `state` is
    # LIVE_VERIFIED because it is computed from live evidence (never
    # fabricated). DEGRADED stays as the state when a signal failed.
    updated_ms = freshest.get("time_updated") if freshest else None
    if cli_up and isinstance(updated_ms, (int, float)):
        age_s = max(0.0, now - (updated_ms / 1000.0))
        verdict = "ACTIVE" if age_s <= liveness_window_s else "IDLE"
        note = f"freshest session updated {age_s:.0f}s ago (window {liveness_window_s:.0f}s)"
        vstate = LIVE_VERIFIED
    elif proc_alive or cli_up:
        verdict = "IDLE"
        note = "process/cli present but no fresh session row"
        vstate = LIVE_VERIFIED
    else:
        verdict = "OFFLINE"
        note = "no opencode cli and no process"
        vstate = OFFLINE
    signals["verdict"] = fact(verdict, vstate, "derived", note=note)
    signals["liveness_window_s"] = fact(liveness_window_s, LIVE_VERIFIED, "config")
    return signals


def read_codex_state(codex_home: str = "~/.codex", max_sessions: int = 20,
                     heartbeat_active_s: float = 600.0,
                     timeout: float = 20.0) -> dict[str, SourceFact]:
    """Codex external-worker telemetry from rollout JSONL (read-only).

    Codex (OpenAI Codex CLI / desktop app) writes one JSONL per thread under
    `<home>/sessions/YYYY/MM/DD/rollout-<LOCAL-ISO-start>-<uuid>.jsonl`. Each
    line is {timestamp, ordinal, type, payload}. We read ONLY the first line
    (session_meta: id/cwd/originator/forks) and the last line (latest
    timestamp) per newest session — never auth.json, config.toml, or the
    secrets dir (§14). Rollout file mtime + last-line timestamp are the
    heartbeat. `codex doctor`/`codex resume` are interactive/slow — never
    called from a read-model; `codex --version` is the only CLI probe.

    Verdict (derived, never fabricated): ACTIVE (newest rollout written within
    heartbeat_active_s) / IDLE (rollouts exist but stale) / OFFLINE (no
    sessions root or no files).
    """
    home = os.path.expanduser(codex_home)
    sessions_root = os.path.join(home, "sessions")
    now = _now()

    # CLI version probe (fast, safe). Absent binary -> OFFLINE cli fact.
    try:
        p = _run_cli(["codex", "--version"], min(timeout, 15.0))
        cli_version = (p.stdout or "").strip()[:80] if p.returncode == 0 else ""
        cli_up = p.returncode == 0
    except (OSError, subprocess.SubprocessError):
        cli_version, cli_up = "", False

    if not os.path.isdir(sessions_root):
        return {
            "codex": fact(None, OFFLINE, "codex-rollout",
                          note="no sessions root (codex never ran or different home)"),
            "cli": fact(cli_version or None, LIVE_VERIFIED if cli_up else OFFLINE,
                        "codex-cli"),
        }

    rollouts: list[str] = []
    for root, _dirs, files in os.walk(sessions_root):
        for fn in files:
            if fn.startswith("rollout-") and fn.endswith(".jsonl"):
                rollouts.append(os.path.join(root, fn))
    rollouts.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    newest = rollouts[:max_sessions]

    sessions: list[dict[str, Any]] = []
    newest_mtime = 0.0
    for path in newest:
        try:
            mtime = os.path.getmtime(path)
            newest_mtime = max(newest_mtime, mtime)
            meta: dict[str, Any] = {}
            last_ts = ""
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:  # first line only for meta
                    line = line.strip()
                    if line:
                        try:
                            first = json.loads(line)
                            meta = (first.get("payload", {})
                                    if isinstance(first, dict) else {})
                        except (ValueError, TypeError):
                            pass
                    break
                # last line: bounded reverse read
                last_ts = _last_line_timestamp(path)
            sessions.append({
                "id": meta.get("id") or os.path.basename(path),
                "cwd": meta.get("cwd"),
                "originator": meta.get("originator"),
                "forked_from_id": meta.get("forked_from_id"),
                "parent_thread_id": meta.get("parent_thread_id"),
                "thread_cli_version": meta.get("cli_version"),
                "last_event_at": last_ts,
                "file_mtime_s": round(mtime, 1),
                "age_s": round(now - mtime, 1),
            })
        except (OSError, ValueError):
            continue

    if not sessions:
        return {
            "codex": fact(None, OFFLINE, "codex-rollout",
                          note="no readable rollout files"),
            "cli": fact(cli_version or None, LIVE_VERIFIED if cli_up else OFFLINE,
                        "codex-cli"),
        }

    age_s = now - newest_mtime if newest_mtime else None
    if age_s is not None and age_s <= heartbeat_active_s:
        verdict, vstate = "ACTIVE", LIVE_VERIFIED
    elif age_s is not None:
        verdict, vstate = "IDLE", LIVE_VERIFIED
    else:
        verdict, vstate = "UNKNOWN", UNKNOWN

    return {
        "cli": fact(cli_version or None, LIVE_VERIFIED if cli_up else OFFLINE,
                    "codex-cli"),
        "rollout_count": fact(len(rollouts), LIVE_VERIFIED, "codex-rollout"),
        "sessions": fact(sessions, LIVE_VERIFIED, "codex-rollout"),
        "verdict": fact(verdict, vstate, "derived",
                        note=f"newest rollout {age_s:.0f}s ago" if age_s is not None
                        else "no mtime"),
        "heartbeat_active_s": fact(heartbeat_active_s, LIVE_VERIFIED, "config"),
    }


def _last_line_timestamp(path: str, chunk: int = 4096) -> str:
    """Read the trailing JSON line's `timestamp` without loading the file."""
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - chunk))
            tail = fh.read().decode("utf-8", errors="replace").strip().splitlines()
        for line in reversed(tail):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict) and "timestamp" in obj:
                    return str(obj["timestamp"])
            except (ValueError, TypeError):
                continue
    except OSError:
        pass
    return ""


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


def create_supervisor_state(bus: Any = None, session_id: str = "",
                            event_ring: int = 500) -> SupervisorState:
    """Canonical factory for a supervisor read-model bound to a live EventBus.

    Pass the runtime/session `EventBus` (the one `runtime.py` creates and
    emits execution./task./gate./approval. events onto) and the supervisor
    subscribes "*" — the same pattern runtime.py itself uses for its history.
    With `bus=None` you get an isolated state you can `ingest()` into manually
    (used by tests and the acceptance demo). Never fabricates events.
    """
    st = SupervisorState(bus=bus, event_ring=event_ring)
    if session_id:
        st.session_id = session_id
    return st


def read_hive_state(hive: Any) -> dict[str, SourceFact]:
    """Quota-aware hive workforce overview for the dashboard (§30, §31).

    `hive` is a compute.hive_scheduler.HiveScheduler instance (injected, never
    constructed here — the supervisor is a read-model, not a second
    scheduler). Every number comes from the live scheduler; UNKNOWN quota
    stays UNKNOWN (§38) — the dashboard shows the honesty, not a fake %.
    """
    if hive is None:
        return {"hive": not_exposed("hive scheduler not wired")}
    try:
        ov = hive.overview()
    except Exception as e:  # noqa: BLE001
        return {"hive": fact(None, DEGRADED, "hive-scheduler",
                             note=f"{type(e).__name__}: {e}")}
    workers = []
    quota_rows = []
    for wid, w in sorted(hive._workers.items()):
        workers.append({
            "worker_id": wid,
            "provider": w.get("provider"),
            "tier": w.get("tier"),
            "privacy_class": w.get("privacy_class"),
            "state": w.get("state"),
            "capabilities": w.get("capabilities"),
        })
        q = hive._quota.get(wid)
        if q is not None:
            d = q.to_dict()
            frac = q.remaining_fraction()
            # §38: remaining_fraction None => UNKNOWN, never an invented %.
            d["remaining_fraction"] = frac
            quota_rows.append(d)
    return {
        "overview": fact(ov, LIVE_VERIFIED, "hive-scheduler"),
        "workers": fact(workers, LIVE_VERIFIED, "hive-scheduler"),
        "quotas": fact(quota_rows, LIVE_VERIFIED, "hive-scheduler"),
        "waiting_for_quota": fact(list(hive._deferred.keys()), LIVE_VERIFIED,
                                  "hive-scheduler"),
        "handoffs": fact([h.to_dict() for h in hive.handoffs()[-20:]],
                         LIVE_VERIFIED, "hive-scheduler"),
    }


# --- refresh wiring ---------------------------------------------------------
def refresh_snapshot(state: SupervisorState, repos: dict[str, str],
                     ollama_url: str = "http://127.0.0.1:11434",
                     team_registry: Any = None,
                     opencode_bin: Optional[str] = None,
                     opencode_session_id: str = "",
                     codex_home: Optional[str] = None,
                     opencode_liveness_window_s: float = 600.0,
                     hive: Any = None) -> None:
    """Pull real adapter data into the snapshot. Call on a timer or per-request.

    `repos` maps a project label -> absolute repo path. `team_registry` is an
    optional TeamRegistry instance (read-only). All adapters are read-only.
    """
    git_section: dict[str, Any] = {}
    for label, path in repos.items():
        git_section[label] = {k: v.to_dict() for k, v in read_git_state(path).items()}
    state.set_section("repositories", git_section)

    oll = {k: v.to_dict() for k, v in read_ollama_state(ollama_url).items()}
    state.set_section("local_models", oll)

    if team_registry is not None:
        reg = {k: v.to_dict() for k, v in read_team_registry(team_registry).items()}
        state.set_section("team_registry", reg)
    else:
        # Optional injection also still supported for a custom reader.
        workers_reader: Any = getattr(state, "_workers_reader", None)
        if callable(workers_reader):
            try:
                state.set_section("workers", workers_reader())
            except Exception as e:  # noqa: BLE001
                state.set_section("workers", {"error": fact(str(e), DEGRADED, "team_registry").to_dict()})
        else:
            state.set_section("workers", {
                "note": fact("team_registry not wired", NOT_EXPOSED,
                             "team_registry").to_dict()})

    if opencode_bin is not None:
        oc: dict[str, Any] = {k: v.to_dict()
                              for k, v in read_opencode_sessions(opencode_bin).items()}
        if opencode_session_id:
            oc.update({k: v.to_dict() for k, v in
                       read_opencode_session(opencode_bin, opencode_session_id).items()})
        # Liveness/heartbeat: derived ACTIVE/IDLE/OFFLINE from the sanctioned
        # `opencode db` channel (the app owns the WAL; never a raw sqlite3).
        liveness = {k: v.to_dict() for k, v in
                    read_opencode_liveness(opencode_bin,
                                           opencode_liveness_window_s).items()}
        oc["liveness"] = liveness
        state.set_section("opencode", oc)
        _emit_verdict_change(state, "opencode",
                             liveness.get("verdict", {}).get("value"))

    if codex_home is not None:
        cx = {k: v.to_dict() for k, v in read_codex_state(codex_home).items()}
        state.set_section("codex", cx)
        _emit_verdict_change(state, "codex",
                             cx.get("verdict", {}).get("value"))

    if hive is not None:
        state.set_section("hive", {k: v.to_dict()
                                   for k, v in read_hive_state(hive).items()})


def _emit_verdict_change(state: SupervisorState, worker: str,
                         verdict: Any) -> None:
    """Emit a worker.heartbeat only when the verdict CHANGES (coalescing).

    Per reconciliation §10 the risk is event flooding, so we keep the last
    verdict per worker on the state and emit the existing `worker.heartbeat`
    event name (no new event family) only on a transition. First sight always
    emits so the dashboard has a baseline.
    """
    if verdict is None:
        return
    prev = getattr(state, "_last_verdicts", None)
    if prev is None:
        prev = {}
        state._last_verdicts = prev  # type: ignore[attr-defined]
    if prev.get(worker) == verdict:
        return
    prev[worker] = verdict
    state.ingest({
        "event": "worker.heartbeat",
        "worker": worker,
        "verdict": verdict,
        "timestamp": _now_iso(),
    })


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

