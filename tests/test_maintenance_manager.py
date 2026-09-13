"""v0.9.0 maintenance manager tests (mocked; never mutates the machine)."""
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from machine_maintenance import (
    ALWAYS_REQUIRE_APPROVAL,
    ActionKind,
    AuditRecord,
    CapabilityFinding,
    ConfigurationManager,
    HealthState,
    InstallationManager,
    MachineHealthAnalyzer,
    MachineImprovementPlanner,
    MaintenanceHistory,
    MaintenanceMode,
    MaintenancePolicy,
    MaintenanceSettings,
    PlanStep,
    PolicyDecision,
    RepairManager,
    UpdateManager,
    VerificationManager,
    describe_schedule,
    prepare_project,
)


def _step(tool="make", action=ActionKind.REPAIR, risk="safe_local", admin=False,
          source="none"):
    return PlanStep(action=action, tool=tool, reason="test",
                    command=["echo", "hi"], source=source,
                    risk_class=risk, admin_required=admin,
                    verification=f"re-probe {tool}")


class TestPolicy(unittest.TestCase):
    def test_off_denies_everything(self):
        p = MaintenancePolicy(MaintenanceSettings(mode=MaintenanceMode.OFF))
        self.assertEqual(p.decide(_step()), PolicyDecision.DENY)

    def test_disabled_denies(self):
        p = MaintenancePolicy(MaintenanceSettings(enabled=False,
                                                  mode=MaintenanceMode.AUTO_SAFE))
        self.assertEqual(p.decide(_step()), PolicyDecision.DENY)

    def test_ask_requires_approval(self):
        p = MaintenancePolicy(MaintenanceSettings(mode=MaintenanceMode.ASK))
        self.assertEqual(p.decide(_step()), PolicyDecision.REQUIRE_APPROVAL)

    def test_auto_safe_allows_safe_repair(self):
        p = MaintenancePolicy(MaintenanceSettings(mode=MaintenanceMode.AUTO_SAFE))
        self.assertEqual(p.decide(_step()), PolicyDecision.ALLOW)

    def test_firmware_always_requires_approval(self):
        for mode in MaintenanceMode:
            p = MaintenancePolicy(MaintenanceSettings(mode=mode))
            s = _step(tool="BIOS updater", risk="firmware")
            s2 = _step(tool="GPU driver", risk="driver")
            if mode == MaintenanceMode.OFF:
                # OFF denies everything outright (strictly safer than asking).
                self.assertEqual(p.decide(s), PolicyDecision.DENY, mode)
                self.assertEqual(p.decide(s2), PolicyDecision.DENY, mode)
            else:
                self.assertEqual(p.decide(s), PolicyDecision.REQUIRE_APPROVAL, mode)
                self.assertEqual(p.decide(s2), PolicyDecision.REQUIRE_APPROVAL, mode)

    def test_destructive_always_requires_approval(self):
        p = MaintenancePolicy(MaintenanceSettings(mode=MaintenanceMode.AUTO_MANAGED))
        for risk in sorted(ALWAYS_REQUIRE_APPROVAL):
            s = _step(tool="x", risk=risk)
            self.assertEqual(p.decide(s), PolicyDecision.REQUIRE_APPROVAL, risk)

    def test_admin_blocked_without_allowance(self):
        p = MaintenancePolicy(MaintenanceSettings(mode=MaintenanceMode.AUTO_SAFE,
                                                  allow_admin_operations=False))
        self.assertEqual(p.decide(_step(admin=True)), PolicyDecision.REQUIRE_APPROVAL)

    def test_category_gates(self):
        p = MaintenancePolicy(MaintenanceSettings(mode=MaintenanceMode.AUTO_SAFE,
                                                  allow_installs=False))
        self.assertEqual(p.decide(_step(action=ActionKind.INSTALL, source="winget")),
                         PolicyDecision.REQUIRE_APPROVAL)
        p2 = MaintenancePolicy(MaintenanceSettings(mode=MaintenanceMode.AUTO_SAFE,
                                                   allow_updates=False))
        self.assertEqual(p2.decide(_step(action=ActionKind.UPDATE, source="winget")),
                         PolicyDecision.REQUIRE_APPROVAL)

    def test_settings_defaults_require_approvals(self):
        s = MaintenanceSettings()
        self.assertTrue(s.require_driver_approval)
        self.assertTrue(s.require_firmware_approval)
        self.assertTrue(s.require_os_upgrade_approval)
        self.assertTrue(s.require_destructive_approval)
        self.assertTrue(s.verify_after_change)
        self.assertTrue(s.rollback_when_possible)
        self.assertTrue(s.prefer_existing_tools)
        self.assertTrue(s.avoid_duplicate_tools)


class TestAnalyzer(unittest.TestCase):
    def test_state_mapping(self):
        from machine_capability import ToolInfo
        machine = type("M", (), {})()
        machine.tools = [
            ToolInfo(name="a", executable="/x/a", version="1.0", working=True),
            ToolInfo(name="b", executable="/x/b", version="", working=False),
            ToolInfo(name="c", executable="", version="", working=False),
        ]
        findings = MachineHealthAnalyzer(machine).analyze({"a": ["proj"]})
        by_name = {f.capability: f for f in findings}
        self.assertEqual(by_name["a"].state, HealthState.HEALTHY)
        self.assertEqual(by_name["a"].required_by, ["proj"])
        self.assertEqual(by_name["b"].state, HealthState.PARTIALLY_WORKING)
        self.assertEqual(by_name["c"].state, HealthState.MISSING)


class TestPlanner(unittest.TestCase):
    def test_smallest_sufficient_no_duplicates(self):
        planner = MachineImprovementPlanner()
        findings = [
            CapabilityFinding(capability="make", state=HealthState.MISSING),
            CapabilityFinding(capability="make", state=HealthState.MISSING),
            CapabilityFinding(capability="python", state=HealthState.HEALTHY),
            CapabilityFinding(capability="node", state=HealthState.HEALTHY),
        ]
        steps = planner.plan(findings, ["make", "python"])
        self.assertEqual([s.tool for s in steps], ["make"])
        self.assertEqual(steps[0].action, ActionKind.INSTALL)

    def test_repairs_before_installs_deterministic(self):
        planner = MachineImprovementPlanner()
        findings = [
            CapabilityFinding(capability="z-tool", state=HealthState.MISSING),
            CapabilityFinding(capability="a-tool", state=HealthState.BROKEN,
                              root_cause="bad config"),
        ]
        steps = planner.plan(findings)
        self.assertEqual([s.tool for s in steps], ["a-tool", "z-tool"])

    def test_outdated_suggests_cautious_update(self):
        planner = MachineImprovementPlanner()
        steps = planner.plan([CapabilityFinding(capability="cmake",
                                                state=HealthState.OUTDATED_BUT_WORKING)])
        self.assertEqual(steps[0].action, ActionKind.UPDATE)
        self.assertIn("only if", steps[0].reason)


class TestManagers(unittest.TestCase):
    def _history(self):
        tmp = Path(tempfile.mkdtemp(prefix="v090_maint_"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        return MaintenanceHistory(tmp / "h.jsonl")

    def test_off_never_executes(self):
        calls = []
        m = RepairManager(MaintenancePolicy(MaintenanceSettings(mode=MaintenanceMode.OFF)),
                          self._history(), runner=lambda c: calls.append(c) or {"ok": True})
        out = m.execute(_step(), dry_run=False)
        self.assertFalse(out["ok"])
        self.assertEqual(calls, [])

    def test_ask_never_executes_without_approval(self):
        calls = []
        m = InstallationManager(
            MaintenancePolicy(MaintenanceSettings(mode=MaintenanceMode.ASK)),
            self._history(), runner=lambda c: calls.append(c) or {"ok": True})
        out = m.execute(_step(action=ActionKind.INSTALL, source="winget"), dry_run=False)
        self.assertEqual(out["decision"], "REQUIRE_APPROVAL")
        self.assertEqual(calls, [])

    def test_dry_run_records_without_running(self):
        calls = []
        m = UpdateManager(
            MaintenancePolicy(MaintenanceSettings(mode=MaintenanceMode.AUTO_SAFE)),
            self._history(), runner=lambda c: calls.append(c) or {"ok": True})
        out = m.execute(_step(action=ActionKind.UPDATE, source="winget"), dry_run=True)
        self.assertTrue(out["dry_run"])
        self.assertEqual(calls, [])

    def test_untrusted_source_refused(self):
        m = InstallationManager(
            MaintenancePolicy(MaintenanceSettings(mode=MaintenanceMode.AUTO_SAFE)),
            self._history(), runner=lambda c: {"ok": True})
        s = _step(action=ActionKind.INSTALL, source="http://random-mirror/evil")
        out = m.execute(s, dry_run=False)
        self.assertFalse(out["ok"])
        self.assertIn("untrusted", out["error"])

    def test_execute_success_records_history(self):
        h = self._history()
        m = ConfigurationManager(
            MaintenancePolicy(MaintenanceSettings(mode=MaintenanceMode.AUTO_SAFE)),
            h, runner=lambda c: {"ok": True, "stdout": "done"})
        out = m.execute(_step(), dry_run=False)
        self.assertTrue(out["ok"])
        self.assertEqual(len(h.read_all()), 1)
        self.assertEqual(h.read_all()[0]["requested_action"], "REPAIR:make")


class TestVerification(unittest.TestCase):
    def test_check_tool_mocked(self):
        v = VerificationManager(runner=lambda c: {"ok": True, "stdout": "v1"})
        r = v.check_tool("make", ["make", "--version"])
        self.assertTrue(r["ok"])

    def test_verify_plan_reprobe(self):
        v = VerificationManager()
        steps = [_step(tool="python")]
        with mock.patch("machine_maintenance.shutil.which",
                         return_value="/usr/bin/python"):
            out = v.verify_plan(steps)
        self.assertTrue(out[0]["ok"])


class TestScheduleAndProjectReady(unittest.TestCase):
    def test_triggers(self):
        for t in ("ON_DEMAND", "ON_PROJECT_OPEN", "ON_BUILD_FAILURE",
                  "ON_HEALTH_SCAN", "PERIODIC_CHECK"):
            r = describe_schedule(t)
            self.assertTrue(r["ok"])
            self.assertTrue(r["read_only_checks"])
        self.assertFalse(describe_schedule("ALWAYS_DAEMON")["ok"])

    def test_prepare_project_dry_run_no_mutation(self):
        import tempfile as _tf
        from pathlib import Path as _P
        tmp = _P(_tf.mkdtemp(prefix="v090_pr_"))
        try:
            (tmp / "pyproject.toml").write_text("[project]\nname='x'\n")
            (tmp / "a.py").write_text("x=1\n")
            from machine_capability import MachineCapability, ToolInfo
            fake = MachineCapability(tools=[
                ToolInfo(name="python", executable="/p", version="3.13",
                         category="interpreter", working=True, languages=["python"])])
            out = prepare_project(str(tmp),
                                  MaintenanceSettings(mode=MaintenanceMode.PROJECT_READY),
                                  machine=fake, dry_run=True)
            self.assertTrue(out["dry_run"])
            self.assertIn("python", out["project_languages"])
            self.assertEqual(out["executable_now"], [])
        finally:
            import shutil as _s
            _s.rmtree(tmp, ignore_errors=True)

    def test_history_defaults_under_local(self):
        h = MaintenanceHistory()
        self.assertIn("local", str(h.path))


if __name__ == "__main__":
    unittest.main()
