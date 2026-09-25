"""Change-aware test selection (P21, REQ-p21-test-impact).

Changed files -> dependency graph -> historical failures -> fast
relevant test set, with honest RUN / SKIPPED_BY_PREDICTION states.

Relationship to existing code (no duplicates):
- testmap.py remains the heuristic single-file mapper (changed -> tests
  with confidence). This module composes the PLAN layer that does not
  exist: transitive graph traversal, history signals, mandatory tests,
  deterministic ordered plans with per-test reasons.
- SessionMemory (memory.py) failed[]/tests_run[] and ProblemMemory are
  history SOURCES via the plain-dict HistoricalRecord interface; this
  module stores nothing.
- resultkit.py scorecards record execution OUTCOMES; plan states live
  here. A plan is not a result: RUN != PASSED, skipped != passed.

Permanent rules enforced:
- NOT RUN != PASSED; SKIPPED_BY_PREDICTION is a visible state, never
  converted to pass.
- UNKNOWN IMPACT != IRRELEVANT: changed files unknown to the graph
  conservatively RUN the universe with reason UNKNOWN_IMPACT.
- History is additional evidence, never sole authority: direct impact
  without history still RUNs.
- Mandatory policy > prediction (mandatory list is caller input).
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

RUN = "RUN"
SKIPPED_BY_PREDICTION = "SKIPPED_BY_PREDICTION"

PLAN_STATES = (RUN, SKIPPED_BY_PREDICTION)

# Reasons a human or evaluator can audit.
DIRECT_DEPENDENCY = "DIRECT_DEPENDENCY"
TRANSITIVE_DEPENDENCY = "TRANSITIVE_DEPENDENCY"
HISTORICAL_FAILURE = "HISTORICAL_FAILURE"
HISTORICALLY_FLAKY = "HISTORICALLY_FLAKY"
MANDATORY = "MANDATORY"
SELF_TEST = "SELF_TEST"
NAME_MATCH = "NAME_MATCH"
UNKNOWN_IMPACT = "UNKNOWN_IMPACT"
NO_RELEVANT_PATH = "NO_RELEVANT_PATH"


class ImpactError(Exception):
    """Malformed plan input."""


@dataclass
class TestDecision:
    test_id: str
    state: str
    reasons: list[str] = field(default_factory=list)
    related_paths: list[str] = field(default_factory=list)


@dataclass
class TestImpactPlan:
    decisions: list[TestDecision] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def selected(self) -> list[str]:
        return sorted(d.test_id for d in self.decisions if d.state == RUN)

    def skipped(self) -> list[str]:
        return sorted(d.test_id for d in self.decisions if d.state == SKIPPED_BY_PREDICTION)


def normalize_changed(files: list[str]) -> list[str]:
    """Project-relative paths only. No absolute paths, no escapes."""
    clean: list[str] = []
    for raw in files:
        if not isinstance(raw, str) or not raw.strip():
            raise ImpactError("changed files must be non-empty strings")
        candidate = raw.strip().replace("\\", "/")
        if candidate.startswith("/") or ".." in candidate.split("/"):
            raise ImpactError(f"changed file escapes project boundary: {raw}")
        if candidate not in clean:
            clean.append(candidate)
    return sorted(clean)


def validate_graph(graph: dict[str, list[str]]) -> None:
    if not isinstance(graph, dict):
        raise ImpactError("dependency graph must be an object")
    for node, deps in graph.items():
        if not isinstance(node, str) or not node.strip():
            raise ImpactError("graph nodes must be non-empty strings")
        if not isinstance(deps, list) or any(not isinstance(d, str) or not d.strip() for d in deps):
            raise ImpactError(f"graph edges for {node} must be non-empty string lists")


def validate_history(history: dict[str, dict]) -> None:
    if not isinstance(history, dict):
        raise ImpactError("history must be an object")
    for test_id, record in history.items():
        if not isinstance(record, dict):
            raise ImpactError(f"history for {test_id} must be an object")
        for key in ("failures", "runs"):
            value = record.get(key, 0)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ImpactError(f"history {test_id}.{key} must be a non-negative integer")


def _stem(path: str) -> str:
    return Path(path).stem


def _is_test_file(path: str) -> bool:
    name = Path(path).name
    return name.startswith("test_") or name.endswith("_test.py")


def build_import_graph(root: str | Path, max_files: int = 5000) -> dict[str, list[str]]:
    """Bounded deterministic import graph over a repo root.

    Nodes are project-relative posix paths; edges point from importer to
    imported local modules (best-effort stem match). stdlib/third-party
    imports are ignored. Cycles are the caller's concern (traversal
    dedupes); unparseable files contribute no edges, never errors.
    """
    base = Path(root)
    if not base.is_dir():
        raise ImpactError(f"graph root is not a directory: {root}")
    graph: dict[str, list[str]] = {}
    try:
        candidates = sorted(
            str(p.relative_to(base)).replace("\\", "/")
            for p in base.rglob("*.py")
            if ".git" not in p.parts and "node_modules" not in p.parts
            and "__pycache__" not in p.parts and ".venv" not in p.parts
        )
    except Exception as exc:
        raise ImpactError(f"cannot enumerate {root}: {exc}") from None
    stems: dict[str, str] = {}
    for rel in candidates[:max_files]:
        stems.setdefault(_stem(rel), rel)
    for rel in candidates[:max_files]:
        deps: set[str] = set()
        try:
            tree = ast.parse((base / rel).read_text(encoding="utf-8"))
        except Exception:
            graph[rel] = []
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    target = stems.get(alias.name.split(".")[0], "")
                    if target and target != rel:
                        deps.add(target)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    target = stems.get(node.module.split(".")[0], "")
                    if target and target != rel:
                        deps.add(target)
        graph[rel] = sorted(deps)
    return graph


def _reverse_graph(graph: dict[str, list[str]]) -> dict[str, set[str]]:
    """Who imports whom: dependent -> set of dependencies inverted."""
    reverse: dict[str, set[str]] = {}
    for node, deps in graph.items():
        reverse.setdefault(node, set())
        for dep in deps:
            reverse.setdefault(dep, set()).add(node)
    return reverse


def _transitive_dependents(reverse: dict[str, set[str]], start: str) -> dict[str, list[str]]:
    """BFS over dependents with visited dedup; returns node -> path taken."""
    found: dict[str, list[str]] = {}
    queue: list[tuple[str, list[str]]] = [(start, [start])]
    seen = {start}
    while queue:
        node, path = queue.pop(0)
        for dependent in sorted(reverse.get(node, ())):
            if dependent in seen:
                continue
            seen.add(dependent)
            found[dependent] = path + [dependent]
            queue.append((dependent, path + [dependent]))
    return found


def predict(
    changed_files: list[str],
    universe: list[str],
    graph: dict[str, list[str]] | None = None,
    history: dict[str, dict] | None = None,
    mandatory: list[str] | None = None,
) -> TestImpactPlan:
    """Deterministic test-impact plan.

    changed_files: explicit project-relative paths (validated).
    universe: explicit test-id list (the plan never invents tests).
    graph: module -> [modules it imports]; absent = no traversal evidence.
    history: test_id -> {failures, runs}; absent = NO_HISTORY (documented).
    mandatory: explicit always-run list (policy > prediction).
    """
    changed = normalize_changed(changed_files)
    tests = sorted(set(universe))
    for test_id in tests:
        if not test_id.strip():
            raise ImpactError("universe test ids must be non-empty strings")
    graph = dict(graph or {})
    validate_graph(graph)
    history = dict(history or {})
    validate_history(history)
    required = sorted(set(mandatory or []))

    reverse = _reverse_graph(graph)
    decisions: dict[str, TestDecision] = {
        test_id: TestDecision(test_id=test_id, state=SKIPPED_BY_PREDICTION,
                              reasons=[NO_RELEVANT_PATH], related_paths=[])
        for test_id in tests
    }

    def mark_run(test_id: str, reason: str, paths: list[str]) -> None:
        decision = decisions.get(test_id)
        if decision is None:
            return
        decision.state = RUN
        if reason not in decision.reasons:
            # Replace the default skip reason on first RUN marking.
            if decision.reasons == [NO_RELEVANT_PATH]:
                decision.reasons = [reason]
            else:
                decision.reasons.append(reason)
        for path in paths:
            if path not in decision.related_paths:
                decision.related_paths.append(path)
        decision.related_paths.sort()

    unknown_impact = [c for c in changed if c not in graph and c not in tests]
    notes: list[str] = []
    unknown_code = [c for c in unknown_impact if c.endswith(".py")]
    unknown_other = [c for c in unknown_impact if not c.endswith(".py")]
    if unknown_other:
        # Non-code files carry no import evidence; noted, never force runs.
        notes.append(f"no code impact assessable for: {', '.join(sorted(unknown_other))}")
    if unknown_code and tests:
        # Conservative: unknown code files implicate the whole universe.
        for test_id in tests:
            mark_run(test_id, UNKNOWN_IMPACT, sorted(unknown_code))
    for changed_path in changed:
        if changed_path in decisions:
            mark_run(changed_path, SELF_TEST, [changed_path])
        dependents = _transitive_dependents(reverse, changed_path)
        for dependent, path in dependents.items():
            if dependent in decisions:
                reason = DIRECT_DEPENDENCY if len(path) == 2 else TRANSITIVE_DEPENDENCY
                mark_run(dependent, reason, [changed_path])
        # Name-match heuristic (weak, recorded as such): test_<stem>.
        stem = _stem(changed_path)
        for test_id in tests:
            if _stem(test_id) == f"test_{stem}":
                mark_run(test_id, NAME_MATCH, [changed_path])
    # History is additional evidence, never sole authority.
    for test_id, record in history.items():
        failures = record.get("failures", 0)
        runs = record.get("runs", 0)
        decision = decisions.get(test_id)
        if decision is None:
            continue
        if failures > 0 and decision.state == RUN:
            if HISTORICAL_FAILURE not in decision.reasons:
                decision.reasons.append(HISTORICAL_FAILURE)
        # Flakiness is metadata, not authority: recorded, never forces runs.
        if runs > 0 and 0 < failures < runs and HISTORICALLY_FLAKY not in decision.reasons:
            decision.reasons.append(HISTORICALLY_FLAKY)
    for test_id in required:
        if test_id in decisions:
            mark_run(test_id, MANDATORY, [])

    ordered = [decisions[test_id] for test_id in tests]
    return TestImpactPlan(decisions=ordered, notes=sorted(notes))
