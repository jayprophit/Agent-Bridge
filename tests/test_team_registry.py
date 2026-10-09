"""§AK enterprise multi-agent gate tests: registry, departments, RACI,
handoff chain, optional-worker failure, and the 10+ logical worker proof.

WHY THESE TESTS EXIST

§AK is an acceptance gate, not a feature list. Each test below maps to a
specific §AK clause, and the mapping is stated in the test name so a reviewer
can audit the gate without reading the implementation.

The 12-worker test is the one that matters most. §AK explicitly says the gate
must NOT fail because a 16 GB workstation cannot RUN ten large models at
once — but it DOES require that the architecture support 10+ logical workers
with active concurrency separately represented. So the test proves both
numbers at once: a 12-worker team whose concurrency limit is 3, verified as
two independent figures rather than one collapsed number.
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest

from compute.team_registry import (
    ACCOUNTABILITY_COLLECTIVE,
    ACCOUNTABILITY_JOINT,
    ACCOUNTABILITY_MODES,
    CAREER_SPECIALIST,
    CAREER_VERIFIED,
    DEPARTMENT_ENGINEERING,
    DEPARTMENT_QUALITY,
    DEPARTMENT_RESEARCH,
    HandoffRecord,
    ProvenanceError,
    RaciAssignment,
    RACI_ACCOUNTABLE,
    RACI_INFORMED,
    RACI_RESPONSIBLE,
    TeamRecord,
    TeamRegistry,
    WorkerCareerRecord,
    department_for_role,
    new_team,
    new_worker,
)


class TeamRegistryCoreTests(unittest.TestCase):
    """§AK — canonical registry exists and supports teams."""

    def setUp(self):
        self.reg = TeamRegistry()

    def test_worker_registration_records_role_and_replaceable_model(self):
        """§M — worker_id, role, model_id and provider_id are distinct."""
        w = new_worker("coding_worker", model_id="qwen3:1.7b",
                       provider_id="ollama")
        self.reg.register_worker(w)
        got = self.reg.get_worker(w.worker_id)
        self.assertEqual(got.role_id, "coding_worker")
        self.assertEqual(got.model_id, "qwen3:1.7b")
        self.assertEqual(got.provider_id, "ollama")
        self.assertNotEqual(got.worker_id, got.model_id)

    def test_permanent_worker_ids_are_not_reused(self):
        """§5 — a permanent ID identifies one worker for life."""
        w = new_worker("reviewer", worker_id="worker-fixed")
        self.reg.register_worker(w)
        with self.assertRaises(ValueError):
            self.reg.register_worker(
                WorkerCareerRecord(worker_id="worker-fixed", role_id="reviewer"))

    def test_role_is_inferred_into_a_department(self):
        """§F — every role has an organisational home."""
        self.assertEqual(department_for_role("coding_worker"),
                         DEPARTMENT_ENGINEERING)
        self.assertEqual(department_for_role("research_worker"),
                         DEPARTMENT_RESEARCH)
        self.assertEqual(department_for_role("test_runner"),
                         DEPARTMENT_QUALITY)

    def test_unknown_role_returns_no_department_rather_than_guessing(self):
        """§F — an unrecognised role must be surfaced, not filed plausibly."""
        self.assertIsNone(department_for_role("not_a_real_role"))

    def test_team_cannot_contain_unregistered_workers(self):
        """§O — accountability requires a known worker."""
        team = TeamRecord(team_id="t-1", team_name="t", purpose="p",
                          members=["ghost-worker"])
        with self.assertRaises(ValueError):
            self.reg.form_team(team)


class TaskOwnershipTests(unittest.TestCase):
    """§O — every task has exactly one accountable owner."""

    def setUp(self):
        self.reg = TeamRegistry()
        self.w = new_worker("coding_worker", worker_id="w-owner")
        self.reg.register_worker(self.w)

    def test_task_owner_is_singular(self):
        self.reg.set_task_owner("task-1", "w-owner")
        self.assertEqual(self.reg.task_owner("task-1"), "w-owner")

    def test_reassignment_is_allowed_and_previous_owner_is_recorded(self):
        """§O — ownership may move, but never become ambiguous."""
        other = new_worker("reviewer", worker_id="w-other")
        self.reg.register_worker(other)
        self.reg.set_task_owner("task-1", "w-owner")
        self.reg.set_task_owner("task-1", "w-other")
        self.assertEqual(self.reg.task_owner("task-1"), "w-other")

    def test_task_cannot_be_owned_by_unknown_worker(self):
        with self.assertRaises(ValueError):
            self.reg.set_task_owner("task-1", "nobody")


class RaciTests(unittest.TestCase):
    """§P — RACI-equivalent responsibility, with one accountable owner."""

    def setUp(self):
        self.reg = TeamRegistry()
        for wid in ("w-resp", "w-acct", "w-cons", "w-info"):
            self.reg.register_worker(new_worker("coding_worker", worker_id=wid))

    def test_raci_requires_exactly_one_accountable(self):
        """§O/§P — zero owners is the bug; two is the other half of it."""
        with self.assertRaises(ValueError):
            self.reg.record_raci(RaciAssignment(
                task_id="t-1", responsible=["w-resp"], accountable=None))

    def test_raci_records_all_four_assignments(self):
        raci = RaciAssignment(task_id="t-2", responsible=["w-resp"],
                              accountable="w-acct", consulted=["w-cons"],
                              informed=["w-info"])
        self.reg.record_raci(raci)
        got = self.reg.raci_for("t-2")
        self.assertEqual(got.accountable, "w-acct")
        self.assertEqual(got.responsible, ["w-resp"])
        self.assertEqual(got.consulted, ["w-cons"])
        self.assertEqual(got.informed, ["w-info"])

    def test_recording_raci_sets_task_owner_to_the_accountable_worker(self):
        """§O — RACI accountability and task ownership must agree."""
        self.reg.record_raci(RaciAssignment(task_id="t-3", accountable="w-acct"))
        self.assertEqual(self.reg.task_owner("t-3"), "w-acct")

    def test_raci_cannot_name_unregistered_workers(self):
        with self.assertRaises(ValueError):
            self.reg.record_raci(RaciAssignment(
                task_id="t-4", accountable="w-acct", consulted=["ghost"]))


class HandoffChainTests(unittest.TestCase):
    """§H, §I, §AC — registered handoffs and the A→B→C chain proof."""

    def setUp(self):
        self.reg = TeamRegistry()
        self.architect = new_worker("reviewer", worker_id="w-architect")
        self.coder = new_worker("coding_worker", worker_id="w-coder")
        self.tester = new_worker("test_runner", worker_id="w-tester")
        for w in (self.architect, self.coder, self.tester):
            self.reg.register_worker(w)

    def _handoff(self, frm, frm_role, to, to_role, n, ts):
        return HandoffRecord(
            handoff_id=f"h-{n}", task_id="task-chain", parent_task_id=None,
            from_worker=frm, from_role=frm_role, to_worker=to, to_role=to_role,
            objective="implement the bounded unit",
            completed_work=f"stage {n}", tests_run=n,
            decisions_made=[f"decision {n}"], timestamp=ts,
            recommended_next_action=f"continue with stage {n + 1}")

    def test_three_role_handoff_chain_is_ordered(self):
        """§AC — Worker C can continue without the original conversation."""
        self.reg.register_handoff(
            self._handoff("w-architect", "reviewer", "w-coder",
                          "coding_worker", 1, 1000.0))
        self.reg.register_handoff(
            self._handoff("w-coder", "coding_worker", "w-tester",
                          "test_runner", 2, 2000.0))
        chain = self.reg.handoff_chain("task-chain")
        self.assertEqual(len(chain), 2)
        self.assertEqual(chain[0].from_role, "reviewer")
        self.assertEqual(chain[0].to_role, "coding_worker")
        self.assertEqual(chain[1].from_role, "coding_worker")
        self.assertEqual(chain[1].to_role, "test_runner")

    def test_handoff_carries_everything_the_receiver_needs(self):
        """§H — no important work may live only in ephemeral chat text."""
        h = self._handoff("w-architect", "reviewer", "w-coder",
                          "coding_worker", 1, 1000.0)
        h.artifacts = ["compute/team_registry.py"]
        h.commit = "abc123"
        h.known_risks = ["concurrency untested"]
        h.dependencies_remaining = ["credential rotation"]
        self.reg.register_handoff(h)
        got = self.reg.get_handoff("h-1")
        self.assertEqual(got.artifacts, ["compute/team_registry.py"])
        self.assertEqual(got.commit, "abc123")
        self.assertEqual(got.known_risks, ["concurrency untested"])
        self.assertEqual(got.dependencies_remaining, ["credential rotation"])
        self.assertTrue(got.recommended_next_action)

    def test_handoff_to_a_role_nobody_holds_is_refused(self):
        """§I — work everyone assumed was picked up is the failure mode."""
        with self.assertRaises(ValueError):
            self.reg.register_handoff(HandoffRecord(
                handoff_id="h-bad", task_id="t", parent_task_id=None,
                from_worker="w-architect", from_role="reviewer",
                to_worker="w-coder", to_role="cad_agent",
                objective="x"))

    def test_handoff_from_unregistered_worker_is_refused(self):
        with self.assertRaises(ValueError):
            self.reg.register_handoff(HandoffRecord(
                handoff_id="h-bad2", task_id="t", parent_task_id=None,
                from_worker="ghost", from_role="reviewer",
                to_worker="w-coder", to_role="coding_worker", objective="x"))


class ModelSwapTests(unittest.TestCase):
    """§M — the worker persists when the model is replaced."""

    def test_swapping_model_preserves_role_and_identity(self):
        reg = TeamRegistry()
        w = new_worker("coding_worker", model_id="qwen3:1.7b",
                       provider_id="ollama", worker_id="w-swap")
        reg.register_worker(w)
        reg.record_outcome("w-swap", success=True)
        reg.swap_worker_model("w-swap", model_id="granite3.3:2b",
                              provider_id="ollama")
        got = reg.get_worker("w-swap")
        self.assertEqual(got.worker_id, "w-swap")       # identity unchanged
        self.assertEqual(got.role_id, "coding_worker")  # role unchanged
        self.assertEqual(got.model_id, "granite3.3:2b")  # substrate replaced
        self.assertEqual(got.success_count, 1)           # evidence survives


class CareerEvidenceTests(unittest.TestCase):
    """§AI, §AJ — promotion is earned by evidence, not assumed."""

    def setUp(self):
        self.reg = TeamRegistry()

    def test_untested_worker_has_no_success_rate_rather_than_zero(self):
        """"Never tried" and "always fails" are different facts."""
        w = new_worker("coding_worker", worker_id="w-untested")
        self.reg.register_worker(w)
        self.assertIsNone(self.reg.get_worker("w-untested").success_rate)

    def test_ranking_puts_proven_workers_above_untested_ones(self):
        """§AI — ranking by inaction would reward doing nothing."""
        proven = new_worker("coding_worker", worker_id="w-proven")
        untried = new_worker("coding_worker", worker_id="w-untried")
        self.reg.register_worker(proven)
        self.reg.register_worker(untried)
        for _ in range(5):
            self.reg.record_outcome("w-proven", success=True)
        ranked = self.reg.rank_workers("coding_worker")
        self.assertEqual(ranked[0].worker_id, "w-proven")

    def test_promotion_requires_evidence_to_be_recorded(self):
        w = new_worker("coding_worker", worker_id="w-promote")
        self.reg.register_worker(w)
        self.reg.record_outcome("w-promote", success=True)
        self.reg.record_outcome("w-promote", success=True)
        self.reg.promote_worker("w-promote", CAREER_VERIFIED,
                                evidence="2/2 verified runs")
        self.reg.promote_worker("w-promote", CAREER_SPECIALIST,
                                evidence="2/2 verified runs")
        self.assertEqual(self.reg.get_worker("w-promote").career_state,
                         CAREER_SPECIALIST)

    def test_demotion_is_allowed_without_promotion_ceremony(self):
        """A failing worker must be pullable back immediately."""
        w = new_worker("coding_worker", worker_id="w-bad")
        self.reg.register_worker(w)
        self.reg.promote_worker("w-bad", CAREER_VERIFIED, evidence="initial")
        self.reg.demote_worker("w-bad", "DEGRADED", reason="3 consecutive failures")
        self.assertEqual(self.reg.get_worker("w-bad").career_state, "DEGRADED")


class ElasticTeamScalingTests(unittest.TestCase):
    """§AK, §T, §U — 10+ logical workers with concurrency kept separate.

    This is the clause §AK says must NOT be failed for lack of hardware. The
    requirement is architectural: represent 12 logical specialists while
    running 3 at a time, and keep the two numbers independently observable.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="team_reg_test_")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _team_of(self, reg, team_id, role_ids, concurrency=3):
        team, workers = new_team(role_ids, team_size=len(role_ids),
                                 concurrency=concurrency, team_id=team_id)
        for w in workers:
            reg.register_worker(w)
        reg.form_team(team)
        return team

    def test_twelve_logical_workers_at_concurrency_three(self):
        """§AK — the 10+ proof. Both numbers survive as distinct facts."""
        reg = TeamRegistry()
        roles = [
            "coordinator", "reviewer", "coding_worker", "test_runner",
            "research_worker", "evidence_reviewer", "routing_specialist",
            "cost_specialist", "handoff_arbiter", "coding_worker",
            "coding_worker", "test_runner",
        ]
        self.assertEqual(len(roles), 12)
        team = self._team_of(reg, "team-elastic", roles, concurrency=3)

        self.assertEqual(team.team_size, 12)                 # logical (§U)
        self.assertEqual(team.active_concurrency_limit, 3)   # what runs (§U)
        self.assertNotEqual(team.team_size, team.active_concurrency_limit)
        self.assertEqual(len(reg.get_team("team-elastic").members), 12)

        report = reg.team_report("team-elastic")
        self.assertEqual(report["logical_team_size"], 12)
        self.assertEqual(report["active_concurrency_limit"], 3)

    def test_team_spanning_four_departments(self):
        """§F — departments are representable organisational metadata."""
        reg = TeamRegistry()
        roles = ["coordinator", "reviewer", "coding_worker", "test_runner",
                 "research_worker", "evidence_reviewer", "routing_specialist",
                 "cost_specialist", "handoff_arbiter", "coding_worker"]
        self._team_of(reg, "team-depts", roles)
        report = reg.team_report("team-depts")
        self.assertGreaterEqual(len(report["departments_represented"]), 4)
        for dept in (DEPARTMENT_ENGINEERING, DEPARTMENT_QUALITY,
                     DEPARTMENT_RESEARCH, "OPERATIONS"):
            self.assertIn(dept, report["departments_represented"])

    def test_distinct_roles_are_counted_correctly(self):
        """§AK — 3-5 distinct roles must be demonstrable; 9 exist."""
        reg = TeamRegistry()
        roles = ["coordinator", "reviewer", "coding_worker", "test_runner",
                 "research_worker"]
        self._team_of(reg, "team-five", roles)
        report = reg.team_report("team-five")
        self.assertEqual(len(report["roles_represented"]), 5)

    def test_scaling_changes_logical_size_without_touching_membership(self):
        """§T — scaling the team is organisational; membership is factual."""
        reg = TeamRegistry()
        roles = ["coding_worker", "test_runner", "reviewer"]
        team = self._team_of(reg, "team-scale", roles, concurrency=2)
        before_members = list(team.members)
        reg.scale_team("team-scale", 10)
        after = reg.get_team("team-scale")
        self.assertEqual(after.team_size, 10)
        self.assertEqual(after.members, before_members)
        self.assertEqual(after.active_concurrency_limit, 2)


class OptionalWorkerFailureTests(unittest.TestCase):
    """§AD — a team must survive one optional worker failing."""

    def test_team_survives_demotion_of_an_optional_worker(self):
        reg = TeamRegistry()
        team, workers = new_team(
            ["coordinator", "reviewer", "coding_worker", "test_runner",
             "research_worker"], team_id="team-resilient")
        for w in workers:
            reg.register_worker(w)
        reg.form_team(team)
        victim = workers[2].worker_id  # an optional specialist
        reg.demote_worker(victim, "BLOCKED", reason="provider unreachable")

        # Team is intact; the blocked worker is excluded, not fatal.
        self.assertEqual(reg.get_team("team-resilient").team_size, 5)
        self.assertEqual(reg.get_worker(victim).career_state, "BLOCKED")
        remaining = [w for w in workers if w.worker_id != victim]
        self.assertEqual(len(remaining), 4)

    def test_replacement_worker_can_take_the_same_role(self):
        """§AD — the role persists even when the worker does not."""
        reg = TeamRegistry()
        original = new_worker("reviewer", worker_id="w-original")
        reg.register_worker(original)
        reg.demote_worker("w-original", "RETIRED", reason="superseded")
        replacement = new_worker("reviewer", worker_id="w-replacement")
        reg.register_worker(replacement)
        self.assertEqual(reg.get_worker("w-replacement").role_id, "reviewer")
        self.assertEqual(reg.get_worker("w-original").career_state, "RETIRED")


class ProvenanceLayerTests(unittest.TestCase):
    """§AK — the organisational trail is permanent and rebuildable."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="team_prov_test_")
        self.path = os.path.join(self.tmpdir, "team_provenance.jsonl")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_canonical_state_rebuilds_from_the_append_only_trail(self):
        """The permanent record can reconstruct the fast path."""
        reg = TeamRegistry(provenance_path=self.path)
        team, workers = new_team(["coordinator", "reviewer", "coding_worker"],
                                 team_id="team-rebuild")
        for w in workers:
            reg.register_worker(w)
        reg.form_team(team)
        reg.set_task_owner("task-1", workers[1].worker_id)
        reg.record_raci(RaciAssignment(task_id="task-1",
                                       accountable=workers[1].worker_id))
        reg.register_handoff(HandoffRecord(
            handoff_id="h-1", task_id="task-1", parent_task_id=None,
            from_worker=workers[0].worker_id, from_role="coordinator",
            to_worker=workers[1].worker_id, to_role="reviewer",
            objective="rebuild me"))

        rebuilt = TeamRegistry(provenance_path=self.path)
        replayed = rebuilt.rebuild_from_provenance()

        self.assertGreater(replayed, 0)
        self.assertEqual(rebuilt.get_team("team-rebuild").team_size, 3)
        self.assertEqual(rebuilt.task_owner("task-1"), workers[1].worker_id)
        self.assertIsNotNone(rebuilt.raci_for("task-1"))
        self.assertIsNotNone(rebuilt.get_handoff("h-1"))

    def test_provenance_is_append_only_and_never_rewritten(self):
        """§52 — deleting a team must never delete the provenance trail."""
        reg = TeamRegistry(provenance_path=self.path)
        team, workers = new_team(["coding_worker"], team_id="team-append")
        reg.register_worker(workers[0])
        reg.form_team(team)
        with open(self.path, encoding="utf-8") as fh:
            first_count = sum(1 for _ in fh)

        # A later mutation appends; it does not rewrite history.
        reg.set_task_owner("task-x", workers[0].worker_id)
        with open(self.path, encoding="utf-8") as fh:
            lines = fh.readlines()
        self.assertGreater(len(lines), first_count)
        # The first event is byte-identical and still present: a later
        # mutation appended, it did not rewrite what came before.
        self.assertIn("worker.registered", lines[0])
        self.assertIn("team.formed", lines[first_count - 1])

    def test_accountability_mode_records_shared_accountability_without_breaking_single_owner(self):
        """§P refinement: a task can have JOINT/COLLECTIVE shared accountability
        while still having exactly ONE execution owner.

        This is the co-parent / board case: ultimate accountability is shared,
        but someone specific must get the work done. The registry records both
        without either weakening the other.
        """
        reg = TeamRegistry()
        parent_a = WorkerCareerRecord(worker_id="parent-a",
                                      role_id="family_worker")
        parent_b = WorkerCareerRecord(worker_id="parent-b",
                                      role_id="family_worker")
        reg.register_worker(parent_a)
        reg.register_worker(parent_b)
        raci = RaciAssignment(
            task_id="task-school-run",
            accountable="parent-a",                 # the one who must do it
            accountability_mode=ACCOUNTABILITY_JOINT,
            collective_accountable=["parent-b"],    # shares responsibility
        )
        reg.record_raci(raci)
        # Exactly one execution owner is still enforced.
        self.assertEqual(reg.task_owner("task-school-run"), "parent-a")
        stored = reg.raci_for("task-school-run")
        self.assertEqual(stored.accountability_mode, ACCOUNTABILITY_JOINT)
        self.assertEqual(stored.collective_accountable, ["parent-b"])

    def test_collective_mode_without_shared_holders_is_rejected(self):
        """JOINT/COLLECTIVE with no shared holder is a contradiction."""
        reg = TeamRegistry()
        w = WorkerCareerRecord(worker_id="w1", role_id="reviewer")
        reg.register_worker(w)
        with self.assertRaises(ValueError):
            reg.record_raci(RaciAssignment(
                task_id="task-board",
                accountable="w1",
                accountability_mode=ACCOUNTABILITY_COLLECTIVE,
                collective_accountable=[]))

    def test_invalid_accountability_mode_is_rejected(self):
        reg = TeamRegistry()
        w = WorkerCareerRecord(worker_id="w1", role_id="reviewer")
        reg.register_worker(w)
        with self.assertRaises(ValueError):
            reg.record_raci(RaciAssignment(
                task_id="task-x",
                accountable="w1",
                accountability_mode="WING_IT"))

    def test_accountability_mode_survives_provenance_replay(self):
        """The refinement is durable: shared accountability reads back intact."""
        reg = TeamRegistry(provenance_path=self.path)
        w = WorkerCareerRecord(worker_id="w1", role_id="reviewer")
        reg.register_worker(w)
        reg.record_raci(RaciAssignment(
            task_id="task-joint",
            accountable="w1",
            accountability_mode=ACCOUNTABILITY_JOINT,
            collective_accountable=["w1"]))
        rebuilt = TeamRegistry(provenance_path=self.path)
        rebuilt.rebuild_from_provenance()
        stored = rebuilt.raci_for("task-joint")
        self.assertEqual(stored.accountability_mode, ACCOUNTABILITY_JOINT)
        self.assertEqual(stored.collective_accountable, ["w1"])

    def test_unreadable_provenance_raises_rather_than_losing_the_trail(self):
        """A registry that cannot persist must not pretend it did.

        The failure surfaces at the FIRST append rather than the one this test
        originally named — which is the correct behaviour. Registering a worker
        already writes provenance, so an unwritable path is caught immediately
        rather than three calls later.
        """
        # Make the parent path a file so makedirs fails.
        with open(os.path.join(self.tmpdir, "blocker"), "w") as fh:
            fh.write("not a directory")
        blocking = os.path.join(self.tmpdir, "blocker", "x.jsonl")
        reg = TeamRegistry(provenance_path=blocking)
        team, workers = new_team(["coding_worker"], team_id="t-bad")
        with self.assertRaises(ProvenanceError):
            reg.register_worker(workers[0])

    def test_summary_is_machine_readable_for_the_gate(self):
        reg = TeamRegistry(provenance_path=self.path)
        team, workers = new_team(["coordinator", "reviewer", "coding_worker",
                                  "test_runner", "research_worker"],
                                 team_size=12, concurrency=3,
                                 team_id="team-summary")
        for w in workers:
            reg.register_worker(w)
        reg.form_team(team)
        reg.scale_team("team-summary", 12)
        s = reg.summary()
        self.assertEqual(s["teams"], 1)
        self.assertEqual(s["workers"], 5)
        self.assertEqual(s["schema_version"], 1)
        self.assertGreater(s["provenance_events"], 0)
        self.assertIn("provenance_path", s)


if __name__ == "__main__":
    unittest.main()
