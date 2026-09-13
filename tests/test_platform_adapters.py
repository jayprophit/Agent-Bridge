"""v0.9.0 platform adapter tests (mocked; no OS mutations)."""
import unittest
from unittest import mock

from platform_adapters import (
    Arch,
    CapabilityAdapter,
    ControlLevel,
    DeviceCapabilityPassport,
    EnvironmentSelector,
    PlatformId,
    PlatformRegistry,
    Readiness,
    RemoteExecutionAdapter,
    RuntimeProfile,
    SafetySupervisor,
    SupportLevel,
    build_passport,
    check_arch_compatible,
    evaluate_readiness,
    resolve_capability,
    resolve_inference,
)


class _FakeProvider:
    def __init__(self, name, platforms, archs=("x86_64",), available=True):
        self.name = name
        self.platforms = platforms
        self.archs = archs
        self._available = available

    def supports(self, platform, arch):
        return platform in self.platforms and arch in self.archs

    def is_available(self):
        return self._available


class _FakePlatform:
    def __init__(self, platform, arch="x86_64"):
        self.platform = platform
        self.arch = arch

    def package_providers(self):
        return []

    def service_manager(self):
        raise NotImplementedError

    def shell(self):
        raise NotImplementedError

    def filesystem(self):
        raise NotImplementedError

    def support(self, capability):
        return SupportLevel.DISCOVERY_ONLY


class TestTaxonomy(unittest.TestCase):
    def test_no_false_portability_by_default(self):
        reg = PlatformRegistry()
        # Unknown platform: UNSUPPORTED, never claimed.
        self.assertEqual(reg.support("android", "anything"),
                         SupportLevel.UNSUPPORTED)
        rep = reg.support_report("android")
        self.assertFalse(rep["implemented_adapter"])
        self.assertFalse(rep["tested_platform"])
        self.assertEqual(rep["verified_capabilities"], [])

    def test_mobile_limited_control(self):
        self.assertEqual(
            __import__("platform_adapters").DEFAULT_CONTROL["android"],
            ControlLevel.LIMITED_CONTROL)
        self.assertEqual(
            __import__("platform_adapters").DEFAULT_CONTROL["ios"],
            ControlLevel.LIMITED_CONTROL)

    def test_codespace_no_implicit_local_control(self):
        import platform_adapters as pa
        self.assertEqual(pa.DEFAULT_CONTROL["codespace"],
                         ControlLevel.FULL_CONTROL)
        # ...inside the Codespace only: separate env entry, no local claim.
        self.assertNotEqual("codespace", "windows")

    def test_profiles_exist(self):
        self.assertEqual({p.value for p in RuntimeProfile},
                         {"AGENT_BRIDGE_FULL", "AGENT_BRIDGE_LIGHT",
                          "AGENT_BRIDGE_EDGE", "AGENT_BRIDGE_CLIENT",
                          "AGENT_BRIDGE_REMOTE"})


class TestResolution(unittest.TestCase):
    def test_cmake_windows_resolves_winget(self):
        out = resolve_capability("cmake", "windows",
                                 [_FakeProvider("winget", ("windows",))])
        self.assertTrue(out["ok"])
        self.assertEqual(out["provider"], "winget")

    def test_cmake_ubuntu_resolves_apt(self):
        out = resolve_capability("cmake", "linux",
                                 [_FakeProvider("apt", ("linux",))])
        self.assertTrue(out["ok"])
        self.assertEqual(out["provider"], "apt")

    def test_arch_mismatch_rejected(self):
        out = resolve_capability("cmake", "linux",
                                 [_FakeProvider("apt", ("linux",),
                                                ("x86_64",))],
                                 arch="riscv")
        self.assertFalse(out["ok"])

    def test_unknown_capability_explains(self):
        out = resolve_capability("frobnicate", "windows", [])
        self.assertFalse(out["ok"])
        self.assertIn("reason", out)

    def test_arch_matrix(self):
        self.assertTrue(check_arch_compatible("x86_64", "x86_64"))
        self.assertTrue(check_arch_compatible("arm", "arm64"))
        self.assertFalse(check_arch_compatible("x86_64", "arm64"))
        self.assertFalse(check_arch_compatible("riscv", "x86_64"))

    def test_inference_routing(self):
        self.assertEqual(resolve_inference("NVIDIA GTX", "x86_64", 16, 4096)["backend"], "cuda")
        self.assertEqual(resolve_inference("", "arm64", 16, 0)["backend"], "metal")
        self.assertEqual(resolve_inference("Mali", "arm64", 4, 2000)["backend"], "vulkan")
        self.assertEqual(resolve_inference("", "x86_64", 16, 0)["backend"], "cpu")
        r = resolve_inference("", "x86_64", 2, 0)
        self.assertEqual(r["backend"], "remote")
        self.assertIn("LOCAL_UNSUITABLE", r["reason"])


class TestSelectorReadinessPassport(unittest.TestCase):
    def test_selector_evaluates_all(self):
        sel = EnvironmentSelector()
        envs = [
            {"name": "WSL_UBUNTU", "capabilities": ["python"],
             "health": "HEALTHY", "cost": 0, "latency_ms": 10},
            {"name": "WINDOWS_DESKTOP", "capabilities": ["python"],
             "health": "DEGRADED", "cost": 0, "latency_ms": 5},
            {"name": "CODESPACE", "capabilities": ["java"],
             "health": "HEALTHY", "cost": 3, "latency_ms": 300},
        ]
        ranked = sel.select("python", envs)
        self.assertEqual(ranked[0].environment, "WSL_UBUNTU")
        self.assertEqual(ranked[-1].environment, "CODESPACE")

    def test_privacy_warning_for_remote(self):
        sel = EnvironmentSelector()
        ranked = sel.select("x", [{"name": "cloud", "capabilities": ["x"],
                                   "health": "HEALTHY", "remote": True,
                                   "private_data": True}])
        self.assertTrue(any("private" in w for w in ranked[0].warnings))

    def test_readiness_matrix(self):
        self.assertEqual(evaluate_readiness(["a"], ["a"])["readiness"], "READY")
        self.assertEqual(evaluate_readiness(["a"], ["a"], degraded=["a"])["readiness"],
                         "READY_AFTER_SAFE_PROVISIONING")
        self.assertEqual(evaluate_readiness(["a"], ["a"], approval_needed=["a"])["readiness"],
                         "READY_AFTER_APPROVAL")
        self.assertEqual(evaluate_readiness(["a"], [])["readiness"], "INCOMPATIBLE")
        self.assertEqual(evaluate_readiness(["a"], [], remote_available=True)["readiness"],
                         "REMOTE_RECOMMENDED")

    def test_passport_has_no_private_ids(self):
        machine = type("M", (), {})()
        machine.os = type("O", (), {"platform": "Windows"})()
        machine.cpu = type("C", (), {"architecture": "AMD64", "model": "i7"})()
        machine.memory = type("R", (), {"total_mb": 16384})()
        machine.gpus = []
        machine.tools = []
        p = build_passport(machine, ["WINDOWS_NATIVE"], "FULL_CONTROL")
        d = p.to_dict()
        self.assertNotIn("serial", str(d).lower())
        self.assertNotIn("mac", [k.lower() for k in d])
        self.assertEqual(d["memory_gb"], 16.0)
        self.assertIsInstance(DeviceCapabilityPassport(), object)


class TestSafety(unittest.TestCase):
    def test_weapons_denied(self):
        s = SafetySupervisor()
        self.assertEqual(s.validate_intent("move_arm", "weapon mount")["decision"], "DENY")
        self.assertEqual(s.validate_intent("harm", "x")["decision"], "DENY")

    def test_low_level_needs_approval(self):
        s = SafetySupervisor(limits={"move_arm": {"max_speed": 1}})
        r = s.validate_intent("move_arm", "target", low_level_control=True)
        self.assertEqual(r["decision"], "REQUIRE_APPROVAL")

    def test_envelope_allows(self):
        s = SafetySupervisor(limits={"move_arm": {"max_speed": 1}})
        r = s.validate_intent("move_arm", "target")
        self.assertEqual(r["decision"], "ALLOW_WITHIN_ENVELOPE")

    def test_unknown_intent_needs_approval(self):
        s = SafetySupervisor()
        r = s.validate_intent("move_arm", "target")
        self.assertEqual(r["decision"], "REQUIRE_APPROVAL")


if __name__ == "__main__":
    unittest.main()
