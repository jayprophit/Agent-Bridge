"""Versioned prompt profiles (v0.4). Prompts live in prompts/*.txt so they
are testable, replaceable, and protected from model writes (.bridge-external
but still workspace-guarded: prompt dir lives in the runtime package, never
in a task workspace).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
PROFILES = ("planner_v1", "coder_v1", "reviewer_v1", "general_v1",
            "small_v1", "strong_v1")


def load_profile(name: str) -> str:
    p = (PROMPT_DIR / f"{name}.txt").resolve()
    if PROMPT_DIR not in p.parents and p != PROMPT_DIR:
        raise ValueError(f"unknown prompt profile: {name!r}")
    if name not in PROFILES:
        raise ValueError(f"unknown prompt profile: {name!r}")
    return p.read_text(encoding="utf-8")


def available_profiles() -> list[str]:
    return [n for n in PROFILES if (PROMPT_DIR / f"{n}.txt").exists()]


def capability_card(role: str, cfg: Any, budget_left: int = -1) -> str:
    """Concise capability brief for a model before a complex task."""
    lines = [
        f"protocol={cfg.protocol_version if hasattr(cfg, 'protocol_version') else '0.4'} "
        f"mode={cfg.mode} approval={cfg.approval} role={role}",
        f"workspace={Path(cfg.workspace).name} test_profile={cfg.test_profile.profile} "
        f"shell={cfg.shell_profile}",
        "actions: list read write edit patch mkdir delete restore move copy "
        "search exists stat diff shell test capabilities status finish",
        "rules: ONE JSON/action; relative paths; shell single simple commands; "
        "writes to others' files need approval; finish when done.",
    ]
    if budget_left >= 0:
        lines.append(f"context_budget_left_chars={budget_left}")
    return "\n".join(lines)
