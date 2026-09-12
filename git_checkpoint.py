"""Backward-compat shim: v0.2 import path for GitManager."""
from __future__ import annotations

from checkpoints import CheckpointManager, GitManager

__all__ = ["CheckpointManager", "GitManager"]
