"""Tool negotiation for small models (v0.8). Extends tools/toolkit.py.

Never dumps all ~350 schemas into a small model: intent -> family ->
bounded shortlist -> compact schemas -> one/few actions per turn.
"""
from __future__ import annotations

from typing import Any

from compat.modes import SMALL_CONTEXT_MODE
from tools.toolkit import negotiate as _negotiate
from tools.toolkit import short_schemas as _short_schemas

# Prompt budgets per mode (max tool shortlist length / schema chars).
MODE_BUDGETS = {
    "default": (12, 3000),
    SMALL_CONTEXT_MODE: (6, 1200),
    "LEGACY_MODEL_MODE": (4, 800),
}


def negotiate_tools(task_text: str, tool_registry,
                    modes: list[str] | None = None,
                    include_always: tuple[str, ...] = ("tools.list", "tools.search",
                                                       "tools.describe")) -> list[str]:
    """Bounded relevant-tool shortlist honoring compatibility modes."""
    modes = modes or []
    limit = MODE_BUDGETS["default"][0]
    for mode in modes:
        if mode in MODE_BUDGETS:
            limit = min(limit, MODE_BUDGETS[mode][0])
    try:
        shortlist = _negotiate(task_text, tool_registry, limit=limit,
                               include_always=include_always)
    except TypeError:
        shortlist = _negotiate(task_text, tool_registry, limit=limit)
    # tools.search stays reachable so the model can expand the shortlist.
    if "tools.search" not in shortlist:
        shortlist = (shortlist + ["tools.search"])[:limit + 1]
    return shortlist


def compact_prompt(task_text: str, tool_registry, tool_ids: list[str],
                   modes: list[str] | None = None) -> str:
    """One-turn prompt: task + compact schemas + mode instructions."""
    modes = modes or []
    max_chars = MODE_BUDGETS["default"][1]
    for mode in modes:
        if mode in MODE_BUDGETS:
            max_chars = min(max_chars, MODE_BUDGETS[mode][1])
    schemas = _short_schemas(tool_registry, tool_ids, max_chars=max_chars)
    style = ("Respond with exactly one JSON tool action per turn, e.g. "
             '{"tool": "<tool_id>", "arguments": {...}}. '
             if "LEGACY_MODEL_MODE" in modes or SMALL_CONTEXT_MODE in modes
             else "Respond with tool actions as JSON. ")
    return (f"TASK: {task_text}\n\nAVAILABLE TOOLS (use only these):\n{schemas}\n\n"
            f"{style}If done, respond with {{\"tool\": \"finish\", "
            f"\"arguments\": {{\"message\": \"done\"}}}}.")


def expand_via_search(tool_registry, query: str, limit: int = 5) -> list[str]:
    """tools.search expansion hook (registry search, bounded)."""
    try:
        return [r.tool_id for r in tool_registry.search(query, limit=limit)]
    except Exception:
        return []
