"""Quota-aware multi-agent hive workforce scheduler (§1-§43 of the hive
directive).

Hermes is the HIVE SUPERVISOR: internal subagents and external agents
(OpenCode, Codex, Claude, local Ollama workers, ...) are workers in one shared
pool. This module is the SCHEDULER / ROUTER / QUOTA MANAGER — it does not
execute anything itself; it decides WHO should do WHAT, tracks quota, and
records machine-readable handoffs.

EXTENDS, never duplicates (§49):
- worker identity comes from compute.team_registry (MODEL != WORKER !=
  PROVIDER; career records with success_rate);
- installed-app capability comes from app_registry (verification_status is the
  honesty gate — an INTERACTIVE_ONLY app is not routable);
- this module adds ONLY the quota ledger, the task router, the task graph and
  the structured handoff message.

Honesty rules (non-negotiable):
- quota confidence is VERIFIED / OBSERVED / ESTIMATED / UNKNOWN (§38). If a
  provider does not expose remaining credits, it is UNKNOWN — never an
  invented percentage.
- PAID work is never selected unless explicitly reserved (default budget 0,
  §4). FREE_FIRST_STRICT.
- SECRET/PRIVATE work never routes to an external cloud worker (§29).

Persistence: the ledger and task graph serialise to JSON (§37 power-failure
recovery — the hive state survives a reboot; reload -> verify -> resume).
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

# --- honesty vocabulary (closed) --------------------------------------------
VERIFIED = "VERIFIED"      # read from an authoritative usage API/page
OBSERVED = "OBSERVED"      # derived from observed behaviour (e.g. a reset seen)
ESTIMATED = "ESTIMATED"    # computed from an estimate, clearly marked
UNKNOWN = "UNKNOWN"        # not determinable — never fabricate a number

QUOTA_CONFIDENCE = frozenset({VERIFIED, OBSERVED, ESTIMATED, UNKNOWN})

# --- account tiers (§3) ------------------------------------------------------
LOCAL_UNLIMITED = "LOCAL_UNLIMITED"
FREE = "FREE"
FREE_PLAN = "FREE_PLAN"
FREE_TIER = "FREE_TIER"
FREEMIUM = "FREEMIUM"
TRIAL = "TRIAL"
PAID = "PAID"
OWNED_PAID_ENTITLEMENT = "OWNED_PAID_ENTITLEMENT"  # existing owner-paid sub
TIERS = frozenset({LOCAL_UNLIMITED, FREE, FREE_PLAN, FREE_TIER, FREEMIUM,
                   TRIAL, PAID, OWNED_PAID_ENTITLEMENT, UNKNOWN})

# --- quota POOLS (§2 of the quota directive: limits are INDEPENDENT windows,
# never one number — five-hour + weekly + monthly each gate separately) ------
POOL_SHORT_WINDOW = "SHORT_WINDOW"      # e.g. Codex five-hour allowance
POOL_WEEKLY = "WEEKLY"
POOL_MONTHLY = "MONTHLY"
POOL_CREDIT_PERIOD = "CREDIT_PERIOD"    # monthly credit/usage allowance view
POOL_MODEL_SPECIFIC = "MODEL_SPECIFIC"
POOL_REQUEST_RATE = "REQUEST_RATE"
POOL_CONCURRENCY = "CONCURRENCY"
POOL_BANKED_RESET = "BANKED_RESET"
POOL_PROMOTIONAL = "PROMOTIONAL_RESET"
QUOTA_POOLS = frozenset({POOL_SHORT_WINDOW, POOL_WEEKLY, POOL_MONTHLY,
                         POOL_CREDIT_PERIOD, POOL_MODEL_SPECIFIC,
                         POOL_REQUEST_RATE, POOL_CONCURRENCY,
                         POOL_BANKED_RESET, POOL_PROMOTIONAL, UNKNOWN})

# --- reset cadence (§5, §24) -------------------------------------------------
HOURLY = "HOURLY"
DAILY = "DAILY"
ROLLING_24H = "ROLLING_24H"
WEEKLY = "WEEKLY"
ROLLING_7D = "ROLLING_7D"
MONTHLY = "MONTHLY"
BILLING_CYCLE = "BILLING_CYCLE"
PER_SESSION = "PER_SESSION"
PER_REQUEST = "PER_REQUEST"
RESET_TYPES = frozenset({HOURLY, DAILY, ROLLING_24H, WEEKLY, ROLLING_7D,
                         MONTHLY, BILLING_CYCLE, PER_SESSION, PER_REQUEST,
                         UNKNOWN})

# --- worker states (§33) -----------------------------------------------------
AVAILABLE = "AVAILABLE"
ASSIGNED = "ASSIGNED"
ANALYSING = "ANALYSING"
PLANNING = "PLANNING"
IMPLEMENTING = "IMPLEMENTING"
TESTING = "TESTING"
REVIEWING = "REVIEWING"
WAITING = "WAITING"
WAITING_FOR_QUOTA = "WAITING_FOR_QUOTA"
BLOCKED = "BLOCKED"
HUNG = "HUNG"
INTERRUPTED = "INTERRUPTED"
COMMITTING = "COMMITTING"
PUSHING = "PUSHING"
QA = "QA"
COMPLETE = "COMPLETE"
OFFLINE = "OFFLINE"
WORKER_STATES = frozenset({
    AVAILABLE, ASSIGNED, ANALYSING, PLANNING, IMPLEMENTING, TESTING,
    REVIEWING, WAITING, WAITING_FOR_QUOTA, BLOCKED, HUNG, INTERRUPTED,
    COMMITTING, PUSHING, QA, COMPLETE, OFFLINE})

# --- privacy classes (§29) ---------------------------------------------------
PUBLIC = "PUBLIC"          # safe for any worker incl. external cloud
INTERNAL = "INTERNAL"      # owner-controlled or verified workers only
SECRET = "SECRET"          # local/owner-controlled ONLY, unless explicitly
                           # authorised — external cloud is a hard NO
PRIVACY_CLASSES = frozenset({PUBLIC, INTERNAL, SECRET})

# --- free-first priority (§4): lower number = preferred ----------------------
TIER_PRIORITY = {
    LOCAL_UNLIMITED: 0,
    FREE: 1,
    FREE_PLAN: 2,
    FREE_TIER: 3,
    FREEMIUM: 4,
    TRIAL: 5,
    PAID: 8,
    UNKNOWN: 6,  # unknown tier is treated as potentially paid — not favoured
}


def _now() -> float:
    return time.time()


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(_now(), timezone.utc).isoformat(
        timespec="seconds")


@dataclass(frozen=True)
class QuotaLedgerEntry:
    """One worker/provider quota observation (§5).

    quota_remaining=None means UNKNOWN (never 0-as-fabrication and never a
    guessed percentage). confidence says how the number was obtained.

    `pool` (§2 of the quota directive): which INDEPENDENT allowance window
    this entry describes — SHORT_WINDOW (five-hour), WEEKLY, MONTHLY, ... A
    worker with several pools needs each recorded separately; capacity is the
    MOST RESTRICTIVE window, never an average (§4). `pool_id` identifies a
    shared pool so the scheduler knows two apps drawing on the same account
    allowance reduce each other's capacity (§15 of the quota directive).
    """
    worker_id: str
    provider: str
    tier: str = UNKNOWN
    quota_total: Optional[float] = None
    quota_remaining: Optional[float] = None
    quota_used: Optional[float] = None
    quota_unit: str = "tokens"
    reset_type: str = UNKNOWN
    next_reset_epoch: Optional[float] = None
    confidence: str = UNKNOWN
    source: str = ""
    pool: str = UNKNOWN
    pool_id: str = ""
    paid_option_available: bool = False     # §10: recorded, NEVER purchased
    observed_at: str = field(default_factory=_now_iso)

    def __post_init__(self) -> None:
        if self.tier not in TIERS:
            raise ValueError(f"unknown tier {self.tier!r}")
        if self.confidence not in QUOTA_CONFIDENCE:
            raise ValueError(f"unknown confidence {self.confidence!r}")
        if self.reset_type not in RESET_TYPES:
            raise ValueError(f"unknown reset_type {self.reset_type!r}")
        if self.pool not in QUOTA_POOLS:
            raise ValueError(f"unknown pool {self.pool!r}")

    def remaining_fraction(self) -> Optional[float]:
        """Honest remaining fraction, or None when UNKNOWN (§38)."""
        if (self.quota_total is None or self.quota_remaining is None
                or self.quota_total <= 0):
            return None
        return max(0.0, min(1.0, self.quota_remaining / self.quota_total))

    def exhausted(self) -> bool:
        """True only when the pool is KNOWN-empty. UNKNOWN is not exhausted
        (§38 honesty) — the scheduler treats UNKNOWN separately."""
        frac = self.remaining_fraction()
        return frac is not None and frac <= 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class TaskSpec:
    """A bounded unit of work offered to the hive (§9, §26)."""
    task_id: str
    title: str
    project: str = ""
    required_capability: str = ""      # capability_family / role_id
    privacy_class: str = PUBLIC
    estimated_input_tokens: Optional[int] = None
    estimated_output_tokens: Optional[int] = None
    estimated_iterations: int = 1
    write_set: str = ""                # checkout/worktree this task owns
    depends_on: tuple[str, ...] = ()
    priority: int = 0
    budget_max_iterations: int = 10    # §26 no endless self-retry loops
    timeout_s: float = 600.0
    success_criteria: str = ""

    def __post_init__(self) -> None:
        if self.privacy_class not in PRIVACY_CLASSES:
            raise ValueError(f"unknown privacy_class {self.privacy_class!r}")

    def estimated_tokens(self) -> Optional[int]:
        if self.estimated_input_tokens is None and self.estimated_output_tokens is None:
            return None
        return (self.estimated_input_tokens or 0) + (self.estimated_output_tokens or 0)

    def to_dict(self) -> dict:
        return {**asdict(self), "depends_on": list(self.depends_on)}


@dataclass(frozen=True)
class HandoffMessage:
    """Compact structured machine-to-machine handoff (§14, §17).

    No opaque 'robot speech' — plain JSON fields a human can also read.
    """
    type: str                          # handoff | correction | result | query
    from_worker: str
    to_worker: str
    project: str = ""
    unit: str = ""
    state: str = ""                    # READY | IN_PROGRESS | BLOCKED | DONE
    requirements: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    next_action: str = ""
    task_id: str = ""
    sent_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return {**asdict(self),
                "requirements": list(self.requirements),
                "dependencies": list(self.dependencies),
                "evidence": list(self.evidence),
                "blockers": list(self.blockers)}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=1)


class HiveSchedulerError(Exception):
    pass


class HiveScheduler:
    """The hive supervisor's scheduling core (thread-safe, persistable).

    Workers are referenced by worker_id (team_registry identity). Their
    execution target (app_registry app_id / provider) carries the quota and
    privacy attributes. The scheduler never executes a worker — it selects,
    reserves, records handoffs and reallocates.
    """

    def __init__(self, paid_budget: int = 0) -> None:
        self._lock = threading.RLock()
        self._paid_budget = paid_budget      # §4 default 0
        self._workers: dict[str, dict[str, Any]] = {}   # worker_id -> profile
        self._quota: dict[str, QuotaLedgerEntry] = {}   # worker_id -> latest
        self._quota_pools: dict[str, dict[str, QuotaLedgerEntry]] = {}
        self._plans: dict[str, dict[str, Any]] = {}     # PlanProfiles
        self._tasks: dict[str, TaskSpec] = {}
        self._assignments: dict[str, str] = {}          # task_id -> worker_id
        self._reservations: dict[str, float] = {}       # worker_id -> fraction
        self._deferred: dict[str, dict[str, Any]] = {}  # task_id -> wait record
        self._handoffs: list[HandoffMessage] = []

    # -- worker registry (§2, §6) -------------------------------------------
    def register_worker(self, worker_id: str, provider: str,
                        app_id: str = "", tier: str = UNKNOWN,
                        privacy_class: str = PUBLIC,
                        capabilities: tuple[str, ...] = (),
                        execution_target: str = "",
                        verification_status: str = "PARTIAL") -> None:
        """Register (or update) a worker profile.

        verification_status gates routability: an INTERACTIVE_ONLY or ABSENT
        app cannot be autonomously assigned (§2 'installed != controllable').
        """
        if tier not in TIERS:
            raise HiveSchedulerError(f"unknown tier {tier!r}")
        if privacy_class not in PRIVACY_CLASSES:
            raise HiveSchedulerError(f"unknown privacy_class {privacy_class!r}")
        with self._lock:
            self._workers[worker_id] = {
                "worker_id": worker_id,
                "provider": provider,
                "app_id": app_id,
                "tier": tier,
                "privacy_class": privacy_class,
                "capabilities": list(capabilities),
                "execution_target": execution_target,
                "verification_status": verification_status,
                "state": AVAILABLE,
                "last_heartbeat": _now(),
                "registered_at": _now_iso(),
            }

    def set_worker_state(self, worker_id: str, state: str) -> None:
        if state not in WORKER_STATES:
            raise HiveSchedulerError(f"unknown worker state {state!r}")
        with self._lock:
            w = self._workers.get(worker_id)
            if w is None:
                raise HiveSchedulerError(f"unknown worker {worker_id!r}")
            w["state"] = state
            w["last_heartbeat"] = _now()

    def heartbeat(self, worker_id: str, state: str = "") -> None:
        """§34: monitor liveness; stale heartbeat is diagnosed, not killed."""
        with self._lock:
            w = self._workers.get(worker_id)
            if w is None:
                raise HiveSchedulerError(f"unknown worker {worker_id!r}")
            w["last_heartbeat"] = _now()
            if state:
                if state not in WORKER_STATES:
                    raise HiveSchedulerError(f"unknown worker state {state!r}")
                w["state"] = state

    def record_quota(self, entry: QuotaLedgerEntry) -> None:
        """§5/§6: persist one quota observation (UNKNOWN stays UNKNOWN).

        §2/§4 of the quota directive: pools are INDEPENDENT windows. A worker
        may have several (five-hour + weekly + monthly) — each is stored
        separately under (worker_id, pool) and worker capacity is the MOST
        RESTRICTIVE window, never an average.
        """
        with self._lock:
            self._quota[entry.worker_id] = entry
            self._quota_pools.setdefault(entry.worker_id, {})[entry.pool] = \
                entry

    def record_plan(self, worker_id: str, provider: str, tier: str,
                    pools: list[QuotaLedgerEntry],
                    banked_resets: int = 0,
                    last_verified: str = "") -> None:
        """§18/§27: record a full PlanProfile for one worker. All pools are
        stored; `paid_option_available` is recorded but NEVER acted on (§10 —
        owner policy: no purchases)."""
        for e in pools:
            self.record_quota(e)
        with self._lock:
            self._plans[worker_id] = {
                "worker_id": worker_id,
                "provider": provider,
                "tier": tier,
                "pools": [e.pool for e in pools],
                "banked_resets": banked_resets,
                "last_verified": last_verified or _now_iso(),
            }

    def worker_capacity(self, worker_id: str) -> dict[str, Any]:
        """§4: MULTI-WINDOW CAPACITY — the most restrictive known pool wins.
        Returns an honest summary: capacity=None means UNKNOWN (never
        fabricated), next_reset is the earliest upcoming reset, and
        exhausted=True only when a KNOWN pool is empty."""
        with self._lock:
            entries = list(self._quota_pools.get(worker_id, {}).values())
            if not entries:
                entries = [self._quota[worker_id]] \
                    if worker_id in self._quota else []
        fracs = [e.remaining_fraction() for e in entries]
        known = [f for f in fracs if f is not None]
        resets = [e.next_reset_epoch for e in entries
                  if e.next_reset_epoch is not None]
        return {
            "worker_id": worker_id,
            "capacity": (min(known) if known else None),
            "pools_known": len(known),
            "pools_total": len(entries),
            "exhausted": any(e.exhausted() for e in entries),
            "next_reset_epoch": (min(resets) if resets else None),
            "paid_option_available": any(e.paid_option_available
                                         for e in entries),
            "confidence": (entries[0].confidence if entries else UNKNOWN),
        }

    def reserve_quota(self, worker_id: str, fraction: float) -> None:
        """§25: hold scarce quota for a known upcoming task."""
        if not 0.0 <= fraction <= 1.0:
            raise HiveSchedulerError("reservation fraction must be 0..1")
        with self._lock:
            self._reservations[worker_id] = fraction

    # -- scoring (§9) ---------------------------------------------------------
    def worker_score(self, worker_id: str, task: TaskSpec) -> Optional[float]:
        """WORKER_SCORE (§9). Returns None when the worker is INELIGIBLE
        (hard gates), so the router can skip it rather than score it low.
        """
        with self._lock:
            w = self._workers.get(worker_id)
            if w is None:
                return None
            # Hard gates first.
            # §29 privacy before quota: SECRET never leaves owner control.
            if task.privacy_class == SECRET and w["privacy_class"] != SECRET:
                return None
            if task.privacy_class == INTERNAL and w["privacy_class"] == PUBLIC:
                return None
            # §13 one writer per write-set.
            if task.write_set:
                for tid, wid in self._assignments.items():
                    other = self._tasks.get(tid)
                    if (wid != worker_id and other is not None
                            and other.write_set == task.write_set):
                        return None
            # §2 installed != controllable: non-automatable apps are not
            # autonomous candidates.
            if w["verification_status"] in ("INTERACTIVE_ONLY", "ABSENT"):
                return None
            # §4 free-first: PAID workers need the (default-zero) paid budget.
            if w["tier"] == PAID and self._paid_budget <= 0:
                return None
            # §27 exhausted quota: a KNOWN-empty pool is a hard skip; UNKNOWN
            # (None) is NOT a skip — it is routed with an honest note. §4:
            # multi-window — ANY known pool at zero blocks the worker.
            cap = self.worker_capacity(worker_id)
            if cap["exhausted"]:
                return None
            q = self._quota.get(worker_id)

            score = 0.0
            # capability_fit (+3 exact, +1 family-prefix)
            if task.required_capability:
                if task.required_capability in w["capabilities"]:
                    score += 3.0
                elif any(c.startswith(task.required_capability)
                         for c in w["capabilities"]):
                    score += 1.0
            else:
                score += 1.0  # no requirement: everyone fits
            # §4 tier priority (free-first): lower tier number scores higher.
            score += (9 - TIER_PRIORITY.get(w["tier"], 6)) * 0.8
            # remaining_free_quota (§9); UNKNOWN contributes neutrally.
            # §4: score on the MOST RESTRICTIVE pool, not the latest entry —
            # five-hour at 80% with weekly at 18% is an 18% worker.
            if q is not None:
                frac = cap["capacity"]
                if frac is not None:
                    score += frac * 2.0
                    # §8 quota scarcity penalty when the task is large.
                    est = task.estimated_tokens()
                    if (est and q.quota_total and frac < 0.25
                            and est > q.quota_total * frac):
                        score -= 2.0
                else:
                    score += 0.5  # UNKNOWN: mild neutral, never a bonus
            # availability (§9): an idle/available worker beats a busy one.
            if w["state"] in (AVAILABLE, WAITING):
                score += 1.0
            elif w["state"] in (IMPLEMENTING, TESTING, ANALYSING, REVIEWING):
                score -= 1.5
            elif w["state"] in (HUNG, BLOCKED, OFFLINE, INTERRUPTED):
                score -= 4.0
            # §25 reservations hold quota back: reserved fraction is not
            # spendable on this task.
            reserved = self._reservations.get(worker_id, 0.0)
            score -= reserved * 1.5
            return score

    # -- routing (§9, §10, §28) -----------------------------------------------
    def route(self, task: TaskSpec) -> Optional[str]:
        """Select the highest-scoring ELIGIBLE worker. Honest None when no
        worker is eligible (§27 free-quota failure: defer, never pay)."""
        with self._lock:
            best_id, best_score = None, float("-inf")
            for wid in self._workers:
                s = self.worker_score(wid, task)
                if s is not None and s > best_score:
                    best_id, best_score = wid, s
            if best_id is None:
                # §28: park the task for the next quota reset instead of
                # silently dropping it or paying.
                self._deferred[task.task_id] = {
                    "task": task.to_dict(),
                    "reason": "no eligible free/local worker",
                    "deferred_at": _now_iso(),
                }
                return None
            self.assign(task, best_id)
            return best_id

    def assign(self, task: TaskSpec, worker_id: str) -> None:
        with self._lock:
            if worker_id not in self._workers:
                raise HiveSchedulerError(f"unknown worker {worker_id!r}")
            self._tasks[task.task_id] = task
            self._assignments[task.task_id] = worker_id
            self._workers[worker_id]["state"] = ASSIGNED
            self._deferred.pop(task.task_id, None)

    def release(self, task_id: str, state: str = COMPLETE) -> None:
        """Worker finished (or failed); free the write-set and the worker."""
        with self._lock:
            wid = self._assignments.pop(task_id, None)
            if wid and wid in self._workers:
                self._workers[wid]["state"] = (
                    AVAILABLE if state == COMPLETE else state)
            if state != COMPLETE:
                self._tasks[task_id] = TaskSpec(  # keep the record
                    **{**self._tasks.get(task_id, TaskSpec(task_id, "")).__dict__})

    # -- reallocation (§10) ----------------------------------------------------
    def reallocate(self, task_id: str, reason: str = "") -> Optional[str]:
        """§10: worker limit reached / slow / hung -> checkpoint & hand off to
        the next compatible free worker. Completed work is never discarded —
        the handoff message carries the evidence. The OLD worker is excluded
        (it was the problem), so the write-set genuinely moves.
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise HiveSchedulerError(f"unknown task {task_id!r}")
            old = self._assignments.get(task_id)
            if old:
                self._workers[old]["state"] = WAITING
            self._assignments.pop(task_id, None)
            # park the old worker so it is not immediately re-selected
            if old:
                self._parked = getattr(self, "_parked", set())
                self._parked.add(old)
            new = self._route_excluding(task, exclude={old} if old else set())
            if old and new:
                self._handoffs.append(HandoffMessage(
                    type="handoff", from_worker=old, to_worker=new,
                    project=task.project, unit=task.write_set,
                    state="READY", task_id=task_id,
                    evidence=(f"reallocated: {reason}",) if reason else (),
                    next_action="resume from checkpoint"))
            return new

    def _route_excluding(self, task: TaskSpec,
                         exclude: set[str]) -> Optional[str]:
        """route() that skips the given workers (used by reallocate)."""
        best_id, best_score = None, float("-inf")
        for wid in self._workers:
            if wid in exclude:
                continue
            s = self.worker_score(wid, task)
            if s is not None and s > best_score:
                best_id, best_score = wid, s
        if best_id is None:
            self._deferred[task.task_id] = {
                "task": task.to_dict(),
                "reason": "no eligible free/local worker",
                "deferred_at": _now_iso(),
            }
            return None
        self.assign(task, best_id)
        return best_id

    # -- structured messages (§14) ---------------------------------------------
    def send_handoff(self, msg: HandoffMessage) -> HandoffMessage:
        with self._lock:
            self._handoffs.append(msg)
            return msg

    def handoffs(self) -> list[HandoffMessage]:
        with self._lock:
            return list(self._handoffs)

    # -- overview (§31) ----------------------------------------------------------
    def overview(self) -> dict[str, Any]:
        with self._lock:
            states: dict[str, int] = {}
            for w in self._workers.values():
                states[w["state"]] = states.get(w["state"], 0) + 1
            next_resets = sorted(
                q.next_reset_epoch for q in self._quota.values()
                if q.next_reset_epoch)
            return {
                "workers": len(self._workers),
                "by_state": states,
                "internal_vs_external": {
                    "internal": sum(1 for w in self._workers.values()
                                    if w["provider"] == "hermes"),
                    "external": sum(1 for w in self._workers.values()
                                    if w["provider"] != "hermes"),
                },
                "tasks_total": len(self._tasks),
                "tasks_assigned": len(self._assignments),
                "waiting_for_quota": len(self._deferred),
                "next_quota_reset_epoch": next_resets[0] if next_resets else None,
                "paid_budget": self._paid_budget,
            }

    # -- persistence (§37 power-failure recovery) --------------------------------
    def to_dict(self) -> dict:
        with self._lock:
            return {
                "paid_budget": self._paid_budget,
                "workers": list(self._workers.values()),
                "quota": {k: v.to_dict() for k, v in self._quota.items()},
                "tasks": {k: v.to_dict() for k, v in self._tasks.items()},
                "assignments": dict(self._assignments),
                "reservations": dict(self._reservations),
                "deferred": dict(self._deferred),
                "handoffs": [h.to_dict() for h in self._handoffs],
                "saved_at": _now_iso(),
            }

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=1), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "HiveScheduler":
        """§22/§37: on reboot, reload -> verify -> resume. Never lose the
        hive state again."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        hive = cls(paid_budget=data.get("paid_budget", 0))
        for w in data.get("workers", []):
            hive._workers[w["worker_id"]] = w
        for k, v in data.get("quota", {}).items():
            hive._quota[k] = QuotaLedgerEntry(**v)
        for k, v in data.get("tasks", {}).items():
            hive._tasks[k] = TaskSpec(**{**v, "depends_on": tuple(v.get("depends_on", ()))})
        hive._assignments = dict(data.get("assignments", {}))
        hive._reservations = {k: float(v) for k, v in data.get("reservations", {}).items()}
        hive._deferred = dict(data.get("deferred", {}))
        for h in data.get("handoffs", []):
            hive._handoffs.append(HandoffMessage(**{
                **h,
                "requirements": tuple(h.get("requirements", ())),
                "dependencies": tuple(h.get("dependencies", ())),
                "evidence": tuple(h.get("evidence", ())),
                "blockers": tuple(h.get("blockers", ())),
            }))
        return hive
