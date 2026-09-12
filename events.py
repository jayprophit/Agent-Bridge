"""Event bus + structured logging (v0.3).

EventBus: observer/subscriber abstraction. CLI subscribes now; a future
Genesis GUI can subscribe later without touching policy logic.
EventLogger keeps the v0.2-compatible human + JSONL sinks and also acts
as a bus subscriber.
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any, Callable

APPROVAL_REQUESTED = "approval.requested"
APPROVAL_APPROVED = "approval.approved"
APPROVAL_DENIED = "approval.denied"
EXECUTION_STARTED = "execution.started"
EXECUTION_COMPLETED = "execution.completed"
EXECUTION_FAILED = "execution.failed"
REVIEW_STARTED = "review.started"
REVIEW_COMPLETED = "review.completed"
ROLLBACK_STARTED = "rollback.started"
ROLLBACK_COMPLETED = "rollback.completed"


def _now() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


class EventBus:
    def __init__(self):
        self._subs: dict[str, list[Callable[[dict], None]]] = {}
        self.history: list[dict[str, Any]] = []

    def subscribe(self, event: str, fn: Callable[[dict], None]) -> None:
        self._subs.setdefault(event, []).append(fn)

    def emit(self, event: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        evt = {"event": event, "timestamp": _now()}
        evt.update(payload or {})
        self.history.append(evt)
        for fn in list(self._subs.get(event, [])) + list(self._subs.get("*", [])):
            try:
                fn(evt)
            except Exception:
                pass
        return evt

    def of(self, event: str) -> list[dict[str, Any]]:
        return [e for e in self.history if e.get("event") == event]


class EventLogger:
    """v0.2-compatible human + JSONL logger, also a bus subscriber."""

    def __init__(self, human_path: str | Path | None, jsonl_path: str | Path | None,
                 model: str, mode: str, session_id: str | None = None,
                 bus: EventBus | None = None):
        import uuid as _u
        self.human_path = Path(human_path) if human_path else None
        self.jsonl_path = Path(jsonl_path) if jsonl_path else None
        self.model = model
        self.mode = mode
        self.session_id = session_id or _u.uuid4().hex[:12]
        self.bus = bus or EventBus()
        self.bus.subscribe("*", self._on_bus_event)

    def _write(self, path: Path | None, text: str) -> None:
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(text + "\n")
        except OSError:
            pass

    def human(self, text: str) -> None:
        line = f"[{_now()}] session={self.session_id} model={self.model} mode={self.mode} {text}"
        print(line, flush=True)
        self._write(self.human_path, line)

    def event(self, **fields: Any) -> None:
        evt = {"timestamp": _now(), "session_id": self.session_id,
               "mode": self.mode, "model": self.model}
        evt.update(fields)
        for k in ("api_key", "token", "password", "secret"):
            evt.pop(k, None)
        self._write(self.jsonl_path, json.dumps(evt)[:8000])

    def _on_bus_event(self, evt: dict[str, Any]) -> None:
        name = str(evt.get("event", ""))
        if name.startswith(("approval.", "execution.", "review.", "rollback.")):
            self.event(bus_event=name,
                       **{k: (str(v)[:1200]) for k, v in evt.items()
                          if k not in ("event", "timestamp")})
