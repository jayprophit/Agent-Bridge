"""OpenModelica application adapter: the smallest reusable seam between Agent
Bridge and the installed OpenModelica compiler/simulator.

This module does NOT grant desktop control and does NOT execute arbitrary
commands. It exposes exactly two capabilities, each bounded:

- discover() ......... locate omc.exe, or report it missing (no fake)
- run_mos() ........... execute one supervisor-approved .mos script file
                        inside one approved directory, with a time budget,
                        capturing stdout/stderr/exit. The script file must
                        already exist; this module never writes scripts.
                        The working directory IS the simulation directory:
                        omc compiles and writes result files there, so cwd
                        is always the approved workdir, never elsewhere.

Authorization, leases, task identity and evidence live in the canonical
runtime (worker_runtime, TaskCenter). This adapter is the hands, never the
authority: every call takes explicit paths, and anything outside the
approved directory is refused before the application starts.

Measured 2026-10-07 on OpenModelica 1.27.1: the decay-model .mos
(loadFile + simulate + dassl) compiles ~117s and yields x(2)=0.1353,
exactly e^-2. Budgets below ~300s risk false timeouts on first compile.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

OMC_NAMES = ("omc.exe", "omc")
KNOWN_INSTALL_DIRS = (
    Path("C:/Program Files/OpenModelica1.27.1-64bit/bin"),
    Path("C:/Program Files/OpenModelica/bin"),
)

_BANNER_VERSION = re.compile(r"OpenModelica\s+v?(\S+)")


@dataclass(frozen=True)
class OpenModelicaDiscovery:
    found: bool
    executable: str | None
    version: str | None
    reason: str


@dataclass(frozen=True)
class MosResult:
    ok: bool
    exit_code: int | None
    stdout_tail: str
    stderr_tail: str
    elapsed_s: float
    timed_out: bool


def discover(search_dirs: tuple[Path, ...] = KNOWN_INSTALL_DIRS) -> OpenModelicaDiscovery:
    """Locate an omc binary. A missing application is a reported fact,
    never a simulated success."""
    for name in OMC_NAMES:
        found = shutil.which(name)
        if found:
            return OpenModelicaDiscovery(True, found, _version_of(found),
                                        f"found on PATH as {name}")
    for directory in search_dirs:
        for name in OMC_NAMES:
            candidate = directory / name
            if candidate.is_file():
                return OpenModelicaDiscovery(True, str(candidate),
                                            _version_of(str(candidate)),
                                            f"found at {candidate}")
    return OpenModelicaDiscovery(False, None, None,
                                 "omc not on PATH or in known install dirs")


def _version_of(executable: str) -> str | None:
    try:
        proc = subprocess.run([executable, "--version"], capture_output=True,
                              text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    match = _BANNER_VERSION.search(proc.stdout + proc.stderr)
    return match.group(1) if match else None


def _inside(directory: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(directory.resolve())
        return True
    except ValueError:
        return False


def run_mos(executable: str, script: Path, workdir: Path,
            timeout_s: float = 600.0) -> MosResult:
    """Execute an existing .mos script with omc, inside workdir.

    The script must live inside workdir; omc inherits cwd=workdir so all
    compilation and result artifacts land in the approved directory.
    The success marker is printed LAST by convention, so the kept tail is
    wider (4000 chars) than the FreeCAD seam: omc banners are long.
    """
    workdir = workdir.resolve()
    script = script.resolve()
    started = time.time()
    if not _inside(workdir, script):
        return MosResult(False, None, "", f"refused: {script} is outside {workdir}",
                         0.0, False)
    if script.suffix.lower() != ".mos":
        return MosResult(False, None, "", f"refused: not a Modelica script: {script}",
                         0.0, False)
    if not script.is_file():
        return MosResult(False, None, "", f"missing script: {script}", 0.0, False)
    try:
        proc = subprocess.run(
            [executable, str(script)], capture_output=True, text=True,
            timeout=timeout_s, cwd=str(workdir))
    except subprocess.TimeoutExpired as e:
        elapsed = time.time() - started
        out = (e.stdout or "") if isinstance(e.stdout, str) else ""
        err = (e.stderr or "") if isinstance(e.stderr, str) else ""
        return MosResult(False, None, out[-4000:],
                         (err + f"\ntimed out after {timeout_s}s")[-4000:],
                         elapsed, True)
    except OSError as e:
        return MosResult(False, None, "", f"could not start application: {e}",
                         time.time() - started, False)
    # omc exit codes alone prove little (like FreeCADCmd, 0 does not mean
    # the simulation succeeded); the supervisor verifies marker + artifact.
    return MosResult(proc.returncode == 0, proc.returncode,
                     proc.stdout[-4000:], proc.stderr[-4000:],
                     time.time() - started, False)
