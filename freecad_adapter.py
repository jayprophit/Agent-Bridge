"""FreeCAD application adapter: the smallest reusable seam between Agent Bridge
and a real installed CAD application.

This module does NOT grant desktop control and does NOT execute arbitrary
commands. It exposes exactly three capabilities, each bounded:

- discover() ......... locate freecadcmd.exe, or report it missing (no fake)
- run_script() ....... execute one supervisor-approved script file inside one
                        approved directory, with a time budget, capturing
                        stdout/stderr/exit. The script file must already exist;
                        this module never writes or modifies scripts.
- verify_document() .. reopen a saved .FCStd through a supervisor-approved
                        inspector script and report the inspected facts.

Authorization, leases, task identity and evidence live in the canonical
runtime (worker_runtime, TaskCenter, P25). This adapter is the hands, never
the authority: every call takes explicit paths, and anything outside the
approved directory is refused before the application starts.
"""
from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

FREECADCMD_NAMES = ("freecadcmd.exe", "FreeCADCmd.exe", "freecadcmd", "FreeCADCmd")
KNOWN_INSTALL_DIRS = (
    Path("C:/Program Files/FreeCAD 1.0/bin"),
    Path("C:/Program Files/FreeCAD/bin"),
)


@dataclass(frozen=True)
class FreeCADDiscovery:
    found: bool
    executable: str | None
    version: str | None
    reason: str


def discover(search_dirs: tuple[Path, ...] = KNOWN_INSTALL_DIRS) -> FreeCADDiscovery:
    """Locate a FreeCAD console binary. A missing application is a reported
    fact, never a simulated success."""
    for name in FREECADCMD_NAMES:
        found = shutil.which(name)
        if found:
            return FreeCADDiscovery(True, found, _version_of(found), f"found on PATH as {name}")
    for directory in search_dirs:
        for name in FREECADCMD_NAMES:
            candidate = directory / name
            if candidate.is_file():
                return FreeCADDiscovery(True, str(candidate), _version_of(str(candidate)),
                                        f"found at {candidate}")
    return FreeCADDiscovery(False, None, None, "freecadcmd not on PATH or in known install dirs")


def _version_of(executable: str) -> str | None:
    try:
        proc = subprocess.run([executable, "--version"], capture_output=True,
                              text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.lower().startswith("freecad"):
            return line
    return None


@dataclass(frozen=True)
class ScriptResult:
    ok: bool
    exit_code: int | None
    stdout_tail: str
    stderr_tail: str
    elapsed_s: float
    timed_out: bool


def _inside(directory: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(directory.resolve())
        return True
    except ValueError:
        return False


def run_script(executable: str, script: Path, workdir: Path,
               timeout_s: float = 300.0) -> ScriptResult:
    """Execute an existing script file with the FreeCAD console binary.

    Both the script and the working directory must resolve inside `workdir`'s
    tree... more precisely: the script must live inside workdir. The
    application inherits no authority beyond what the OS gives the process;
    budgets and approvals are enforced by the caller.
    """
    workdir = workdir.resolve()
    script = script.resolve()
    started = time.time()
    if not _inside(workdir, script):
        return ScriptResult(False, None, "", f"refused: {script} is outside {workdir}", 0.0, False)
    if script.suffix.lower() != ".py":
        return ScriptResult(False, None, "", f"refused: not a Python script: {script}", 0.0, False)
    if not script.is_file():
        return ScriptResult(False, None, "", f"missing script: {script}", 0.0, False)
    try:
        proc = subprocess.run(
            [executable, str(script)], capture_output=True, text=True,
            timeout=timeout_s, cwd=str(workdir))
    except subprocess.TimeoutExpired as e:
        elapsed = time.time() - started
        out = (e.stdout or "") if isinstance(e.stdout, str) else ""
        err = (e.stderr or "") if isinstance(e.stderr, str) else ""
        return ScriptResult(False, None, out[-2000:], (err + f"\ntimed out after {timeout_s}s")[-2000:],
                            elapsed, True)
    except OSError as e:
        return ScriptResult(False, None, "", f"could not start application: {e}",
                            time.time() - started, False)
    return ScriptResult(proc.returncode == 0, proc.returncode,
                        proc.stdout[-2000:], proc.stderr[-2000:],
                        time.time() - started, False)
