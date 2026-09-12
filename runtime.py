"""GENESIS LOCAL AGENT RUNTIME — public Python API (v0.4, stdlib only).

    runtime = AgentRuntime(RuntimeConfig(...))
    session = runtime.create_session(workspace=..., mode="hybrid")
    result = session.run_task("Build and test a small Python module")

Callers never touch executor/policy internals. Conservative local
concurrency (one worker thread per task). Storage is transparent
JSON/JSONL under .bridge/ — no database, no telemetry, no cloud.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from bridge import build_task_result, run_bridge
from checkpoints import CheckpointManager
from config import BridgeConfig
from errors import CANCELLED, INTERRUPTED
from events import EventBus
from state import (CANCELLED as ST_CANCELLED, COMPLETED, EXECUTING, FAILED,
                   INTERRUPTED as ST_INTERRUPTED, PLANNING, QUEUED,
                   ROLLED_BACK, is_valid_transition)
from versions import API_VERSION, RUNTIME_VERSION

TASK_ACTIVE = (QUEUED, PLANNING, EXECUTING, "WAITING_APPROVAL", "TESTING",
               "REVIEWING", "REVISING", "WAITING_FINAL_APPROVAL")


def _redact_event(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: ("<redacted>" if str(k).lower() in
                    ("token", "password", "secret", "api_key", "authorization")
                    else _redact_event(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact_event(v) for v in obj]
    if isinstance(obj, str) and ".bridge/" in obj.replace("\\", "/"):
        return "<internal>"
    return obj


@dataclass
class RuntimeConfig:
    allowed_workspace_roots: list[str] = field(default_factory=list)
    host: str = "127.0.0.1"  # localhost only by default; never 0.0.0.0
    port: int = 8471
    token: str = ""  # optional local bearer token; "" = disabled
    max_request_bytes: int = 1_000_000
    rate_limit_per_min: int = 120
    default_mode: str = "hybrid"
    default_approval: str = "AUTO_SAFE"
    default_model: str = "hhao/qwen2.5-coder-tools:3b"
    preset: str = "LOW_RESOURCE"  # LOW_RESOURCE | STANDARD | HIGH_QUALITY
    network_policy: str = "LOCAL_MODEL_NETWORK"  # + EXTERNAL_NETWORK (owner)
    task_timeout_s: int = 1800
    # v0.6 owner mode: BOTH profile selection and explicit authorization
    profile: str = ""
    owner_authorized: bool = False
    # v0.5: quotas, per-root rules, human final gate
    quotas: dict = field(default_factory=dict)
    root_rules: dict = field(default_factory=dict)  # root -> rule dict
    human_gate: str = "NONE"  # NONE|ON_REVIEW_REJECT|ON_REVIEW_REVISE|BEFORE_COMPLETE|ALWAYS
    gate_timeout_s: int = 1800


PRESET_QUOTAS = {
    "LOW_RESOURCE": {"max_active_sessions": 4, "max_active_tasks": 8,
                     "max_actions_per_task": 32, "max_events_retained": 1000,
                     "max_export_bytes": 1_000_000, "max_workspace_bytes": 200_000_000},
    "STANDARD": {"max_active_sessions": 16, "max_active_tasks": 32,
                 "max_actions_per_task": 64, "max_events_retained": 2000,
                 "max_export_bytes": 2_000_000, "max_workspace_bytes": 1_000_000_000},
    "HIGH_QUALITY": {"max_active_sessions": 32, "max_active_tasks": 64,
                     "max_actions_per_task": 128, "max_events_retained": 5000,
                     "max_export_bytes": 5_000_000, "max_workspace_bytes": 5_000_000_000},
}

APPROVAL_STRICTNESS = {"AUTO_SAFE": 0, "ASK_RISKY": 1, "ASK_ALL_WRITES": 2,
                       "READ_ONLY": 3}
VALID_GATES = ("NONE", "ON_REVIEW_REJECT", "ON_REVIEW_REVISE",
               "BEFORE_COMPLETE", "ALWAYS")


@dataclass
class TaskRequest:
    text: str
    idempotency_key: str = ""
    timeout_s: int = 0


@dataclass
class TaskResult:
    session_id: str
    task_id: str
    status: str
    mode: str
    models_used: dict
    summary: str
    files_created: list
    files_modified: list
    files_deleted: list
    commands_executed: list
    tests: dict
    review_verdict: str
    revision_count: int
    approvals: list
    errors: list
    duration_s: float
    finished_reason: str
    task_result: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RuntimeApproval:
    """ApprovalInterface that pauses the worker and waits for an external
    decision (service endpoint / SDK / CLI). Never auto-approves."""

    def __init__(self, session: "Session", timeout_s: int = 600):
        self.session = session
        self.timeout_s = timeout_s

    def request(self, action: dict[str, Any], context: dict[str, Any]) -> str:
        from policy import DECIDE_APPROVE_ONCE, DECIDE_APPROVE_SESSION, DECIDE_DENY
        aid = f"ap-{uuid.uuid4().hex[:10]}"
        evt: dict[str, Any] = {"id": aid, "action": action, "context": context,
                               "decision": None, "resolved": threading.Event()}
        with self.session.lock:
            self.session.pending_approvals[aid] = evt
            self.session.status = "WAITING_APPROVAL"
        self.session.bus.emit("approval.requested",
                              {"approval_id": aid, "action": action,
                               "risk": context.get("risk", "")})
        got = evt["resolved"].wait(self.timeout_s)
        with self.session.lock:
            self.session.pending_approvals.pop(aid, None)
            if self.session.status == "WAITING_APPROVAL":
                self.session.status = EXECUTING
        decision = evt["decision"] if got else DECIDE_DENY
        self.session.bus.emit("approval.resolved",
                              {"approval_id": aid, "decision": decision})
        return decision or DECIDE_DENY


class TaskRecord:
    def __init__(self, task_id: str, text: str, idempotency_key: str = "",
                 parent_task_id: str = ""):
        self.task_id = task_id
        self.text = text
        self.idempotency_key = idempotency_key
        self.parent_task_id = parent_task_id
        self.status = QUEUED
        self.result: dict[str, Any] | None = None
        self.error = ""
        self.submitted_at = time.time()
        self.ended_at = 0.0
        self.thread: threading.Thread | None = None


class Session:
    def __init__(self, runtime: "AgentRuntime", session_id: str, workspace: Path,
                 mode: str, bridge_cfg: BridgeConfig,
                 provider_factory: Callable[[str], Any] | None = None):
        self.runtime = runtime
        self.session_id = session_id
        self.workspace = workspace
        self.mode = mode
        self.bridge_cfg = bridge_cfg
        self.provider_factory = provider_factory
        self.lock = threading.RLock()
        self.status = QUEUED
        self.tasks: dict[str, TaskRecord] = {}
        self.events: list[dict[str, Any]] = []
        self.bus = EventBus()
        self.bus.subscribe("*", self._record_event)
        self.pending_approvals: dict[str, dict] = {}
        self.created_at = time.time()
        self.metrics = {"actions": 0, "executed": 0, "blocked": 0}
        self.last_submit_deduped = False

    def _record_event(self, evt: dict) -> None:
        with self.lock:
            self.events.append(evt)
            cap = self.runtime.cfg.quotas.get("max_events_retained", 2000)
            self.events = self.events[-cap:]
        # human final gate may be waiting on terminal events
        if evt.get("event") in ("task.completed", "task.failed"):
            gate = getattr(self, "_gate", None)
            if gate is not None:
                gate["event"].set()

    # -- lifecycle ---------------------------------------------------------
    def submit_task(self, text: str, idempotency_key: str = "",
                    parent_task_id: str = "") -> str:
        """Submit without blocking. Same key+payload returns existing task."""
        if len(text.encode()) > self.runtime.cfg.max_request_bytes:
            raise ValueError("task text exceeds max_request_bytes")
        _, active_tasks = self.runtime._active_counts()
        if active_tasks >= self.runtime.cfg.quotas["max_active_tasks"]:
            raise ValueError("quota exhausted: max_active_tasks")
        digest = hashlib.sha256(text.encode()).hexdigest()[:16]
        with self.lock:
            if idempotency_key:
                for t in self.tasks.values():
                    if t.idempotency_key == idempotency_key and \
                            hashlib.sha256(t.text.encode()).hexdigest()[:16] == digest:
                        self.bus.emit("task.deduplicated",
                                      {"task_id": t.task_id,
                                       "idempotency_key": idempotency_key})
                        self.last_submit_deduped = True
                        return t.task_id
            self.last_submit_deduped = False
            tid = f"t-{uuid.uuid4().hex[:10]}"
            rec = TaskRecord(tid, text, idempotency_key)
            rec.parent_task_id = parent_task_id
            self.tasks[tid] = rec
            self.status = QUEUED
            self.bus.emit("task.started", {"task_id": tid})
        # per-task action budget from quota (conservative cap on bridge steps)
        cap = self.runtime.cfg.quotas["max_actions_per_task"]
        if self.bridge_cfg.max_steps > cap:
            self.bridge_cfg.max_steps = cap
        th = threading.Thread(target=self._execute, args=(tid,), daemon=True,
                              name=f"task-{tid}")
        rec.thread = th
        th.start()
        return tid

    def _execute(self, task_id: str) -> None:
        rec = self.tasks[task_id]
        rec.status = PLANNING
        with self.lock:
            self.status = PLANNING
        self.bus.emit("planning.started", {"task_id": task_id})
        t0 = time.time()
        try:
            providers: dict[str, Any] = {}
            if self.provider_factory:
                for role in ("planner", "coder", "reviewer", "general"):
                    try:
                        providers[role] = self.provider_factory(role)
                    except Exception:
                        pass
            approval_iface = None
            if not self.bridge_cfg.non_interactive:
                approval_iface = RuntimeApproval(self)
            out = run_bridge(self.bridge_cfg, rec.text,
                             providers=providers or None,
                             approval_interface=approval_iface)
            self.bus.emit("planning.completed", {"task_id": task_id})
            rec.result = out.get("task_result") or {
                "session_id": self.session_id, "task_id": task_id,
                "status": out.get("status", "FAILED"),
                "finished_reason": out.get("error", out.get("message", "")),
                "history": out.get("history", [])}
            rec.result.setdefault("task_id", task_id)
            rec.result["task_id"] = task_id  # runtime id wins over bridge id
            rec.status = out.get("status", FAILED)
            gated = self._apply_final_gate(rec)
            if gated:
                rec.status, extra = gated
                rec.result.update(extra)
                rec.result["status"] = rec.status
            for h in out.get("history", []):
                if h.get("executed"):
                    self.metrics["executed"] += 1
                elif h.get("kind") in ("APPROVAL_DENIED", "VALIDATION_ERROR",
                                       "MODEL_OUTPUT_ERROR"):
                    self.metrics["blocked"] += 1
                self.metrics["actions"] += 1
            self.runtime.metrics["tasks_completed"] += 1
        except Exception as e:  # never lose the task
            rec.status = FAILED
            rec.error = f"{type(e).__name__}: {e}"
            rec.result = {"session_id": self.session_id, "task_id": task_id,
                          "status": FAILED, "finished_reason": rec.error}
            self.runtime.metrics["tasks_failed"] += 1
        finally:
            rec.ended_at = time.time()
            with self.lock:
                self.status = rec.status
            self.bus.emit("task.completed" if rec.status == COMPLETED else "task.failed",
                          {"task_id": task_id, "status": rec.status,
                           "duration_s": round(rec.ended_at - t0, 2)})
            try:
                self.runtime._save_metrics()
            except Exception:
                pass

    def _gate_needed(self, rec: TaskRecord) -> bool:
        gate = self.runtime.cfg.human_gate
        if gate == "ALWAYS":
            return rec.status == COMPLETED
        if gate == "BEFORE_COMPLETE":
            return rec.status == COMPLETED
        verdict = ((rec.result or {}).get("review_verdict")
                   if isinstance(rec.result, dict) else "")
        if gate == "ON_REVIEW_REJECT":
            return verdict == "reject"
        if gate == "ON_REVIEW_REVISE":
            return verdict == "revise"
        return False

    def _apply_final_gate(self, rec: TaskRecord):
        """Optional human final gate. Returns (status, extra) or None."""
        if not self._gate_needed(rec):
            return None
        gate = {"task_id": rec.task_id, "decision": None, "note": "",
                "resolved": threading.Event()}
        with self.lock:
            self._gate = gate
            self.status = "WAITING_FINAL_APPROVAL"
            rec.status = "WAITING_FINAL_APPROVAL"  # held: not final yet
        self.bus.emit("gate.waiting", {"task_id": rec.task_id,
                                       "policy": self.runtime.cfg.human_gate})
        got = gate["resolved"].wait(self.runtime.cfg.gate_timeout_s)
        with self.lock:
            self._gate = None
        if not got or not gate["decision"]:
            self.bus.emit("gate.timeout", {"task_id": rec.task_id})
            return FAILED, {"finished_reason":
                            "final approval timeout: never auto-accepted"}
        action = gate["decision"]
        note = gate.get("note", "")
        if action == "accept":
            self.bus.emit("gate.resolved", {"task_id": rec.task_id,
                                            "decision": "accept"})
            return COMPLETED, {"final_approval": "accepted by user"}
        if action == "rollback":
            rb = self.rollback()
            self.bus.emit("gate.resolved", {"task_id": rec.task_id,
                                            "decision": "rollback"})
            return ROLLED_BACK, {"final_approval": "rolled back by user",
                                 "rollback": rb}
        if action == "revise":
            child = self.submit_task(
                f"User revision request on task {rec.task_id}: {note}",
                parent_task_id=rec.task_id)
            self.bus.emit("gate.resolved", {"task_id": rec.task_id,
                                            "decision": "revise",
                                            "child": child})
            return ST_CANCELLED, {"finished_reason":
                                  f"superseded by user revision {child}",
                                  "revision_child": child}
        self.bus.emit("gate.resolved", {"task_id": rec.task_id,
                                        "decision": "cancel"})
        return ST_CANCELLED, {"finished_reason": "cancelled at final gate"}

    def resolve_final(self, task_id: str, action: str, note: str = "") -> dict[str, Any]:
        if action not in ("accept", "revise", "rollback", "cancel"):
            raise ValueError(f"bad final action: {action!r}")
        with self.lock:
            gate = getattr(self, "_gate", None)
            if not gate or gate["task_id"] != task_id:
                raise KeyError(f"no pending final gate for task: {task_id}")
            gate["decision"] = action
            gate["note"] = note
            gate["resolved"].set()
        return {"ok": True, "task_id": task_id, "decision": action}

    def request_revision(self, task_id: str, instruction: str) -> str:
        """User revision request: new linked task, original history untouched."""
        with self.lock:
            if task_id not in self.tasks:
                raise KeyError(f"unknown task: {task_id}")
        child = self.submit_task(
            f"User revision request on task {task_id}: {instruction}",
            parent_task_id=task_id)
        self.bus.emit("revision.requested", {"parent": task_id, "child": child,
                                             "instruction": instruction[:500]})
        return child

    def status_dashboard(self) -> dict[str, Any]:
        with self.lock:
            tasks = {t: r.status for t, r in self.tasks.items()}
            details = {t: {"status": r.status,
                           "parent": getattr(r, "parent_task_id", "")}
                       for t, r in self.tasks.items()}
            last = None
            for r in self.tasks.values():
                if isinstance(r.result, dict):
                    last = r.result
        tr = last or {}
        return {
            "session_id": self.session_id, "status": self.status, "mode": self.mode,
            "tasks": tasks, "task_details": details,
            "step": (tr.get("history") or [{}])[-1].get("step", 0) if tr.get("history") else 0,
            "models": (tr.get("models_used") or {}),
            "files_touched": ((tr.get("files_created") or []) +
                              (tr.get("files_modified") or [])),
            "tests": tr.get("tests", {}),
            "review": tr.get("review_verdict", ""),
            "approvals": tr.get("approvals", []),
            "errors": tr.get("errors", []),
            "duration_s": tr.get("duration_s", 0),
            "competence": (tr.get("competence") or {}),
            "pending_approvals": list(self.pending_approvals),
            "pending_final": bool(getattr(self, "_gate", None)),
        }

    def wait_task(self, task_id: str, timeout: float = 1200) -> dict[str, Any]:
        rec = self.tasks[task_id]
        th = rec.thread
        if th is not None:
            th.join(timeout)
        with self.lock:
            gate_open = bool(getattr(self, "_gate", None)) and \
                getattr(self, "_gate", {}).get("task_id") == task_id
            if rec.result is None or gate_open or rec.status == "WAITING_FINAL_APPROVAL":
                return {"session_id": self.session_id, "task_id": task_id,
                        "status": rec.status, "pending": True,
                        "pending_final": gate_open}
            return dict(rec.result)

    def run_task(self, text: str, idempotency_key: str = "",
                 timeout: float = 1200) -> dict[str, Any]:
        return self.wait_task(self.submit_task(text, idempotency_key), timeout)

    def cancel_task(self, task_id: str) -> dict[str, Any]:
        from bridge import request_cancel
        request_cancel()
        with self.lock:
            rec = self.tasks.get(task_id)
            if rec and rec.status in TASK_ACTIVE:
                rec.status = ST_CANCELLED
            self.status = ST_CANCELLED
        self.bus.emit("task.cancelled", {"task_id": task_id})
        return {"ok": True, "task_id": task_id, "status": ST_CANCELLED}

    def task_status(self, task_id: str) -> dict[str, Any]:
        with self.lock:
            rec = self.tasks[task_id]
            return {"task_id": task_id, "status": rec.status,
                    "pending": rec.result is None,
                    "result": rec.result}

    def events_since(self, index: int = 0) -> dict[str, Any]:
        with self.lock:
            return {"events": self.events[index:], "next_index": len(self.events)}

    def resolve_approval(self, approval_id: str, decision: str) -> dict[str, Any]:
        from policy import DECIDE_APPROVE_ONCE, DECIDE_APPROVE_SESSION, DECIDE_DENY
        if decision not in (DECIDE_APPROVE_ONCE, DECIDE_APPROVE_SESSION, DECIDE_DENY):
            raise ValueError(f"bad decision: {decision!r}")
        with self.lock:
            evt = self.pending_approvals.get(approval_id)
            if not evt:
                raise KeyError(f"unknown approval: {approval_id}")
            evt["decision"] = decision
            evt["resolved"].set()
        return {"ok": True, "approval_id": approval_id, "decision": decision}

    def rollback(self, label: str = "") -> dict[str, Any]:
        from checkpoints import CheckpointManager
        self.bus.emit("rollback.started", {"session": self.session_id})
        mgr = CheckpointManager(self.workspace,
                                label or f"bridge-v06-{self.session_id}")
        # legacy labels from older runtimes remain readable (never written)
        if not (mgr.dir / "manifest.json").exists():
            for legacy in (f"bridge-v04-{self.session_id}",
                           f"bridge-v03-{self.session_id}"):  # legacy-reader
                alt = CheckpointManager(self.workspace, legacy)
                if (alt.dir / "manifest.json").exists():
                    mgr = alt
                    break
        out = mgr.rollback()
        with self.lock:
            if out.get("ok"):
                self.status = ROLLED_BACK
        self.bus.emit("rollback.completed", {"ok": out.get("ok")})
        return out


class AgentRuntime:
    """Public entry point. Owns roots policy, sessions, metrics, health."""

    def __init__(self, cfg: RuntimeConfig | None = None,
                 provider_factory: Callable[[str], Any] | None = None):
        self.cfg = cfg or RuntimeConfig()
        if self.cfg.human_gate not in VALID_GATES:
            raise ValueError(f"human_gate must be one of {VALID_GATES}")
        if self.cfg.network_policy not in ("LOCAL_MODEL_NETWORK", "NO_NETWORK",
                                           "EXTERNAL_NETWORK"):
            raise ValueError("unknown network_policy")
        # quotas: explicit values win, preset fills the rest (LOW_RESOURCE first-class)
        base = dict(PRESET_QUOTAS.get(self.cfg.preset, PRESET_QUOTAS["LOW_RESOURCE"]))
        base.update(self.cfg.quotas or {})
        for k, v in base.items():
            if not isinstance(v, int) or v <= 0:
                raise ValueError(f"quota {k!r} must be a positive integer")
        self.cfg.quotas = base
        self.provider_factory = provider_factory
        self.lock = threading.RLock()
        self.sessions: dict[str, Session] = {}
        self.metrics = {"sessions": 0, "tasks_completed": 0, "tasks_failed": 0,
                        "tasks_deduplicated": 0}
        for r in self.cfg.allowed_workspace_roots:
            p = Path(r).expanduser()
            if not p.exists():
                raise ValueError(f"workspace root does not exist: {r}")
        self._validate_root_rules()

    def _root_rule(self, workspace: Path) -> dict[str, Any]:
        for root, rule in (self.cfg.root_rules or {}).items():
            try:
                workspace.relative_to(Path(root).expanduser().resolve())
                if isinstance(rule, dict):
                    return rule
            except ValueError:
                continue
        return {}

    def _validate_root_rules(self) -> None:
        from config import VALID_APPROVALS, VALID_MODES
        for root, rule in (self.cfg.root_rules or {}).items():
            if not isinstance(rule, dict):
                raise ValueError(f"root rule {root!r} must be an object")
            for m in rule.get("allowed_modes", []) or []:
                if m not in VALID_MODES:
                    raise ValueError(f"root {root!r}: unknown mode {m!r}")
            ap = rule.get("allowed_approval", "")
            if ap:
                if ap not in VALID_APPROVALS:
                    raise ValueError(f"root {root!r}: unknown approval {ap!r}")
                # a root may only restrict, never weaken global policy
                if APPROVAL_STRICTNESS[ap] < APPROVAL_STRICTNESS.get(
                        self.cfg.default_approval, 0):
                    raise ValueError(
                        f"root {root!r}: approval {ap!r} weakens global "
                        f"{self.cfg.default_approval!r}")
            for qk in ("max_concurrent_sessions", "max_workspace_bytes"):
                if qk in rule and (not isinstance(rule[qk], int) or rule[qk] <= 0):
                    raise ValueError(f"root {root!r}: bad quota {qk!r}")

    # -- host policy ---------------------------------------------------------
    def authorize_workspace(self, workspace: str | Path) -> Path:
        ws = Path(workspace).expanduser().resolve()
        for root in self.cfg.allowed_workspace_roots:
            rp = Path(root).expanduser().resolve()
            try:
                ws.relative_to(rp)
                if ws.exists() and ws.is_dir():
                    return ws
            except ValueError:
                continue
        raise PermissionError(
            f"workspace {ws} is outside allowed roots {self.cfg.allowed_workspace_roots}")

    # -- sessions --------------------------------------------------------------
    def _active_counts(self) -> tuple[int, int]:
        with self.lock:
            ns = sum(1 for s in self.sessions.values()
                     if any(t.status in TASK_ACTIVE for t in s.tasks.values()))
            nt = sum(1 for s in self.sessions.values() for t in s.tasks.values()
                     if t.status in TASK_ACTIVE)
        return ns, nt

    def create_session(self, workspace: str | Path, mode: str = "",
                       approval: str = "", model: str = "",
                       roles: dict | None = None,
                       profile: str = "", owner_authorized: bool = False,
                       network_policy: str = "") -> Session:
        ws = self.authorize_workspace(workspace)
        mode = mode or self.cfg.default_mode
        approval = approval or self.cfg.default_approval
        profile = profile or self.cfg.profile
        owner_authorized = owner_authorized or self.cfg.owner_authorized
        network_policy = network_policy or self.cfg.network_policy
        if profile == "OWNER_FULL_ACCESS":
            if not owner_authorized:
                raise PermissionError(
                    "OWNER_FULL_ACCESS requires explicit owner authorization")
            approval = "OWNER_AUTO_APPROVE"
            if network_policy == "LOCAL_MODEL_NETWORK":
                network_policy = "EXTERNAL_NETWORK"
        rule = self._root_rule(ws)
        if rule.get("allowed_modes") and mode not in rule["allowed_modes"]:
            raise PermissionError(
                f"mode {mode!r} not allowed under this root (rule allows "
                f"{rule['allowed_modes']})")
        if rule.get("allowed_approval"):
            need = APPROVAL_STRICTNESS[rule["allowed_approval"]]
            if APPROVAL_STRICTNESS.get(approval, 0) < need:
                raise PermissionError(
                    f"approval {approval!r} weakened below root minimum "
                    f"{rule['allowed_approval']!r}")
        with self.lock:
            active_sessions = sum(
                1 for s in self.sessions.values()
                if any(t.status in TASK_ACTIVE for t in s.tasks.values()))
            if active_sessions >= self.cfg.quotas["max_active_sessions"]:
                raise ValueError("quota exhausted: max_active_sessions")
            if rule.get("max_concurrent_sessions") is not None:
                n = sum(1 for s in self.sessions.values()
                        if s.workspace == ws or
                        str(s.workspace).startswith(str(ws)))
                if n >= rule["max_concurrent_sessions"]:
                    raise ValueError("root quota exhausted: max_concurrent_sessions")
        sid = f"s-{uuid.uuid4().hex[:10]}"
        bcfg = BridgeConfig(
            workspace=ws, mode=mode,
            approval=approval,
            model=model or self.cfg.default_model,
            non_interactive=True)
        if profile:
            bcfg.profile = profile
        if owner_authorized:
            bcfg.owner_authorized = True
        bcfg.network_policy = network_policy
        bcfg.shell_profile = "owner" if profile == "OWNER_FULL_ACCESS" \
            else bcfg.shell_profile
        bcfg.__post_init__()
        # honor timeout/step env knobs (no explicit API params exist for them)
        import os as _os
        for _var, _attr in (("BRIDGE_REQUEST_TIMEOUT", "request_timeout_s"),
                            ("BRIDGE_SHELL_TIMEOUT", "shell_timeout_s"),
                            ("BRIDGE_MAX_STEPS", "max_steps")):
            if _os.environ.get(_var):
                try:
                    setattr(bcfg, _attr, int(_os.environ[_var]))
                except ValueError:
                    pass
        if roles:
            from config import RoleModels
            bcfg.roles = RoleModels(**{k: roles.get(k, "") for k in
                                       ("planner", "coder", "reviewer", "general")})
        bcfg.session_id = sid
        sess = Session(self, sid, ws, bcfg.mode, bcfg, self.provider_factory)
        with self.lock:
            self.sessions[sid] = sess
            self.metrics["sessions"] += 1
        sess.bus.emit("session.created", {"session_id": sid, "mode": sess.mode})
        return sess

    def get_session(self, session_id: str) -> Session:
        with self.lock:
            if session_id not in self.sessions:
                raise KeyError(f"unknown session: {session_id}")
            return self.sessions[session_id]

    def delete_session(self, session_id: str) -> dict[str, Any]:
        with self.lock:
            sess = self.get_session(session_id)
            active = [t for t in sess.tasks.values() if t.status in TASK_ACTIVE]
            if active:
                raise ValueError("session has active tasks; cancel first")
            del self.sessions[session_id]
        return {"ok": True, "session_id": session_id}

    def load_session(self, session_id: str, workspace: str | Path) -> Session:
        """Recover persisted state after restart. Active work resumes as
        INTERRUPTED and requires an explicit new task (never auto-resumed)."""
        ws = self.authorize_workspace(workspace)
        snap_path = ws / ".bridge" / "sessions" / session_id / "session.json"
        if not snap_path.exists():
            raise KeyError(f"no persisted session: {session_id}")
        snap = json.loads(snap_path.read_text(encoding="utf-8"))
        bcfg = BridgeConfig(workspace=ws, mode=snap.get("mode", "build"),
                            approval=snap.get("approval", "AUTO_SAFE"),
                            non_interactive=True)
        bcfg.session_id = session_id
        sess = Session(self, session_id, ws, bcfg.mode, bcfg, self.provider_factory)
        sess.status = ST_INTERRUPTED
        with self.lock:
            self.sessions[session_id] = sess
        sess.bus.emit("session.recovered", {"session_id": session_id,
                                            "status": ST_INTERRUPTED})
        return sess

    # -- model inventory (public, safe metadata only) --------------------------
    def model_inventory(self) -> dict[str, Any]:
        from providers import ProviderError, create_provider
        try:
            prov = create_provider("ollama", host="http://127.0.0.1:11434",
                                   model=self.cfg.default_model, timeout_s=10)
            raw = prov._get("/api/tags") if hasattr(prov, "_get") else {"models": []}
            out = []
            for m in raw.get("models", []):
                details = m.get("details", {}) or {}
                out.append({
                    "name": m.get("name", ""),
                    "size_bytes": m.get("size", 0),
                    "modified": m.get("modified_at", ""),
                    "availability": "local",
                    "kind": "local",
                    "parameter_size": details.get("parameter_size", ""),
                    "context": details.get("context_length", 0),
                    "capabilities": m.get("capabilities", []),
                })
            return {"ok": True, "source": "ollama@127.0.0.1", "models": out}
        except ProviderError as e:
            return {"ok": False, "source": "ollama@127.0.0.1", "models": [],
                    "error": str(e)[:200]}

    # -- session history / export / inspection ---------------------------------
    def list_sessions(self, status: str = "", workspace: str = "",
                      since_ts: float = 0.0) -> list[dict[str, Any]]:
        with self.lock:
            items = []
            for sid, s in self.sessions.items():
                if status and s.status != status:
                    continue
                if workspace and str(s.workspace) != str(Path(workspace).resolve()):
                    continue
                if since_ts and s.created_at < since_ts:
                    continue
                items.append({"session_id": sid, "status": s.status,
                              "mode": s.mode, "workspace": str(s.workspace),
                              "created_at": s.created_at,
                              "tasks": {t: r.status for t, r in s.tasks.items()}})
            return items

    def session_diff(self, session_id: str, target: str = "session",
                     path: str = "", label: str = "") -> dict[str, Any]:
        import difflib
        import json as _j
        s = self.get_session(session_id)
        if target == "file" and path:
            t = (s.workspace / path).resolve()
            try:
                t.relative_to(s.workspace)
            except ValueError:
                raise PermissionError("path escapes session workspace")
            before = ""
            mgr_dir = s.workspace / ".bridge" / "checkpoints"
            for man in sorted(mgr_dir.glob("*/manifest.json")):
                try:
                    files = _j.loads(man.read_text()) .get("files", {})
                except (OSError, ValueError):
                    continue
                if path in files and files[path].get("backup"):
                    try:
                        before = (s.workspace / files[path]["backup"]).read_bytes(
                        ).decode("utf-8", "replace")
                        break
                    except OSError:
                        pass
            after = t.read_text(encoding="utf-8") if t.is_file() else ""
            diff = "\n".join(difflib.unified_diff(
                before.splitlines(), after.splitlines(),
                f"a/{path}", f"b/{path}"))[:8000]
            return {"ok": True, "diff": diff or "(no changes)"}
        # session/checkpoint diff from manifest blobs
        mgr_dir = s.workspace / ".bridge" / "checkpoints"
        diffs = []
        labels = [label] if label else sorted(p.name for p in mgr_dir.iterdir()
                                              if p.is_dir())
        for lbl in labels[:5]:
            man = mgr_dir / lbl / "manifest.json"
            if not man.exists():
                continue
            try:
                files = _j.loads(man.read_text()).get("files", {})
            except (OSError, ValueError):
                continue
            for rel, en in files.items():
                if target == "session" or True:
                    b = ""
                    if en.get("backup"):
                        try:
                            b = (s.workspace / en["backup"]).read_bytes().decode(
                                "utf-8", "replace")
                        except OSError:
                            pass
                    t = s.workspace / rel
                    a = t.read_text(encoding="utf-8") if t.is_file() else ""
                    d = "\n".join(difflib.unified_diff(
                        b.splitlines(), a.splitlines(), f"a/{rel}", f"b/{rel}"))
                    if d:
                        diffs.append(d)
        return {"ok": True, "diff": "\n".join(diffs)[:8000] or "(no changes)"}

    def session_manifest(self, session_id: str) -> dict[str, Any]:
        import json as _j
        s = self.get_session(session_id)
        entries: list[dict[str, Any]] = []
        mgr_dir = s.workspace / ".bridge" / "checkpoints"
        for man in sorted(mgr_dir.glob("*/manifest.json")):
            try:
                files = _j.loads(man.read_text()).get("files", {})
            except (OSError, ValueError):
                continue
            for rel in files:
                entries.append({"path": rel, "backup": bool(files[rel].get("backup")),
                                "existed": bool(files[rel].get("existed"))})
        # never expose protected internals
        entries = [e for e in entries if not e["path"].startswith(".bridge")]
        return {"ok": True, "session_id": session_id, "changes": entries}

    def session_scorecard(self, session_id: str) -> dict[str, Any]:
        from resultkit import scorecard
        s = self.get_session(session_id)
        with s.lock:
            last = None
            for r in s.tasks.values():
                if isinstance(r.result, dict):
                    last = r.result
        if not last:
            return {"ok": False, "error": "no completed task yet"}
        return {"ok": True, "scorecard": scorecard(last)}

    def session_timeline(self, session_id: str) -> dict[str, Any]:
        from resultkit import timeline
        s = self.get_session(session_id)
        with s.lock:
            return {"ok": True, "timeline": timeline(list(s.events))}

    def export_result(self, session_id: str, task_id: str = "",
                      fmt: str = "json") -> str:
        from resultkit import export_json, export_markdown
        s = self.get_session(session_id)
        with s.lock:
            rec = s.tasks.get(task_id) if task_id else None
            if rec is None:
                recs = [r for r in s.tasks.values() if isinstance(r.result, dict)]
                if not recs:
                    raise KeyError("no completed task to export")
                rec = recs[-1]
            result = dict(rec.result or {})
            events = list(s.events)
        cap = self.cfg.quotas.get("max_export_bytes", 2_000_000)
        if fmt == "markdown":
            return export_markdown(result, events)[:cap]
        if fmt == "jsonl":
            import json as _j
            lines = [_j.dumps(_redact_event(e)) for e in events[-500:]]
            lines.append(_j.dumps({"export": "task_result",
                                   "result": _redact_event(result)}))
            return "\n".join(lines)[:cap]
        return export_json(result, events, max_bytes=cap)

    # -- diagnostics / self-check ----------------------------------------------
    def diagnostics(self) -> dict[str, Any]:
        import time as _t
        diag: dict[str, Any] = {
            "runtime": RUNTIME_VERSION, "generated_at": _t.time(),
            "health": self.health(),
            "inventory": {"models": [m["name"] for m in
                                     self.model_inventory().get("models", [])]},
            "metrics": dict(self.metrics),
            "sessions": [{"session_id": sid, "status": s.status}
                         for sid, s in self.sessions.items()],
        }
        return diag

    def self_check(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []

        def item(name: str, status: str, reason: str = "") -> None:
            out.append({"check": name, "status": status, "reason": reason})

        try:
            from config_validate import validate_dict
            ok, problems = validate_dict({"mode": self.cfg.default_mode,
                                          "approval": self.cfg.default_approval})
            item("config", "PASS" if ok else "FAIL", "; ".join(problems))
        except Exception as e:  # noqa: BLE001
            item("config", "FAIL", str(e)[:200])
        try:
            import tempfile
            probe = Path(tempfile.mkdtemp(prefix="v05_self_"))
            (probe / "w").write_text("x")
            shutil_ok = (probe / "w").read_text() == "x"
            import shutil as _sh
            _sh.rmtree(probe, ignore_errors=True)
            item("storage", "PASS" if shutil_ok else "FAIL")
        except Exception as e:  # noqa: BLE001
            item("storage", "FAIL", str(e)[:200])
        roots_ok = all(Path(r).expanduser().exists()
                       for r in self.cfg.allowed_workspace_roots)
        item("allowed_roots", "PASS" if roots_ok else "FAIL")
        h = self.health()
        item("ollama", {"HEALTHY": "PASS", "DEGRADED": "WARN"}.get(
            h["checks"].get("ollama", {}).get("status", ""), "FAIL"))
        inv = self.model_inventory()
        item("models", "PASS" if inv.get("models") else "WARN",
             f"{len(inv.get('models', []))} local model(s)")
        try:
            bus_hits: list = []
            from events import EventBus
            b = EventBus()
            b.subscribe("selfcheck", bus_hits.append)
            b.emit("selfcheck", {"x": 1})
            item("event_system", "PASS" if bus_hits else "FAIL")
        except Exception as e:  # noqa: BLE001
            item("event_system", "FAIL", str(e)[:200])
        try:
            import tempfile
            from executor import Sandbox, SandboxViolation
            d = Path(tempfile.mkdtemp(prefix="v05_sb_"))
            sb = Sandbox(d)
            blocked = False
            try:
                sb.resolve("../escape")
            except SandboxViolation:
                blocked = True
            import shutil as _sh2
            _sh2.rmtree(d, ignore_errors=True)
            item("sandbox", "PASS" if blocked else "FAIL")
        except Exception as e:  # noqa: BLE001
            item("sandbox", "FAIL", str(e)[:200])
        try:
            from versions import COMPATIBILITY
            item("client_service_compat", "PASS"
                 if COMPATIBILITY["api"] == API_VERSION else "FAIL")
        except Exception as e:  # noqa: BLE001
            item("client_service_compat", "FAIL", str(e)[:200])
        try:
            import tempfile
            from memory import SessionMemory
            d = Path(tempfile.mkdtemp(prefix="v05_persist_"))
            m = SessionMemory(d / "m.json")
            m.set_task("selfcheck", "none")
            ok = (d / "m.json").exists()
            import shutil as _sh3
            _sh3.rmtree(d, ignore_errors=True)
            item("persistence", "PASS" if ok else "FAIL")
        except Exception as e:  # noqa: BLE001
            item("persistence", "FAIL", str(e)[:200])
        return out

    # -- observability -----------------------------------------------------------
    def _save_metrics(self) -> None:
        pass  # per-session storage is source of truth; aggregated on health()

    def health(self) -> dict[str, Any]:
        from providers import ProviderError, create_provider
        checks: dict[str, Any] = {}
        overall = "HEALTHY"
        try:
            prov = create_provider("ollama", host="http://127.0.0.1:11434",
                                   model=self.cfg.default_model, timeout_s=10)
            models = prov.list_models()
            checks["ollama"] = {"status": "HEALTHY", "models": len(models)}
            checks["coder_model"] = {"status": "HEALTHY" if any(
                self.cfg.default_model in m or m in self.cfg.default_model
                for m in models) else "DEGRADED"}
            if checks["coder_model"]["status"] != "HEALTHY":
                overall = "DEGRADED"
        except ProviderError as e:
            checks["ollama"] = {"status": "UNAVAILABLE", "error": str(e)[:200]}
            overall = "UNAVAILABLE"
        roots_ok = all(Path(r).expanduser().exists()
                       for r in self.cfg.allowed_workspace_roots)
        checks["workspace_roots"] = {"status": "HEALTHY" if roots_ok else "UNAVAILABLE"}
        if not roots_ok:
            overall = "UNAVAILABLE"
        checks["storage"] = {"status": "HEALTHY"}
        checks["reviewer_optional"] = {"status": "HEALTHY",
                                       "note": "reviewer absence degrades, never kills"}
        return {"status": overall, "runtime": RUNTIME_VERSION,
                "checks": checks, "metrics": dict(self.metrics)}

    def capabilities(self) -> dict[str, Any]:
        from protocol import ACTIONS, PROTOCOL_VERSION
        from versions import COMPATIBILITY
        out: dict[str, Any] = {
            "ok": True, "runtime": RUNTIME_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "actions": list(ACTIONS), "modes": ["build", "plan", "hybrid"],
            "approvals": ["AUTO_SAFE", "ASK_RISKY", "ASK_ALL_WRITES", "READ_ONLY"],
            "profiles": ["SAFE_EXPLORATION", "ASSISTED_BUILD",
                         "AUTONOMOUS_SANDBOX", "PRECIOUS_PROJECT",
                         "OWNER_FULL_ACCESS"],
            "owner_profile": self.cfg.profile,
            "owner_authorized": bool(self.cfg.owner_authorized),
            "presets": ["LOW_RESOURCE", "STANDARD", "HIGH_QUALITY"],
            "default_model": self.cfg.default_model,
            "network_policy": self.cfg.network_policy,
            "compat": COMPATIBILITY,
            "limitations": ["localhost Ollama only", "no public bind by default",
                            "single simple shell commands",
                            ".bridge internals model-protected"]}
        if self.cfg.profile == "OWNER_FULL_ACCESS" and self.cfg.owner_authorized:
            from owner import OWNER, admin_state
            try:
                import sysinfo
                inv = sysinfo.inventory()
            except Exception:  # noqa: BLE001
                inv = {}
            out["owner"] = {
                "filesystem_scope": [str(d) for d in
                                     __import__("owner").machine_roots()],
                "network_policy": self.cfg.network_policy,
                "shell_policy": "owner",
                "browser_available": bool(
                    (inv.get("browsers") or [])),
                "admin_state": admin_state(),
                "git_available": bool(
                    (inv.get("tools") or {}).get("git", {}).get("present")),
                "package_managers": {k: v.get("present", False) for k, v in
                                     (inv.get("tools") or {}).items()
                                     if k in ("pip", "npm", "winget", "choco")},
                "process_control": True,
                "auto_approve": True,
                "emergency_stop": True,
                "audit_enabled": True,
                "activation": OWNER.record() if OWNER.active else
                {"owner_authorization_active": False},
            }
        return out

    def machine_inventory(self) -> dict[str, Any]:
        try:
            import sysinfo
            return {"ok": True, "inventory": sysinfo.inventory()}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)[:200]}

    def emergency_stop(self, reason: str = "operator stop") -> dict[str, Any]:
        from owner import emergency_stop
        with self.lock:
            for s in self.sessions.values():
                for t in s.tasks.values():
                    if t.status in TASK_ACTIVE:
                        t.status = "CANCELLED"
                s.status = "CANCELLED"
        return emergency_stop(reason)
