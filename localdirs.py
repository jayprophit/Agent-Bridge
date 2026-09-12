"""Canonical local (non-product) storage resolution (v0.8.1).

All local/runtime/removable material defaults beneath <repo>/local/
(acceptance, archives, captures, cache, downloads, history, harness,
logs, models, runtime, sessions, temp, workspaces). Paths stay
configurable: explicit argument > AGENT_BRIDGE_LOCAL / AGENT_BRIDGE_ROOT
env > repository root inference. Never hard-code a user home/Desktop.
"""
from __future__ import annotations

import os

SUBDIRS = ("acceptance", "archives", "captures", "cache", "downloads",
           "history", "harness", "logs", "models", "runtime", "sessions",
           "temp", "workspaces")


def repo_root(start: str = "") -> str:
    """Nearest directory containing README.md + tools/ (the product root)."""
    cur = os.path.abspath(start or os.getcwd())
    while True:
        if os.path.isfile(os.path.join(cur, "README.md")) and \
                os.path.isdir(os.path.join(cur, "tools")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return os.path.abspath(start or os.getcwd())
        cur = parent


def local_root(explicit: str = "", root: str = "") -> str:
    """Resolve the local storage root (created on demand by callers)."""
    if explicit:
        return os.path.abspath(explicit)
    env = os.getenv("AGENT_BRIDGE_LOCAL", "")
    if env:
        return os.path.abspath(env)
    base = os.getenv("AGENT_BRIDGE_ROOT", "") or repo_root(root)
    return os.path.join(os.path.abspath(base), "local")


def local_subdir(name: str, explicit: str = "", root: str = "",
                 create: bool = False) -> str:
    """Resolve (and optionally create) one canonical local subdirectory."""
    if name not in SUBDIRS:
        raise ValueError(f"unknown local area: {name!r}")
    path = os.path.join(local_root(explicit, root), name)
    if create:
        os.makedirs(path, exist_ok=True)
    return path
