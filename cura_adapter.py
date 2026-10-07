"""CuraEngine application adapter: the smallest reusable seam between Agent
Bridge and the installed UltiMaker Cura slicer.

This module does NOT grant desktop control and does NOT execute arbitrary
commands. It exposes exactly three capabilities, each bounded:

- discover() ......... locate CuraEngine.exe, or report it missing (no fake)
- slice_stl() ........ slice ONE .stl file inside one approved directory into
                        g-code, with a time budget, capturing stdout/stderr/
                        exit. Measured 2026-10-07: the bare fdmprinter +
                        fdmextruder definition chain dies mid-slice unless
                        roofing_layer_count and flooring_layer_count are set
                        explicitly, so the adapter always supplies safe
                        defaults for those two (caller settings win).
- verify_gcode() ..... independently parse the produced g-code (line count,
                        ;LAYER_COUNT:, G1 move count). Exit code 0 alone is
                        not proof: CuraEngine happily writes an empty file.

Authorization, leases, task identity and evidence live in the canonical
runtime (worker_runtime, TaskCenter). This adapter is the hands, never the
authority: every call takes explicit paths, and anything outside the
approved directory is refused before the application starts.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

ENGINE_NAMES = ("CuraEngine.exe", "CuraEngine")
KNOWN_INSTALL_DIRS = (
    Path("C:/Program Files/UltiMaker Cura 5.13.0"),
    Path("C:/Program Files/UltiMaker Cura"),
    Path("C:/Program Files/Cura"),
)

# Measured 2026-10-07 on Cura_SteamEngine 5.13.0: without these two the engine
# processes insets, then dies silently during skins/infill (empty .gcode).
REQUIRED_SETTINGS = {"roofing_layer_count": "0", "flooring_layer_count": "0"}

_BANNER_VERSION = re.compile(r"Cura_SteamEngine version (\S+)")


@dataclass(frozen=True)
class CuraDiscovery:
    found: bool
    executable: str | None
    version: str | None
    reason: str


@dataclass(frozen=True)
class SliceResult:
    ok: bool
    gcode_path: str | None
    layers: int | None
    g1_moves: int | None
    elapsed_s: float
    timed_out: bool
    stderr_tail: str


@dataclass(frozen=True)
class GcodeReport:
    ok: bool
    lines: int
    layers: int | None
    g1_moves: int
    reason: str


def discover(search_dirs: tuple[Path, ...] = KNOWN_INSTALL_DIRS) -> CuraDiscovery:
    """Locate a CuraEngine binary. A missing application is a reported fact,
    never a simulated success."""
    for name in ENGINE_NAMES:
        found = shutil.which(name)
        if found:
            return CuraDiscovery(True, found, _version_of(found),
                                 f"found on PATH as {name}")
    for directory in search_dirs:
        for name in ENGINE_NAMES:
            candidate = directory / name
            if candidate.is_file():
                return CuraDiscovery(True, str(candidate),
                                     _version_of(str(candidate)),
                                     f"found at {candidate}")
    return CuraDiscovery(False, None, None,
                         "CuraEngine not on PATH or in known install dirs")


def _version_of(executable: str) -> str | None:
    try:
        proc = subprocess.run([executable, "help"], capture_output=True,
                              text=True, timeout=60)
        match = _BANNER_VERSION.search(proc.stdout + proc.stderr)
        return match.group(1) if match else None
    except Exception:
        return None


def _inside(path: Path, workdir: Path) -> bool:
    try:
        path.resolve().relative_to(workdir.resolve())
        return True
    except ValueError:
        return False


def slice_stl(executable: str, stl_path: Path, out_gcode: Path,
              workdir: Path, printer_def: Path, extruder_def: Path,
              settings: dict[str, str] | None = None,
              timeout_s: float = 300.0) -> SliceResult:
    """Slice one STL to g-code. All three paths must live inside workdir."""
    started = time.monotonic()
    stl_path, out_gcode, workdir = Path(stl_path), Path(out_gcode), Path(workdir)
    for label, path in (("stl", stl_path), ("output", out_gcode)):
        if not _inside(path, workdir):
            return SliceResult(False, None, None, None,
                               time.monotonic() - started, False,
                               f"refused: {label} path outside workdir")
    if stl_path.suffix.lower() != ".stl":
        return SliceResult(False, None, None, None,
                           time.monotonic() - started, False,
                           "refused: input is not a .stl file")
    if not stl_path.is_file():
        return SliceResult(False, None, None, None,
                           time.monotonic() - started, False,
                           "missing input stl (nothing executed)")
    for label, path in (("printer definition", printer_def),
                        ("extruder definition", extruder_def)):
        if not Path(path).is_file():
            return SliceResult(False, None, None, None,
                               time.monotonic() - started, False,
                               f"missing {label}: {path}")
    merged = dict(REQUIRED_SETTINGS)
    merged.update(settings or {})
    cmd = [executable, "slice", "-j", str(printer_def),
           "-e0", "-j", str(extruder_def)]
    for key, value in merged.items():
        cmd += ["-s", f"{key}={value}"]
    cmd += ["-l", str(stl_path), "-o", str(out_gcode)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout_s, cwd=str(workdir))
        tail = (proc.stdout + proc.stderr)[-2000:]
        if proc.returncode != 0:
            return SliceResult(False, None, None, None,
                               time.monotonic() - started, False,
                               f"engine exit {proc.returncode}: {tail[-500:]}")
    except subprocess.TimeoutExpired:
        return SliceResult(False, None, None, None,
                           time.monotonic() - started, True,
                           f"timed out after {timeout_s}s (killed, no g-code trusted)")
    report = verify_gcode(out_gcode)
    if not report.ok:
        return SliceResult(False, None, None, None,
                           time.monotonic() - started, False,
                           f"g-code failed verification: {report.reason}")
    return SliceResult(True, str(out_gcode), report.layers, report.g1_moves,
                       time.monotonic() - started, False, "")


def verify_gcode(path: Path) -> GcodeReport:
    """Independently parse g-code. Returns ok only with real toolpath."""
    path = Path(path)
    if not path.is_file():
        return GcodeReport(False, 0, None, 0, "no g-code file produced")
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return GcodeReport(False, 0, None, 0, f"unreadable g-code: {exc}")
    lines = text.splitlines()
    layers = None
    match = re.search(r";LAYER_COUNT:(\d+)", text)
    if match:
        layers = int(match.group(1))
    moves = sum(1 for line in lines if line.startswith("G1 "))
    if not lines:
        return GcodeReport(False, 0, layers, 0, "g-code file is empty")
    if (layers or 0) <= 0 or moves <= 0:
        return GcodeReport(False, len(lines), layers, moves,
                           "g-code has no layers or no extrusion moves")
    return GcodeReport(True, len(lines), layers, moves, "real toolpath")

