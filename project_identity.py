"""Canonical project identity + historical aliases (v1).

Owner correction 2026-09-16: CANONICAL_NAME = ATHENA (health/fitness/sports).
ATHEENA is a historical alias: it appears in older routing, registry records,
and analysis outputs. Rules:
- All NEW routing/registry/task references resolve aliases to canonical names.
- Historical raw text and dated run records are NEVER rewritten; they keep
  RAW_SOURCE_NAME with CANONICAL_RESOLVED_NAME recorded alongside.
"""
from __future__ import annotations

import re

CANONICAL_PROJECTS = ("GENESIS", "AGENT_BRIDGE", "IDE_WORKSPACE", "MAT",
                      "UNIVERSAL_BRIDGE", "POIETEK", "ATHENA", "AETHERIUS_OS")

# Canonical -> known historical spellings (all matched case-insensitively).
PROJECT_ALIASES = {
    "ATHENA": ("ATHEENA",),
}

_ALIAS_TO_CANONICAL = {a.upper(): c for c, als in PROJECT_ALIASES.items() for a in als}
_ALIAS_TO_CANONICAL.update({c.upper(): c for c in CANONICAL_PROJECTS})


def normalize_project(name: str) -> str:
    """Resolve a project name or historical alias to its canonical form."""
    if not name:
        return name
    return _ALIAS_TO_CANONICAL.get(name.strip().upper(), name.strip().upper())


def canonical_spellings(text: str) -> list[str]:
    """Find historical alias spellings present in text (for detection, not rewriting)."""
    found = []
    for alias in [a for als in PROJECT_ALIASES.values() for a in als]:
        if re.search(r"\b" + re.escape(alias) + r"\b", text, re.I):
            found.append(alias)
    return found
