"""Programme-wide canonical output routing (v1).

Repo-local storage stays in localdirs (<repo>/local/). This module routes
programme-wide analysis/research/governance outputs beneath OPENCODE_DATA_ROOT
(default E:/OpenCode-Data) so automation never emits canonical data onto the
Windows Desktop or into arbitrary repository roots.

Programme rule: ALLOW_DESKTOP_PROGRAMME_OUTPUT = FALSE unless the owner
explicitly requests a Desktop artifact (OWNER_EXPLICIT_DESKTOP_REQUEST=TRUE).
Owner-facing shortcuts/launchers already on the Desktop are unaffected.
"""
from __future__ import annotations

import os
from pathlib import Path

DEFAULT_ROOT = "E:/OpenCode-Data"

# Workstream -> area beneath OPENCODE_DATA_ROOT.
WORKSTREAM_AREAS = {
    "CONVERSATION_ANALYSIS": "conversation-analysis",
    "REPOSITORY_GOVERNANCE": "Repository-Governance",
    "APP_ECOSYSTEM": "Aetherius-App-Ecosystem",
    "POIETEK_AUDIO_RESEARCH": "Poietek-Audio-Research",
    "SIMULATION_GAME_VIDEO": "Simulation-Game-Video-Research",
    "KNOWLEDGE": "Knowledge",
    "GENESIS": "Genesis",
    "SHARED": "Shared",
    "LOGS": "logs",
    "TEMP": "temp",
}

ALLOW_DESKTOP_PROGRAMME_OUTPUT = False


def data_root(explicit: str = "") -> Path:
    """Programme data root: explicit > OPENCODE_DATA_ROOT env > default."""
    if explicit:
        return Path(explicit)
    return Path(os.getenv("OPENCODE_DATA_ROOT", DEFAULT_ROOT))


def area(workstream: str, root: str = "") -> Path:
    """Canonical directory for a workstream (not created)."""
    if workstream not in WORKSTREAM_AREAS:
        raise ValueError(f"unknown workstream: {workstream!r}")
    return data_root(root) / WORKSTREAM_AREAS[workstream]


def resolve(workstream: str, *subpath: str, root: str = "",
            create: bool = False) -> Path:
    """Canonical output path for a workstream artifact."""
    path = area(workstream, root).joinpath(*subpath)
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _desktop_roots() -> tuple:
    home = os.path.expanduser("~").replace("\\", "/").lower()
    return (home + "/desktop", "c:/users/jpowe/desktop")


def is_desktop_path(path: str | Path) -> bool:
    """True if path sits on the Windows Desktop (any user)."""
    p = str(path).replace("\\", "/").lower()
    return any(p == r or p.startswith(r + "/") for r in _desktop_roots())


def assert_not_desktop(path: str | Path) -> Path:
    """Guard: refuse programme-output paths on the Desktop.

    Override only with OWNER_EXPLICIT_DESKTOP_REQUEST=TRUE in the environment
    (explicit owner request for a Desktop artifact).
    """
    if is_desktop_path(path):
        if ALLOW_DESKTOP_PROGRAMME_OUTPUT or \
                os.getenv("OWNER_EXPLICIT_DESKTOP_REQUEST", "").upper() == "TRUE":
            return Path(path)
        raise ValueError(
            f"programme output must not target the Desktop: {path} "
            "(set OWNER_EXPLICIT_DESKTOP_REQUEST=TRUE for an explicit owner request)")
    return Path(path)


class OutputLocationResolver:
    """Conceptual API: (PROJECT, WORKSTREAM, ARTIFACT_TYPE, PERSISTENCE) -> path."""

    PERSISTENCE_SUBDIR = {"STANDARD": "", "REPORT": "reports", "ARTIFACT": "artifacts",
                          "LOG": "logs", "TEMP": "temp"}

    def __init__(self, root: str = ""):
        self._root = root

    def resolve(self, workstream: str, artifact_type: str = "",
                persistence: str = "STANDARD", project: str = "") -> Path:
        sub = self.PERSISTENCE_SUBDIR.get(persistence.upper())
        if sub is None:
            raise ValueError(f"unknown persistence class: {persistence!r}")
        parts = [p for p in (sub, project, artifact_type) if p]
        return resolve(workstream, *parts, root=self._root)
