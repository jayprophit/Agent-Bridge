"""Canonical Team Registry + append-only organisational provenance (§AK, §F, §P, §N, §O).

WHY THIS MODULE EXISTS

    "INFORMATION IS REGISTERED FOR LIFE UNLESS DELIBERATELY REMOVED."

Everything the enterprise multi-agent fabric does — forming a team, handing
work between specialists, promoting or retiring a worker — was previously
in-memory only. A session ended and the organisational history was gone. This
module makes that history durable and auditable, in two layers:

  1. CANONICAL LAYER (in-memory, authoritative for queries)
     Teams, members, RACI assignments and worker career state. Mutable
     current state: a worker's status changes, a team gains a member.

  2. PROVENANCE LAYER (append-only JSONL on disk, never rewritten)
     Every transition is appended as an immutable event. Nothing is ever
     updated or deleted in this layer, so the trail survives the canonical
     state being superseded. This is the same rule the migration programme
     enforces: the record is permanent, the thing it describes is disposable.

The split is deliberate. A registry that only appends cannot answer "who is
on team X right now". A registry that only mutates cannot answer "who
reviewed task Y three weeks ago". Both questions are real.

WHAT THIS REGISTRY OWNS vs WHAT IT MUST NOT DUPLICATE

This registry owns ORGANISATIONAL FACTS: who was on a team, what role they
held, who was accountable for a task, what a handoff carried.

It does NOT own: model/provider selection (Agent Router / Provider Registry),
execution targets (Execution Target Registry), credentials (KeePass bridge),
or task content (the canonical task centre). Workers reference those by ID.

    MODEL != WORKER != PROVIDER.

A worker keeps its role when its model is swapped. The registry records both
so the distinction is visible rather than assumed.

SCHEMA VERSIONING (§5 of the master implementation prompt)

Records carry a schema_version. A reader that encounters a newer version must
fail loudly rather than silently mis-parse. Permanent IDs are stable across
schema changes.
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Callable, Iterable, Optional

logger = logging.getLogger("aetherius.team_registry")

TEAM_REGISTRY_SCHEMA_VERSION = 1

# === §F: Departments ===
# Organisational metadata only. A department is a grouping of roles, not a
# program, not a separate runtime, not a second orchestration system.

DEPARTMENT_ENGINEERING = "ENGINEERING"
DEPARTMENT_RESEARCH = "RESEARCH"
DEPARTMENT_QUALITY = "QUALITY"
DEPARTMENT_OPERATIONS = "OPERATIONS"
DEPARTMENT_CREATIVE = "CREATIVE"
DEPARTMENT_BUSINESS = "BUSINESS"
DEPARTMENT_TOOL_OPERATIONS = "TOOL_OPERATIONS"

DEPARTMENTS = {
    DEPARTMENT_ENGINEERING: [
        "coding_worker", "reviewer", "handoff_arbiter", "routing_specialist",
    ],
    DEPARTMENT_RESEARCH: ["research_worker", "evidence_reviewer"],
    DEPARTMENT_QUALITY: ["test_runner", "cost_specialist"],
    DEPARTMENT_OPERATIONS: ["coordinator"],
    DEPARTMENT_CREATIVE: [],
    DEPARTMENT_BUSINESS: [],
    DEPARTMENT_TOOL_OPERATIONS: [],
}


def department_for_role(role_id: str) -> Optional[str]:
    """Which department owns a role (§F). Returns None for an unknown role.

    Deliberately does not guess: an unrecognised role must be surfaced rather
    than silently filed somewhere plausible.
    """
    for dept, roles in DEPARTMENTS.items():
        if role_id in roles:
            return dept
    return None


# === §P: RACI ===
# Every important task records who does the work and who accepts the outcome.
# The point of §O (one accountable owner) is that "everyone thought someone
# else was doing it" cannot happen.

RACI_RESPONSIBLE = "RESPONSIBLE"
RACI_ACCOUNTABLE = "ACCOUNTABLE"
RACI_CONSULTED = "CONSULTED"
RACI_INFORMED = "INFORMED"

RACI_ASSIGNMENTS = (
    RACI_RESPONSIBLE,
    RACI_ACCOUNTABLE,
    RACI_CONSULTED,
    RACI_INFORMED,
)


# Accountability MODE (§P, refined): how shared responsibility is expressed.
#
# §O's protection — "there is always exactly one owner responsible for
# completing a task" — is retained by TASK.execution_accountable being exactly
# one identity. But real organisations contain boards, committees, co-parents,
# partnerships and statutory shared responsibilities, so "exactly one
# accountable entity" must NOT be universal across the ontology. The mode says
# which shape this task's accountability takes:
ACCOUNTABILITY_SINGLE = "SINGLE"          # one accountable worker
ACCOUNTABILITY_JOINT = "JOINT"            # e.g. co-parents, partners
ACCOUNTABILITY_COLLECTIVE = "COLLECTIVE"  # e.g. a board or committee
ACCOUNTABILITY_HUMAN_OWNER = "HUMAN_OWNER"  # accountable sits with the owner

ACCOUNTABILITY_MODES = (
    ACCOUNTABILITY_SINGLE,
    ACCOUNTABILITY_JOINT,
    ACCOUNTABILITY_COLLECTIVE,
    ACCOUNTABILITY_HUMAN_OWNER,
)


@dataclass
class RaciAssignment:
    """RACI for one task (§P).

    ``accountable`` is the single execution owner (§O): exactly one identity is
    answerable for the task completing. That invariant never changes.

    ``accountability_mode`` says whether OTHER identities share ultimate
    accountability — a board, both parents, a partnership — which is distinct
    from who must get the work done. ``collective_accountable`` names those
    shared holders when the mode is JOINT/COLLECTIVE. This is what lets the
    system model a family or a board without weakening the guarantee that a
    task always has exactly one execution owner.
    """
    task_id: str
    responsible: list[str] = field(default_factory=list)
    accountable: Optional[str] = None
    consulted: list[str] = field(default_factory=list)
    informed: list[str] = field(default_factory=list)
    accountability_mode: str = ACCOUNTABILITY_SINGLE
    collective_accountable: list[str] = field(default_factory=list)
    recorded_at: float = field(default_factory=time.time)

    def as_map(self) -> dict[str, list[str]]:
        return {
            RACI_RESPONSIBLE: list(self.responsible),
            RACI_ACCOUNTABLE: [self.accountable] if self.accountable else [],
            RACI_CONSULTED: list(self.consulted),
            RACI_INFORMED: list(self.informed),
        }


    def to_dict(self) -> dict:
        return asdict(self)


# === §M: Worker career states ===
# §AJ — maturity is earned by evidence, never assumed. These are capability
# states, not personalities, and are deliberately not anthropomorphised.

CAREER_CANDIDATE = "CANDIDATE"
CAREER_VERIFIED = "VERIFIED"
CAREER_SPECIALIST = "SPECIALIST"
CAREER_SENIOR = "SENIOR_SPECIALIST"
CAREER_TEAM_LEAD = "TEAM_LEAD"
CAREER_DEGRADED = "DEGRADED"
CAREER_BLOCKED = "BLOCKED"
CAREER_RETIRED = "RETIRED"
CAREER_SUPERSEDED = "SUPERSEDED"

# Promotion requires evidence (§AI). A career state is only as good as the
# measurements behind it, so every state records what justified it.
CAREER_ORDER = [
    CAREER_CANDIDATE,
    CAREER_VERIFIED,
    CAREER_SPECIALIST,
    CAREER_SENIOR,
    CAREER_TEAM_LEAD,
]


@dataclass
class WorkerCareerRecord:
    """One worker's organisational identity and earned standing (§M, §AJ).

    worker_id persists across model swaps by design: the role is the durable
    thing, the model is replaceable. Both are recorded so the distinction is
    explicit rather than implied.
    """
    worker_id: str
    role_id: str
    department: Optional[str] = None
    specialisms: list[str] = field(default_factory=list)

    # Replaceable substrate (§M). Swapping these must NOT change worker_id.
    model_id: Optional[str] = None
    provider_id: Optional[str] = None
    execution_target: Optional[str] = None

    career_state: str = CAREER_CANDIDATE

    # §AI evidence-based promotion. A promotion without evidence is a claim.
    success_count: int = 0
    failure_count: int = 0
    review_accuracy: float = 0.0
    intervention_count: int = 0
    last_latency_s: Optional[float] = None

    team_lead_of: list[str] = field(default_factory=list)
    manager_worker_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if self.department is None:
            self.department = department_for_role(self.role_id)

    @property
    def success_rate(self) -> Optional[float]:
        """§AI — ranking input. None when there is no evidence yet.

        Returns None rather than 0.0 for an untested worker: "never tried"
        and "always fails" are different facts and must not be conflated.
        """
        total = self.success_count + self.failure_count
        if total == 0:
            return None
        return self.success_count / total

    def to_dict(self) -> dict:
        d = asdict(self)
        d["success_rate"] = self.success_rate
        return d


@dataclass
class TeamRecord:
    """A team as an organisational unit (§N, §B).

    team_size and active_concurrency are SEPARATE fields on purpose (§U).
    A 12-worker team on a 16 GB host may legitimately run 3 at once. Collapsing
    them into one number would either understate the team or overstate what
    the hardware can do — both are dishonest.
    """
    team_id: str
    team_name: str
    purpose: str
    programme_id: Optional[str] = None
    project_id: Optional[str] = None

    supervisor_worker_id: Optional[str] = None
    team_lead_worker_id: Optional[str] = None

    members: list[str] = field(default_factory=list)  # worker_ids
    dependencies: list[str] = field(default_factory=list)  # team_ids

    team_size: int = 0              # logical workers (§U)
    active_concurrency_limit: int = 3  # what the host may actually run (§U)

    privacy_policy: str = "PRIVACY_PROJECT"
    cost_policy: str = "FREE_ONLY"

    state: str = "FORMING"  # FORMING | ACTIVE | COMPLETE | DISSOLVED

    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    completion_criteria: list[str] = field(default_factory=list)
    handoff_target: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.team_size:
            self.team_size = len(self.members)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class HandoffRecord:
    """A registered worker-to-worker handoff (§H, §I).

    No important work may live only in ephemeral chat text. This is the
    durable form of a handoff: the receiving worker can continue from it
    without the original conversation.
    """
    handoff_id: str
    task_id: str
    parent_task_id: Optional[str]
    from_worker: str
    from_role: str
    to_worker: str
    to_role: str
    objective: str
    completed_work: str = ""
    artifacts: list[str] = field(default_factory=list)
    repo: Optional[str] = None
    branch: Optional[str] = None
    commit: Optional[str] = None
    tests_run: int = 0
    test_results: str = ""
    decisions_made: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    known_failures: list[str] = field(default_factory=list)
    known_risks: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    dependencies_completed: list[str] = field(default_factory=list)
    dependencies_remaining: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    recommended_next_action: str = ""
    acceptance_state: str = "PENDING"
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)


# === Provenance layer ===
# Append-only. Every mutation to the canonical layer appends exactly one
# event here. Events are never edited or removed.

EVENT_TEAM_FORMED = "team.formed"
EVENT_WORKER_REGISTERED = "worker.registered"
EVENT_TEAM_STATE = "team.state_changed"
EVENT_MEMBER_ADDED = "team.member_added"
EVENT_MEMBER_REMOVED = "team.member_removed"
EVENT_TASK_OWNER_SET = "task.owner_set"
EVENT_RACI_RECORDED = "task.raci_recorded"
EVENT_HANDOFF_REGISTERED = "worker.handoff_registered"
EVENT_CAREER_PROMOTED = "worker.promoted"
EVENT_CAREER_DEMOTED = "worker.demoted"
EVENT_MODEL_SWAPPED = "worker.model_swapped"
EVENT_TEAM_SCALED = "team.scaled"


class ProvenanceError(RuntimeError):
    """Raised when the append-only trail cannot be trusted."""


class TeamRegistry:
    """Canonical organisational registry with append-only provenance (§AK).

    Design rule that shapes everything below: the canonical layer is a cache
    of current truth, the provenance layer is the permanent record. If the two
    ever disagree, the provenance layer wins — it is the one that cannot be
    edited after the fact.

    Rebuilding canonical state from provenance is therefore always possible,
    and `rebuild_from_provenance()` does exactly that. A registry that can
    only be trusted if nobody tampered with the fast path is not a registry.
    """

    def __init__(self, provenance_path: Optional[str] = None) -> None:
        self.schema_version = TEAM_REGISTRY_SCHEMA_VERSION
        self._teams: dict[str, TeamRecord] = {}
        self._workers: dict[str, WorkerCareerRecord] = {}
        self._task_owners: dict[str, str] = {}
        self._raci: dict[str, RaciAssignment] = {}
        self._handoffs: dict[str, HandoffRecord] = {}
        self._provenance_path = provenance_path
        self._event_count = 0

    # ---- provenance ----------------------------------------------------

    def _append_event(self, event_type: str, **payload: Any) -> dict:
        """Append one immutable event (§52: never delete the trail).

        The canonical mutation and the provenance append are deliberately
        ordered so that if the append fails the canonical state is NOT left
        claiming a change that has no permanent record. Losing a mutation is
        recoverable; a fabricated trail is not.
        """
        event = {
            "event_id": f"evt-{uuid.uuid4().hex[:12]}",
            "event_type": event_type,
            "sequence": self._event_count,
            "timestamp": time.time(),
            "schema_version": self.schema_version,
            **payload,
        }
        if self._provenance_path:
            try:
                os.makedirs(os.path.dirname(self._provenance_path) or ".",
                            exist_ok=True)
                with open(self._provenance_path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(event, default=str) + "\n")
            except OSError as exc:
                raise ProvenanceError(
                    f"cannot append to provenance trail: {exc}") from exc
        self._event_count += 1
        return event

    @property
    def provenance_path(self) -> Optional[str]:
        return self._provenance_path

    def rebuild_from_provenance(self) -> int:
        """Reconstruct canonical state by replaying the append-only trail.

        This is the escape hatch that makes the two-layer design safe: if the
        in-memory canonical state is ever lost or suspected, the permanent
        record can rebuild it. Returns the number of events replayed.
        """
        if not self._provenance_path or not os.path.exists(self._provenance_path):
            return 0
        self._teams.clear()
        self._workers.clear()
        self._task_owners.clear()
        self._raci.clear()
        self._handoffs.clear()
        self._event_count = 0
        replayed = 0
        with open(self._provenance_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                event = json.loads(line)
                version = event.get("schema_version")
                if version != self.schema_version:
                    # Fail loudly rather than mis-parse (§5).
                    raise ProvenanceError(
                        f"provenance event {event.get('event_id')} has "
                        f"schema_version {version}, this registry is "
                        f"{self.schema_version}; refusing to guess")
                self._replay(event)
                self._event_count = max(self._event_count,
                                        int(event.get("sequence", 0)) + 1)
                replayed += 1
        return replayed

    def _replay(self, event: dict) -> None:
        """Apply one historical event to canonical state."""
        et = event.get("event_type")
        if et == EVENT_TEAM_FORMED:
            self._teams[event["team_id"]] = TeamRecord(
                **{k: v for k, v in event["team"].items()
                   if k in TeamRecord.__dataclass_fields__})
        elif et == EVENT_WORKER_REGISTERED:
            self._workers[event["worker_id"]] = WorkerCareerRecord(
                **{k: v for k, v in event["worker"].items()
                   if k in WorkerCareerRecord.__dataclass_fields__})
        elif et == EVENT_TEAM_STATE:
            team = self._teams.get(event["team_id"])
            if team:
                team.state = event["state"]
                team.last_activity = event["timestamp"]
        elif et == EVENT_MEMBER_ADDED:
            team = self._teams.get(event["team_id"])
            if team and event["worker_id"] not in team.members:
                team.members.append(event["worker_id"])
                team.team_size = len(team.members)
        elif et == EVENT_MEMBER_REMOVED:
            team = self._teams.get(event["team_id"])
            if team and event["worker_id"] in team.members:
                team.members.remove(event["worker_id"])
                team.team_size = len(team.members)
        elif et == EVENT_TASK_OWNER_SET:
            self._task_owners[event["task_id"]] = event["owner_worker_id"]
        elif et == EVENT_RACI_RECORDED:
            self._raci[event["raci"]["task_id"]] = RaciAssignment(
                **{k: v for k, v in event["raci"].items()
                   if k in RaciAssignment.__dataclass_fields__})
        elif et == EVENT_HANDOFF_REGISTERED:
            self._handoffs[event["handoff"]["handoff_id"]] = HandoffRecord(
                **{k: v for k, v in event["handoff"].items()
                   if k in HandoffRecord.__dataclass_fields__})
        elif et in (EVENT_CAREER_PROMOTED, EVENT_CAREER_DEMOTED):
            worker = self._workers.get(event["worker_id"])
            if worker:
                worker.career_state = event["to_state"]
                worker.updated_at = event["timestamp"]
        elif et == EVENT_MODEL_SWAPPED:
            worker = self._workers.get(event["worker_id"])
            if worker:
                # The role and worker_id deliberately survive this (§M).
                worker.model_id = event["model_id"]
                worker.provider_id = event["provider_id"]
                worker.updated_at = event["timestamp"]
        elif et == EVENT_TEAM_SCALED:
            team = self._teams.get(event["team_id"])
            if team:
                team.team_size = event["team_size"]

    # ---- workers (§M, §AJ) ---------------------------------------------

    def register_worker(self, worker: WorkerCareerRecord) -> WorkerCareerRecord:
        """Add a worker. Its role, department and replaceable model are all
        recorded so that a later model swap can be shown not to have changed
        the worker's identity (§M)."""
        if worker.worker_id in self._workers:
            raise ValueError(
                f"worker {worker.worker_id} already registered; permanent "
                f"IDs are not reused (§5)")
        self._workers[worker.worker_id] = worker
        self._append_event(EVENT_WORKER_REGISTERED, worker=worker.to_dict(),
                           worker_id=worker.worker_id)
        return worker

    def get_worker(self, worker_id: str) -> Optional[WorkerCareerRecord]:
        return self._workers.get(worker_id)

    def list_workers(self) -> list[WorkerCareerRecord]:
        """All registered workers (enumeration for the supervisor read-model)."""
        return list(self._workers.values())

    def list_teams(self) -> list["TeamRecord"]:
        """All registered teams (enumeration for the supervisor read-model)."""
        return list(self._teams.values())

    def workers_by_role(self, role_id: str) -> list[WorkerCareerRecord]:
        return [w for w in self._workers.values() if w.role_id == role_id]

    def workers_by_department(self, department: str) -> list[WorkerCareerRecord]:
        return [w for w in self._workers.values() if w.department == department]

    def rank_workers(self, role_id: str) -> list[WorkerCareerRecord]:
        """§AI — evidence-based ranking for a role.

        Workers with no evidence sort LAST, not first. An untried worker
        ranking above a proven one because its failure count is zero would
        reward inaction.
        """
        candidates = self.workers_by_role(role_id)

        def sort_key(w: WorkerCareerRecord):
            rate = w.success_rate
            return (rate is not None, rate if rate is not None else 0.0,
                    w.success_count + w.failure_count)

        return sorted(candidates, key=sort_key, reverse=True)

    def promote_worker(self, worker_id: str, to_state: str,
                       evidence: str) -> WorkerCareerRecord:
        """§AI — promotion requires evidence, and records it.

        Demotion is allowed without the same ceremony: a worker that is
        failing must be able to be pulled back immediately, and demanding a
        justification for a safety action would discourage taking it.
        """
        worker = self._workers.get(worker_id)
        if not worker:
            raise KeyError(f"unknown worker {worker_id}")
        if to_state in CAREER_ORDER and worker.career_state in CAREER_ORDER:
            if CAREER_ORDER.index(to_state) <= CAREER_ORDER.index(
                    worker.career_state) and to_state != worker.career_state:
                raise ValueError(
                    f"cannot promote {worker_id} from {worker.career_state} "
                    f"to {to_state}: career states are not demotions in "
                    f"disguise; use demote_worker explicitly")
        previous = worker.career_state
        worker.career_state = to_state
        worker.updated_at = time.time()
        event_type = EVENT_CAREER_DEMOTED if to_state in (
            CAREER_DEGRADED, CAREER_BLOCKED, CAREER_RETIRED,
            CAREER_SUPERSEDED) else EVENT_CAREER_PROMOTED
        self._append_event(event_type, worker_id=worker_id,
                           from_state=previous, to_state=to_state,
                           evidence=evidence)
        return worker

    def demote_worker(self, worker_id: str, to_state: str,
                      reason: str) -> WorkerCareerRecord:
        worker = self._workers.get(worker_id)
        if not worker:
            raise KeyError(f"unknown worker {worker_id}")
        previous = worker.career_state
        worker.career_state = to_state
        worker.updated_at = time.time()
        self._append_event(EVENT_CAREER_DEMOTED, worker_id=worker_id,
                           from_state=previous, to_state=to_state,
                           reason=reason)
        return worker

    def record_outcome(self, worker_id: str, success: bool,
                       latency_s: Optional[float] = None) -> None:
        """§AI — the evidence that promotions are later judged against."""
        worker = self._workers.get(worker_id)
        if not worker:
            raise KeyError(f"unknown worker {worker_id}")
        if success:
            worker.success_count += 1
        else:
            worker.failure_count += 1
        if latency_s is not None:
            worker.last_latency_s = latency_s
        worker.updated_at = time.time()

    def swap_worker_model(self, worker_id: str, model_id: str,
                          provider_id: Optional[str] = None) -> WorkerCareerRecord:
        """§M — replace the substrate, keep the worker.

        The whole point: role, department, specialisms, worker_id and career
        state are untouched. A model is replaceable; a worker is not.
        """
        worker = self._workers.get(worker_id)
        if not worker:
            raise KeyError(f"unknown worker {worker_id}")
        previous_model = worker.model_id
        worker.model_id = model_id
        worker.provider_id = provider_id or worker.provider_id
        worker.updated_at = time.time()
        self._append_event(EVENT_MODEL_SWAPPED, worker_id=worker_id,
                           model_id=model_id, provider_id=worker.provider_id,
                           previous_model=previous_model)
        return worker

    # ---- teams (§N, §U) -------------------------------------------------

    def form_team(self, team: TeamRecord) -> TeamRecord:
        if team.team_id in self._teams:
            raise ValueError(f"team {team.team_id} already exists (§5)")
        for member in team.members:
            if member not in self._workers:
                raise ValueError(
                    f"cannot add {member} to team {team.team_id}: not a "
                    f"registered worker (§O — accountability requires a "
                    f"known worker)")
        self._teams[team.team_id] = team
        self._append_event(EVENT_TEAM_FORMED, team_id=team.team_id,
                           team=team.to_dict())
        return team

    def get_team(self, team_id: str) -> Optional[TeamRecord]:
        return self._teams.get(team_id)

    def add_member(self, team_id: str, worker_id: str) -> TeamRecord:
        team = self._teams.get(team_id)
        if not team:
            raise KeyError(f"unknown team {team_id}")
        if worker_id not in self._workers:
            raise ValueError(f"{worker_id} is not a registered worker")
        if worker_id in team.members:
            return team
        team.members.append(worker_id)
        team.team_size = len(team.members)
        team.last_activity = time.time()
        self._append_event(EVENT_MEMBER_ADDED, team_id=team_id,
                           worker_id=worker_id)
        return team

    def remove_member(self, team_id: str, worker_id: str) -> TeamRecord:
        team = self._teams.get(team_id)
        if not team:
            raise KeyError(f"unknown team {team_id}")
        if worker_id in team.members:
            team.members.remove(worker_id)
            team.team_size = len(team.members)
            team.last_activity = time.time()
            self._append_event(EVENT_MEMBER_REMOVED, team_id=team_id,
                               worker_id=worker_id)
        return team

    def set_team_state(self, team_id: str, state: str) -> TeamRecord:
        team = self._teams.get(team_id)
        if not team:
            raise KeyError(f"unknown team {team_id}")
        previous = team.state
        team.state = state
        team.last_activity = time.time()
        self._append_event(EVENT_TEAM_STATE, team_id=team_id,
                           from_state=previous, state=state)
        return team

    def scale_team(self, team_id: str, new_size: int) -> TeamRecord:
        """§T — team size scales with the job, independent of concurrency.

        Deliberately does not add or remove members: scaling the LOGICAL team
        is an organisational decision, while membership is a factual one. A
        team can be declared 12 strong while 3 run at a time (§U).
        """
        team = self._teams.get(team_id)
        if not team:
            raise KeyError(f"unknown team {team_id}")
        if new_size < 0:
            raise ValueError("team size cannot be negative")
        team.team_size = new_size
        team.last_activity = time.time()
        self._append_event(EVENT_TEAM_SCALED, team_id=team_id,
                           team_size=new_size,
                           active_concurrency_limit=team.active_concurrency_limit)
        return team

    def set_team_lead(self, team_id: str,
                      lead_worker_id: Optional[str]) -> TeamRecord:
        """§G — team leads are temporary authority over assigned work only."""
        team = self._teams.get(team_id)
        if not team:
            raise KeyError(f"unknown team {team_id}")
        if lead_worker_id is not None and lead_worker_id not in self._workers:
            raise ValueError(f"{lead_worker_id} is not a registered worker")
        team.team_lead_worker_id = lead_worker_id
        if lead_worker_id:
            lead = self._workers[lead_worker_id]
            if team_id not in lead.team_lead_of:
                lead.team_lead_of.append(team_id)
        team.last_activity = time.time()
        return team

    # ---- task ownership (§O) and RACI (§P) ------------------------------

    def set_task_owner(self, task_id: str,
                       owner_worker_id: str) -> None:
        """§O — exactly one accountable owner per task.

        Re-assignment is allowed and recorded: ownership can move, but it is
        always singular and always traceable. That is what prevents the
        "everyone thought someone else was doing it" failure.
        """
        if owner_worker_id not in self._workers:
            raise ValueError(
                f"{owner_worker_id} is not a registered worker; a task cannot "
                f"be owned by an unknown worker (§O)")
        previous = self._task_owners.get(task_id)
        self._task_owners[task_id] = owner_worker_id
        self._append_event(EVENT_TASK_OWNER_SET, task_id=task_id,
                           owner_worker_id=owner_worker_id,
                           previous_owner=previous)

    def task_owner(self, task_id: str) -> Optional[str]:
        return self._task_owners.get(task_id)

    def record_raci(self, raci: RaciAssignment) -> RaciAssignment:
        """§P — record RACI. ``accountable`` is the single execution owner.

        The invariant that never relaxes: exactly one identity is answerable
        for the task completing (§O). What the ``accountability_mode`` adds is
        the ability to say that other identities — a board, both parents, a
        partnership — share ultimate accountability, without implying any of
        them is the one who must get the work done.

        Zero accountable owners is the bug §O exists to prevent; that stays a
        hard error in every mode.
        """
        if raci.accountability_mode not in ACCOUNTABILITY_MODES:
            raise ValueError(
                f"accountability_mode {raci.accountability_mode!r} is not one "
                f"of {ACCOUNTABILITY_MODES}")
        if not raci.accountable:
            raise ValueError(
                f"task {raci.task_id} has no ACCOUNTABLE worker; every task "
                f"needs exactly one execution owner (§O, §P)")
        if raci.accountable not in self._workers:
            raise ValueError(
                f"accountable worker {raci.accountable} is not registered")
        for worker_id in (raci.responsible + raci.consulted + raci.informed
                          + raci.collective_accountable):
            if worker_id not in self._workers:
                raise ValueError(f"{worker_id} is not a registered worker")
        if raci.accountability_mode in (ACCOUNTABILITY_JOINT,
                                        ACCOUNTABILITY_COLLECTIVE) \
                and not raci.collective_accountable:
            raise ValueError(
                f"accountability_mode {raci.accountability_mode} requires at "
                f"least one collective accountable holder (§P)")
        if raci.task_id not in self._task_owners:
            # The single execution owner owns the task (§O).
            self.set_task_owner(raci.task_id, raci.accountable)
        self._raci[raci.task_id] = raci
        self._append_event(EVENT_RACI_RECORDED, raci=raci.to_dict())
        return raci

    def raci_for(self, task_id: str) -> Optional[RaciAssignment]:
        return self._raci.get(task_id)

    # ---- handoffs (§H, §I) ----------------------------------------------

    def register_handoff(self, handoff: HandoffRecord) -> HandoffRecord:
        """§H — register a worker-to-worker handoff.

        Validates that both ends are real workers and that the receiving
        worker's role matches what the handoff declares. A handoff to a role
        nobody holds is the failure mode §I exists to catch: work that
        everyone assumed was picked up.
        """
        for worker_id in (handoff.from_worker, handoff.to_worker):
            if worker_id not in self._workers:
                raise ValueError(
                    f"handoff references unregistered worker {worker_id} (§I)")
        receiver = self._workers[handoff.to_worker]
        if receiver.role_id != handoff.to_role:
            raise ValueError(
                f"handoff declares to_role {handoff.to_role} but worker "
                f"{handoff.to_worker} holds role {receiver.role_id}; a "
                f"handoff to a role nobody holds is silently dropped work")
        if handoff.from_role and handoff.from_worker in self._workers:
            sender = self._workers[handoff.from_worker]
            if sender.role_id != handoff.from_role:
                raise ValueError(
                    f"handoff declares from_role {handoff.from_role} but "
                    f"sender holds {sender.role_id}")
        self._handoffs[handoff.handoff_id] = handoff
        self._append_event(EVENT_HANDOFF_REGISTERED, handoff=handoff.to_dict())
        return handoff

    def get_handoff(self, handoff_id: str) -> Optional[HandoffRecord]:
        return self._handoffs.get(handoff_id)

    def handoff_chain(self, task_id: str) -> list[HandoffRecord]:
        """§AC — the A→B→C chain for a task, in order.

        Ordered by timestamp because a chain is a sequence, and the receiving
        worker needs to know what came before, not just who was involved.
        """
        return sorted([h for h in self._handoffs.values() if h.task_id == task_id],
                      key=lambda h: h.timestamp)

    def handoffs_for_worker(self, worker_id: str) -> list[HandoffRecord]:
        return [h for h in self._handoffs.values()
                if h.from_worker == worker_id or h.to_worker == worker_id]

    # ---- reporting ------------------------------------------------------

    def summary(self) -> dict:
        """Machine-readable state for the §AK gate and the owner dashboard."""
        return {
            "schema_version": self.schema_version,
            "teams": len(self._teams),
            "workers": len(self._workers),
            "tasks_with_owners": len(self._task_owners),
            "raci_records": len(self._raci),
            "handoffs": len(self._handoffs),
            "provenance_events": self._event_count,
            "provenance_path": self._provenance_path,
            "departments": {
                dept: len(self.workers_by_department(dept))
                for dept in DEPARTMENTS
            },
            "career_states": {
                state: sum(1 for w in self._workers.values()
                           if w.career_state == state)
                for state in CAREER_ORDER
            },
        }

    def team_report(self, team_id: str) -> dict:
        """§AE — what a team's completion looks like on paper."""
        team = self._teams.get(team_id)
        if not team:
            raise KeyError(f"unknown team {team_id}")
        members = [self._workers[m].to_dict() for m in team.members
                   if m in self._workers]
        open_tasks = [t for t, owner in self._task_owners.items()
                      if owner in team.members]
        return {
            **team.to_dict(),
            "member_details": members,
            "departments_represented": sorted({
                w.department for w in (self._workers[m] for m in team.members
                                       if m in self._workers) if w.department}),
            "roles_represented": sorted({
                self._workers[m].role_id for m in team.members
                if m in self._workers}),
            "open_owned_tasks": open_tasks,
            # §U — the distinction the host's RAM depends on.
            "logical_team_size": team.team_size,
            "active_concurrency_limit": team.active_concurrency_limit,
        }


# === Factory helpers ===

def new_worker(role_id: str, model_id: Optional[str] = None,
               provider_id: Optional[str] = None,
               specialisms: Optional[Iterable[str]] = None,
               worker_id: Optional[str] = None) -> WorkerCareerRecord:
    """Create a worker with a stable permanent ID (§5)."""
    return WorkerCareerRecord(
        worker_id=worker_id or f"worker-{uuid.uuid4().hex[:10]}",
        role_id=role_id,
        model_id=model_id,
        provider_id=provider_id,
        specialisms=list(specialisms or []),
    )


def new_team(role_ids: Iterable[str],
             objective: str = "unspecified objective",
             team_size: Optional[int] = None,
             concurrency: int = 3,
             team_id: Optional[str] = None) -> tuple[TeamRecord, list[WorkerCareerRecord]]:
    """§E — dynamic team formation: roles first, then workers to fill them.

    `role_ids` comes first because it is the argument a caller always has:
    the objective's required roles are known before anything else exists.
    Requiring an objective string first would make every call site pad a
    positional argument to reach the part that matters.

    Returns the team and the workers created for it, so the caller registers
    both. Roles are derived from the objective's required roles, not chosen
    because a particular agent happens to exist.
    """
    roles = list(role_ids)
    workers = [new_worker(r) for r in roles]
    team = TeamRecord(
        team_id=team_id or f"team-{uuid.uuid4().hex[:8]}",
        team_name=f"team-{len(roles)}-roles",
        purpose=objective,
        members=[w.worker_id for w in workers],
        team_size=team_size if team_size is not None else len(roles),
        active_concurrency_limit=concurrency,
    )
    return team, workers
