"""Local Genesis runtime (Phase 2): persistent logical identity over Agent Bridge.

Genesis owns session/identity/memory refs; Agent Bridge owns execution.
Identity survives model rotation, worker replacement and restarts via a
JSON session store. No provider/model is special: rotation re-pings the
new model before switching. Additive only.
"""
from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from genesis_bridge import GenesisBridge, GenesisIdentity, GenesisSession


@dataclass
class GenesisEvent:
    kind: str = ""
    timestamp: float = field(default_factory=time.time)
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LocalGenesisRuntime(GenesisBridge):
    """Usable Genesis runtime backed by an Agent Bridge runtime factory."""

    def __init__(self, store_path: str | Path,
                 bridge_factory: Callable[[], Any] | None = None,
                 model_ping: Callable[[str], bool] | None = None):
        self.store_path = Path(store_path)
        self._bridge_factory = bridge_factory
        self._model_ping = model_ping or self._default_ping
        self.identity = GenesisIdentity()
        self.sessions: dict[str, GenesisSession] = {}
        self.events: list[dict[str, Any]] = []
        self._bridges: dict[str, Any] = {}
        self.load()

    # -- events ----------------------------------------------------------
    def _emit(self, kind: str, **detail: Any) -> None:
        self.events.append(GenesisEvent(kind=kind, detail=detail).to_dict())

    # -- identity ----------------------------------------------------------
    def identify(self, genesis_id: str, display_name: str = "Genesis") -> dict[str, Any]:
        self.identity.genesis_id = genesis_id
        self.identity.display_name = display_name
        self._emit("session.started", genesis_id=genesis_id)
        self.save()
        return self.identity.to_dict()

    def rotate_model(self, new_model: str) -> dict[str, Any]:
        """Ping-then-switch: identity continues only on a live model."""
        self._emit("model.selected", model=new_model)
        try:
            alive = bool(self._model_ping(new_model))
        except Exception as e:  # noqa: BLE001 - ping failure is a signal
            alive = False
            self._emit("fallback.triggered", model=new_model,
                       error=str(e)[:150])
        if not alive:
            self._emit("model.unavailable", model=new_model)
            return {"ok": False, "model": new_model,
                    "identity": self.identity.to_dict()}
        out = self.identity.rotate_model(new_model)
        self._emit("model.ready", model=new_model)
        self.save()
        return {"ok": True, **out}

    @staticmethod
    def _default_ping(model: str) -> bool:
        payload = {"model": model, "prompt": "ok", "stream": False,
                   "options": {"num_predict": 2, "temperature": 0}}
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/generate",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return bool(data.get("done", True)) or "response" in data
        except Exception:
            return False

    # -- delegation ----------------------------------------------------------
    def _bridge(self, genesis_session_id: str) -> Any:
        if self._bridge_factory is None:
            raise RuntimeError("no bridge factory configured")
        if genesis_session_id not in self._bridges:
            self._bridges[genesis_session_id] = self._bridge_factory()
        return self._bridges[genesis_session_id]

    def start_session(self, objective: str) -> GenesisSession:
        session = GenesisSession(
            session_id=f"gs-{int(time.time() * 1000) % 100000000:08d}",
            genesis_id=self.identity.genesis_id, objective=objective)
        self.sessions[session.session_id] = session
        self._emit("objective.received", session=session.session_id,
                   objective=objective)
        self.save()
        return session

    def submit_objective(self, objective: str,
                         budget: dict[str, Any] | None = None) -> str:
        session = self.start_session(objective)
        return session.session_id

    def delegate(self, handoff: dict[str, Any]) -> str:
        session_id = str(handoff.get("genesis_session", ""))
        if session_id not in self.sessions:
            raise KeyError(f"unknown genesis session: {session_id!r}")
        bridge = self._bridge(session_id)
        task_id = bridge.submit(
            dict(handoff, model=self.identity.active_model))
        self._emit("task.created", session=session_id, task=task_id)
        self._emit("worker.assigned", session=session_id, task=task_id)
        self.save()
        return str(task_id)

    def observe(self, task_id: str) -> dict[str, Any]:
        for sid, bridge in self._bridges.items():
            try:
                state = bridge.poll(task_id)
            except Exception:
                continue
            self._emit("task.observed", session=sid, task=task_id,
                       state=str(state.get("status", "")))
            return {"task_id": task_id, "session": sid, **state}
        return {"task_id": task_id, "status": "UNKNOWN"}

    def integrate(self, task_id: str) -> dict[str, Any]:
        obs = self.observe(task_id)
        ok = obs.get("status") in ("COMPLETED", "VERIFIED_COMPLETE")
        self._emit("verification.passed" if ok else "test.failed",
                   task=task_id)
        self._emit("task.completed", task=task_id, ok=ok)
        self.save()
        return {"task_id": task_id, "ok": ok, "observation": obs}

    # -- persistence ----------------------------------------------------------
    def save(self) -> str:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"identity": self.identity.to_dict(),
                "sessions": {k: asdict(v) for k, v in self.sessions.items()},
                "events": self.events[-500:]}
        self.store_path.write_text(json.dumps(data, indent=1), encoding="utf-8")
        return str(self.store_path)

    def load(self) -> bool:
        if not self.store_path.exists():
            return False
        try:
            data = json.loads(self.store_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        ident = data.get("identity", {})
        self.identity.genesis_id = str(ident.get("genesis_id", ""))
        self.identity.display_name = str(ident.get("display_name", "Genesis"))
        self.identity.active_model = str(ident.get("active_model", ""))
        self.identity.model_history = list(ident.get("model_history", []))
        for sid, s in data.get("sessions", {}).items():
            try:
                self.sessions[sid] = GenesisSession(**s)
            except TypeError:
                continue
        self.events = list(data.get("events", []))
        return True
