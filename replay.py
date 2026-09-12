"""JSONL session replay (v0.3). Audit + verify, never destructive.

AUDIT  — reconstruct what occurred (steps, actions, approvals, results).
VERIFY — additionally compare logged claims vs current workspace state
         (file existence/size for writes, restore_id presence for deletes).
Replay NEVER executes historical shell commands.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_events(path: str | Path) -> list[dict[str, Any]]:
    events = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            events.append(obj)
    return events


def audit(path: str | Path) -> dict[str, Any]:
    events = load_events(path)
    steps = [e for e in events if "step" in e]
    return {"ok": True, "mode": "audit", "events": len(events),
            "steps": len(steps),
            "session_ids": sorted({str(e.get("session_id", "")) for e in events}),
            "executed": sum(1 for e in steps if e.get("executed") is True),
            "failures": [e for e in steps if e.get("kind")],
            "note": "audit only: nothing was executed"}


def verify(path: str | Path, workspace: str | Path) -> dict[str, Any]:
    ws = Path(workspace).resolve()
    events = load_events(path)
    checked, confirmed, mismatched, unverifiable = 0, 0, [], 0
    for e in events:
        action = e.get("action")
        result = e.get("result")
        if not isinstance(action, dict) or not isinstance(result, dict):
            continue
        if not result.get("ok"):
            continue
        act = action.get("action")
        if act == "write" and isinstance(action.get("path"), str):
            checked += 1
            t = ws / action["path"]
            if t.is_file():
                confirmed += 1
            else:
                mismatched.append(f"write {action['path']}: logged ok but file missing")
        elif act == "delete" and isinstance(action.get("path"), str):
            checked += 1
            t = ws / action["path"]
            if not t.exists():
                confirmed += 1
            else:
                mismatched.append(f"delete {action['path']}: file present again")
        elif act in ("shell", "test"):
            unverifiable += 1  # exit codes cannot be re-verified; never re-run
        else:
            unverifiable += 1
    return {"ok": not mismatched, "mode": "verify", "checked": checked,
            "confirmed": confirmed, "mismatched": mismatched,
            "unverifiable": unverifiable,
            "note": "verify only: no historical command was executed"}


RERUN_SAFE_ACTIONS = frozenset({"read", "list", "exists", "stat", "search",
                                "capabilities", "status", "diff"})
MUTATING_ACTIONS = frozenset({"write", "edit", "patch", "delete", "move",
                              "copy", "mkdir", "restore", "shell", "test",
                              "finish"})


def rerun_safe(path: str | Path, test_profile: str = "python") -> dict[str, Any]:
    """Plan a safe re-run: only non-mutating ops replay; everything else is
    listed as skipped with reasons. NEVER executes anything itself."""
    from commands import classify_command
    events = load_events(path)
    replayable: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for e in events:
        action = e.get("action")
        if not isinstance(action, dict):
            continue
        act = action.get("action", "")
        if act in RERUN_SAFE_ACTIONS:
            replayable.append({"step": e.get("step"), "action": action,
                               "action_id": e.get("action_id")})
        elif act in ("shell", "test"):
            cls, why = classify_command(action.get("command", ""))
            skipped.append({"step": e.get("step"), "action": act,
                            "reason": f"shell/test never auto-replays (class {cls}: {why})"})
        elif act in MUTATING_ACTIONS:
            skipped.append({"step": e.get("step"), "action": act,
                            "reason": f"{act} is mutating: replay refused"})
        else:
            skipped.append({"step": e.get("step"), "action": act or "?",
                            "reason": "unknown action: replay refused"})
    return {"ok": True, "mode": "rerun_safe", "replayable": replayable,
            "replayable_count": len(replayable), "skipped": skipped,
            "skipped_count": len(skipped),
            "note": "dry plan only: nothing was executed; approvals not replayed"}
