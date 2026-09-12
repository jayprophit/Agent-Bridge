"""Small/legacy model compatibility (v0.8).

Capability lives in the bridge: negotiation, constrained translation, and
measured mode selection let older or small models drive modern tools.
"""
from __future__ import annotations

from compat.modes import (
    BASE_MODES, BRIDGE_STRUCTURED_ACTION, LEGACY_MODEL_MODE, MODES,
    NATIVE_TOOL_CALLING, SMALL_CONTEXT_MODE, STRICT_JSON_ACTION,
    TEXT_ACTION_TRANSLATION, select_modes,
)
from compat.negotiation import compact_prompt, expand_via_search, negotiate_tools
from compat.probe import ModelCapabilityProbe
from compat.translator import LegacyActionTranslator, TranslationResult

__all__ = [
    "BASE_MODES", "BRIDGE_STRUCTURED_ACTION", "LEGACY_MODEL_MODE", "MODES",
    "NATIVE_TOOL_CALLING", "SMALL_CONTEXT_MODE", "STRICT_JSON_ACTION",
    "TEXT_ACTION_TRANSLATION", "select_modes",
    "compact_prompt", "expand_via_search", "negotiate_tools",
    "ModelCapabilityProbe",
    "LegacyActionTranslator", "TranslationResult",
]
