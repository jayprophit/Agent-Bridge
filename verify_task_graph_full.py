#!/usr/bin/env python3
"""Section 20: full verification of all task-graph integration records.

Validates every task (not a sample): schema, duplicate TASK_IDs, dependency
references, cycles, orphans, TASK_ID consistency with the Pass-1 log, and
full Merkle integrity via AdaptiveTaskGraph.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import task_dag

from output_locations import area as _area, assert_not_desktop as _guard

BASE = _area("CONVERSATION_ANALYSIS")
_guard(BASE)  # programme outputs must not target the Desktop
NOW = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
REQ = {"task_id": str, "parent_task": str, "objective": str,
       "requirements": list, "status": str}
VALID_STATUS = {s.value for s in task_dag.TaskStatus}

tg = json.load(open(BASE / "TASK_GRAPH_INTEGRATION.json", encoding="utf-8"))
tasks = tg["tasks"]
issues = []

# 1. Schema.
for t in tasks:
    for k, typ in REQ.items():
        if k not in t:
            issues.append(f"{t.get('task_id', '?')}: missing key {k}")
        elif not isinstance(t[k], typ):
            issues.append(f"{t.get('task_id', '?')}: {k} wrong type")
    if t.get("status") not in VALID_STATUS:
        issues.append(f"{t.get('task_id', '?')}: bad status {t.get('status')}")
    if not t.get("task_id"):
        issues.append("empty task_id")
    if not t.get("requirements"):
        issues.append(f"{t.get('task_id', '?')}: empty requirements")

# 2. Duplicate IDs.
seen, dups = set(), set()
for t in tasks:
    if t["task_id"] in seen:
        dups.add(t["task_id"])
    seen.add(t["task_id"])
if dups:
    issues.append(f"duplicate TASK_IDs: {sorted(dups)}")

# 3. Dependency references (parent_task must exist unless root).
by_id = {t["task_id"]: t for t in tasks}
orphans = [t["task_id"] for t in tasks
           if t["parent_task"] and t["parent_task"] not in by_id]
if orphans:
    issues.append(f"orphans (missing parent): {orphans[:10]}")

# 4. Cycle analysis over parent edges.
def has_cycle():
    state = {}

    def visit(nid, stack):
        state[nid] = 1
        parent = by_id[nid]["parent_task"]
        if parent:
            if parent not in by_id:
                return False
            if state.get(parent) == 1:
                return True
            if state.get(parent) is None and visit(parent, stack):
                return True
        state[nid] = 2
        return False

    return any(state.get(t["task_id"]) is None and visit(t["task_id"], [])
               for t in tasks)

cyclic = has_cycle()
if cyclic:
    issues.append("parent cycle detected")

# 5. TASK_ID consistency with Pass-1 log.
log = json.load(open(BASE / "pass_1_fragment_classification" /
                     "UNKNOWN_REQUIREMENT_RECONCILIATION_LOG.json", encoding="utf-8"))["records"]
log_task_ids = {r["TASK_ID"] for r in log if r.get("TASK_ID")}
file_child_ids = {t["task_id"] for t in tasks if t["parent_task"]}
if file_child_ids - log_task_ids:
    issues.append(f"task file IDs absent from Pass-1 log: {sorted(file_child_ids - log_task_ids)[:5]}")
coverage = len(file_child_ids & log_task_ids)

# 6. Full Merkle load (ALL tasks, not a sample).
g = task_dag.AdaptiveTaskGraph()
roots = sorted(t["task_id"] for t in tasks if not t["parent_task"])
for tid in roots:
    t = by_id[tid]
    g.add_task(task_dag.TaskRecord(task_id=t["task_id"], parent_task="",
                                   objective=t["objective"][:200],
                                   requirements=t["requirements"],
                                   status=task_dag.TaskStatus.PLANNED))
for t in tasks:
    if t["parent_task"]:
        g.add_task(task_dag.TaskRecord(task_id=t["task_id"], parent_task=t["parent_task"],
                                       objective=t["objective"][:200],
                                       requirements=t["requirements"],
                                       status=task_dag.TaskStatus.PLANNED))
merkle = g.merkle_dag.verify_integrity()
if not merkle["ok"]:
    issues.append(f"merkle integrity FAILED: {merkle['issues'][:5]}")

report = {"generated_at": NOW, "task_count": len(tasks),
          "roots": len(roots), "duplicates": sorted(dups),
          "orphans": orphans, "cycle": cyclic,
          "pass1_task_id_coverage": f"{coverage}/{len(file_child_ids)}",
          "merkle": {"ok": merkle["ok"], "global_root": merkle["global_root"][:16] + "...",
                     "records": len(g.merkle_dag.records)},
          "issues": issues, "verdict": "PASS" if not issues else "FAIL"}
json.dump(report, open(BASE / "TASK_GRAPH_FULL_VERIFICATION.json", "w", encoding="utf-8"), indent=1)
print(f"tasks={len(tasks)} roots={len(roots)} dups={len(dups)} orphans={len(orphans)} "
      f"cycle={cyclic} coverage={coverage}/{len(file_child_ids)} merkle_ok={merkle['ok']}")
print("VERDICT:", report["verdict"])
for i in issues[:10]:
    print("  ISSUE:", i)
