"""Avatar controller (Phase 2): provider-independent visual presence.

The avatar is NOT Genesis itself: it renders state produced by Agent
Bridge (today) or Genesis (later) through AvatarEventAdapter. Visual
presentation stays separate from model/provider/agent/worker. Future:
Genesis runtime -> avatar events -> IDE avatar, with no rewrite.

States: idle, listening, thinking, planning, working, coding,
tool-use, testing, waiting, success, warning, error, offline.
Animation switching is the UI's job; this module owns state truth.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any


AVATAR_STATES: tuple[str, ...] = (
    "idle", "listening", "thinking", "planning", "working", "coding",
    "tool-use", "testing", "waiting", "success", "warning", "error",
    "offline",
)


@dataclass
class AvatarState:
    state: str = "idle"
    activity: str = ""
    progress_pct: float = 0.0
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Runtime/task states -> avatar states (deterministic mapping).
TASK_TO_AVATAR: dict[str, str] = {
    "QUEUED": "waiting",
    "PLANNING": "planning",
    "EXECUTING": "working",
    "TESTING": "testing",
    "REVIEWING": "thinking",
    "REVISING": "working",
    "COMPLETED": "success",
    "FAILED": "error",
    "CANCELLED": "warning",
    "ROLLED_BACK": "warning",
    "INTERRUPTED": "warning",
    "WAITING_APPROVAL": "waiting",
    "WAITING_FINAL_APPROVAL": "waiting",
}


class AvatarController:
    """Single source of truth for avatar presentation state."""

    def __init__(self):
        self.state = AvatarState()

    def set_state(self, state: str, activity: str = "",
                  progress_pct: float | None = None) -> AvatarState:
        if state not in AVATAR_STATES:
            raise ValueError(f"unknown avatar state: {state!r}")
        self.state.state = state
        if activity:
            self.state.activity = activity[:200]
        if progress_pct is not None:
            self.state.progress_pct = max(0.0, min(100.0, progress_pct))
        self.state.updated_at = time.time()
        return self.state

    def from_task_status(self, status: str, activity: str = "",
                         progress_pct: float | None = None) -> AvatarState:
        return self.set_state(TASK_TO_AVATAR.get(status, "thinking"),
                              activity, progress_pct)

    def offline(self) -> AvatarState:
        return self.set_state("offline", "backend unreachable")

    def snapshot(self) -> dict[str, Any]:
        return self.state.to_dict()


class AvatarEventAdapter:
    """Translate runtime/session events into avatar state transitions."""

    def __init__(self, controller: AvatarController | None = None):
        self.controller = controller or AvatarController()
        self.log: list[dict[str, Any]] = []

    def handle(self, event: dict[str, Any]) -> dict[str, Any]:
        kind = str(event.get("event", event.get("kind", "")))
        if kind in ("task.started", "task.assigned"):
            state = self.controller.from_task_status(
                "EXECUTING", str(event.get("task_id", "")))
        elif kind == "task.progress":
            try:
                pct = float(event.get("progress_pct", 0) or 0)
            except (TypeError, ValueError):
                pct = 0.0
            state = self.controller.set_state(
                "working", str(event.get("task_id", "")), pct)
        elif kind in ("task.completed", "verification.passed"):
            state = self.controller.from_task_status("COMPLETED")
        elif kind in ("task.failed", "test.failed"):
            state = self.controller.from_task_status("FAILED")
        elif kind == "fallback.triggered":
            state = self.controller.set_state(
                "warning", "fallback: " + str(event.get("from", "")))
        elif kind in ("approval.requested", "permission.requested"):
            state = self.controller.from_task_status("WAITING_APPROVAL")
        elif kind == "session.started":
            state = self.controller.set_state("listening")
        elif kind in ("tool.called", "tool.started"):
            state = self.controller.set_state(
                "tool-use", str(event.get("tool", "")))
        else:
            state = self.controller.snapshot()
            state = AvatarState(**state)
        record = {"event": kind, "state": state.to_dict()}
        self.log.append(record)
        return record

    def feed_session_events(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        for event in events:
            if isinstance(event, dict):
                self.handle(event)
        return self.controller.snapshot()
