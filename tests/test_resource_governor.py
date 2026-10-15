"""Resource Governor tests — live-pressure admission, honesty, throttling.

Key contracts: UNKNOWN pressure never admits blindly; a task is admitted only
if all axes stay within gates AFTER adding its demand + the governor reserve;
throttling escalates with pressure; offload hints are privacy-aware.
"""
from __future__ import annotations

import pytest

from compute.resource_governor import (
    CRITICAL, ELEVATED, GPU_HEAVY, HEALTHY, HEAVY, LIGHT, MEDIUM, PRESSURE,
    AdmissionVerdict, ResourceGovernor, ResourceSample, TASK_CLASSES,
)


def _sample(**kw):
    return ResourceSample(**kw)


class TestPressureModel:
    def test_healthy_when_all_axes_low(self):
        g = ResourceGovernor()
        assert g.pressure(_sample(cpu=0.2, ram=0.3, gpu=0.1)) == HEALTHY

    def test_elevated_at_60_percent(self):
        g = ResourceGovernor()
        assert g.pressure(_sample(cpu=0.65, ram=0.2)) == ELEVATED

    def test_pressure_at_80_percent(self):
        g = ResourceGovernor()
        assert g.pressure(_sample(cpu=0.85, ram=0.2)) == PRESSURE

    def test_critical_at_95_percent(self):
        g = ResourceGovernor()
        assert g.pressure(_sample(cpu=0.96, ram=0.2)) == CRITICAL

    def test_disk_starvation_is_critical(self):
        g = ResourceGovernor(disk_min_free_gb=20.0)
        assert g.pressure(_sample(cpu=0.1, ram=0.1, disk_free_gb=5.0)) == CRITICAL

    def test_no_sample_means_critical_not_admitted_blindly(self):
        g = ResourceGovernor()
        assert g.pressure(None) == CRITICAL

    def test_nothing_measured_means_pressure(self):
        # honest: unmeasurable axes are not assumed idle
        g = ResourceGovernor()
        assert g.pressure(_sample()) == PRESSURE


class TestAdmission:
    def test_light_task_admitted_when_healthy(self):
        g = ResourceGovernor()
        v = g.may_start(LIGHT, _sample(cpu=0.2, ram=0.3))
        assert v.admitted is True
        assert v.pressure_state == HEALTHY

    def test_heavy_task_blocked_when_cpu_saturated(self):
        g = ResourceGovernor()
        v = g.may_start(HEAVY, _sample(cpu=0.80, ram=0.2))
        assert v.admitted is False
        assert "cpu" in v.reason
        assert v.offload_hint  # explainable (§37)

    def test_gpu_heavy_blocked_on_vram(self):
        g = ResourceGovernor()
        v = g.may_start(GPU_HEAVY, _sample(cpu=0.2, ram=0.2, vram=0.85))
        assert v.admitted is False
        assert "vram" in v.reason

    def test_critical_never_admits(self):
        g = ResourceGovernor()
        v = g.may_start(LIGHT, _sample(cpu=0.97, ram=0.2))
        assert v.admitted is False
        assert v.pressure_state == CRITICAL

    def test_unknown_axes_are_not_assumed_idle(self):
        # cpu known healthy, gpu None -> gpu axis headroom is None (unknown),
        # and a GPU_HEAVY task must still be admitted only on known axes;
        # the honest behaviour is: unknown gpu does NOT block (no fabrication)
        # but the reason names it.
        g = ResourceGovernor()
        v = g.may_start(GPU_HEAVY, _sample(cpu=0.2, ram=0.3))
        assert v.headroom_after["gpu"] is None

    def test_unknown_task_class_rejected(self):
        g = ResourceGovernor()
        with pytest.raises(ValueError):
            g.may_start("QUANTUM", _sample(cpu=0.1, ram=0.1))

    def test_governor_reserve_protects_desktop(self):
        # a task that fits without reserve must be blocked once reserve is
        # applied — that is the point of GOVERNOR_RESERVE for heavy work
        g = ResourceGovernor()
        v = g.may_start(HEAVY, _sample(cpu=0.75, ram=0.2))
        # 0.75 + 0.45 demand + 0.15 reserve = 1.35 > 0.85 gate -> blocked
        assert v.admitted is False

    def test_light_never_vetoed_by_reserve(self):
        # §25 BLOCKED TASK != BLOCKED PROGRAMME: the reserve SCALES with
        # class, so a LIGHT task (subagent call, git read) stays admissible
        # even at ELEVATED — otherwise the governor would halt the programme.
        g = ResourceGovernor()
        v = g.may_start(LIGHT, _sample(cpu=0.75, ram=0.70))
        # 0.70 + 0.05 + 0.03 reserve = 0.78 < 0.85 gate -> admitted
        assert v.admitted is True

    def test_reserve_scales_with_class(self):
        from compute.resource_governor import class_reserve
        assert class_reserve(LIGHT) < class_reserve(MEDIUM) < class_reserve(HEAVY)


class TestThrottling:
    def test_healthy_has_no_actions(self):
        g = ResourceGovernor()
        g._sample = _sample(cpu=0.2, ram=0.2)
        assert g.throttle_actions() == []

    def test_elevated_prefers_light(self):
        g = ResourceGovernor()
        g._sample = _sample(cpu=0.65, ram=0.2)
        actions = g.throttle_actions()
        assert any("LIGHT" in a for a in actions)

    def test_pressure_releases_models(self):
        g = ResourceGovernor()
        g._sample = _sample(cpu=0.85, ram=0.2)
        actions = g.throttle_actions()
        assert any("resident models" in a for a in actions)
        assert any("cloud" in a for a in actions)

    def test_critical_pauses_everything(self):
        g = ResourceGovernor()
        g._sample = _sample(cpu=0.97, ram=0.2)
        actions = g.throttle_actions()
        assert any("ALL non-essential" in a for a in actions)


class TestOverview:
    def test_overview_is_dashboard_shaped(self):
        g = ResourceGovernor()
        g._sample = _sample(cpu=0.5, ram=0.6, gpu=0.2, vram=0.1,
                            disk_free_gb=100.0, confidence="VERIFIED")
        ov = g.overview()
        assert ov["pressure_state"] == ELEVATED
        assert ov["sample"]["cpu"] == 0.5
        assert ov["sample"]["confidence"] == "VERIFIED"
        assert ov["governor_reserve"] > 0

    def test_overview_without_sample(self):
        g = ResourceGovernor()
        ov = g.overview()
        assert ov["sample"] is None
        assert ov["pressure_state"] == CRITICAL  # honest: unknown resources


# --- AT-25: quota exhaustion + nested fan-out prevention + remaining resources -
# (appended for V2 H05)

from compute.resource_governor import (
    AdmissionVerdict, ResourceGovernor as _Gov,
    ResourceSample as _RS,
)


def _rs(**kw):
    return _RS(**kw)


class TestAT25QuotaExhaustion:
    """Simulate provider quota exhaustion and fail-closed on uncertainty."""

    def test_exhausted_provider_blocks_admission(self):
        """When a provider's daily quota is exhausted, may_start denies."""
        g = ResourceGovernor(
            provider_quotas={"nous": {"daily_budget": 10, "daily_used": 10.0,
                                      "spend_verified": True}})
        v = g.may_start(LIGHT, _rs(cpu=0.2, ram=0.2), provider="nous")
        assert v.admitted is False
        assert "exhausted" in v.reason.lower()

    def test_unverified_spend_blocks_fail_closed(self):
        """Uncertain billing/free eligibility → BLOCKED (fail-closed)."""
        g = ResourceGovernor(
            provider_quotas={"nous": {"daily_budget": 10, "daily_used": 5.0,
                                      "spend_verified": False}})
        v = g.may_start(LIGHT, _rs(cpu=0.2, ram=0.2), provider="nous")
        assert v.admitted is False
        assert "uncertain" in v.reason.lower() or "fail closed" in v.offload_hint.lower()

    def test_unknown_provider_blocks(self):
        """Unknown provider → no quota data → BLOCKED."""
        g = ResourceGovernor()
        v = g.may_start(LIGHT, _rs(cpu=0.2, ram=0.2), provider="unknown-cloud")
        assert v.admitted is False
        assert "unknown provider" in v.reason

    def test_free_tier_provider_passes(self):
        """A free-eligible provider (budget=0) doesn't block admission."""
        g = ResourceGovernor(
            provider_quotas={"ollama-local": {"daily_budget": 0, "daily_used": 0.0,
                                             "spend_verified": True}})
        v = g.may_start(LIGHT, _rs(cpu=0.2, ram=0.2), provider="ollama-local")
        assert v.admitted is True

    def test_no_provider_arg_preserves_backward_compatibility(self):
        """may_start without provider arg still works (existing tests)."""
        g = ResourceGovernor()
        v = g.may_start(LIGHT, _rs(cpu=0.2, ram=0.3))
        assert v.admitted is True


class TestAT25NestedSpawnPrevention:
    """Prevent oversubscription and runaway nested spawning."""

    def test_total_concurrency_ceiling_blocks(self):
        """When total concurrent tasks hit the ceiling, new tasks are denied."""
        g = ResourceGovernor(max_total_concurrent=3)
        for _ in range(3):
            g.begin_task(LIGHT)
        v = g.may_start(LIGHT, _rs(cpu=0.1, ram=0.1))
        assert v.admitted is False
        assert "concurrency limit" in v.reason

    def test_heavy_concurrency_ceiling_blocks(self):
        """When heavy tasks hit their ceiling, new heavy tasks are denied."""
        g = ResourceGovernor(max_concurrent_heavy=2)
        g.begin_task(HEAVY)
        g.begin_task(GPU_HEAVY)
        v = g.may_start(HEAVY, _rs(cpu=0.2, ram=0.3))
        assert v.admitted is False
        assert "heavy limit" in v.reason

    def test_light_not_blocked_by_heavy_ceiling(self):
        """LIGHT tasks are not subject to the heavy-task ceiling."""
        g = ResourceGovernor(max_concurrent_heavy=1)
        g.begin_task(HEAVY)  # heavy slot full
        v = g.may_start(LIGHT, _rs(cpu=0.2, ram=0.3))
        # LIGHT is admitted (not counted against heavy limit)
        assert v.admitted is True

    def test_begin_end_task_counters(self):
        """begin/end_task correctly tracks active counts."""
        g = ResourceGovernor()
        assert g.active_count == 0
        assert g.active_heavy_count == 0
        g.begin_task(LIGHT)
        assert g.active_count == 1
        assert g.active_heavy_count == 0
        g.begin_task(HEAVY)
        assert g.active_count == 2
        assert g.active_heavy_count == 1
        g.end_task(HEAVY)
        assert g.active_count == 1
        assert g.active_heavy_count == 0

    def test_nested_fan_out_stops_at_ceiling(self):
        """Simulate a worker spawning nested subagents — governor stops the storm."""
        g = ResourceGovernor(max_total_concurrent=5)
        admitted = 0
        denied = 0
        for i in range(10):  # try to spawn 10 nested workers
            v = g.may_start(LIGHT, _rs(cpu=0.1, ram=0.1))
            if v.admitted:
                g.begin_task(LIGHT)
                admitted += 1
            else:
                denied += 1
        assert admitted == 5
        assert denied == 5
        assert g.active_count == 5

    def test_concurrency_status_reports_remaining(self):
        """concurrency_status shows how many slots remain."""
        g = ResourceGovernor(max_total_concurrent=10, max_concurrent_heavy=3)
        g.begin_task(LIGHT)
        g.begin_task(HEAVY)
        status = g.concurrency_status()
        assert status["active_total"] == 2
        assert status["active_heavy"] == 1
        assert status["remaining_total"] == 8
        assert status["remaining_heavy"] == 2


class TestAT25RemainingResources:
    """Report actual remaining resources via overview()."""

    def test_overview_includes_remaining_resources(self):
        """overview() reports remaining_slots in remaining_resources."""
        g = ResourceGovernor()
        g._sample = _rs(cpu=0.5, ram=0.6, gpu=0.2, vram=0.1,
                         disk_free_gb=100.0, confidence="VERIFIED")
        ov = g.overview()
        assert "remaining_resources" in ov
        assert "heavy_slots" in ov["remaining_resources"]
        assert "total_slots" in ov["remaining_resources"]
        assert ov["remaining_resources"]["heavy_slots"] > 0
        assert ov["remaining_resources"]["total_slots"] > 0

    def test_overview_includes_concurrency_and_quotas(self):
        """overview() includes concurrency status + provider quotas."""
        g = ResourceGovernor()
        g._sample = _rs(cpu=0.3, ram=0.4, confidence="VERIFIED")
        ov = g.overview()
        assert "concurrency" in ov
        assert "provider_quotas" in ov
        assert "nous" in ov["provider_quotas"]

    def test_set_quota_updates_status(self):
        """set_quota_updates_status reflects live usage changes."""
        g = ResourceGovernor()
        g.set_quota_usage("nous", daily_used=0.0)
        assert g.quota_status("nous")["status"] == "FREE_ELIGIBLE"
        g.set_quota_usage("nous", daily_used=5.0, spend_verified=False)
        assert g.quota_status("nous")["status"] == "BLOCKED"
        g.set_quota_usage("nous", daily_used=5.0, spend_verified=True)
        assert g.quota_status("nous")["status"] == "FREE_ELIGIBLE"
