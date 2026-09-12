"""Local shell preferences (display + submission defaults ONLY).

Preferences never touch security policy: approval levels, workspace roots,
quotas and network posture always come from the runtime. This module stores
UI choices (verbosity, default mode/profile presented to the user, last
workspace) and applies them as explicit submission parameters.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULTS = {
    "default_mode": "hybrid",
    "default_model_profile": "LOW_RESOURCE",
    "approval_preference": "AUTO_SAFE",  # offered choice, runtime may refuse
    "event_verbosity": "friendly",  # friendly | raw
    "display": {"colors": False, "page_size": 20},
    "workspace_root": "",
    "last_workspace": "",
}

PREFS_FILE = Path.home() / ".agent_shell_prefs.json"


class Prefs:
    def __init__(self, path: Path | None = None):
        self.path = path or PREFS_FILE
        self.data = dict(DEFAULTS)
        try:
            if self.path.exists():
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    for k, v in loaded.items():
                        if k in DEFAULTS:
                            self.data[k] = v
        except (OSError, ValueError):
            pass

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data, indent=2)[:8000],
                                 encoding="utf-8")
        except OSError:
            pass
