"""Blender application adapter: the smallest reusable seam between Agent Bridge
and the installed Blender 5.2.2 LTS (Store package, owner-pinned version).

Verified platform facts this adapter is built on (do not assume otherwise):
- The Store package's blender.exe is not directly executable (Access denied);
  the `blender-launcher.exe` execution alias forwards `-b -P script.py` and
  runs headless scripts correctly (proven: version probe, scene, render).
- The launcher captures NO console output: verification is file-based only.
  Scripts report by writing transcript/result files into the workdir.
- Both FreeCADCmd and Blender exit 0 on script errors (and Blender may crash
  on shutdown AFTER writing valid output), so exit codes prove nothing. Only
  artifacts + transcripts count.

Capabilities, all bounded:
- discover() ..... locate a working launcher, or report it missing (no fake)
- run_script() .... execute one supervisor-approved .py file inside one
                    approved directory with a time budget; kill on timeout.
                    The script file must already exist; this module never
                    writes scripts.
- (verification) .. performed by supervisor-approved inspector scripts whose
                    transcript files the caller reads back; see tests.

Authorization, leases, task identity and evidence live in the canonical
runtime. This adapter is the hands, never the authority.
"""
from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

LAUNCHER_NAMES = ("blender-launcher.exe", "blender-launcher")
# Owner-pinned Store installation. Never upgraded, replaced or reconfigured
# by this adapter: it integrates against the INSTALLED version.
STORE_PACKAGE = "BlenderFoundation.Blender_5.2.2.0_x64__ppwjx1n5r4v9t"


@dataclass(frozen=True)
class BlenderDiscovery:
    found: bool
    launcher: str | None
    version: str | None
    reason: str


def discover() -> BlenderDiscovery:
    """Locate a working Blender launcher. Missing means missing."""
    for name in LAUNCHER_NAMES:
        found = shutil.which(name)
        if found:
            return BlenderDiscovery(True, found, None, f"launcher on PATH: {found}")
    return BlenderDiscovery(False, None, None,
                            "no Blender launcher on PATH and no configured install dir")


@dataclass(frozen=True)
class BlenderResult:
    ok: bool
    exit_code: int | None
    elapsed_s: float
    timed_out: bool
    killed: bool
    note: str


def _inside(directory: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(directory.resolve())
        return True
    except ValueError:
        return False


def run_script(launcher: str, script: Path, workdir: Path,
               timeout_s: float = 300.0) -> BlenderResult:
    """Run an existing Blender script headless. Refusals happen before any
    process starts; failures are reported, never hidden behind exit code 0."""
    workdir = workdir.resolve()
    script = script.resolve()
    started = time.time()
    if not _inside(workdir, script):
        return BlenderResult(False, None, 0.0, False, False,
                             f"refused: {script} is outside {workdir}")
    if script.suffix.lower() != ".py":
        return BlenderResult(False, None, 0.0, False, False,
                             f"refused: not a Python script: {script}")
    if not script.is_file():
        return BlenderResult(False, None, 0.0, False, False,
                             f"missing script: {script}")
    try:
        proc = subprocess.Popen(
            [launcher, "-b", "-P", str(script)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            cwd=str(workdir))
    except OSError as e:
        return BlenderResult(False, None, time.time() - started, False, False,
                             f"could not start Blender: {e}")
    try:
        code = proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=15.0)
        except subprocess.TimeoutExpired:
            pass
        return BlenderResult(False, None, time.time() - started, True, True,
                             f"timed out after {timeout_s}s and was killed")
    return BlenderResult(True, code, time.time() - started, False, False,
                         f"process exited with code {code} (proves nothing by itself)")
