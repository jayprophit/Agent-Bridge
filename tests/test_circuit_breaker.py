"""Circuit breaker + provider health tests (deterministic fake clock)."""
import unittest

from models.health import (BreakerConfig, CircuitBreaker, HealthState,
                           ProviderHealthRegistry)


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def _breaker(**kw):
    clock = FakeClock()
    cfg = BreakerConfig(failures_to_trip=3, degraded_to_trip=5,
                        cooldown_s=300.0, rate_limit_cooldown_s=120.0)
    for k, v in kw.items():
        setattr(cfg, k, v)
    return CircuitBreaker(cfg, clock), clock


class TestTripAndCooldown(unittest.TestCase):
    def test_unknown_resource_defaults_healthy(self):
        br, _ = _breaker()
        self.assertEqual(br.state("new-model"), HealthState.HEALTHY)
        self.assertTrue(br.healthy("new-model"))

    def test_trips_after_threshold(self):
        br, _ = _breaker()
        br.record_failure("m", "timeout")
        br.record_failure("m", "timeout")
        self.assertTrue(br.healthy("m"))  # not yet tripped
        st = br.record_failure("m", "timeout")
        self.assertEqual(st, HealthState.TIMED_OUT)
        self.assertFalse(br.healthy("m"))

    def test_success_resets_consecutive_count(self):
        br, _ = _breaker()
        br.record_failure("m", "timeout")
        br.record_failure("m", "timeout")
        br.record_success("m")
        br.record_failure("m", "timeout")
        self.assertTrue(br.healthy("m"))

    def test_cooldown_then_probe_rejoins(self):
        br, clock = _breaker()
        for _ in range(3):
            br.record_failure("m", "provider_failure")
        self.assertFalse(br.healthy("m"))
        clock.advance(301.0)
        self.assertEqual(br.state("m"), HealthState.COOLDOWN)
        self.assertTrue(br.healthy("m"))
        self.assertTrue(br.allow_probe("m"))
        br.record_success("m")
        self.assertEqual(br.state("m"), HealthState.HEALTHY)

    def test_rate_limit_uses_shorter_cooldown(self):
        br, clock = _breaker()
        for _ in range(3):
            br.record_failure("m", "rate_limited")
        self.assertEqual(br.state("m"), HealthState.RATE_LIMITED)
        clock.advance(121.0)
        self.assertEqual(br.state("m"), HealthState.COOLDOWN)

    def test_invalid_request_terminal(self):
        br, _ = _breaker()
        for _ in range(3):
            br.record_failure("m", "invalid_request")
        self.assertEqual(br.state("m"), HealthState.INVALID_REQUEST)
        self.assertFalse(br.healthy("m"))

    def test_degraded_kinds_dont_trip_immediately(self):
        br, _ = _breaker()
        st = br.record_failure("m", "bad_tool_call")
        self.assertEqual(st, HealthState.DEGRADED)
        self.assertTrue(br.healthy("m"))
        for _ in range(4):
            br.record_failure("m", "malformed_output")
        self.assertEqual(br.state("m"), HealthState.BROKEN)
        self.assertFalse(br.healthy("m"))

    def test_unknown_kind_never_crashes(self):
        br, _ = _breaker()
        st = br.record_failure("m", "something totally novel")
        self.assertIsInstance(st, HealthState)


class TestProviderHealthRegistry(unittest.TestCase):
    def test_pick_first_healthy_skips_broken(self):
        reg = ProviderHealthRegistry()
        for _ in range(3):
            reg.report("primary", ok=False, kind="timeout")
        self.assertEqual(reg.pick_first_healthy(["primary", "fallback"]),
                         "fallback")

    def test_pick_returns_empty_when_all_down(self):
        reg = ProviderHealthRegistry()
        for m in ("a", "b"):
            for _ in range(3):
                reg.report(m, ok=False, kind="provider_failure")
        self.assertEqual(reg.pick_first_healthy(["a", "b"]), "")

    def test_success_restores_routing(self):
        reg = ProviderHealthRegistry()
        for _ in range(3):
            reg.report("m", ok=False, kind="timeout")
        self.assertFalse(reg.healthy("m"))
        reg.report("m", ok=True)
        self.assertTrue(reg.healthy("m"))


if __name__ == "__main__":
    unittest.main()
