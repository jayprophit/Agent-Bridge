import unittest

from agents import (
    AgentDescriptor, AgentDiscoveryManager, AgentRouter, DiscoveryProbe,
    ProtocolDefinition,
)


class AgentDiscoveryTests(unittest.TestCase):
    def test_unknown_compatible_agent_is_registered_as_available(self):
        manager = AgentDiscoveryManager()
        manager.register_protocol(ProtocolDefinition("FUTURE_PROTOCOL"), adapter=object())
        manager.add_probe(DiscoveryProbe(
            "fixture",
            lambda: [AgentDescriptor(
                "future-agent", display_name="Future Agent",
                protocols=["FUTURE_PROTOCOL"], capabilities=["coding"],
            )],
        ))
        found = manager.refresh()
        self.assertEqual(found[0].status, "AVAILABLE")
        self.assertEqual(manager.registry.get("future-agent").agent_type, "UNKNOWN_AGENT")

    def test_unknown_unsupported_agent_requires_adapter(self):
        manager = AgentDiscoveryManager()
        manager.add_probe(DiscoveryProbe(
            "fixture",
            lambda: [AgentDescriptor("unknown", protocols=["UNSUPPORTED"])],
        ))
        manager.refresh()
        self.assertEqual(manager.registry.get("unknown").status, "ADAPTER_REQUIRED")

    def test_router_uses_capabilities_and_locality(self):
        manager = AgentDiscoveryManager()
        manager.registry.register(AgentDescriptor(
            "local-coder", status="AVAILABLE", local_or_remote="local",
            capabilities=["coding"], protocols=["CLI_AGENT"],
        ))
        self.assertEqual(
            AgentRouter(manager.registry).route(["coding"], local_only=True).agent_id,
            "local-coder",
        )


if __name__ == "__main__":
    unittest.main()
