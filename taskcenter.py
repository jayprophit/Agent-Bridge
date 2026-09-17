"""TaskCenter MVP (Phase 1 acceptance).

Owner-visible hierarchical task system:

- nested parent / child / grandchild tasks (arbitrary depth)
- total X / Y progress + percentages (per node roll-up + global)
- expand parent tasks (tree view)
- Copy task / Copy branch (deep copy with new IDs, provenance preserved)
- Edit a task (amendments preserved; old verified history never lost)
- View Sources / View Evidence / View History
- selectable text (render_html uses plain text + user-select:text, no canvas)
- current status, actual assigned model/agent attribution
- direct vs Agent-Bridge-delegated execution mode
- amendments without losing old verified history
- persistence across restart (JSON file, atomic write)
- plan versions, last verified checkpoint, next action preserved

Evidence-first: sources/evidence/history are append-only lists.
Edit never deletes verified entries; it appends an amendment record and
bumps plan_version.
"""
from __future__ import annotations

import copy
import html
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

COMPLETE_STATES = ("COMPLETED", "VERIFIED_COMPLETE")
EXECUTION_MODES = ("DIRECT", "DELEGATED")


def _now() -> float:
    return time.time()


def _new_id(prefix: str) -> str:
    return f"{prefix}-" + uuid.uuid4().hex[:8]


@dataclass
class TaskCenterNode:
    task_id: str = ""
    parent_id: str = ""
    objective: str = ""
    status: str = "PLANNED"
    # attribution
    supervisor: str = ""
    assigned_agent: str = ""
    assigned_model: str = ""
    provider: str = ""
    execution_mode: str = "DIRECT"  # DIRECT | DELEGATED
    # progress
    progress_pct: float = 0.0  # leaf progress; branch progress is rolled up
    # content refs (append-only)
    sources: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    history: list[dict[str, Any]] = field(default_factory=list)
    amendments: list[dict[str, Any]] = field(default_factory=list)
    children: list[str] = field(default_factory=list)
    # planning / recovery
    plan_version: int = 1
    last_checkpoint: str = ""
    next_action: str = ""
    # adaptive-loop state (§14: PLAN VERSION / CURRENT STAGE / CURRENT
    # ACTION / LAST RESULT / VERIFICATION / LAST RE-EVALUATION /
    # ADAPTATION / NEXT ACTION). Display only; enforcement truth lives in
    # execution_contract.py.
    current_stage: str = "RECEIVED"
    current_action: str = ""
    last_result: str = ""
    verification: str = ""
    last_reevaluation: str = ""
    created_at: float = field(default_factory=_now)
    updated_at: float = field(default_factory=_now)
    # problem / workaround links + resource summary
    problems: list[str] = field(default_factory=list)
    resources: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TaskCenter:
    """Hierarchical task store with progress roll-up and file persistence."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else None
        self.tasks: dict[str, TaskCenterNode] = {}
        # problem / workaround history (preserved across restart)
        self.problems: dict[str, dict[str, Any]] = {}
        # adaptation / plan-revision log
        self.adaptations: list[dict[str, Any]] = []
        if self.path is not None and self.path.exists():
            self.load()

    # -- CRUD ----------------------------------------------------------
    def add(self, objective: str, parent_id: str = "", status: str = "PLANNED",
            supervisor: str = "", assigned_agent: str = "",
            assigned_model: str = "", provider: str = "",
            execution_mode: str = "DIRECT",
            sources: list[str] | None = None,
            next_action: str = "") -> TaskCenterNode:
        if execution_mode not in EXECUTION_MODES:
            raise ValueError(f"bad execution_mode {execution_mode!r}")
        node = TaskCenterNode(
            task_id=_new_id("t"),
            parent_id=parent_id,
            objective=objective,
            status=status,
            supervisor=supervisor,
            assigned_agent=assigned_agent,
            assigned_model=assigned_model,
            provider=provider,
            execution_mode=execution_mode,
            sources=list(sources or []),
            next_action=next_action,
        )
        node.history.append({"ts": _now(), "event": "created",
                             "status": status, "objective": objective,
                             "by": supervisor or assigned_agent})
        self.tasks[node.task_id] = node
        if parent_id:
            parent = self.tasks.get(parent_id)
            if parent is None:
                raise KeyError(f"parent {parent_id!r} not found")
            parent.children.append(node.task_id)
            parent.updated_at = _now()
        self._autosave()
        return node

    def get(self, task_id: str) -> TaskCenterNode:
        try:
            return self.tasks[task_id]
        except KeyError:
            raise KeyError(f"task {task_id!r} not found")

    def edit(self, task_id: str, objective: str | None = None,
             status: str | None = None, next_action: str | None = None,
             assigned_model: str | None = None,
             assigned_agent: str | None = None,
             execution_mode: str | None = None,
             by: str = "", reason: str = "") -> TaskCenterNode:
        """Amend a task. Old values are preserved in amendments + history.

        Verified evidence/sources are never removed by an edit.
        """
        node = self.get(task_id)
        changes: dict[str, Any] = {}
        if objective is not None and objective != node.objective:
            changes["objective"] = {"from": node.objective, "to": objective}
            node.objective = objective
        if status is not None and status != node.status:
            changes["status"] = {"from": node.status, "to": status}
            node.status = status
        if next_action is not None and next_action != node.next_action:
            changes["next_action"] = {"from": node.next_action, "to": next_action}
            node.next_action = next_action
        if assigned_model is not None and assigned_model != node.assigned_model:
            changes["assigned_model"] = {"from": node.assigned_model,
                                         "to": assigned_model}
            node.assigned_model = assigned_model
        if assigned_agent is not None and assigned_agent != node.assigned_agent:
            changes["assigned_agent"] = {"from": node.assigned_agent,
                                         "to": assigned_agent}
            node.assigned_agent = assigned_agent
        if execution_mode is not None:
            if execution_mode not in EXECUTION_MODES:
                raise ValueError(f"bad execution_mode {execution_mode!r}")
            if execution_mode != node.execution_mode:
                changes["execution_mode"] = {"from": node.execution_mode,
                                             "to": execution_mode}
                node.execution_mode = execution_mode
        if changes:
            node.plan_version += 1
            node.amendments.append({"ts": _now(), "by": by, "reason": reason,
                                    "changes": changes,
                                    "plan_version": node.plan_version})
            node.history.append({"ts": _now(), "event": "amended", "by": by,
                                 "reason": reason, "changes": changes,
                                 "plan_version": node.plan_version})
            node.updated_at = _now()
            self.adaptations.append({"ts": _now(), "task_id": task_id,
                                     "by": by, "reason": reason,
                                     "plan_version": node.plan_version})
            self._autosave()
        return node

    # -- Copy ----------------------------------------------------------
    def copy_task(self, task_id: str, new_parent_id: str = "",
                  by: str = "") -> TaskCenterNode:
        """Copy a single task (no children). Provenance preserved."""
        src = self.get(task_id)
        node = copy.deepcopy(src)
        node.task_id = _new_id("t")
        node.parent_id = new_parent_id
        node.children = []
        node.plan_version = 1
        node.history = list(src.history) + [
            {"ts": _now(), "event": "copied_from", "from": task_id, "by": by}]
        node.amendments = list(src.amendments)
        node.created_at = _now()
        node.updated_at = _now()
        self.tasks[node.task_id] = node
        if new_parent_id:
            self.tasks[new_parent_id].children.append(node.task_id)
        self._autosave()
        return node

    def copy_branch(self, task_id: str, new_parent_id: str = "",
                    by: str = "") -> TaskCenterNode:
        """Deep-copy a task and all descendants. Returns the new root."""
        src = self.get(task_id)
        id_map: dict[str, str] = {}

        def _clone(old_id: str, new_parent: str) -> str:
            old = self.get(old_id)
            new = copy.deepcopy(old)
            new_id = _new_id("t")
            id_map[old_id] = new_id
            new.task_id = new_id
            new.parent_id = new_parent
            new.children = []
            new.plan_version = 1
            new.history = list(old.history) + [
                {"ts": _now(), "event": "branch_copied_from",
                 "from": old_id, "by": by}]
            new.created_at = _now()
            new.updated_at = _now()
            self.tasks[new_id] = new
            for child_id in old.children:
                new_child = _clone(child_id, new_id)
                new.children.append(new_child)
            return new_id

        new_root_id = _clone(task_id, new_parent_id)
        _ = src  # keep reference for clarity
        if new_parent_id:
            self.tasks[new_parent_id].children.append(new_root_id)
        self._autosave()
        return self.tasks[new_root_id]

    # -- Views ---------------------------------------------------------
    def view_sources(self, task_id: str) -> list[str]:
        return list(self.get(task_id).sources)

    def view_evidence(self, task_id: str) -> list[str]:
        return list(self.get(task_id).evidence)

    def view_history(self, task_id: str) -> list[dict[str, Any]]:
        return list(self.get(task_id).history)

    def record_source(self, task_id: str, source: str) -> None:
        node = self.get(task_id)
        if source not in node.sources:
            node.sources.append(source)
            node.history.append({"ts": _now(), "event": "source_added",
                                 "source": source})
            node.updated_at = _now()
            self._autosave()

    def record_evidence(self, task_id: str, evidence: str) -> None:
        node = self.get(task_id)
        if evidence not in node.evidence:
            node.evidence.append(evidence)
            node.history.append({"ts": _now(), "event": "evidence_added",
                                 "evidence": evidence})
            node.updated_at = _now()
            self._autosave()

    def set_loop_state(self, task_id: str, stage: str = "",
                       action: str = "", result: str = "",
                       verification: str = "", reevaluation: str = "",
                       next_action: str = "") -> TaskCenterNode:
        """Record adaptive-loop display state. Append-only history."""
        node = self.get(task_id)
        if stage:
            node.current_stage = stage
        if action:
            node.current_action = action
        if result:
            node.last_result = result[:500]
        if verification:
            node.verification = verification
        if reevaluation:
            node.last_reevaluation = reevaluation[:500]
        if next_action:
            node.next_action = next_action
        node.history.append({"ts": _now(), "event": "loop_state",
                             "stage": node.current_stage,
                             "action": node.current_action,
                             "verification": node.verification,
                             "reevaluation": node.last_reevaluation})
        node.updated_at = _now()
        self._autosave()
        return node

    def record_problem(self, problem: dict[str, Any]) -> str:
        pid = problem.get("problem_id") or _new_id("prob")
        problem = dict(problem)
        problem["problem_id"] = pid
        problem.setdefault("ts", _now())
        self.problems[pid] = problem
        task_id = problem.get("task_id", "")
        if task_id and task_id in self.tasks:
            node = self.tasks[task_id]
            if pid not in node.problems:
                node.problems.append(pid)
            node.history.append({"ts": _now(), "event": "problem_linked",
                                 "problem_id": pid})
        self._autosave()
        return pid

    def set_status(self, task_id: str, status: str, by: str = "",
                   checkpoint: str = "", next_action: str = "") -> TaskCenterNode:
        node = self.get(task_id)
        old = node.status
        node.status = status
        if checkpoint:
            node.last_checkpoint = checkpoint
        if next_action:
            node.next_action = next_action
        if status in COMPLETE_STATES and node.progress_pct < 100.0:
            node.progress_pct = 100.0
        if status not in COMPLETE_STATES and old in COMPLETE_STATES:
            node.progress_pct = min(node.progress_pct, 99.0)
        node.history.append({"ts": _now(), "event": "status",
                             "from": old, "to": status, "by": by,
                             "checkpoint": checkpoint})
        node.updated_at = _now()
        self._autosave()
        return node

    def set_leaf_progress(self, task_id: str, pct: float) -> TaskCenterNode:
        node = self.get(task_id)
        if node.children:
            raise ValueError("progress is rolled up for branch nodes; "
                             "set leaf progress only")
        node.progress_pct = max(0.0, min(100.0, float(pct)))
        node.history.append({"ts": _now(), "event": "progress",
                             "pct": node.progress_pct})
        node.updated_at = _now()
        self._autosave()
        return node

    # -- Progress ------------------------------------------------------
    def _subtree_ids(self, task_id: str) -> list[str]:
        out = [task_id]
        for child in self.get(task_id).children:
            out.extend(self._subtree_ids(child))
        return out

    def _leaf_ids(self, task_id: str) -> list[str]:
        node = self.get(task_id)
        if not node.children:
            return [task_id]
        out: list[str] = []
        for child in node.children:
            out.extend(self._leaf_ids(child))
        return out

    def _node_pct(self, task_id: str) -> float:
        node = self.get(task_id)
        if not node.children:
            if node.status in COMPLETE_STATES:
                return 100.0
            return node.progress_pct
        leaves = self._leaf_ids(task_id)
        if not leaves:
            return 0.0
        return round(sum(self._node_pct(l) for l in leaves) / len(leaves), 1)

    def progress(self, task_id: str | None = None) -> dict[str, Any]:
        """X/Y completion + percentage.

        Leaf X/Y (done/total/pct): completed leaves (COMPLETED /
        VERIFIED_COMPLETE) over total leaves. Branch-internal completion is
        derived from leaves so parent/child/grandchild roll-up is consistent.
        Node counts (nodes_done/nodes_total) cover every task including
        parents, so no work is hidden. per_node_pct holds the rolled-up
        percentage per branch root (leaf average; 100 for completed leaves).
        """
        if task_id is not None:
            leaves = self._leaf_ids(task_id)
            scope = self._subtree_ids(task_id)
        else:
            # global: leaves across all roots
            roots = [t.task_id for t in self.tasks.values() if not t.parent_id]
            leaves = []
            scope = []
            for r in roots:
                leaves.extend(self._leaf_ids(r))
                scope.extend(self._subtree_ids(r))
        done = sum(1 for l in leaves
                   if self.tasks[l].status in COMPLETE_STATES)
        total = len(leaves)
        pct = round(100.0 * done / total, 1) if total else 0.0
        nodes_done = sum(1 for t in scope
                         if self.tasks[t].status in COMPLETE_STATES)
        per_node = ({task_id: self._node_pct(task_id)} if task_id is not None
                    else {r: self._node_pct(r)
                          for r in [t.task_id for t in self.tasks.values()
                                    if not t.parent_id]})
        return {"done": done, "total": total, "pct": pct,
                "nodes_done": nodes_done, "nodes_total": len(scope),
                "per_node_pct": per_node}

    def expand(self, task_id: str) -> dict[str, Any]:
        """Nested expandable tree for one task (children recursively)."""
        node = self.get(task_id)
        return {
            "task_id": node.task_id,
            "objective": node.objective,
            "status": node.status,
            "pct": self._node_pct(task_id),
            "supervisor": node.supervisor,
            "assigned_agent": node.assigned_agent,
            "assigned_model": node.assigned_model,
            "provider": node.provider,
            "execution_mode": node.execution_mode,
            "plan_version": node.plan_version,
            "last_checkpoint": node.last_checkpoint,
            "next_action": node.next_action,
            "current_stage": node.current_stage,
            "current_action": node.current_action,
            "last_result": node.last_result,
            "verification": node.verification,
            "last_reevaluation": node.last_reevaluation,
            "adaptations": [a for a in node.amendments],
            "sources": list(node.sources),
            "evidence": list(node.evidence),
            "problems": list(node.problems),
            "resources": dict(node.resources),
            "children": [self.expand(c) for c in node.children],
        }

    def tree(self) -> list[dict[str, Any]]:
        return [self.expand(t.task_id) for t in self.tasks.values()
                if not t.parent_id]

    # -- Selectable HTML rendering -------------------------------------
    def render_html(self, task_id: str | None = None) -> str:
        """Selectable, expandable HTML. Plain text, user-select:text, no canvas."""
        roots = ([self.expand(task_id)] if task_id is not None else self.tree())
        prog = self.progress(task_id)
        parts = [
            "<div class='taskcenter' style='user-select:text;"
            "-webkit-user-select:text;font-family:monospace'>",
            f"<div>Progress: {prog['done']}/{prog['total']} "
            f"({prog['pct']}%)</div>",
        ]
        def _node(h: dict[str, Any], depth: int) -> None:
            title = (f"{h['task_id']} [{h['status']}] {h['pct']}% "
                     f"model={h['assigned_model'] or '?'} "
                     f"agent={h['assigned_agent'] or '?'} "
                     f"mode={h['execution_mode']}")
            parts.append("<details open>" if depth == 0 else "<details>")
            parts.append(f"<summary>{html.escape(title)}<br>"
                         f"{html.escape(h['objective'])}</summary>")
            parts.append(
                f"<div>supervisor={html.escape(h['supervisor'] or '-')} "
                f"provider={html.escape(h['provider'] or '-')} "
                f"plan_v={h['plan_version']} "
                f"stage={html.escape(h.get('current_stage', '') or '-')} "
                f"action={html.escape(h.get('current_action', '') or '-')} "
                f"verification={html.escape(h.get('verification', '') or '-')} "
                f"reeval={html.escape((h.get('last_reevaluation', '') or '-')[:120])} "
                f"checkpoint={html.escape(h['last_checkpoint'] or '-')} "
                f"next={html.escape(h['next_action'] or '-')}</div>")
            if h.get("last_result"):
                parts.append(f"<div>last result: "
                             f"{html.escape(h['last_result'][:300])}</div>")
            if h["sources"]:
                parts.append("<div>Sources:<ul>" + "".join(
                    f"<li>{html.escape(s)}</li>" for s in h["sources"]) + "</ul></div>")
            if h["evidence"]:
                parts.append("<div>Evidence:<ul>" + "".join(
                    f"<li>{html.escape(e)}</li>" for e in h["evidence"]) + "</ul></div>")
            for child in h["children"]:
                _node(child, depth + 1)
            parts.append("</details>")
        for root in roots:
            _node(root, 0)
        parts.append("</div>")
        return "\n".join(parts)

    # -- Persistence ---------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "tasks": {tid: n.to_dict() for tid, n in self.tasks.items()},
            "problems": self.problems,
            "adaptations": self.adaptations,
        }

    def save(self) -> str:
        if self.path is None:
            return ""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=1), encoding="utf-8")
        tmp.replace(self.path)  # atomic on same filesystem
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
            return False  # never reset on corrupt read; caller keeps memory
        tasks = {}
        for tid, td in (data.get("tasks") or {}).items():
            try:
                tasks[tid] = TaskCenterNode(**td)
            except TypeError:
                continue
        # Only replace in-memory state after a successful full parse.
        # A 504 / partial write / provider failure must not wipe the graph.
        self.tasks = tasks
        self.problems = dict(data.get("problems") or {})
        self.adaptations = list(data.get("adaptations") or [])
        return True
