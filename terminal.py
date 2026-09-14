"""Policy-gated terminal/process subsystem (Phase 2).

Real PTY-less process execution for the IDE terminal surface. Every
command passes the SAME Executor dev-profile policy (allowlisted
binaries, blocked shell tokens, workspace-scoped cwd, no shell=True):
the terminal can never bypass the permission engine. Denials surface
as text so the UI shows policy, not silence.

Sessions track history, state, exit codes and PIDs; cancel() kills the
running process. Loopback-only service exposure (see service.py routes).
Additive only; no import side effects.
"""
from __future__ import annotations

import shlex
import subprocess
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class TerminalEntry:
    command: str = ""
    cwd: str = ""
    started_at: float = 0.0
    ended_at: float = 0.0
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    state: str = "DONE"       # DONE | DENIED | TIMEOUT | CANCELLED | FAILED
    origin: str = "user"      # user | agent
    pid: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TerminalSession:
    session_id: str = ""
    cwd: str = ""
    created_at: float = field(default_factory=time.time)
    history: list[dict[str, Any]] = field(default_factory=list)
    running: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TerminalManager:
    """Workspace-scoped terminal sessions with policy-gated execution."""

    def __init__(self, workspace: str | Path, shell_timeout_s: int = 120,
                 max_output: int = 8000):
        from executor import Executor
        self.workspace = Path(workspace)
        self.executor = Executor(workspace, shell_profile="dev",
                                 shell_timeout_s=shell_timeout_s,
                                 max_output_chars=max_output)
        self.shell_timeout_s = shell_timeout_s
        self.max_output = max_output
        self.sessions: dict[str, TerminalSession] = {}
        self._procs: dict[str, subprocess.Popen] = {}
        self._guard = threading.Lock()

    # -- sessions ---------------------------------------------------------
    def create(self, cwd: str = "") -> TerminalSession:
        target = (self.workspace / cwd).resolve() if cwd else self.workspace.resolve()
        try:
            target.relative_to(self.workspace.resolve())
        except ValueError:
            raise PermissionError(f"cwd escapes workspace: {cwd!r}")
        if not target.is_dir():
            raise FileNotFoundError(f"cwd not found: {cwd!r}")
        session = TerminalSession(session_id="term-" + uuid.uuid4().hex[:8],
                                  cwd=str(target))
        with self._guard:
            self.sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> TerminalSession:
        try:
            return self.sessions[session_id]
        except KeyError:
            raise KeyError(f"unknown terminal session: {session_id!r}")

    def list(self) -> list[dict[str, Any]]:
        return [s.to_dict() for s in self.sessions.values()]

    # -- execution ----------------------------------------------------------
    def exec(self, session_id: str, command: str,
             timeout_s: float = 60.0, origin: str = "user") -> dict[str, Any]:
        session = self.get(session_id)
        denied = self.executor._shell_allowed(command)
        if denied:
            entry = TerminalEntry(command=command, cwd=session.cwd,
                                  started_at=time.time(), ended_at=time.time(),
                                  state="DENIED", origin=origin,
                                  stderr=f"POLICY_DENIED: {denied}")
            session.history.append(entry.to_dict())
            return {"ok": False, "denied": True, "error": entry.stderr,
                    "state": "DENIED"}
        try:
            parts = shlex.split(command, posix=False)
        except ValueError as e:
            return {"ok": False, "error": f"unparseable command: {e}",
                    "state": "FAILED"}
        entry = TerminalEntry(command=command, cwd=session.cwd,
                              started_at=time.time(), origin=origin)
        session.running = True
        try:
            proc = subprocess.Popen(
                parts, cwd=session.cwd, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, shell=False)
        except FileNotFoundError:
            session.running = False
            entry.state = "FAILED"
            entry.stderr = f"executable not found: {parts[0]!r}"
            entry.ended_at = time.time()
            session.history.append(entry.to_dict())
            return {"ok": False, "error": entry.stderr, "state": "FAILED"}
        except OSError as e:
            session.running = False
            entry.state = "FAILED"
            entry.stderr = f"launch failed: {e}"
            entry.ended_at = time.time()
            session.history.append(entry.to_dict())
            return {"ok": False, "error": entry.stderr, "state": "FAILED"}
        entry.pid = proc.pid
        with self._guard:
            self._procs[session_id] = proc
        try:
            out, err = proc.communicate(timeout=min(timeout_s, self.shell_timeout_s))
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except OSError:
                pass
            out, err = proc.communicate()
            entry.state = "TIMEOUT"
        finally:
            with self._guard:
                self._procs.pop(session_id, None)
            session.running = False
        entry.ended_at = time.time()
        entry.exit_code = proc.returncode
        entry.stdout = (out or "")[:self.max_output]
        entry.stderr = (err or "")[:self.max_output]
        if entry.state != "TIMEOUT":
            entry.state = "DONE" if proc.returncode == 0 else "FAILED"
        session.history.append(entry.to_dict())
        return {"ok": entry.state == "DONE", "state": entry.state,
                "exit_code": entry.exit_code, "stdout": entry.stdout,
                "stderr": entry.stderr, "pid": entry.pid,
                "origin": origin}

    def cancel(self, session_id: str) -> dict[str, Any]:
        session = self.get(session_id)
        with self._guard:
            proc = self._procs.get(session_id)
        if proc is None or proc.poll() is not None:
            return {"ok": False, "state": "NOT_RUNNING"}
        try:
            proc.kill()
        except OSError as e:
            return {"ok": False, "error": f"cancel failed: {e}"}
        if session.history:
            session.history[-1]["state"] = "CANCELLED"
        session.running = False
        return {"ok": True, "state": "CANCELLED", "pid": proc.pid}
