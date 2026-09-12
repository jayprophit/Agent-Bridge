"""Compatibility modes (v0.8). Capability lives in the bridge, not the model.

A small or older compatible model drives modern bridge tools through the
mode matching what it can actually parse. Modes are selected from measured
capability evidence — never from vendor or model names.
"""
from __future__ import annotations

# Interaction modes, strongest first.
NATIVE_TOOL_CALLING = "NATIVE_TOOL_CALLING"
BRIDGE_STRUCTURED_ACTION = "BRIDGE_STRUCTURED_ACTION"
STRICT_JSON_ACTION = "STRICT_JSON_ACTION"
TEXT_ACTION_TRANSLATION = "TEXT_ACTION_TRANSLATION"
LEGACY_MODEL_MODE = "LEGACY_MODEL_MODE"
SMALL_CONTEXT_MODE = "SMALL_CONTEXT_MODE"

MODES = (
    NATIVE_TOOL_CALLING,
    BRIDGE_STRUCTURED_ACTION,
    STRICT_JSON_ACTION,
    TEXT_ACTION_TRANSLATION,
    LEGACY_MODEL_MODE,
    SMALL_CONTEXT_MODE,
)

# SMALL_CONTEXT_MODE is orthogonal: it constrains prompt budgets and can
# combine with any base mode.
BASE_MODES = (
    NATIVE_TOOL_CALLING,
    BRIDGE_STRUCTURED_ACTION,
    STRICT_JSON_ACTION,
    TEXT_ACTION_TRANSLATION,
    LEGACY_MODEL_MODE,
)


def select_modes(evidence: dict) -> list[str]:
    """Select modes from measured capability evidence (no name conditions).

    evidence keys: native_tools, bridge_structured, strict_json,
    text_actions, context_tokens (numbers/bools from ModelCapabilityProbe).
    Returns [base_mode] plus SMALL_CONTEXT_MODE when context is small.
    """
    native = bool(evidence.get("native_tools"))
    bridge = bool(evidence.get("bridge_structured"))
    strict = bool(evidence.get("strict_json"))
    text = bool(evidence.get("text_actions"))
    context = int(evidence.get("context_tokens", 0) or 0)

    if native:
        base = NATIVE_TOOL_CALLING
    elif bridge:
        base = BRIDGE_STRUCTURED_ACTION
    elif strict:
        base = STRICT_JSON_ACTION
    elif text:
        base = TEXT_ACTION_TRANSLATION
    else:
        base = LEGACY_MODEL_MODE
    modes = [base]
    if 0 < context < 8192:
        modes.append(SMALL_CONTEXT_MODE)
    return modes
