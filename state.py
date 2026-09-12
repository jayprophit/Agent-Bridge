"""Sessions, action IDs and lifecycle statuses (v0.3)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

PLANNING = "PLANNING"
EXECUTING = "EXECUTING"
WAITING_APPROVAL = "WAITING_APPROVAL"
TESTING = "TESTING"
REVIEWING = "REVIEWING"
REVISING = "REVISING"
COMPLETED = "COMPLETED"
FAILED = "FAILED"
ROLLED_BACK = "ROLLED_BACK"
CANCELLED = "CANCELLED"
# v0.4 additions
QUEUED = "QUEUED"
INTERRUPTED = "INTERRUPTED"
WAITING_FINAL_APPROVAL = "WAITING_FINAL_APPROVAL"

VALID_TRANSITIONS = {
    QUEUED: (PLANNING, CANCELLED),
    PLANNING: (EXECUTING, WAITING_APPROVAL, TESTING, COMPLETED, FAILED, CANCELLED),
    EXECUTING: (EXECUTING, WAITING_APPROVAL, TESTING, REVIEWING, REVISING,
                COMPLETED, FAILED, CANCELLED),
    WAITING_APPROVAL: (EXECUTING, TESTING, FAILED, CANCELLED),
    TESTING: (EXECUTING, REVIEWING, FAILED, CANCELLED),
    REVIEWING: (REVISING, COMPLETED, FAILED, CANCELLED),
    REVISING: (EXECUTING, TESTING, REVIEWING, FAILED, CANCELLED),
    WAITING_FINAL_APPROVAL: (COMPLETED, FAILED, CANCELLED, ROLLED_BACK),
    COMPLETED: (ROLLED_BACK,),
    FAILED: (ROLLED_BACK,),
    CANCELLED: (),
    INTERRUPTED: (PLANNING, EXECUTING, FAILED, CANCELLED, ROLLED_BACK),
    ROLLED_BACK: (),
}


def is_valid_transition(frm: str, to: str) -> bool:
    if frm == to:
        return True
    return to in VALID_TRANSITIONS.get(frm, ())


class BridgeSession:
    def __init__(self, task: str, mode: str, approval: str, workspace: str,
                 models: dict[str, str], session_id: str = "", task_id: str = ""):
        self.session_id = session_id or uuid.uuid4().hex[:12]
        self.task_id = task_id or uuid.uuid4().hex[:12]
        self.start_time = datetime.now().isoformat(timespec="seconds")
        self.task = task
        self.mode = mode
        self.approval = approval
        self.workspace = workspace
        self.models = models
        self.status = PLANNING
        self.step = 0
        self.revision = 0
        self.files_touched: list[str] = []
        self.tests_run = 0
        self.errors = 0
        self._action_seq = 0

    def next_action_id(self) -> str:
        self._action_seq += 1
        return f"a-{self.session_id}-{self.step}-{self._action_seq}"

    def set_status(self, to: str) -> None:
        """Guarded transition; raises ValueError on illegal jumps."""
        if not is_valid_transition(self.status, to):
            raise ValueError(f"illegal session transition {self.status} -> {to}")
        self.status = to

    def force_status(self, to: str) -> None:
        self.status = to

    def touch(self, path: str) -> None:
        if path and path not in self.files_touched:
            self.files_touched.append(path)

    def snapshot(self, **extra: Any) -> dict[str, Any]:
        d = {"session_id": self.session_id, "task_id": self.task_id,
             "start_time": self.start_time, "status": self.status,
             "step": self.step, "mode": self.mode, "approval": self.approval,
             "workspace": self.workspace, "models": self.models,
             "revision": self.revision, "files_touched": list(self.files_touched),
             "tests_run": self.tests_run, "errors": self.errors}
        d.update(extra)
        return d
