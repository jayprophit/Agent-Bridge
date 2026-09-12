"""Owner-mode process/application control (stdlib only).

List (via tasklist on Windows), launch, status, wait, terminate.
Windows permission enforcement stays in force; real PIDs/status recorded.
"""
from __future__ import annotations

import os
import shlex
import signal as _signal
import subprocess
import time
from pathlib import Path
from typing import Any


class ProcError(Exception):
    pass


def list_processes(limit: int = 200) -> dict[str, Any]:
    if os.name == "nt":
        try:
            p = subprocess.run(["tasklist", "/FO", "CSV", "/NH"],
                               capture_output=True, text=True, timeout=20,
                               shell=False)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise ProcError(f"process list failed: {e}")
        rows = []
        for line in p.stdout.splitlines()[:limit]:
            parts = [c.strip('"') for c in line.split('","')]
            if len(parts) >= 2:
                rows.append({"image": parts[0], "pid": parts[1],
                             "mem": parts[4] if len(parts) > 4 else ""})
        return {"ok": True, "processes": rows, "count": len(rows)}
    try:
        p = subprocess.run(["ps", "-eo", "pid,comm"], capture_output=True,
                           text=True, timeout=20, shell=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ProcError(f"process list failed: {e}")
    rows = []
    for line in p.stdout.splitlines()[1:limit + 1]:
        cells = line.split(None, 1)
        if len(cells) == 2:
            rows.append({"pid": cells[0], "image": cells[1]})
    return {"ok": True, "processes": rows, "count": len(rows)}


def launch(command: str, cwd: str | Path | None = None,
           timeout_s: int = 120) -> dict[str, Any]:
    """Run a command, capturing evidence. Owner profile only (gated upstream)."""
    t0 = time.monotonic()
    try:
        proc = subprocess.run(command, cwd=str(cwd) if cwd else None,
                              capture_output=True, text=True,
                              timeout=timeout_s, shell=True)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "TIMEOUT: process timeout",
                "exit_code": None}
    except OSError as e:
        return {"ok": False, "error": f"launch failed: {e}", "exit_code": None}
    return {"ok": proc.returncode == 0, "command": command,
            "cwd": str(cwd or Path.cwd()),
            "exit_code": proc.returncode,
            "stdout": (proc.stdout or "")[:8000],
            "stderr": (proc.stderr or "")[:8000],
            "duration_s": round(time.monotonic() - t0, 3),
            "pid": None}


def spawn(command: str, cwd: str | Path | None = None) -> dict[str, Any]:
    """Launch a detached process, returning its real PID."""
    try:
        proc = subprocess.Popen(command, cwd=str(cwd) if cwd else None,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, shell=True)
    except OSError as e:
        raise ProcError(f"spawn failed: {e}")
    return {"ok": True, "pid": proc.pid, "command": command}


def proc_status(pid: int) -> dict[str, Any]:
    if os.name == "nt":
        try:
            p = subprocess.run(["tasklist", "/FI", f"PID eq {int(pid)}",
                                "/FO", "CSV", "/NH"],
                               capture_output=True, text=True, timeout=15,
                               shell=False)
            alive = str(pid) in p.stdout
        except (OSError, subprocess.TimeoutExpired):
            alive = False
        return {"ok": True, "pid": int(pid), "alive": alive}
    try:
        os.kill(int(pid), 0)
        return {"ok": True, "pid": int(pid), "alive": True}
    except (OSError, ProcessLookupError):
        return {"ok": True, "pid": int(pid), "alive": False}


def terminate(pid: int) -> dict[str, Any]:
    """Terminate an owner-authorized process. OS permissions still apply."""
    try:
        if os.name == "nt":
            p = subprocess.run(["taskkill", "/PID", str(int(pid)), "/T", "/F"],
                               capture_output=True, text=True, timeout=20,
                               shell=False)
            return {"ok": p.returncode == 0, "pid": int(pid),
                    "output": (p.stdout or p.stderr or "")[:1000]}
        os.kill(int(pid), _signal.SIGTERM)
        return {"ok": True, "pid": int(pid)}
    except (OSError, ProcessLookupError) as e:
        return {"ok": False, "error": f"terminate failed: {e}"}


def wait_for(pid: int, timeout_s: int = 60) -> dict[str, Any]:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout_s:
        if not proc_status(pid).get("alive"):
            return {"ok": True, "pid": int(pid), "exited": True,
                    "duration_s": round(time.monotonic() - t0, 3)}
        time.sleep(1)
    return {"ok": False, "pid": int(pid), "exited": False,
            "error": "TIMEOUT waiting for process"}
