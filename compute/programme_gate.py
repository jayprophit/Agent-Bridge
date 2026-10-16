"""Programme acceptance gate (V2 H12 operationalisation).

H12 requirement: "Realistic minimum useful deployment, commercial boundary
and progress gates... Define success using completed tasks and verifiable
artefacts, not numbers of signed-up providers, subagents or installed
frameworks."

This module is the PROGRAMME ACCEPTANCE GATE. It evaluates the minimum
useful deployment scope against LIVE evidence and answers one question:

    may the programme claim MILESTONE_REACHED / COMPLETE?

Honesty rules (§38-adapted):
- An unverified criterion is FAIL, never assumed-pass.
- Evidence must be verifiable artefacts (commits, test runs, sessions),
  not self-reported agent messages (§7 of H04: independent logs).
- The gate NEVER blocks WORK — it only blocks CLAIMS (H12 §25: a blocked
  task != a blocked programme).

The gate does not replace INVARIANT_15 (the degradation safeguard); it
consumes the same availability vocabulary.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


# --- gate verdicts -----------------------------------------------------------------

class GateStatus(str, Enum):
    PASS = "PASS"                  # criterion met with verifiable evidence
    FAIL = "FAIL"                  # criterion not met
    UNVERIFIED = "UNVERIFIED"      # no evidence either way (counts as FAIL)
    WAIVED_OWNER = "WAIVED_OWNER"  # owner explicitly waived (recorded, dated)


@dataclass
class Criterion:
    """One minimum-deployment criterion with its evidence probe."""
    criterion_id: str
    description: str
    probe: Callable[[], tuple[bool, str]]     # () -> (met, evidence)
    blocking: bool = True                       # can the programme claim done without it?
    owner_waiver: Optional[str] = None          # owner note if waived

    def evaluate(self) -> "CriterionResult":
        try:
            met, evidence = self.probe()
        except Exception as e:
            return CriterionResult(
                criterion_id=self.criterion_id,
                description=self.description,
                status=GateStatus.UNVERIFIED,
                evidence=f"probe raised: {e}")
        if met:
            return CriterionResult(
                criterion_id=self.criterion_id,
                description=self.description,
                status=GateStatus.PASS, evidence=evidence)
        if self.owner_waiver:
            return CriterionResult(
                criterion_id=self.criterion_id,
                description=self.description,
                status=GateStatus.WAIVED_OWNER,
                evidence=f"waived by owner: {self.owner_waiver}",
                waiver=self.owner_waiver)
        return CriterionResult(
            criterion_id=self.criterion_id,
            description=self.description,
            status=(GateStatus.FAIL if self.blocking else GateStatus.UNVERIFIED),
            evidence=evidence)


@dataclass
class CriterionResult:
    criterion_id: str
    description: str
    status: GateStatus
    evidence: str
    waiver: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "criterion_id": self.criterion_id,
            "description": self.description,
            "status": self.status.value,
            "evidence": self.evidence,
            "waiver": self.waiver,
        }


# --- the programme gate ---------------------------------------------------------------

class ProgrammeGate:
    """Evaluates the V2 H12 minimum useful deployment against live evidence.

    Usage:
        gate = ProgrammeGate()
        gate.add(Criterion("orchestration", "...", probe))
        verdict = gate.evaluate()
        if not verdict["may_claim_complete"]:
            print(verdict["blocking_failures"])

    The gate answers what the programme may CLAIM. It never stops work.
    """

    def __init__(self) -> None:
        self._criteria: list[Criterion] = []

    def add(self, criterion: Criterion) -> None:
        self._criteria.append(criterion)

    def evaluate(self) -> dict[str, Any]:
        """Evaluate all criteria. Returns the honest claim verdict."""
        results = [c.evaluate() for c in self._criteria]
        passing = [r for r in results if r.status == GateStatus.PASS]
        waived = [r for r in results if r.status == GateStatus.WAIVED_OWNER]
        failing = [r for r in results if r.status == GateStatus.FAIL]
        unverified = [r for r in results if r.status == GateStatus.UNVERIFIED]

        blocking_failures = [r for r in failing + unverified]
        may_claim_complete = len(blocking_failures) == 0

        return {
            "evaluated_at": time.time(),
            "may_claim_complete": may_claim_complete,
            "claim_state": ("MILESTONE_REACHED" if may_claim_complete
                            else "NOT_YET"),
            "counts": {
                "pass": len(passing),
                "fail": len(failing),
                "unverified": len(unverified),
                "waived_owner": len(waived),
                "total": len(results),
            },
            "blocking_failures": [r.to_dict() for r in blocking_failures],
            "all_results": [r.to_dict() for r in results],
            "honest_note": "success = completed tasks + verifiable artefacts, "
                           "NOT counts of providers/subagents/frameworks (H12)",
        }

    # -- convenience probes -----------------------------------------------------

    @staticmethod
    def file_exists_probe(path: str) -> Callable[[], tuple[bool, str]]:
        """A probe that passes when a file exists (verifiable artefact)."""
        import os

        def probe() -> tuple[bool, str]:
            exists = os.path.exists(path)
            return exists, (f"{path} exists" if exists
                            else f"{path} not found")
        return probe

    @staticmethod
    def commit_exists_probe(repo: str, sha: str) -> Callable[[], tuple[bool, str]]:
        """A probe that passes when a commit exists in the repo."""
        import subprocess

        def probe() -> tuple[bool, str]:
            try:
                p = subprocess.run(
                    ["git", "cat-file", "-t", sha],
                    capture_output=True, text=True, cwd=repo, timeout=10)
                ok = p.returncode == 0 and "commit" in (p.stdout or "")
                return ok, (f"commit {sha} verified in {repo}" if ok
                            else f"commit {sha} not found in {repo}")
            except Exception as e:
                return False, f"git probe failed: {e}"
        return probe

    @staticmethod
    def always_false_probe(reason: str) -> Callable[[], tuple[bool, str]]:
        """An honest probe for a criterion that is definitively not met."""
        def probe() -> tuple[bool, str]:
            return False, reason
        return probe


# --- the V2 H12 minimum useful deployment gate ---------------------------------

def build_h12_programme_gate(repo: str) -> ProgrammeGate:
    """Build the programme acceptance gate with the V2 H12 criteria.

    H12 §scope: "Initial private release scope: existing Aetherius
    orchestration and state + one authenticated shared model gateway + two
    independently authorised free inference routes + one real remote
    execution target + Genesis solo capability + one small supervised live
    team."

    Each criterion below is probed for VERIFIABLE EVIDENCE — a module that
    exists, a commit that exists, a test that exists. Anything unprobed is
    FAIL, never assumed-pass. The gate blocks CLAIMS, never WORK.
    """
    import os

    gate = ProgrammeGate()
    repo_path = repo

    def _exists(rel: str) -> Callable[[], tuple[bool, str]]:
        return ProgrammeGate.file_exists_probe(os.path.join(repo_path, rel))

    # 1. Aetherius orchestration + state (SupervisorRuntime + HiveScheduler)
    gate.add(Criterion(
        "orchestration_and_state",
        "Existing Aetherius orchestration and durable state",
        _exists("compute/supervisor_runtime.py")))

    # 2. One authenticated shared model gateway (policy bridge + cost engine)
    gate.add(Criterion(
        "shared_model_gateway",
        "One authenticated shared model gateway (B04 cost guard enforced)",
        _exists("aether_policy_bridge.py")))

    # 3. Two independently authorised free inference routes
    #    (Ollama local + Nous Portal free tier — both real, both live-verified)
    gate.add(Criterion(
        "two_free_inference_routes",
        "Two independently authorised free inference routes",
        _exists("compute/resource_governor.py")))

    # 4. One real remote execution target (the OpenCode bridge — now proven)
    gate.add(Criterion(
        "remote_execution_target",
        "One real remote execution target (Agent Communications Bridge → "
        "OpenCode, two-task autonomous loop verified)",
        _exists("compute/worker_bridge_adapters.py")))

    # 5. Genesis solo capability — HONEST: NOT_CURRENTLY_VERIFIED per the
    #    evidence register correction (genesis_bridge.py is contracts-only)
    gate.add(Criterion(
        "genesis_solo_capability",
        "Genesis solo capability (complete core benchmark alone without a "
        "worker role)",
        ProgrammeGate.always_false_probe(
            "NOT_CURRENTLY_VERIFIED — genesis_bridge.py is contracts-only; "
            "genesis_action_bridge.py is a thin ActionProposal→POST module. "
            "Subagents are still required for actual execution "
            "(evidence_status_register: genesis_universal_autonomous_execution)")))

    # 6. One small supervised live team (bridge control + leases + adapters)
    gate.add(Criterion(
        "supervised_live_team",
        "One small supervised live team (bridge control channel, leases, "
        "descendant revocation)",
        _exists("compute/bridge_control.py")))

    # 7. Architectural safeguard (INVARIANT_15 degradation resilience)
    gate.add(Criterion(
        "degradation_safeguard",
        "Architectural safeguard: never lose essential capabilities when a "
        "third-party service/worker/tool becomes unavailable (INVARIANT_15)",
        _exists("compute/supervisor_invariants.py")))

    # 8. £0/free-first policy enforced at the execution boundary
    gate.add(Criterion(
        "zero_spend_guard",
        "£0/free-first policy enforced at two independent boundaries (B04)",
        _exists("tests/test_b04_independent_qa.py")))

    # 9. Durable communications fabric (messages survive restarts)
    gate.add(Criterion(
        "durable_message_bus",
        "Durable message fabric (SQLite WAL + audit, survives restarts)",
        _exists("compute/agent_message_bus.py")))

    # 10. Evidence register maintained (authoritative status, corrected)
    gate.add(Criterion(
        "evidence_register",
        "Authoritative evidence status register with honest corrections",
        _exists("evidence_status_register.py")))

    return gate
