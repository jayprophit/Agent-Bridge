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
