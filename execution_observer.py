"""Real-time execution observability (Phase 1 acceptance).

Safe chain view for a delegated task:

  OWNER / SUPERVISOR -> AGENT BRIDGE -> WORKER -> REVIEWER / TESTER -> VERIFICATION

Exposes plan / status / evidence fields only. Never exposes hidden
chain-of-thought. Each event carries:

  task ID, current step, supervisor, worker, model, provider,
  execution mode, start time, duration, retry, fallback, status,
  CPU, RAM, GPU/VRAM, latency, tokens/sec, result, verification.

Persistence: JSON file, atomic writes, tolerant reload (a failed /
partial write never resets the in-memory chain).
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

STAGES = ("SUPERVISOR", "BRIDGE", "WORKER", "REVIEWER", "TESTER", "VERIFICATION")


def _now() -> float:
    return time.time()


@dataclass
class ChainEvent:
    event_id: str = field(default_factory=lambda: "ev-" + uuid.uuid4().hex[:8])
    task_id: str = ""
    step: int = 0
    stage: str = ""  # one of STAGES
    supervisor: str = ""
    worker: str = ""
    model: str = ""
    provider: str = ""
    execution_mode: str = "DELEGATED"  # DIRECT | DELEGATED
    status: str = ""
    start_ts: float = 0.0
    duration_s: float = 0.0
    retry: int = 0
    fallback: str = ""
    cpu_pct: float = 0.0
    ram_mb: float = 0.0
    gpu_pct: float = 0.0
    vram_mb: float = 0.0
    latency_ms: float = 0.0
    tokens_per_sec: float = 0.0
    result: str = ""
    verification: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ExecutionObserver:
    """Append-only per-task chain log with live current-step view."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else None
        self.events: list[ChainEvent] = []
        if self.path is not None and self.path.exists():
            self.load()

    def log(self, event: ChainEvent) -> ChainEvent:
        if event.stage and event.stage not in STAGES:
            raise ValueError(f"bad stage {event.stage!r}")
        if not event.event_id:
            event.event_id = "ev-" + uuid.uuid4().hex[:8]
        self.events.append(event)
        self._autosave()
        return event

    def chain(self, task_id: str) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self.events if e.task_id == task_id]

    def current_step(self, task_id: str) -> dict[str, Any]:
        items = [e for e in self.events if e.task_id == task_id]
        if not items:
            return {"task_id": task_id, "step": 0, "stage": "SUPERVISOR",
                    "status": "UNKNOWN"}
        last = items[-1]
        stages_seen = [e.stage for e in items]
        return {
            "task_id": task_id,
            "step": last.step,
            "stage": last.stage,
            "status": last.status,
            "supervisor": last.supervisor,
            "worker": last.worker,
            "model": last.model,
            "provider": last.provider,
            "execution_mode": last.execution_mode,
            "stages_seen": stages_seen,
            "verification": last.verification,
        }

    def summary(self, task_id: str) -> dict[str, Any]:
        items = [e for e in self.events if e.task_id == task_id]
        retries = sum(e.retry for e in items)
        fallbacks = [e.fallback for e in items if e.fallback]
        duration = round(sum(e.duration_s for e in items), 2)
        lat = [e.latency_ms for e in items if e.latency_ms]
        tps = [e.tokens_per_sec for e in items if e.tokens_per_sec]
        return {
            "task_id": task_id,
            "events": len(items),
            "retries": retries,
            "fallbacks": fallbacks,
            "duration_s": duration,
            "avg_latency_ms": round(sum(lat) / len(lat), 1) if lat else 0.0,
            "avg_tokens_per_sec": round(sum(tps) / len(tps), 1) if tps else 0.0,
            "final_status": items[-1].status if items else "UNKNOWN",
            "final_verification": items[-1].verification if items else "",
        }

    @staticmethod
    def from_bridge_evidence(evidence: dict[str, Any],
                             supervisor: str = "") -> "ExecutionObserver":
        """Build an observer chain from a real delegation evidence record.

        Uses only safe fields: session/models/steps/hashes/test result.
        No model chain-of-thought is recorded.
        """
        obs = ExecutionObserver()
        task_id = str(evidence.get("fixture_file", "delegation"))
        session = str(evidence.get("bridge_session_id", ""))
        model = str(evidence.get("coder_model", ""))
        planner = str(evidence.get("planner_model", ""))
        reviewer = str(evidence.get("reviewer_model", ""))
        steps = int(evidence.get("steps_executed", 0) or 0)
        status = str(evidence.get("final_status", ""))
        test_ok = bool(evidence.get("test_passed"))
        verdict = str(evidence.get("review_verdict", ""))
        t0 = float(evidence.get("timestamp", _now()))
        obs.log(ChainEvent(task_id=task_id, step=0, stage="SUPERVISOR",
                           supervisor=supervisor or "supervisor",
                           status="SUBMITTED", start_ts=t0,
                           result=str(evidence.get("task_description", ""))[:200]))
        obs.log(ChainEvent(task_id=task_id, step=1, stage="BRIDGE",
                           supervisor=supervisor or "supervisor",
                           worker=planner or model, model=planner or model,
                           provider="ollama", execution_mode="DELEGATED",
                           status="ROUTED", start_ts=t0,
                           result=f"session={session}"))
        obs.log(ChainEvent(task_id=task_id, step=2, stage="WORKER",
                           supervisor=supervisor or "supervisor",
                           worker=model, model=model, provider="ollama",
                           execution_mode="DELEGATED",
                           status="EXECUTED" if evidence.get("file_changed") else "NO_CHANGE",
                           start_ts=t0,
                           result=f"steps={steps} "
                                  f"before={evidence.get('file_before_hash')} "
                                  f"after={evidence.get('file_after_hash')}"))
        obs.log(ChainEvent(task_id=task_id, step=3, stage="REVIEWER",
                           supervisor=supervisor or "supervisor",
                           worker=reviewer or model, model=reviewer or model,
                           provider="ollama", execution_mode="DELEGATED",
                           status="REVIEWED", start_ts=t0, result=verdict))
        obs.log(ChainEvent(task_id=task_id, step=4, stage="TESTER",
                           supervisor=supervisor or "supervisor",
                           worker="tester", execution_mode="DELEGATED",
                           status="TEST_PASSED" if test_ok else "TEST_FAILED",
                           start_ts=t0,
                           result="ALL_TESTS_PASS" if test_ok else "FAIL"))
        obs.log(ChainEvent(task_id=task_id, step=5, stage="VERIFICATION",
                           supervisor=supervisor or "supervisor",
                           worker=model, model=model, provider="ollama",
                           execution_mode="DELEGATED", status=status,
                           start_ts=t0, verification=status,
                           result=f"file_changed={evidence.get('file_changed')}"))
        return obs

    # -- persistence -------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {"version": 1,
                "events": [e.to_dict() for e in self.events]}

    def save(self) -> str:
        if self.path is None:
            return ""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=1), encoding="utf-8")
        tmp.replace(self.path)
        return str(self.path)

    def _autosave(self) -> None:
        if self.path is not None:
            try:
                self.save()
            except OSError:
                pass

    def load(self) -> bool:
        if self.path is None or not self.path.exists():
            return False
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        events = []
        for ed in data.get("events") or []:
            try:
                events.append(ChainEvent(**ed))
            except TypeError:
                continue
        self.events = events
        return True
