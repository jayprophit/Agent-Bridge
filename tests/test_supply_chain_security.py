"""v0.9.0 supply-chain security contract tests (mocked, no I/O)."""
import unittest

from supply_chain_security import (
    AUTOMATION_PRINCIPLE,
    MCPInspector,
    PermissionManifest,
    PermissionPolicy,
    PIPELINE_STAGES,
    SecurityFinding,
    SecurityScannerAdapter,
    Severity,
    SkillRecord,
    SkillRegistry,
    SupplyChainRecord,
    TrustState,
    advance_trust,
    gate_pipeline,
    review_update,
)


class FakeScanner(SecurityScannerAdapter):
    scanner_id = "fake"
    specialises = ("skills",)

    def __init__(self, findings):
        self._findings = findings

    def scan(self, target):
        return list(self._findings)


class TestTrustMachine(unittest.TestCase):
    def test_legal_path(self):
        state = TrustState.UNKNOWN
        for nxt in (TrustState.DISCOVERED, TrustState.SCANNED,
                    TrustState.STAGED, TrustState.VERIFIED,
                    TrustState.APPROVED, TrustState.TRUSTED_VERSION):
            state = advance_trust(state, nxt)
        self.assertEqual(state, TrustState.TRUSTED_VERSION)

    def test_no_jumps(self):
        with self.assertRaises(ValueError):
            advance_trust(TrustState.UNKNOWN, TrustState.TRUSTED_VERSION)
        with self.assertRaises(ValueError):
            advance_trust(TrustState.DISCOVERED, TrustState.APPROVED)

    def test_revocation_terminal(self):
        self.assertEqual(
            advance_trust(TrustState.APPROVED, TrustState.REVOKED),
            TrustState.REVOKED)
        with self.assertRaises(ValueError):
            advance_trust(TrustState.REVOKED, TrustState.VERIFIED)

    def test_version_binding(self):
        rec = SkillRecord(skill_id="s", version="1.0", commit="aaa",
                          trust=TrustState.TRUSTED_VERSION)
        self.assertFalse(rec.needs_rescan("1.0", "aaa"))
        self.assertTrue(rec.needs_rescan("1.1", "aaa"))
        self.assertTrue(rec.needs_rescan("1.0", "bbb"))


class TestRegistryPopularity(unittest.TestCase):
    def test_unknown_skill_not_trusted(self):
        reg = SkillRegistry()
        self.assertFalse(reg.trusted("famous-skill", "9.9", "zzz"))

    def test_trust_requires_exact_version(self):
        reg = SkillRegistry()
        reg.register(SkillRecord(skill_id="s", version="1.0", commit="aaa",
                                 trust=TrustState.TRUSTED_VERSION))
        self.assertTrue(reg.trusted("s", "1.0", "aaa"))
        self.assertFalse(reg.trusted("s", "1.1", "aaa"))

    def test_set_trust_follows_machine(self):
        reg = SkillRegistry()
        reg.register(SkillRecord(skill_id="s"))
        with self.assertRaises(ValueError):
            reg.set_trust("s", TrustState.APPROVED)
        reg.set_trust("s", TrustState.DISCOVERED)
        self.assertEqual(reg.get("s").trust, TrustState.DISCOVERED)


class TestPermissionsMCP(unittest.TestCase):
    def test_least_privilege(self):
        policy = PermissionPolicy()
        ok = policy.check(PermissionManifest(component="x",
                                             permissions=("filesystem.read",)))
        self.assertEqual(ok["decision"], "ALLOW")
        bad = policy.check(PermissionManifest(component="x", permissions=(
            "shell.execute", "secrets.request")))
        self.assertEqual(bad["decision"], "REQUIRE_APPROVAL")
        self.assertIn("shell.execute", bad["denied"])

    def test_mcp_shell_blocked(self):
        r = MCPInspector.inspect({"name": "t", "shell": True})
        self.assertEqual(r["decision"], "BLOCK")

    def test_mcp_network_sandboxed(self):
        r = MCPInspector.inspect({"name": "t", "network": True})
        self.assertEqual(r["decision"], "SANDBOX")

    def test_mcp_plain_needs_approval(self):
        r = MCPInspector.inspect({"name": "t"})
        self.assertEqual(r["decision"], "REQUIRE_APPROVAL")


class TestUpdatesPipeline(unittest.TestCase):
    def test_update_review(self):
        old = SupplyChainRecord(version="1.0", permissions=("filesystem.read",))
        self.assertEqual(review_update(old, {"version": "1.0",
                                             "permissions": ("filesystem.read",),
                                             "dependencies": None,
                                             "binaries": None})["decision"],
                         "KEEP_TRUST")
        self.assertEqual(review_update(old, {"version": "1.1",
                                             "permissions": ("shell.execute",),
                                             "dependencies": None,
                                             "binaries": None})["decision"],
                         "RENEW_APPROVAL")

    def test_pipeline_clean_allows(self):
        out = gate_pipeline({"id": "s", "permissions": ("filesystem.read",)},
                            [FakeScanner([])], PermissionPolicy())
        self.assertEqual(out["decision"], "ALLOW")
        self.assertEqual(out["stages"], list(PIPELINE_STAGES))

    def test_pipeline_critical_blocks(self):
        out = gate_pipeline(
            {"id": "s", "permissions": ("filesystem.read",)},
            [FakeScanner([SecurityFinding("TOOL_POISONING", Severity.CRITICAL,
                                          "evil", "block")])],
            PermissionPolicy())
        self.assertEqual(out["decision"], "BLOCK")
        self.assertEqual(out["worst_severity"], "CRITICAL")

    def test_automation_principle(self):
        self.assertIn("PROPORTIONAL", AUTOMATION_PRINCIPLE)


if __name__ == "__main__":
    unittest.main()
