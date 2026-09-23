"""MCP adapter boundary tests (P21, REQ-mcp-adapter-boundary)."""
import unittest

import mcp_adapter
from mcp_adapter import (
    LoopbackTransport,
    MCPDiscoveryError,
    MCPUnavailable,
    MCPVersionError,
    SUPPORTED_MCP_VERSIONS,
    negotiate_version,
    parse_discovery,
    sse_transport,
    stdio_transport,
    to_bridge_capabilities,
    websocket_transport,
)
from protocol import validate_action

PAYLOAD = {
    "tools": [
        {"name": "read_file", "description": "Read a file", "input_schema": {"type": "object"}, "extra": 1},
        {"name": "list_dir"},
    ],
    "resources": [{"uri": "file:///docs", "name": "docs", "mimeType": "text/plain"}],
    "prompts": [{"name": "summarize", "description": "Summarize text"}],
}


class TestNegotiation(unittest.TestCase):
    def test_exact_and_highest_common(self):
        self.assertEqual(negotiate_version(["2025-03-26"], "2025-03-26"), "2025-03-26")
        self.assertEqual(
            negotiate_version(["2024-11-05", "2025-06-18"], "2024-11-05"), "2024-11-05"
        )
        # Our preference order wins among overlap: newest first.
        self.assertEqual(
            negotiate_version(["2024-11-05", "2025-06-18"], "2025-06-18"), "2025-06-18"
        )

    def test_no_overlap_fails_closed(self):
        with self.assertRaises(MCPVersionError):
            negotiate_version(["2024-11-05"], "1999-01-01")
        with self.assertRaises(MCPVersionError):
            negotiate_version([], "2025-03-26")
        with self.assertRaises(MCPVersionError):
            negotiate_version(["2025-03-26"], "  ")
        self.assertTrue(len(SUPPORTED_MCP_VERSIONS) >= 1)


class TestDiscovery(unittest.TestCase):
    def test_parse_typed_records_with_opaque_remainder(self):
        d = parse_discovery("srv", "2025-03-26", PAYLOAD)
        self.assertEqual(d.server, "srv")
        self.assertEqual(len(d.tools), 2)
        self.assertEqual(d.tools[0].name, "read_file")
        self.assertEqual(d.tools[0].raw, {"extra": 1})
        self.assertEqual(d.tools[1].description, "")
        self.assertEqual(d.resources[0].uri, "file:///docs")
        self.assertEqual(d.prompts[0].name, "summarize")

    def test_malformed_payloads_fail(self):
        with self.assertRaises(MCPDiscoveryError):
            parse_discovery("s", "v", {"tools": {"not": "a list"}})
        with self.assertRaises(MCPDiscoveryError):
            parse_discovery("s", "v", {"tools": [{"description": "no name"}]})
        with self.assertRaises(MCPDiscoveryError):
            parse_discovery("s", "v", {"resources": [{"name": "no uri"}]})
        with self.assertRaises(MCPDiscoveryError):
            parse_discovery("s", "v", ["not", "an", "object"])

    def test_loopback_serves_discovery_only(self):
        t = LoopbackTransport(PAYLOAD)
        self.assertTrue(t.simulated)
        d = t.discover("srv", "2025-03-26")
        self.assertEqual(len(d.tools), 2)
        with self.assertRaises(mcp_adapter.MCPError):
            t.request("tools/call", {})


class TestBridgeBoundary(unittest.TestCase):
    def test_descriptions_carry_source_never_authority(self):
        d = parse_discovery("srv", "2025-03-26", PAYLOAD)
        caps = to_bridge_capabilities(d)
        self.assertEqual(len(caps), 2 + 1 + 1)
        for cap in caps:
            self.assertTrue(cap.source.startswith("mcp:"))
            self.assertTrue(cap.capability.startswith("mcp."))
        kinds = sorted(c.mcp_kind for c in caps)
        self.assertEqual(kinds, ["prompt", "resource", "tool", "tool"])

    def test_adapter_has_no_execution_surface(self):
        for forbidden in ("execute", "grant", "approve", "authorize", "run_tool", "call_tool"):
            self.assertFalse(hasattr(mcp_adapter, forbidden), forbidden)
        import inspect

        source = inspect.getsource(mcp_adapter)
        for banned in ("from executor", "import executor", "from bridge", "import bridge",
                       "from policy", "import policy", "from owner", "import owner"):
            self.assertNotIn(banned, source)

    def test_mcp_names_do_not_pass_bridge_validation(self):
        # A forged bridge action built from an MCP tool name is rejected by
        # the canonical protocol gate: discovery never equals authority.
        ok, _ = validate_action({"action": "read_file", "path": "x"})
        self.assertFalse(ok)

    def test_real_transports_declare_unavailability(self):
        for make in (stdio_transport, websocket_transport, sse_transport):
            t = make()
            with self.assertRaises(MCPUnavailable):
                t.request("discovery", {})
            with self.assertRaises(MCPUnavailable):
                t.discover("srv", "2025-03-26")


if __name__ == "__main__":
    unittest.main()
