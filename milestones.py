"""Task milestone tracking (v0.6). Explicit required milestones verified
from execution evidence before FINISH is accepted.

Milestone keys (evidence-derived, never model claims):
  files_created, files_changed, tests_run, tests_passed, app_executed,
  output_observed, status_checked
"""
from __future__ import annotations

from typing import Any

KNOWN = ("files_created", "files_changed", "tests_run", "tests_passed",
         "app_executed", "output_observed", "status_checked")


def check(history: list[dict[str, Any]],
          required: list[str]) -> tuple[bool, list[str], str]:
    """Return (ok, missing, next_step). Unknown keys are ignored safely."""
    required = [m for m in required if m in KNOWN]
    if not required:
        return True, [], ""
    have: set[str] = set()
    for h in history:
        if not h.get("executed"):
            continue
        act = (h.get("action") or {}).get("action", "")
        res = h.get("result") or {}
        if not res.get("ok"):
            continue
        if act == "write" and not (h.get("action") or {}).get("path", "").startswith("."):
            have.add("files_created")
        if act in ("write", "edit", "patch", "copy", "move"):
            have.add("files_changed")
        if act == "test":
            have.add("tests_run")
            if res.get("passed"):
                have.add("tests_passed")
        if act == "shell":
            have.add("app_executed")
            if str(res.get("stdout", "")).strip():
                have.add("output_observed")
        if act in ("status", "capabilities"):
            have.add("status_checked")
    missing = [m for m in required if m not in have]
    if missing:
        nxt = {"files_created": "create the required file with a write action",
               "files_changed": "modify a file with edit/patch",
               "tests_run": "run a test command",
               "tests_passed": "make the failing test pass",
               "app_executed": "execute the application with a shell action",
               "output_observed": "run the app so it prints real output",
               "status_checked": "request the status action"}[missing[0]]
        return False, missing, nxt
    return True, [], ""
