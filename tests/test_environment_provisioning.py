"""v0.9.0 provisioning manager tests (mocked; never mutates the machine)."""
import unittest
from unittest import mock

from environment_provisioning import (
    AGENT_BRIDGE_REQUIREMENTS,
    AutoFix,
    BinaryAdapter,
    CapabilityAdapter,
    ConfigAmendment,
    ConfigurationApplier,
    Detection,
    DockerManager,
    DriverManager,
    FirmwareManager,
    HealthState,
    KubernetesManager,
    MaintenanceMode,
    MaintenancePolicy,
    MaintenanceSettings,
    PackageManagerAdapters,
    PlanStep,
    PolicyDecision,
    ProvisionGraph,
    ProvisionNode,
    RemoteRouter,
    RequiredCapability,
    RequirementKind,
    ResourceAdvisor,
    UpdateDecider,
    UpdateDecision,
    WindowsFeatureManager,
    build_provision_plan,
    prepare_self_requirements,
    provision_for_project,
    verify_provisioning,
)
from machine_maintenance import ActionKind


class TestAdapters(unittest.TestCase):
    def test_binary_adapter_missing_plans_install(self):
        a = BinaryAdapter("kubectl", "kubectl")
        with mock.patch("environment_provisioning.shutil.which", return_value=None):
            det = a.detect()
        self.assertFalse(det.present)
        req = RequiredCapability(name="kubectl", required_by="proj")
        steps = a.plan(req, det)
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].action, ActionKind.INSTALL)

    def test_binary_adapter_present_no_steps(self):
        a = BinaryAdapter("git", "git")
        with mock.patch("environment_provisioning.shutil.which",
                         return_value="/usr/bin/git"):
            det = a.detect()
        self.assertTrue(det.present)
        req = RequiredCapability(name="git", required_by="proj")
        self.assertEqual(a.plan(req, det), [])

    def test_optional_missing_no_steps(self):
        a = BinaryAdapter("podman", "podman")
        det = Detection(capability="podman", present=False, state=HealthState.MISSING)
        req = RequiredCapability(name="podman", required_by="proj", optional=True)
        self.assertEqual(a.plan(req, det), [])


class TestGraph(unittest.TestCase):
    def test_ordered_dependencies_first(self):
        g = ProvisionGraph()
        g.add(ProvisionNode(capability="helm", depends_on=["kubectl"]))
        g.add(ProvisionNode(capability="kubectl", depends_on=["docker"]))
        g.add(ProvisionNode(capability="docker"))
        self.assertEqual([n.capability for n in g.ordered()],
                         ["docker", "kubectl", "helm"])

    def test_cycle_rejected(self):
        g = ProvisionGraph()
        g.add(ProvisionNode(capability="a", depends_on=["b"]))
        g.add(ProvisionNode(capability="b", depends_on=["a"]))
        with self.assertRaises(ValueError):
            g.ordered()

    def test_stop_when_dependency_fails(self):
        g = ProvisionGraph()
        ok_step = PlanStep(action=ActionKind.REPAIR, tool="docker", reason="x")
        bad_step = PlanStep(action=ActionKind.INSTALL, tool="kubectl", reason="x")
        g.add(ProvisionNode(capability="docker", steps=[ok_step]))
        g.add(ProvisionNode(capability="kubectl", depends_on=["docker"],
                            steps=[bad_step]))

        def runner(step):
            return {"ok": step.tool == "docker"}

        out = g.execute(runner)
        self.assertFalse(out["ok"])
        self.assertEqual(out["failed"], "kubectl")
        self.assertEqual(out["completed"], ["docker"])

    def test_build_plan_compares_requirements(self):
        reqs = [RequiredCapability(name="kubectl", required_by="t")]
        dets = {"kubectl": Detection(capability="kubectl", present=False,
                                     state=HealthState.MISSING)}
        with mock.patch("environment_provisioning.shutil.which",
                         return_value=None):
            g = build_provision_plan(reqs, dets)
        nodes = g.ordered()
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0].steps[0].action, ActionKind.INSTALL)

    def test_unknown_capability_yields_no_fabricated_steps(self):
        reqs = [RequiredCapability(name="x-tool", required_by="t")]
        dets = {"x-tool": Detection(capability="x-tool", present=False,
                                    state=HealthState.MISSING)}
        g = build_provision_plan(reqs, dets)
        self.assertEqual(g.ordered()[0].steps, [])


class TestDockerManager(unittest.TestCase):
    def _mgr(self, outputs):
        return DockerManager(runner=lambda cmd: outputs.get(cmd[1], {"ok": False}))

    def test_plan_never_deletes_user_resources(self):
        m = self._mgr({"version": {"ok": True}, "compose": {"ok": True},
                       "context": {"ok": True, "stdout": "default"}})
        for step in m.plan_repairs():
            blob = " ".join(step.command).lower()
            for forbidden in (" rm ", " rmi ", "volume rm", "network rm",
                              "system prune", "builder prune"):
                self.assertNotIn(forbidden, blob)
            self.assertNotEqual(step.action.value, "DELETE")

    def test_daemon_down_plans_restart_not_reinstall(self):
        m = DockerManager(runner=lambda cmd: {"ok": cmd[1] == "version"})
        # version probe fails -> daemon False; cli present is faked below
        with mock.patch.object(DockerManager, "detect", return_value={
                "cli_present": True, "cli_path": "docker", "compose_present": True,
                "daemon": False, "contexts": [], "wsl_backend": False}):
            steps = m.plan_repairs()
        kinds = [s.action for s in steps]
        self.assertIn(ActionKind.SERVICE_RESTART, kinds)
        self.assertNotIn(ActionKind.INSTALL, kinds)


class TestKubernetesManager(unittest.TestCase):
    def test_compose_preferred_when_no_k8s_apis(self):
        m = KubernetesManager(runner=lambda cmd: {"ok": False})
        self.assertEqual(m.select_lightest(False), "compose")

    def test_lightest_existing_provider_wins(self):
        m = KubernetesManager(runner=lambda cmd: {"ok": False})
        with mock.patch.object(KubernetesManager, "detect", return_value={
                "kubectl": True, "helm": False, "kubeconfig": True,
                "contexts": [], "current_context": "", "api_reachable": False,
                "nodes": [], "providers": {"kind": False, "k3d": True,
                                           "minikube": False, "compose": True}}):
            self.assertEqual(m.select_lightest(True), "k3d")

    def test_plan_installs_kubectl_when_missing(self):
        m = KubernetesManager(runner=lambda cmd: {"ok": False})
        with mock.patch.object(KubernetesManager, "detect", return_value={
                "kubectl": False, "helm": False, "kubeconfig": False,
                "contexts": [], "current_context": "", "api_reachable": False,
                "nodes": [], "providers": {"kind": False, "k3d": False,
                                           "minikube": False, "compose": True}}):
            steps = m.plan(True)
        tools = [s.tool for s in steps]
        self.assertIn("kubectl", tools)


class TestPackagesConfigAutofix(unittest.TestCase):
    def test_preflight_prefers_existing(self):
        r = PackageManagerAdapters.preflight("make", "winget", is_present=True)
        self.assertEqual(r["decision"], "KEEP")
        r = PackageManagerAdapters.preflight("make", "winget",
                                             equivalent="mingw32-make")
        self.assertEqual(r["decision"], "KEEP")
        r = PackageManagerAdapters.preflight("huge-sdk", "winget",
                                             disk_mb_needed=10 ** 12)
        self.assertEqual(r["decision"], "DEFER")
        r = PackageManagerAdapters.preflight("nope", "random-mirror")
        self.assertFalse(r["ok"])

    def test_autofix_diagnosis(self):
        d = AutoFix.diagnose("cmake", "'cmake' is not recognized")
        self.assertIn("cmake", d["repair"])
        d = AutoFix.diagnose("node", "some totally novel trace")
        self.assertEqual(d["root_cause"], "unknown")
        self.assertEqual(AutoFix.plan_for("node", "novel"), [])

    def test_config_dry_run_by_default(self):
        applier = ConfigurationApplier(MaintenancePolicy(
            MaintenanceSettings(mode=MaintenanceMode.AUTO_SAFE)))
        out = applier.apply(ConfigAmendment(target="PATH", operation="APPEND_PATH",
                                            value="C:\\x"))
        self.assertTrue(out["dry_run"])


class TestUpdatesFirmwareDriversFeatures(unittest.TestCase):
    def test_update_matrix(self):
        self.assertEqual(UpdateDecider.decide("1.0", "1.0"), UpdateDecision.KEEP)
        self.assertEqual(UpdateDecider.decide("1.0", "2.0"), UpdateDecision.DEFER)
        self.assertEqual(UpdateDecider.decide("1.0", "2.0", security=True),
                         UpdateDecision.UPDATE)
        self.assertEqual(UpdateDecider.decide("1.0", "2.0", required_feature=True),
                         UpdateDecision.UPDATE)
        self.assertEqual(UpdateDecider.decide("1.0", "2.0", breaks_others=True,
                                              side_by_side_possible=True),
                         UpdateDecision.SIDE_BY_SIDE)
        self.assertEqual(UpdateDecider.decide("1.0", "2.0", breaks_others=True),
                         UpdateDecision.REQUIRES_APPROVAL)

    def test_firmware_drivers_always_gated(self):
        for mode in MaintenanceMode:
            s = MaintenanceSettings(mode=mode)
            fw = FirmwareManager(MaintenancePolicy(s)).check("BIOS", "1", "2")
            dv = DriverManager(MaintenancePolicy(s)).check("GPU", "1", "2")
            if mode == MaintenanceMode.OFF:
                self.assertEqual(fw["decision"], "DENY")
                self.assertEqual(dv["decision"], "DENY")
            else:
                self.assertEqual(fw["decision"], "REQUIRE_APPROVAL")
                self.assertEqual(dv["decision"], "REQUIRE_APPROVAL")

    def test_windows_features_gated(self):
        out = WindowsFeatureManager(MaintenancePolicy(
            MaintenanceSettings(mode=MaintenanceMode.AUTO_MANAGED))).require(
                "VirtualMachinePlatform", "wsl2 backend")
        self.assertEqual(out["decision"], "REQUIRE_APPROVAL")


class TestRoutingSelfVerify(unittest.TestCase):
    def test_resource_advisor(self):
        self.assertEqual(ResourceAdvisor.advise(
            {"ram_gb": 16, "free_disk_gb": 500})["place"], "local")
        self.assertEqual(ResourceAdvisor.advise(
            {"ram_gb": 16, "free_disk_gb": 4})["place"], "remote")
        self.assertEqual(ResourceAdvisor.advise(
            {"ram_gb": 4, "free_disk_gb": 500}, needs_k8s_apis=True)["place"],
            "compose-or-remote")

    def test_remote_router(self):
        r = RemoteRouter.route("gpu-train", True, ["local"])
        self.assertEqual(r["route"], "local")
        r = RemoteRouter.route("gpu-train", False, ["local", "wsl", "docker"])
        self.assertEqual(r["route"], "wsl")
        r = RemoteRouter.route("gpu-train", False, ["local"])
        self.assertIn("register", r["reason"])

    def test_self_requirements_no_bypass(self):
        out = prepare_self_requirements(
            MaintenanceSettings(mode=MaintenanceMode.ASK), {})
        self.assertFalse(out["privileged_bypass"])
        self.assertTrue(out["steps"])
        self.assertTrue(all(d == "REQUIRE_APPROVAL" for d in out["decisions"]))
        names = [r.name for r in AGENT_BRIDGE_REQUIREMENTS]
        self.assertIn("git", names)
        self.assertIn("python", names)

    def test_verify_gates(self):
        out = verify_provisioning({
            "cli": lambda: {"ok": True},
            "daemon": lambda: {"ok": False, "stage": "connect"},
        })
        self.assertFalse(out["ok"])
        self.assertTrue(out["checks"]["cli"]["ok"])
        self.assertFalse(out["checks"]["daemon"]["ok"])

    def test_provision_dry_run(self):
        import tempfile as _tf
        from pathlib import Path as _P
        tmp = _P(_tf.mkdtemp(prefix="v090_prov_"))
        try:
            (tmp / "Dockerfile").write_text("FROM x\n")
            (tmp / "a.py").write_text("x=1\n")
            out = provision_for_project(
                str(tmp), MaintenanceSettings(mode=MaintenanceMode.ASK),
                dry_run=True)
            self.assertTrue(out["dry_run"])
            self.assertGreaterEqual(out["steps"], 0)
        finally:
            import shutil as _s
            _s.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
