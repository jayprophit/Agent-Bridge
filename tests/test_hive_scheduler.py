"""Hive scheduler tests — the honesty gates are the point (§4, §8, §13, §27,
§28, §29, §37). A scheduler that routes paid or leaks SECRET or fabricates
quota is worse than no scheduler.
"""
from __future__ import annotations

import json

import pytest

from compute import hive_scheduler as hive
from compute.hive_scheduler import (
    DAILY, ESTIMATED, FREE, FREE_TIER, INTERNAL, LOCAL_UNLIMITED, PAID,
    PUBLIC, SECRET, UNKNOWN, VERIFIED, AVAILABLE, WAITING_FOR_QUOTA,
    HandoffMessage, HiveScheduler, HiveSchedulerError, QuotaLedgerEntry,
    TaskSpec,
)


def _task(task_id="t1", **kw):
    return TaskSpec(task_id=task_id, title=task_id, **kw)


class TestQuotaHonesty:
    def test_unknown_quota_stays_unknown(self):
        e = QuotaLedgerEntry(worker_id="w", provider="p", tier=FREE,
                             confidence=UNKNOWN)
        assert e.quota_remaining is None
        assert e.remaining_fraction() is None

    def test_fraction_only_when_both_known(self):
        e = QuotaLedgerEntry(worker_id="w", provider="p", tier=FREE_TIER,
                             quota_total=100.0, quota_remaining=25.0,
                             confidence=VERIFIED)
        assert e.remaining_fraction() == 0.25

    def test_closed_vocabularies_reject_junk(self):
        with pytest.raises(ValueError):
            QuotaLedgerEntry(worker_id="w", provider="p", tier="MAGIC")
        with pytest.raises(ValueError):
            QuotaLedgerEntry(worker_id="w", provider="p", confidence="TRUST_ME")


class TestWorkerRegistration:
    def test_register_and_state(self):
        h = HiveScheduler()
        h.register_worker("w-local", provider="ollama", tier=LOCAL_UNLIMITED)
        h.set_worker_state("w-local", hive.IMPLEMENTING)
        assert h.overview()["by_state"][hive.IMPLEMENTING] == 1

    def test_interactive_only_app_is_not_routable(self):
        # §2 installed != controllable.
        h = HiveScheduler()
        h.register_worker("w-gui", provider="manus", tier=FREE,
                          verification_status="INTERACTIVE_ONLY")
        assert h.route(_task(required_capability="CODING_AGENT")) is None


class TestFreeFirstPolicy:
    def test_paid_worker_never_selected_without_budget(self):
        # §4 default paid budget 0.
        h = HiveScheduler()
        h.register_worker("w-paid", provider="anthropic", tier=PAID)
        assert h.worker_score("w-paid", _task()) is None
        assert h.route(_task()) is None

    def test_paid_worker_eligible_when_budget_granted(self):
        h = HiveScheduler(paid_budget=1)
        h.register_worker("w-paid", provider="anthropic", tier=PAID)
        assert h.route(_task()) == "w-paid"

    def test_local_beats_free_cloud_for_equal_fit(self):
        h = HiveScheduler()
        h.register_worker("w-local", provider="ollama", tier=LOCAL_UNLIMITED,
                          capabilities=("CODING_AGENT",))
        h.register_worker("w-cloud", provider="freecloud", tier=FREE_TIER,
                          capabilities=("CODING_AGENT",))
        picked = h.route(_task(required_capability="CODING_AGENT"))
        assert picked == "w-local"


class TestPrivacyGates:
    def test_secret_never_routes_to_public_worker(self):
        # §29 privacy before quota.
        h = HiveScheduler()
        h.register_worker("w-cloud", provider="freecloud", tier=FREE,
                          privacy_class=PUBLIC)
        h.register_worker("w-local", provider="ollama",
                          tier=LOCAL_UNLIMITED, privacy_class=SECRET)
        picked = h.route(_task(privacy_class=SECRET))
        assert picked == "w-local"

    def test_secret_task_without_local_worker_is_deferred_not_sent(self):
        h = HiveScheduler()
        h.register_worker("w-cloud", provider="freecloud", tier=FREE,
                          privacy_class=PUBLIC)
        assert h.route(_task(privacy_class=SECRET)) is None
        assert h.overview()["waiting_for_quota"] == 1

    def test_internal_task_not_routed_to_public_worker(self):
        h = HiveScheduler()
        h.register_worker("w-cloud", provider="freecloud", tier=FREE,
                          privacy_class=PUBLIC)
        assert h.worker_score("w-cloud", _task(privacy_class=INTERNAL)) is None


class TestOneWriterPerWriteSet:
    def test_second_writer_on_same_write_set_is_ineligible(self):
        # §13 mandatory: another worker cannot take a concurrent writer role
        # on a write-set someone else owns. The OWNER may queue further tasks
        # on it (sequential work on one checkout is fine).
        h = HiveScheduler()
        h.register_worker("w1", provider="ollama", tier=LOCAL_UNLIMITED)
        h.register_worker("w2", provider="ollama", tier=LOCAL_UNLIMITED)
        t = _task(write_set="IDE-Workspace/main")
        assert h.route(t) == "w1"
        t2 = _task(task_id="t2", write_set="IDE-Workspace/main")
        # the OTHER worker is hard-ineligible on this write-set
        assert h.worker_score("w2", t2) is None
        # so the only eligible writer is the current owner (sequential queue)
        assert h.route(t2) == "w1"

    def test_reallocate_moves_write_set_to_another_worker(self):
        # §10: on reallocation the old owner is parked, so the write-set
        # genuinely moves to a different worker (never stays with the hung one).
        h = HiveScheduler()
        h.register_worker("w1", provider="ollama", tier=LOCAL_UNLIMITED)
        h.register_worker("w2", provider="ollama", tier=LOCAL_UNLIMITED)
        h.route(_task(write_set="IDE-Workspace/main"))
        new = h.reallocate("t1", reason="worker hung")
        assert new == "w2"

    def test_different_write_sets_are_independent(self):
        h = HiveScheduler()
        h.register_worker("w1", provider="ollama", tier=LOCAL_UNLIMITED)
        h.register_worker("w2", provider="ollama", tier=LOCAL_UNLIMITED)
        assert h.route(_task(write_set="MAT")) == "w1"
        assert h.route(_task(task_id="t2", write_set="Agent-Bridge")) == "w2"


class TestQuotaScarcityAndReservation:
    def test_exhausted_quota_is_a_hard_skip(self):
        # §27: quota_remaining == 0 -> defer, never pay.
        h = HiveScheduler()
        h.register_worker("w", provider="freecloud", tier=FREE_TIER)
        h.record_quota(QuotaLedgerEntry(
            worker_id="w", provider="freecloud", tier=FREE_TIER,
            quota_total=100.0, quota_remaining=0.0, confidence=VERIFIED))
        assert h.worker_score("w", _task()) is None
        assert h.route(_task()) is None

    def test_reservation_holds_quota_back(self):
        # §25: strong model reserved for architecture review.
        h = HiveScheduler()
        h.register_worker("w-strong", provider="freecloud", tier=FREE_TIER)
        h.register_worker("w-cheap", provider="ollama", tier=LOCAL_UNLIMITED)
        base = h.worker_score("w-strong", _task())
        h.reserve_quota("w-strong", 0.9)
        assert h.worker_score("w-strong", _task()) < base

    def test_large_task_penalised_on_scarce_quota(self):
        # §8: do not burn the last 25% on a huge task.
        h = HiveScheduler()
        h.register_worker("w-scarce", provider="freecloud", tier=FREE_TIER)
        h.register_worker("w-roomy", provider="ollama", tier=LOCAL_UNLIMITED)
        h.record_quota(QuotaLedgerEntry(
            worker_id="w-scarce", provider="freecloud", tier=FREE_TIER,
            quota_total=1000.0, quota_remaining=200.0, confidence=VERIFIED))
        big = _task(estimated_input_tokens=800, estimated_output_tokens=200)
        picked = h.route(big)
        assert picked == "w-roomy"


class TestReallocation:
    def test_reallocate_produces_handoff_and_preserves_task(self):
        # §10: checkpoint -> handoff -> next worker. Work never discarded.
        h = HiveScheduler()
        h.register_worker("w1", provider="ollama", tier=LOCAL_UNLIMITED)
        h.register_worker("w2", provider="ollama", tier=LOCAL_UNLIMITED)
        h.route(_task(write_set="repo-a"))
        new = h.reallocate("t1", reason="worker hung")
        assert new == "w2"
        msgs = h.handoffs()
        assert len(msgs) == 1
        assert msgs[0].type == "handoff"
        assert msgs[0].from_worker == "w1"
        assert msgs[0].to_worker == "w2"
        assert "t1" in h._tasks  # the task record survives

    def test_reallocate_with_no_spare_defers(self):
        h = HiveScheduler()
        h.register_worker("w1", provider="ollama", tier=LOCAL_UNLIMITED)
        h.route(_task(write_set="repo-a"))
        assert h.reallocate("t1") is None
        assert h.overview()["waiting_for_quota"] == 1


class TestHandoffMessages:
    def test_handoff_is_plain_structured_json(self):
        # §14: compact machine-readable, human-readable. No robot speech.
        msg = HandoffMessage(
            type="correction", from_worker="hermes", to_worker="codex",
            project="MAT", unit="thermal-data", state="READY",
            requirements=("index 12 sources",), blockers=(),
            next_action="implement")
        d = json.loads(msg.to_json())
        assert d["from_worker"] == "hermes"
        assert d["requirements"] == ["index 12 sources"]
        assert "evidence" in d and "blockers" in d


class TestPersistence:
    def test_save_load_round_trip(self, tmp_path):
        # §37: the hive state survives a reboot.
        h = HiveScheduler(paid_budget=0)
        h.register_worker("w-local", provider="ollama", tier=LOCAL_UNLIMITED,
                          capabilities=("CODING_AGENT",))
        h.record_quota(QuotaLedgerEntry(
            worker_id="w-local", provider="ollama", tier=LOCAL_UNLIMITED,
            confidence=VERIFIED, reset_type=DAILY,
            next_reset_epoch=9999999999.0))
        h.route(_task(required_capability="CODING_AGENT"))
        h.reserve_quota("w-local", 0.1)
        h.send_handoff(HandoffMessage(type="result", from_worker="w-local",
                                      to_worker="hermes"))
        p = tmp_path / "hive.json"
        h.save(p)

        h2 = HiveScheduler.load(p)
        assert h2.overview()["workers"] == 1
        assert h2.overview()["tasks_assigned"] == 1
        assert h2.overview()["next_quota_reset_epoch"] == 9999999999.0
        assert len(h2.handoffs()) == 1
        assert h2.handoffs()[0].type == "result"
        # quota honesty survived the round trip
        assert h2._quota["w-local"].confidence == VERIFIED
        # still routes after reload (resume, not restart)
        assert h2.worker_score("w-local", _task(task_id="t9")) is not None

    def test_unknown_quota_survives_round_trip_as_unknown(self, tmp_path):
        h = HiveScheduler()
        h.register_worker("w", provider="freecloud", tier=FREE)
        h.record_quota(QuotaLedgerEntry(worker_id="w", provider="freecloud",
                                        tier=FREE, confidence=UNKNOWN))
        p = tmp_path / "hive.json"
        h.save(p)
        h2 = HiveScheduler.load(p)
        assert h2._quota["w"].quota_remaining is None
        assert h2._quota["w"].confidence == UNKNOWN


class TestOverview:
    def test_overview_counts_and_internal_external_split(self):
        h = HiveScheduler()
        h.register_worker("h-sa-01", provider="hermes", tier=LOCAL_UNLIMITED)
        h.register_worker("codex", provider="openai", tier=PAID)
        h.register_worker("opencode", provider="opencode", tier=FREE)
        ov = h.overview()
        assert ov["workers"] == 3
        assert ov["internal_vs_external"]["internal"] == 1
        assert ov["internal_vs_external"]["external"] == 2
        assert ov["paid_budget"] == 0

    def test_waiting_for_quota_tasks_are_visible(self):
        # §31 dashboard overview must see deferred work.
        h = HiveScheduler()
        h.register_worker("w-paid", provider="anthropic", tier=PAID)
        h.route(_task())
        assert h.overview()["waiting_for_quota"] == 1
        assert "t1" in h._deferred
