"""Universal Adaptive Execution Contract (Phase 1.1).

HARD SYSTEM CONTRACT, enforced outside any individual model:

  UNDERSTAND -> PLAN -> EXECUTE BOUNDED UNIT -> OBSERVE RESULT -> VERIFY
  -> DIAGNOSE -> RE-EVALUATE -> ADAPT PLAN IF REQUIRED -> CHECKPOINT
  -> CONTINUE

The model is interchangeable. This contract is not.

Design notes:
- Enforcement lives here (state machine + fail-closed guards), never in
  prompt text. Every model/provider/builder integration goes through the
  same interface (see BuilderAdapter below).
- Reuses existing systems: plan history mirrors the AdaptationEvent shape
  from task_dag; checkpointing is caller-owned (same pattern as
  task_dag.CheckpointManager); TaskCenter/observer carry display, this
  module carries enforcement truth.
- Planning depth is adaptive: LIGHTWEIGHT plans (OBJECTIVE / CHANGE /
  EXPECTED_RESULT / VERIFY) for tiny tasks, FULL plans for substantive
  work. The LOOP is mandatory in both cases; only the SIZE adapts.
- Fail closed: illegal transitions raise ExecutionPolicyViolation with a
  machine-readable reason (PLAN_MISSING / VERIFICATION_MISSING /
  REEVALUATION_MISSING). Nothing silently bypasses.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

# -- States ---------------------------------------------------------------
RECEIVED = "RECEIVED"
CONTEXT_RECOVERED = "CONTEXT_RECOVERED"
PLANNED = "PLANNED"
READY_TO_EXECUTE = "READY_TO_EXECUTE"
EXECUTING = "EXECUTING"
RESULT_CAPTURED = "RESULT_CAPTURED"
VERIFYING = "VERIFYING"
VERIFIED = "VERIFIED"
FAILED = "FAILED"
REEVALUATING = "REEVALUATING"

# Terminal reevaluation decisions (also the only legal exits from REEVALUATING
# back into the loop or out of it).
CONTINUE_CURRENT_PLAN = "CONTINUE_CURRENT_PLAN"
ADAPT_PLAN = "ADAPT_PLAN"
RETRY_WITH_CHANGE = "RETRY_WITH_CHANGE"
ROUTE_TO_DIFFERENT_MODEL = "ROUTE_TO_DIFFERENT_MODEL"
CREATE_NEW_SUBTASK = "CREATE_NEW_SUBTASK"
BLOCK_WITH_EVIDENCE = "BLOCK_WITH_EVIDENCE"
OWNER_REVIEW_REQUIRED = "OWNER_REVIEW_REQUIRED"
COMPLETE = "COMPLETE"

# Fail-closed violation reasons
PLAN_MISSING = "PLAN_MISSING"
VERIFICATION_MISSING = "VERIFICATION_MISSING"
REEVALUATION_MISSING = "REEVALUATION_MISSING"
ILLEGAL_TRANSITION = "ILLEGAL_TRANSITION"

# Legal transitions. Anything not listed is rejected, including
# RECEIVED -> EXECUTING and EXECUTING -> COMPLETE (must pass through
# RESULT_CAPTURED -> VERIFYING -> VERIFIED/FAILED -> REEVALUATING).
LEGAL_TRANSITIONS: dict[str, tuple[str, ...]] = {
    RECEIVED: (CONTEXT_RECOVERED,),
    CONTEXT_RECOVERED: (PLANNED,),
    PLANNED: (READY_TO_EXECUTE, PLANNED, FAILED),  # re-plan allowed
    READY_TO_EXECUTE: (EXECUTING, PLANNED, FAILED),
    EXECUTING: (RESULT_CAPTURED, FAILED),
    # RESULT_CAPTURED loop-backs: next bounded unit within the same plan,
    # verification of the accumulated result, or failure short-circuit.
    RESULT_CAPTURED: (VERIFYING, EXECUTING, FAILED),
    VERIFYING: (VERIFIED, FAILED),
    VERIFIED: (REEVALUATING,),
    FAILED: (REEVALUATING,),
    REEVALUATING: (CONTINUE_CURRENT_PLAN, ADAPT_PLAN, RETRY_WITH_CHANGE,
                   ROUTE_TO_DIFFERENT_MODEL, CREATE_NEW_SUBTASK,
                   BLOCK_WITH_EVIDENCE, OWNER_REVIEW_REQUIRED, COMPLETE),
    # Loop-back edges: decisions re-enter the cycle, never skip it.
    CONTINUE_CURRENT_PLAN: (READY_TO_EXECUTE, PLANNED),
    ADAPT_PLAN: (PLANNED,),
    RETRY_WITH_CHANGE: (READY_TO_EXECUTE, PLANNED),
    ROUTE_TO_DIFFERENT_MODEL: (READY_TO_EXECUTE, PLANNED),
    CREATE_NEW_SUBTASK: (READY_TO_EXECUTE, PLANNED),
    BLOCK_WITH_EVIDENCE: (REEVALUATING,),  # unblock only via re-evaluation
    OWNER_REVIEW_REQUIRED: (REEVALUATING,),
    COMPLETE: (),
}

# Plan depth
LIGHTWEIGHT = "LIGHTWEIGHT"
FULL = "FULL"
LIGHTWEIGHT_FIELDS = ("objective", "change", "expected_result", "verify")
FULL_FIELDS = ("objective", "current_state", "requirements", "constraints",
               "dependencies", "risks", "unknowns", "steps",
               "evidence_requirements", "acceptance")


class ExecutionPolicyViolation(Exception):
    """Fail-closed rejection. `reason` is machine-readable."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


def _now() -> float:
    return time.time()


def _new_id(prefix: str) -> str:
    return f"{prefix}-" + uuid.uuid4().hex[:8]


@dataclass
class PlanRecord:
    plan_id: str = field(default_factory=lambda: _new_id("plan"))
    task_id: str = ""
    version: int = 1  # PLAN-v1, PLAN-v2, ...
    depth: str = LIGHTWEIGHT
    fields: dict[str, Any] = field(default_factory=dict)
    author: str = ""  # agent/model that wrote it
    created_at: float = field(default_factory=_now)
    supersedes: str = ""  # previous plan_id; history is never overwritten

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReevaluationRecord:
    record_id: str = field(default_factory=lambda: _new_id("reev"))
    task_id: str = ""
    plan_version: int = 0
    # Answers to the mandatory post-unit questions.
    findings: dict[str, str] = field(default_factory=dict)
    decision: str = ""
    evidence: list[str] = field(default_factory=list)
    author: str = ""
    created_at: float = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VerificationRecord:
    record_id: str = field(default_factory=lambda: _new_id("ver"))
    task_id: str = ""
    plan_version: int = 0
    verdict: str = ""  # VERIFIED | FAILED | PARTIAL
    evidence: list[str] = field(default_factory=list)
    verifier: str = ""
    created_at: float = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# The nine mandatory post-unit questions (§6).
REEVALUATION_QUESTIONS = (
    "what_changed",
    "behaviour_matched_expected",
    "tests_passed",
    "new_information",
    "performance_or_resource_change",
    "assumptions_correct",
    "dependencies_affected",
    "next_action_still_valid",
    "plan_should_change",
)


class LoopTelemetry:
    """Violation + adaptation counters. Goal: 0 unresolved bypasses."""

    def __init__(self):
        self.planned_ok = 0
        self.violations: dict[str, int] = {}
        self.completions_without_verification = 0
        self.missing_reevaluations = 0
        self.adaptations = 0
        self.unchanged_continuations = 0
        self.reroutes = 0
        self.blocked = 0

    def note_violation(self, reason: str) -> None:
        self.violations[reason] = self.violations.get(reason, 0) + 1

    def snapshot(self) -> dict[str, Any]:
        return {
            "planned_ok": self.planned_ok,
            "violations": dict(self.violations),
            "completions_without_verification": self.completions_without_verification,
            "missing_reevaluations": self.missing_reevaluations,
            "adaptations": self.adaptations,
            "unchanged_continuations": self.unchanged_continuations,
            "reroutes": self.reroutes,
            "blocked": self.blocked,
            "unresolved_bypasses": sum(self.violations.values()),
        }


@dataclass
class _TaskState:
    task_id: str
    substantive: bool
    state: str = RECEIVED
    plan_id: str = ""          # current valid plan
    plan_version: int = 0
    verified_for_plan: int = 0  # plan version that passed verification
    reevaluated_for_plan: int = 0  # plan version that was re-evaluated
    history: list[dict[str, Any]] = field(default_factory=list)


class ExecutionContract:
    """Fail-closed lifecycle enforcement for one programme of tasks."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else None
        self.tasks: dict[str, _TaskState] = {}
        self.plans: dict[str, PlanRecord] = {}
        self.verifications: list[VerificationRecord] = []
        self.reevaluations: list[ReevaluationRecord] = []
        self.telemetry = LoopTelemetry()
        if self.path is not None and self.path.exists():
            self.load()

    # -- task intake -----------------------------------------------------
    def receive(self, task_id: str = "", substantive: bool = True) -> str:
        tid = task_id or _new_id("task")
        if tid in self.tasks:
            raise ValueError(f"task {tid!r} already received")
        self.tasks[tid] = _TaskState(task_id=tid, substantive=substantive)
        self._log(tid, RECEIVED, None, RECEIVED)
        self._autosave()
        return tid

    # -- planning --------------------------------------------------------
    def plan(self, task_id: str, fields: dict[str, Any],
             depth: str = "", author: str = "") -> PlanRecord:
        st = self._get(task_id)
        # Owner/amendment re-plans are legal from READY (a correction
        # arriving before execution starts a new version). Mid-EXECUTING
        # re-plans stay illegal: let the bounded unit finish first.
        self._require_state(st, (CONTEXT_RECOVERED, PLANNED,
                                 READY_TO_EXECUTE,
                                 CONTINUE_CURRENT_PLAN, ADAPT_PLAN,
                                 RETRY_WITH_CHANGE, ROUTE_TO_DIFFERENT_MODEL,
                                 CREATE_NEW_SUBTASK))
        if not depth:
            current = self.plans.get(st.plan_id) if st.plan_id else None
            # Adaptations inherit the established plan depth unless the
            # caller explicitly escalates; new tasks default by complexity.
            depth = current.depth if current is not None else \
                (FULL if st.substantive else LIGHTWEIGHT)
        required = FULL_FIELDS if depth == FULL else LIGHTWEIGHT_FIELDS
        missing = [f for f in required if not fields.get(f)]
        if missing:
            raise ExecutionPolicyViolation(
                PLAN_MISSING,
                f"plan depth {depth} missing fields: {', '.join(missing)}")
        st.plan_version += 1
        plan = PlanRecord(task_id=task_id, version=st.plan_version,
                          depth=depth, fields=dict(fields), author=author,
                          supersedes=st.plan_id)
        st.plan_id = plan.plan_id
        self.plans[plan.plan_id] = plan
        self._move(st, PLANNED)
        self.telemetry.planned_ok += 1
        self._autosave()
        return plan

    # -- guarded transitions ---------------------------------------------
    def recover_context(self, task_id: str) -> str:
        return self._guarded(task_id, CONTEXT_RECOVERED)

    def mark_ready(self, task_id: str) -> str:
        st = self._get(task_id)
        if not st.plan_id:
            self.telemetry.note_violation(PLAN_MISSING)
            raise ExecutionPolicyViolation(
                PLAN_MISSING, f"task {task_id!r} has no valid plan")
        return self._guarded(task_id, READY_TO_EXECUTE)

    def begin_execute(self, task_id: str) -> str:
        st = self._get(task_id)
        if not st.plan_id:
            self.telemetry.note_violation(PLAN_MISSING)
            raise ExecutionPolicyViolation(
                PLAN_MISSING,
                f"substantive execution requires a plan for {task_id!r}")
        return self._guarded(task_id, EXECUTING)

    def capture_result(self, task_id: str, result: str = "") -> str:
        st = self._get(task_id)
        out = self._guarded(task_id, RESULT_CAPTURED)
        st.history.append({"ts": _now(), "event": "result",
                           "result": result[:500]})
        self._autosave()
        return out

    def begin_verify(self, task_id: str) -> str:
        return self._guarded(task_id, VERIFYING)

    def record_verification(self, task_id: str, verdict: str,
                            evidence: list[str] | None = None,
                            verifier: str = "") -> VerificationRecord:
        st = self._get(task_id)
        if verdict not in (VERIFIED, FAILED, "PARTIAL"):
            raise ValueError(f"bad verdict {verdict!r}")
        self._guarded(task_id, VERIFIED if verdict == VERIFIED else FAILED)
        rec = VerificationRecord(task_id=task_id,
                                 plan_version=st.plan_version,
                                 verdict=verdict,
                                 evidence=list(evidence or []),
                                 verifier=verifier)
        self.verifications.append(rec)
        if verdict == VERIFIED:
            st.verified_for_plan = st.plan_version
        self._autosave()
        return rec

    def begin_reevaluate(self, task_id: str) -> str:
        return self._guarded(task_id, REEVALUATING)

    def record_reevaluation(
            self, task_id: str, findings: dict[str, str],
            decision: str, evidence: list[str] | None = None,
            author: str = "") -> ReevaluationRecord:
        st = self._get(task_id)
        self._require_state(st, (REEVALUATING,))
        missing = [q for q in REEVALUATION_QUESTIONS if q not in findings]
        if missing:
            raise ExecutionPolicyViolation(
                REEVALUATION_MISSING,
                f"reevaluation missing answers: {', '.join(missing)}")
        if decision not in (CONTINUE_CURRENT_PLAN, ADAPT_PLAN,
                            RETRY_WITH_CHANGE, ROUTE_TO_DIFFERENT_MODEL,
                            CREATE_NEW_SUBTASK, BLOCK_WITH_EVIDENCE,
                            OWNER_REVIEW_REQUIRED, COMPLETE):
            raise ValueError(f"bad decision {decision!r}")
        if decision == COMPLETE:
            if st.verified_for_plan != st.plan_version:
                self.telemetry.completions_without_verification += 1
                raise ExecutionPolicyViolation(
                    VERIFICATION_MISSING,
                    f"task {task_id!r} cannot complete without verification "
                    f"of plan v{st.plan_version}")
        rec = ReevaluationRecord(task_id=task_id,
                                 plan_version=st.plan_version,
                                 findings=dict(findings), decision=decision,
                                 evidence=list(evidence or []), author=author)
        self.reevaluations.append(rec)
        st.reevaluated_for_plan = st.plan_version
        if decision == ADAPT_PLAN:
            self.telemetry.adaptations += 1
        elif decision == CONTINUE_CURRENT_PLAN:
            self.telemetry.unchanged_continuations += 1
        elif decision == ROUTE_TO_DIFFERENT_MODEL:
            self.telemetry.reroutes += 1
        elif decision in (BLOCK_WITH_EVIDENCE, OWNER_REVIEW_REQUIRED):
            self.telemetry.blocked += 1
        self._move(st, decision)
        self._autosave()
        return rec

    def finalize(self, task_id: str) -> str:
        """COMPLETE is only reachable via a recorded COMPLETE reevaluation."""
        st = self._get(task_id)
        if st.state != COMPLETE:
            self.telemetry.missing_reevaluations += 1
            raise ExecutionPolicyViolation(
                REEVALUATION_MISSING,
                f"task {task_id!r} in {st.state}: finalization requires a "
                "recorded COMPLETE reevaluation decision")
        self._autosave()
        return COMPLETE

    def next_unit(self, task_id: str) -> str:
        """Begin the next bounded unit within the same plan.

        Used by runtimes that execute many small actions per task: each
        captured result cycles back to EXECUTING instead of forcing a
        full re-plan per action.
        """
        return self._guarded(task_id, EXECUTING)

    def note_reroute(self, task_id: str, from_model: str, to_model: str,
                     reason: str) -> ReevaluationRecord:
        """Record a fallback/model change as re-evaluation evidence.

        No state change: the run continues under the same plan with a
        different worker. Satisfies "failure recorded -> re-evaluation ->
        plan adapted -> fallback selected" without aborting the run.
        """
        st = self._get(task_id)
        rec = ReevaluationRecord(
            task_id=task_id, plan_version=st.plan_version,
            findings={q: f"reroute: {reason}"[:200]
                      for q in REEVALUATION_QUESTIONS},
            decision=ROUTE_TO_DIFFERENT_MODEL,
            evidence=[f"fallback {from_model} -> {to_model}: {reason}"[:300]],
            author="bridge-fallback")
        self.reevaluations.append(rec)
        st.history.append({"ts": _now(), "event": "reroute",
                           "from": from_model, "to": to_model,
                           "reason": reason,
                           "plan_version": st.plan_version})
        self.telemetry.reroutes += 1
        self._autosave()
        return rec

    def note_event(self, task_id: str, event: str,
                   data: dict[str, Any] | None = None) -> None:
        """Append an informational event (resume, dry-run note, etc.)."""
        st = self._get(task_id)
        st.history.append({"ts": _now(), "event": event,
                           **(data or {})})
        self._autosave()

    def abort(self, task_id: str, reason: str,
              evidence: list[str] | None = None) -> ReevaluationRecord:
        """Failure short-circuit: -> FAILED -> REEVALUATING ->
        BLOCK_WITH_EVIDENCE. Terminal failure returns in runtimes must go
        through here so verification + re-evaluation are never skipped."""
        st = self._get(task_id)
        if st.state not in (FAILED, REEVALUATING, BLOCK_WITH_EVIDENCE,
                            OWNER_REVIEW_REQUIRED, COMPLETE):
            self._guarded(task_id, FAILED)
        if st.state == FAILED:
            self._guarded(task_id, REEVALUATING)
        return self.record_reevaluation(
            task_id,
            {q: f"abort: {reason}"[:200] for q in REEVALUATION_QUESTIONS},
            BLOCK_WITH_EVIDENCE, list(evidence or []), author="bridge")

    def contract_snapshot(self, task_id: str) -> dict[str, Any]:
        """Small evidence block for runtime return dicts and UI."""
        st = self._get(task_id)
        return {"task_id": task_id, "state": st.state,
                "plan_version": st.plan_version, "plan_id": st.plan_id,
                "verified_for_plan": st.verified_for_plan,
                "reevaluated_for_plan": st.reevaluated_for_plan,
                "telemetry": self.telemetry.snapshot()}

    # -- introspection ----------------------------------------------------
    def state_of(self, task_id: str) -> str:
        return self._get(task_id).state

    def current_plan(self, task_id: str) -> PlanRecord | None:
        st = self._get(task_id)
        return self.plans.get(st.plan_id)

    def plan_history(self, task_id: str) -> list[PlanRecord]:
        out = [p for p in self.plans.values() if p.task_id == task_id]
        return sorted(out, key=lambda p: p.version)

    def pending_reevaluation(self, task_id: str) -> bool:
        st = self._get(task_id)
        return st.state in (VERIFIED, FAILED) and \
            st.reevaluated_for_plan != st.plan_version

    # -- internals ---------------------------------------------------------
    def _get(self, task_id: str) -> _TaskState:
        try:
            return self.tasks[task_id]
        except KeyError:
            raise KeyError(f"unknown task {task_id!r}")

    def _require_state(self, st: _TaskState, allowed: tuple[str, ...]) -> None:
        if st.state not in allowed:
            self.telemetry.note_violation(ILLEGAL_TRANSITION)
            raise ExecutionPolicyViolation(
                ILLEGAL_TRANSITION,
                f"task {st.task_id!r} in {st.state}: "
                f"requires one of {', '.join(allowed)}")

    def _move(self, st: _TaskState, to: str) -> None:
        st.state = to
        st.history.append({"ts": _now(), "event": "state", "to": to,
                           "plan_version": st.plan_version})

    def _guarded(self, task_id: str, to: str) -> str:
        st = self._get(task_id)
        if to not in LEGAL_TRANSITIONS.get(st.state, ()):
            self.telemetry.note_violation(ILLEGAL_TRANSITION)
            raise ExecutionPolicyViolation(
                ILLEGAL_TRANSITION,
                f"task {task_id!r}: {st.state} -> {to} is illegal")
        self._move(st, to)
        self._autosave()
        return to

    def _log(self, task_id: str, event: str,
             frm: str | None, to: str) -> None:
        self.tasks[task_id].history.append(
            {"ts": _now(), "event": event, "from": frm, "to": to})

    # -- persistence (atomic; corrupt reads never reset) --------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "tasks": {tid: {"task_id": s.task_id,
                            "substantive": s.substantive,
                            "state": s.state,
                            "plan_id": s.plan_id,
                            "plan_version": s.plan_version,
                            "verified_for_plan": s.verified_for_plan,
                            "reevaluated_for_plan": s.reevaluated_for_plan,
                            "history": s.history}
                      for tid, s in self.tasks.items()},
            "plans": {pid: p.to_dict() for pid, p in self.plans.items()},
            "verifications": [v.to_dict() for v in self.verifications],
            "reevaluations": [r.to_dict() for r in self.reevaluations],
            "telemetry": self.telemetry.snapshot(),
        }

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
        try:
            tasks = {}
            for tid, td in (data.get("tasks") or {}).items():
                tasks[tid] = _TaskState(
                    task_id=td["task_id"],
                    substantive=bool(td.get("substantive", True)),
                    state=str(td.get("state", RECEIVED)),
                    plan_id=str(td.get("plan_id", "")),
                    plan_version=int(td.get("plan_version", 0)),
                    verified_for_plan=int(td.get("verified_for_plan", 0)),
                    reevaluated_for_plan=int(td.get("reevaluated_for_plan", 0)),
                    history=list(td.get("history", [])))
            plans = {pid: PlanRecord(**pd)
                     for pid, pd in (data.get("plans") or {}).items()}
            verifications = [VerificationRecord(**vd)
                             for vd in data.get("verifications", [])]
            reevaluations = [ReevaluationRecord(**rd)
                             for rd in data.get("reevaluations", [])]
        except (KeyError, TypeError, ValueError):
            return False
        self.tasks = tasks
        self.plans = plans
        self.verifications = verifications
        self.reevaluations = reevaluations
        tel = data.get("telemetry") or {}
        self.telemetry.planned_ok = int(tel.get("planned_ok", 0))
        self.telemetry.violations = dict(tel.get("violations", {}))
        self.telemetry.completions_without_verification = int(
            tel.get("completions_without_verification", 0))
        self.telemetry.missing_reevaluations = int(
            tel.get("missing_reevaluations", 0))
        self.telemetry.adaptations = int(tel.get("adaptations", 0))
        self.telemetry.unchanged_continuations = int(
            tel.get("unchanged_continuations", 0))
        self.telemetry.reroutes = int(tel.get("reroutes", 0))
        self.telemetry.blocked = int(tel.get("blocked", 0))
        return True


# -- Builder adapters -------------------------------------------------------
class BuilderAdapter:
    """Common interface every builder (model, agent, external tool, Genesis)
    must go through. The adapter owns the loop position; the contract owns
    the truth. No builder may bypass the contract."""

    name: str = "builder"

    def __init__(self, contract: ExecutionContract,
                 execute_fn: Callable[[str, dict[str, Any]], str] | None = None,
                 verify_fn: Callable[[str, str], tuple[str, list[str]]] | None = None,
                 cognition_fn: Callable[[str, str], dict[str, Any]] | None = None):
        self.contract = contract
        self._execute_fn = execute_fn or (lambda task_id, plan: "")
        self._verify_fn = verify_fn or (lambda task_id, result: (VERIFIED, []))
        self._cognition_fn = cognition_fn

    def plan(self, task_id: str, fields: dict[str, Any],
             depth: str = "", author: str = "") -> PlanRecord:
        return self.contract.plan(task_id, fields, depth,
                                  author or self.name)

    def execute_unit(self, task_id: str) -> str:
        """Run ONE bounded unit. Guarded: no plan -> violation, no bypass."""
        self.contract.begin_execute(task_id)
        plan = self.contract.current_plan(task_id)
        result = self._execute_fn(task_id, plan.fields if plan else {})
        self.contract.capture_result(task_id, result)
        return result

    def return_result(self, task_id: str) -> str:
        st = self.contract.state_of(task_id)
        if st != RESULT_CAPTURED:
            raise ExecutionPolicyViolation(
                ILLEGAL_TRANSITION,
                f"no captured result to return in {st}")
        return st

    def verify(self, task_id: str, verifier: str = "") -> VerificationRecord:
        self.contract.begin_verify(task_id)
        # NOTE: result text is intentionally NOT re-derived here; the caller
        # supplies verification via verify_fn evidence. Safe metadata only.
        verdict, evidence = self._verify_fn(task_id, "")
        return self.contract.record_verification(
            task_id, verdict, evidence, verifier or self.name)

    def reevaluate(self, task_id: str, findings: dict[str, str],
                   decision: str, evidence: list[str] | None = None
                   ) -> ReevaluationRecord:
        self.contract.begin_reevaluate(task_id)
        return self.contract.record_reevaluation(
            task_id, findings, decision, evidence, author=self.name)

    def checkpoint(self) -> str:
        return self.contract.save()

    def run_unit(self, task_id: str, plan_fields: dict[str, Any],
                 findings: dict[str, str], decision: str,
                 depth: str = "", evidence: list[str] | None = None
                 ) -> ReevaluationRecord:
        """Full bounded loop in one call: plan -> execute -> verify ->
        reevaluate. Each step is still individually guarded."""
        self.plan(task_id, plan_fields, depth)
        self.contract.mark_ready(task_id)
        self.execute_unit(task_id)
        self.verify(task_id)
        return self.reevaluate(task_id, findings, decision, evidence)


class ScriptedBuilderAdapter(BuilderAdapter):
    """Demo external builder driven by a script. Proves an external tool
    cannot bypass the contract: every step routes through the guards."""

    name = "scripted-external-builder"

    def __init__(self, contract: ExecutionContract,
                 script: dict[str, Any] | None = None):
        script = script or {}
        super().__init__(
            contract,
            execute_fn=lambda task_id, plan: str(
                script.get("result", "scripted result")),
            verify_fn=lambda task_id, result: (
                str(script.get("verdict", VERIFIED)),
                list(script.get("evidence", []))))


class GenesisAdapter(BuilderAdapter):
    """Genesis integration interface. Genesis provides higher cognition
    (objectives, plans, reasoning, adaptations) through cognition_fn;
    the Bridge contract enforces the execution lifecycle. Same contract,
    no separate loop."""

    name = "genesis"

    def propose_plan(self, task_id: str, context: dict[str, Any],
                     depth: str = "") -> PlanRecord:
        if self._cognition_fn is None:
            raise ExecutionPolicyViolation(
                PLAN_MISSING, "genesis cognition unavailable; no plan proposed")
        fields = self._cognition_fn(task_id, context)
        # Cognition may include _genesis_depth to signal its depth selection.
        # Extract it so the contract validates against the right field set.
        if not depth:
            depth = fields.pop("_genesis_depth", "")
        else:
            fields.pop("_genesis_depth", None)
        return self.plan(task_id, fields, depth, author="genesis-cognition")
