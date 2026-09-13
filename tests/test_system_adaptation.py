"""v0.9.0 system adaptation tests (mocked; no kernel/disk/firmware touch)."""
import unittest

from system_adaptation import (
    ARCHITECTURE_PRINCIPLES,
    AETHERIUS_MATURITY,
    AetheriusBootAdapter,
    AetheriusKernelAdapter,
    AetheriusPackageAdapter,
    AetheriusPlatformAdapter,
    KernelCapability,
    LinuxKernelAdapter,
    LOCKED_SENTENCE,
    MOBILE_CONSTRAINTS,
    OptimizationAction,
    PASSPORT_SYSTEM_FIELDS,
    ROADMAP,
    ResourceSnapshot,
    RiskLevel,
    StaticHardwareAdapter,
    SystemAdaptationLayer,
    SystemOptimizer,
    WindowsKernelAdapter,
    extend_passport,
    maturity_report,
    risk_decision,
)


class TestLockedArchitecture(unittest.TestCase):
    def test_locked_sentence(self):
        self.assertIn("without requiring a host operating system", LOCKED_SENTENCE)

    def test_principles_count(self):
        self.assertGreaterEqual(len(ARCHITECTURE_PRINCIPLES), 14)

    def test_roadmap_stages(self):
        stages = [s for s, _ in ROADMAP]
        self.assertEqual(stages[0], "STAGE A")
        self.assertEqual(stages[-1], "STAGE J")
        self.assertEqual(len(stages), 10)


class TestRiskLevels(unittest.TestCase):
    def test_l0_always_allowed(self):
        self.assertEqual(risk_decision(RiskLevel.L0_READ_ONLY), "ALLOW")

    def test_l1_l2_need_policy(self):
        self.assertEqual(risk_decision(RiskLevel.L1_USER_SPACE_SAFE, False),
                         "REQUIRE_APPROVAL")
        self.assertEqual(risk_decision(RiskLevel.L1_USER_SPACE_SAFE, True), "ALLOW")
        self.assertEqual(risk_decision(RiskLevel.L2_OS_CONFIGURATION, True), "ALLOW")

    def test_l3_plus_never_auto(self):
        for lvl in (RiskLevel.L3_DRIVER_OR_KERNEL, RiskLevel.L4_KERNEL_DEVELOPMENT,
                    RiskLevel.L5_FIRMWARE_BOOT_DISK):
            self.assertNotEqual(risk_decision(lvl, True), "ALLOW")


class TestKernelContracts(unittest.TestCase):
    def test_windows_no_kernel_replace(self):
        a = WindowsKernelAdapter()
        self.assertEqual(a.level(), KernelCapability.CONFIGURATION_ONLY)
        self.assertEqual(a.facilities()["kernel patch/replacement"], "NOT_AVAILABLE")
        self.assertIn("Job Objects", a.facilities())

    def test_linux_no_auto_modules(self):
        a = LinuxKernelAdapter()
        self.assertEqual(a.facilities()["arbitrary module loading"],
                         "DEVELOPMENT_ONLY")
        self.assertEqual(a.facilities()["cgroups"], "CONFIGURATION_ONLY")

    def test_mobile_sandboxed(self):
        self.assertIn("LIMITED_CONTROL", MOBILE_CONSTRAINTS["android"])
        self.assertIn("LIMITED_CONTROL", MOBILE_CONSTRAINTS["ios"])


class TestOptimizer(unittest.TestCase):
    def test_headroom_executes(self):
        from system_adaptation import ResourcePlacementEngine
        snap = ResourceSnapshot(ram_total_gb=16, ram_free_gb=9,
                                consumers_gb={"ide": 2})
        acts = ResourcePlacementEngine.plan(snap, 4)
        self.assertEqual(acts[0].action, "execute")

    def test_spec_example_reclaims_then_routes(self):
        # IDE 2 + browser 3 + model 5 + docker 4 = 14 of 16GB; build needs 4.
        from system_adaptation import ResourcePlacementEngine
        snap = ResourceSnapshot(
            ram_total_gb=16, ram_free_gb=2,
            consumers_gb={"ide": 2, "browser": 3, "ai-model": 5,
                          "docker-disposable": 4})
        acts = ResourcePlacementEngine.plan(snap, 4, ["codespace"])
        kinds = [a.action for a in acts]
        self.assertIn("release", kinds)
        self.assertTrue(all(isinstance(a, OptimizationAction) for a in acts))

    def test_optimizer_shape(self):
        out = SystemOptimizer().optimize(ResourceSnapshot(ram_free_gb=20), 2)
        self.assertIn("actions", out)
        self.assertIn("principle", out)


class TestPassportLayerAetherius(unittest.TestCase):
    def test_passport_extension_fields(self):
        base = {"device_class": "desktop"}
        out = extend_passport(base, {"kernel_family": "nt"})
        for name in PASSPORT_SYSTEM_FIELDS:
            self.assertIn(name, out)
        self.assertEqual(out["kernel_family"], "nt")
        self.assertEqual(out["device_class"], "desktop")

    def test_layer_delegates(self):
        d = SystemAdaptationLayer(machine=object()).describe()
        self.assertEqual(d["layer"], "SystemAdaptationLayer")
        self.assertIn("MachineCapabilityRegistry", d["delegates"])

    def test_hardware_adapter_passthrough(self):
        snap = {"architecture": "x86_64", "cpu": "i7", "secret_serial": "X"}
        out = StaticHardwareAdapter(snap).detect()
        self.assertEqual(out["cpu"], "i7")
        self.assertNotIn("secret_serial", out)

    def test_aetherius_honest(self):
        for cls in (AetheriusPlatformAdapter, AetheriusPackageAdapter,
                    AetheriusKernelAdapter, AetheriusBootAdapter):
            a = cls()
            self.assertEqual(a.support("anything"), "PLANNED")
            self.assertEqual(a.maturity, "DEFINED_CONTRACT")
        rep = maturity_report()
        self.assertFalse(rep["aetherius"]["production_ready"])
        self.assertEqual(rep["aetherius"]["standalone_os"], "NOT_IMPLEMENTED")
        self.assertEqual(rep["aetherius"]["initial_kernel_strategy"],
                         "LINUX_KERNEL_FOUNDATION")
        self.assertFalse(rep["host_os_dependency_final"])
        self.assertIn("standalone_requirement_locked", rep)


class TestNativeKernelAmendment(unittest.TestCase):
    def test_strategy_amendment(self):
        import system_adaptation as sa
        self.assertEqual(sa.AETHERIUS_BOOTSTRAP_KERNEL_STRATEGY,
                         "LINUX_KERNEL_FOUNDATION")
        self.assertEqual(sa.AETHERIUS_FINAL_KERNEL_STRATEGY,
                         "AETHERIUS_NATIVE_KERNEL")
        self.assertFalse(sa.maturity_report()["host_os_dependency_final"])

    def test_trit_pack_roundtrip(self):
        import system_adaptation as sa
        trits = [-1, 0, 1, 1, -1, 0]
        self.assertEqual(sa.unpack_trits(sa.pack_trits(trits), len(trits)), trits)
        with self.assertRaises(ValueError):
            sa.pack_trits([2])

    def test_ternary_add(self):
        import system_adaptation as sa
        # 1 + 1 = 2 -> digits (least-first): [-1, 1] (i.e. -1 + 3)
        self.assertEqual(sa.ternary_add([1], [1]), [-1, 1])
        self.assertEqual(sa.ternary_add([0], [0]), [0])
        self.assertEqual(sa.ternary_add([-1], [1]), [0])

    def test_capability_routing_not_backend(self):
        import system_adaptation as sa
        r = sa.UnifiedComputeArchitecture.request(
            "search", {"quantum_suitable": True}, {})
        self.assertEqual(r["domain"], "BINARY")
        self.assertIn("QUANTUM_BACKEND_NOT_AVAILABLE", r["note"])
        r = sa.UnifiedComputeArchitecture.request(
            "search", {"quantum_suitable": True},
            {"quantum_simulator": True})
        self.assertEqual(r["backend"], "SIMULATOR")
        r = sa.UnifiedComputeArchitecture.request(
            "infer", {"low_bit_inference": True}, {"ternary": True})
        self.assertEqual(r["domain"], "TERNARY")

    def test_execution_planner(self):
        import system_adaptation as sa
        out = sa.ExecutionPlanner.plan({"name": "t", "needs_control_io": True}, {})
        self.assertEqual(out["workload"], "BINARY_ONLY")
        out = sa.ExecutionPlanner.plan(
            {"name": "t", "needs_control_io": True, "needs_lowbit": True}, {})
        self.assertEqual(out["workload"], "HYBRID")

    def test_research_map_present(self):
        import system_adaptation as sa
        for area in ("scheduling", "ternary compute", "quantum compute interfaces"):
            self.assertIn(area, sa.KERNEL_RESEARCH_AREAS)
        self.assertIn("microkernel", sa.KERNEL_ARCH_OPTIONS)
        self.assertEqual(sa.KERNEL_MILESTONES[0], "boot")
        self.assertIn("progressively migrate services",
                      " ".join(sa.MIGRATION_PATH))

    def test_passport_compute_fields(self):
        import system_adaptation as sa
        out = sa.extend_passport({}, {"ternary_compute": "emulated"})
        self.assertEqual(out["ternary_compute"], "emulated")
        for name in sa.PASSPORT_COMPUTE_FIELDS:
            self.assertIn(name, out)


if __name__ == "__main__":
    unittest.main()
