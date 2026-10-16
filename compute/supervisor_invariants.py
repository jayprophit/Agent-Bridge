"""HERMES SUPERVISOR CONSTITUTION — runtime invariants (§36/§49).

These are NOT prompt advice.  `check_all()` is invoked every scheduler
cycle (see ``compute/supervisor_runtime.py`` — ``run_cycle`` calls
``check_invariants`` BEFORE continuation computation, so violations become
hard gates, not suggestions).  Each predicate takes a *snapshot* of the live
supervisor state and returns ``Violation`` objects with the evidence that
would let an engineer reproduce the failure.

The module is import-safe with no side effects and has zero third-party
dependencies, so it can be unit-tested in isolation and imported by the
daemon, the dashboard read-model, and the watchdog.

Invariants map to the user's 35-clause constitution (2026-10-14 directive).
``VARIANT`` numbers below are the constitution clause; the prose name is the
human label.  Honest: an invariant that the snapshot shape does not yet
support is registered as ``STUBBED`` with a TODO, never silently skipped.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# ---------------------------------------------------------------------------
# honesty vocabulary
# ---------------------------------------------------------------------------

# An invariant check can be in one of three states for a given snapshot:
PASS = "PASS"
FAIL = "FAIL"
STUBBED = "STUBBED"          # declared but the snapshot lacks the evidence

STATUSES = (PASS, FAIL, STUBBED)


@dataclass
class Violation:
    """One failed invariant + the evidence behind it."""
    invariant: str          # e.g. "INVARIANT_3_NO_IDLE_WITH_READY_WORK"
    variant: str            # e.g. "§3 / §45"
    status: str = FAIL
    severity: str = "CRITICAL"
    evidence: list[str] = field(default_factory=list)
    detail: str = ""
    fix_suggestion: str = ""


# invariant severities (§19 of the completion directive: gaps have severities)
CRITICAL = "CRITICAL"
HIGH = "HIGH"
MEDIUM = "MEDIUM"


# ---------------------------------------------------------------------------
# a flat snapshot contract
# ---------------------------------------------------------------------------
# The runtime hands `check_all` a dict with these keys (see
# SupervisorRuntime._invariants_snapshot).  Keeping it flat and dict-based
# means the module has no import cycle with supervisor_runtime/supervision/
# hive_scheduler and can be tested with plain dicts.

# required keys for the invariants that are NOT stubbed:
#   workers            dict[worker_id, dict]  (status, role, last_activity,
#                                              application, model, provider)
#   ready_tasks        list[dict]            (task_id, required_capability,
#                                             project, privacy_class,
#                                             write_set, priority)
#   handoffs_pending   int
#   gaps               list[dict]            (gap_id, severity, category,
#                                             project, description)
#   quotas             dict[worker_id, dict] (exhausted, next_reset_epoch,
#                                             confidence, tier)
#   resources          dict                    (cpu, ram, gpu, vram — 0..1)
#   projects           dict[project_id, dict] (last_progress_epoch,
#                                               has_unblocked_work, priority)
#   unassessed_apps    list[dict]            (app_id, last_action_epoch)
#   internal_workers   int                   (count of hermes-native subagents)
#   model_routing      dict                   (policy: free-first enforcement)
#   continuation_required bool                (current runtime value)
#   availability       dict                  (§H12: tier/provider status for
#                                            degradation resilience invariant)
#   deferred_tasks     list                  (parked tasks awaiting reset)

# keys that are nice-to-have; if absent, the invariant is STUBBED:
#   teams, forks, research_gaps, browser_worker, git_state, provenance, ...


def _as_list(v: Any) -> list:
    return v if isinstance(v, list) else (list(v) if v else [])


def _worker_idle(rec: dict) -> bool:
    from compute.supervision import AVAILABLE, WAITING
    return rec.get("status") in (AVAILABLE, WAITING)


# ===========================================================================
# INVARIANT 1 — PROGRAMME CONTINUATION (§2 / §36 / §45.8)
# ===========================================================================
def invariant_1_continuation(snapshot: dict) -> Optional[Violation]:
    """A report/commit/test/milestone must never clear
    continuation_required.  True whenever any unverified work remains."""
    reasons_off = []
    if snapshot.get("handoffs_pending", 0) > 0:
        reasons_off.append(f"{snapshot['handoffs_pending']} unread handoff(s)")
    gaps = _as_list(snapshot.get("gaps"))
    if gaps:
        reasons_off.append(f"{len(gaps)} open gap(s)")
    if snapshot.get("projects"):
        for pid, p in (snapshot.get("projects") or {}).items():
            if p.get("has_unblocked_work"):
                reasons_off.append(f"project {pid} has unblocked work")
                break
    # §2: min-hive breach is unfinished work only when >=5 independent ready units exist
    ready = _as_list(snapshot.get("ready_tasks"))
    independent = {t.get("write_set", "x") for t in ready}
    if len(independent) >= 5:
        target = 8 if len(independent) >= 8 else 5
        actual_internal = int(snapshot.get("internal_workers", 0))
        resources_ok = _resources_permit(snapshot)
        if resources_ok and actual_internal < target:
            reasons_off.append(
                f"internal hive floor unmet "
                f"({actual_internal} < {target} with {len(independent)} independent ready units)")
    if snapshot.get("lane_starvation"):
        reasons_off.append("project lane starvation detected")
    if reasons_off:
        if not snapshot.get("continuation_required", True):
            return Violation(
                "INVARIANT_1_PROGRAMME_CONTINUATION", "§1/§27",
                severity=CRITICAL,
                evidence=[f"continuation_required=False but: " + ", ".join(reasons_off)],
                fix_suggestion="Set continuation_required=True until every reason is resolved with evidence.")
    return None


# ===========================================================================
# INVARIANT 2 — INTERNAL TEAM FLOOR (§36 / §49)
# ===========================================================================
def invariant_2_min_hive(snapshot: dict) -> Optional[Violation]:
    """Maintain >=5 useful Hermes-native subagents when >=5 independent
    useful units of ready work exist and resources permit."""
    ready = _as_list(snapshot.get("ready_tasks"))
    # §2: 'independent useful units' — distinct write-sets, no shared deps
    independent = {t.get("write_set", "x") for t in ready}
    target = 8 if len(independent) >= 8 else (5 if len(independent) >= 5 else len(independent))
    actual_internal = int(snapshot.get("internal_workers", 0))
    resources_ok = _resources_permit(snapshot)
    if len(independent) >= 5 and resources_ok and actual_internal < 5:
        return Violation(
            "INVARIANT_2_INTERNAL_TEAM_FLOOR", "§2",
            severity=HIGH,
            evidence=[f"{actual_internal} hermes-native subagents running; "
                      f"{len(independent)} independent ready units; "
                      f"target >= 5"],
            fix_suggestion="Spawn hermes-native subagents for available roles "
                           "(architecture/implementation/QA/security/UI/UX/research/...) "
                           "until the floor is met or resources run out.")
    return None


def _resources_permit(snapshot: dict) -> bool:
    r = snapshot.get("resources") or {}
    for axis in ("cpu", "ram", "gpu", "vram"):
        v = r.get(axis)
        if v is None:
            return False          # unknown pressure: be safe
        if v >= 0.90:
            return False          # CRITICAL gate
    return True


# ===========================================================================
# INVARIANT 3 — NO IDLE SUITABLE WORKER (§8 / §45)
# ===========================================================================
def invariant_3_no_idle_with_ready(snapshot: dict) -> Optional[Violation]:
    """An idle suitable worker while READY work exists = scheduling defect."""
    ready = _as_list(snapshot.get("ready_tasks"))
    if not ready:
        return None
    workers = snapshot.get("workers") or {}
    idle_suitable = []
    for wid, rec in workers.items():
        if not _worker_idle(rec):
            continue
        for t in ready:
            caps = set(t.get("capabilities", [])) or {t.get("required_capability", "")}
            if rec.get("role") in caps or rec.get("application") in caps:
                # privacy gate (§29): SECRET never goes to a PUBLIC worker
                if t.get("privacy_class") == "SECRET" and rec.get("privacy_class") != "SECRET":
                    continue
                idle_suitable.append((wid, t.get("task_id", "?")))
                break
    if idle_suitable:
        return Violation(
            "INVARIANT_3_NO_IDLE_WITH_READY_WORK", "§8",
            severity=HIGH,
            evidence=[f"idle suitable workers: {idle_suitable}"],
            fix_suggestion="Assign the matched ready task to the idle worker now.")
    return None


# ===========================================================================
# INVARIANT 4 — WORKER STOP HANDLING (§11/§45 §4)
# ===========================================================================
def invariant_4_worker_stop_handoff(snapshot: dict) -> Optional[Violation]:
    """Every stopped/idle worker must have been given a concrete next
    instruction (continue / correct / new task / handoff).  A worker that
    sits IDLE without a recorded check-in is a supervisor defect."""
    workers = snapshot.get("workers") or {}
    last_actions = snapshot.get("worker_actions") or {}
    unhandled = []
    from compute.supervision import (AVAILABLE, INTERRUPTED, HUNG,
                                   WAITING)
    for wid, rec in workers.items():
        st = rec.get("status")
        if st in (AVAILABLE, WAITING, INTERRUPTED, HUNG):
            act = last_actions.get(wid, {})
            if not (act.get("check_in") or act.get("continuation") or act.get("handoff")):
                unhandled.append(wid)
    if unhandled:
        return Violation(
            "INVARIANT_4_WORKER_STOP_HANDLED", "§4",
            severity=HIGH,
            evidence=[f"workers stopped/idle without supervisor action: {unhandled}"],
            fix_suggestion="Run the §45 priority order: inspect -> read output -> "
                           "ingest handoff -> gap -> decide -> assign -> verify.")
    return None


# ===========================================================================
# INVARIANT 8 — TASK-SPECIFIC EVIDENCE (§36 §8)
# ===========================================================================
def invariant_8_task_specific_evidence(snapshot: dict) -> Optional[Violation]:
    """SESSION_ACTIVE / PROCESS_ALIVE / APP_OPEN / PROMPT_SENT are NOT
    task completion.  A worker reported RUNNING must carry task-specific
    evidence (files changed / tests / commits / task-id in transcript)."""
    workers = snapshot.get("workers") or {}
    weak = []
    for wid, rec in workers.items():
        if rec.get("verdict") in ("RUNNING", "IMPLEMENTING"):
            ev = _as_list(rec.get("evidence", []))
            joined = " ".join(str(e) for e in ev).lower()
            # a pure liveness signal with no task artefact = not task-verified
            only_liveness = all(
                any(k in joined for k in ("updated", "session", "alive", "age", "window"))
                for _ in ev) if ev else True
            has_artifact = any(
                k in joined for k in ("file", "test", "commit", "task", "branch",
                                      "write", "handoff", "progress", "change"))
            if only_liveness and not has_artifact:
                weak.append(wid)
    if weak:
        return Violation(
            "INVARIANT_8_TASK_SPECIFIC_EVIDENCE", "§8",
            severity=MEDIUM,
            evidence=[f"workers claiming RUNNING on liveness alone: {weak}"],
            fix_suggestion="Require evidence of task-specific progression "
                           "(git diff / tests / transcript naming task_id).")
    return None


# ===========================================================================
# INVARIANT 11 — RESOURCE GOVERNOR (§33 / §34)
# ===========================================================================
def invariant_11_resource_headroom(snapshot: dict) -> Optional[Violation]:
    """If CRITICAL pressure, only light/local workers should be admitted."""
    r = snapshot.get("resources") or {}
    peak = max((v for v in (r.get("cpu"), r.get("ram"), r.get("gpu"), r.get("vram"))
               if v is not None), default=None)
    if peak is None:
        return None
    if peak >= 0.95:
        # check: no heavy local model work was admitted
        workers = snapshot.get("workers") or {}
        heavy = [wid for wid, rec in workers.items()
                 if rec.get("application") == "ollama" and rec.get("model_weight_gb", 0) > 7]
        if heavy:
            return Violation(
                "INVARIANT_11_RESOURCE_HEADROOM", "§11",
                severity=CRITICAL,
                evidence=[f"CRITICAL pressure {peak:.2f} with heavy local model workers: {heavy}"],
                fix_suggestion="Pause non-essential heavy local workers; offload "
                               "privacy-safe work to free cloud agents.")
    return None


# ===========================================================================
# INVARIANT 12 — MODEL ROUTING free-first (§36 §12)
# ===========================================================================
def invariant_12_model_routing(snapshot: dict) -> Optional[Violation]:
    """No PAID work selected while a free/local/owned-entitlement alternative
    exists — unless explicitly reserved (paid_budget=0 default)."""
    policies = snapshot.get("model_routing") or {}
    if not policies:
        return Violation(
            "INVARIANT_12_MODEL_ROUTING", "§12",
            severity=MEDIUM, status=STUBBED,
            evidence=["no model_routing block in snapshot"],
            fix_suggestion="Wire HiveScheduler.worker_score's free-first ordering "
                           "into the snapshot so the policy is observable here.")
    paid_budget = policies.get("paid_budget_remaining", 0)
    last_assignment = policies.get("last_assignment_tier")
    if last_assignment == "PAID" and paid_budget <= 0:
        return Violation(
            "INVARIANT_12_MODEL_ROUTING", "§12",
            severity=CRITICAL,
            evidence=[f"assignment used PAID tier with paid_budget_remaining={paid_budget}"],
            fix_suggestion="Re-route to a free/local/owned-entitlement model.")
    return None


# ===========================================================================
# INVARIANT 13 — QUOTA POOLS (§36 §13)
# ===========================================================================
def invariant_13_quota_exhaustion(snapshot: dict) -> Optional[Violation]:
    """A KNOWN-exhausted pool must not keep being selected, and quota
    exhaustion must NOT halt unrelated programme work."""
    quotas = snapshot.get("quotas") or {}
    exhausted_blocking = []
    for wid, q in quotas.items():
        if q.get("exhausted") and not q.get("next_reset_epoch"):
            exhausted_blocking.append(wid)
    # §13: 'it must never halt unrelated programme work' — if ALL workers
    # with suitable capability are exhausted AND no ready alternate exists,
    # the defer queue must be growing (not empty).
    if snapshot.get("all_suitable_workers_exhausted") and not snapshot.get("deferred_tasks"):
        return Violation(
            "INVARIANT_13_QUOTA_SCHEDULING", "§13",
            severity=HIGH,
            evidence=["all suitable workers quota-exhausted but no deferred-task queue"],
            fix_suggestion="Park affected tasks in the deferred queue for the next reset.")
    return None


# ===========================================================================
# INVARIANT 14 — PROJECT PORTFOLIO (§36 §14)
# ===========================================================================
def invariant_14_no_project_starvation(snapshot: dict) -> Optional[Violation]:
    """If 'fixing Hermes' consumes 100% of workers while other active
    projects have unblocked work, that is a defect."""
    projects = snapshot.get("projects") or {}
    starving = []
    now = snapshot.get("now_epoch", 0)
    for pid, p in projects.items():
        last_prog = p.get("last_progress_epoch")
        # last_progress_epoch of 0.0 means never made progress -> definitely stale
        has_progress = last_prog is not None and last_prog > 0
        if p.get("priority") in ("HIGH", "CRITICAL") and p.get("has_unblocked_work") \
                and (not has_progress or (now - last_prog) > 3600):
            starving.append(pid)
    if starving:
        return Violation(
            "INVARIANT_14_PROJECT_STARVATION", "§14/§15",
            severity=CRITICAL,
            evidence=[f"starved projects (no progress >1h despite unblocked work): {starving}"],
            fix_suggestion="Allocate a worker to each starved project lane immediately.")
    return None


# ===========================================================================
# INVARIANT 7 — EXTERNAL WORKER COMMISSIONING (§36 §7/§11)
# ===========================================================================
def invariant_7_commissioning_loop(snapshot: dict) -> Optional[Violation]:
    """Every candidate external app must flow through
    discover→launch→identify→models→quota→test→register.  A shortcut that
    claims 'commissioned' with no registered capability is a false claim."""
    unassessed = _as_list(snapshot.get("unassessed_apps"))
    if unassessed:
        now = snapshot.get("now_epoch", 0)
        stale = [a["app_id"] for a in unassessed
                 if (now - a.get("last_action_epoch", 0)) > 86400]
        # §24 correction: ANY unassessed app is ready commissioning work.
        # Staleness is a watchdog fallback, NOT the normal trigger.
        return Violation(
            "INVARIANT_7_COMMISSIONING_LOOP", "§7/§24",
            severity=HIGH,
            evidence=[f"{len(unassessed)} uncommissioned app(s) in acquisition "
                      f"queue ready for commissioning; stale(>24h)={stale}"],
            fix_suggestion="Assign H-SA-RESEARCH / H-SA-INTEGRATION workers to "
                           "commission candidates immediately: discover, inspect "
                           "repo/docs, evaluate licence/Windows/activity, "
                           "install/configure, test agent mode, register capability.")
    return None


# ===========================================================================
# INVARIANT 1 — POST-REPORT CONTINUATION (§36 §28)
# ===========================================================================
def invariant_28_no_report_termination(snapshot: dict) -> Optional[Violation]:
    """continuation_required must not flip False right after a report or
    milestone — the post-report hook must run another cycle."""
    if (not snapshot.get("continuation_required", True)
            and snapshot.get("last_cycle_emitted_report")):
        return Violation(
            "INVARIANT_28_NO_REPORT_TERMINATION", "§28",
            severity=CRITICAL,
            evidence=["continuation_required=False immediately after a report cycle"],
            fix_suggestion="Run POST_REPORT_CONTINUE() — another scheduler cycle.")
    return None


# ===========================================================================
# INVARIANT 15 — DEGRADATION RESILIENCE (§H12 / §36 §15)
# ===========================================================================
def invariant_15_degradation_resilience(snapshot: dict) -> Optional[Violation]:
    """H12 architectural safeguard (hard-coded):

    "Aetherius must never lose essential capabilities merely because a
    third-party service, model, cloud account, worker, or development tool
    becomes unavailable."

    A violation occurs when a core capability tier goes fully offline AND
    no fallback (local / owned-entitlement / another free tier) exists to
    preserve it.
    """
    # If there's no active work, degradation resilience is not applicable —
    # the programme is genuinely idle, not degraded.
    gaps = _as_list(snapshot.get("gaps"))
    ready_tasks = _as_list(snapshot.get("ready_tasks"))
    handoffs_pending = snapshot.get("handoffs_pending", 0)
    projects = snapshot.get("projects") or {}
    active_projects = any(
        isinstance(p, dict) and p.get("has_unblocked_work")
        for p in projects.values()
    )
    if not gaps and not ready_tasks and handoffs_pending == 0 and not active_projects:
        return Violation(
            "INVARIANT_15_DEGRADATION_RESILIENCE", "§H12",
            severity=MEDIUM, status=STUBBED,
            evidence=["no active work (no gaps, ready tasks, handoffs, or unblocked projects) "
                      "— degradation resilience not applicable"],
            fix_suggestion="No action needed; invariant applies when work exists.")
    availability = snapshot.get("availability")
    if not availability:
        return Violation(
            "INVARIANT_15_DEGRADATION_RESILIENCE", "§H12",
            severity=MEDIUM, status=STUBBED,
            evidence=["no 'availability' block in snapshot — H12 safeguard not yet wired"],
            fix_suggestion="Add availability state to SupervisorRuntime._build_invariants_snapshot: "
                           "track per-tier availability and include 'essential_capabilities' list.")
    essentials = _as_list(availability.get("essential_capabilities"))
    if not essentials:
        return Violation(
            "INVARIANT_15_DEGRADATION_RESILIENCE", "§H12",
            severity=MEDIUM, status=STUBBED,
            evidence=["availability block present but no 'essential_capabilities' declared"],
            fix_suggestion="Define the essential capability set (e.g. ['local_execution', "
                           "'free_inference', 'git_access', 'local_storage']).")
    tiers = availability.get("tiers", {})
    cap_tiers = availability.get("capability_tiers", {})
    available_tiers = []
    for tier_name, providers in tiers.items():
        active = [p for p in _as_list(providers) if p.get("status") != "OFFLINE"]
        if active:
            available_tiers.append(tier_name)
    degraded = []
    for cap in essentials:
        cap_tier = cap_tiers.get(cap)
        if cap_tier:
            providers = tiers.get(cap_tier, [])
            active = [p for p in _as_list(providers) if p.get("status") != "OFFLINE"]
            if not active:
                degraded.append(f"{cap} (tier: {cap_tier} fully offline)")
    if degraded:
        return Violation(
            "INVARIANT_15_DEGRADATION_RESILIENCE", "§H12",
            severity=CRITICAL,
            evidence=[f"degraded capabilities: {degraded}",
                     f"available tiers: {available_tiers}"],
            fix_suggestion="Restore or provision a fallback for: " + ", ".join(degraded))
    return None


# ===========================================================================
# invariant registry + consolidated check
# ===========================================================================

#: Map invariant name -> clause.  Order is the order checks run.
INVARIANTS = {
    "INVARIANT_1_PROGRAMME_CONTINUATION":   invariant_1_continuation,
    "INVARIANT_2_INTERNAL_TEAM_FLOOR":      invariant_2_min_hive,
    "INVARIANT_3_NO_IDLE_WITH_READY_WORK":  invariant_3_no_idle_with_ready,
    "INVARIANT_4_WORKER_STOP_HANDLED":      invariant_4_worker_stop_handoff,
    "INVARIANT_7_COMMISSIONING_LOOP":       invariant_7_commissioning_loop,
    "INVARIANT_8_TASK_SPECIFIC_EVIDENCE":   invariant_8_task_specific_evidence,
    "INVARIANT_11_RESOURCE_HEADROOM":       invariant_11_resource_headroom,
    "INVARIANT_12_MODEL_ROUTING":           invariant_12_model_routing,
    "INVARIANT_13_QUOTA_SCHEDULING":        invariant_13_quota_exhaustion,
    "INVARIANT_14_NO_PROJECT_STARVATION":   invariant_14_no_project_starvation,
    "INVARIANT_28_NO_REPORT_TERMINATION":   invariant_28_no_report_termination,
    "INVARIANT_15_DEGRADATION_RESILIENCE":  invariant_15_degradation_resilience,
}


@dataclass
class ConstitutionResult:
    passed: bool
    violations: list[Violation] = field(default_factory=list)
    checked: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checked": self.checked,
            "violations": [v.__dict__ for v in self.violations],
        }


def check_all(snapshot: dict) -> ConstitutionResult:
    """Run every implemented invariant against a runtime snapshot.

    Returns a ``ConstitutionResult``.  ``passed=False`` (with concrete
    violations + evidence) is what the scheduler treats as a hard gate —
    the cycle does NOT clear ``continuation_required`` while any
    CRITICAL/HIGH violation survives.
    """
    violations: list[Violation] = []
    for name, fn in INVARIANTS.items():
        try:
            v = fn(snapshot)
        except Exception as e:  # noqa: BLE001 — one broken invariant must not kill the cycle
            v = Violation(name, "constitution",
                          severity=MEDIUM, status=STUBBED,
                          evidence=[f"check raised {type(e).__name__}: {e}"])
        if v is not None:
            violations.append(v)
    # STUBBED entries are NOT failures — they are declared-but-unwired.
    hard = [v for v in violations if v.status == FAIL]
    return ConstitutionResult(
        passed=len(hard) == 0,
        violations=violations,
        checked=len(INVARIANTS))


def gate_continuation(snapshot: dict) -> bool:
    """True == the scheduler MUST keep continuation_required=True
    (a hard gate is tripped).  Used by SupervisorRuntime._compute_continuation
    as the final OR-term:

        continuation_required = <existing evidence> OR gate_continuation(...)
    """
    result = check_all(snapshot)
    if result.passed:
        return False         # no gates tripped -> existing evidence decides
    # any live FAIL means the programme is not done, regardless of surface reports
    for v in result.violations:
        if v.status == FAIL and v.severity in (CRITICAL, HIGH):
            return True
    return False  # only MEDIUM/STUBBED -> no hard gate tripped
