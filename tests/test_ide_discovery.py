import unittest

from ides import (
    IDEAdapterRegistry, IDEScriptor, IDEDiscoveryManager, IDEDiscoveryProbe,
    IDERegistry, IDERouter, WorkspaceDescriptor, WorkspaceRegistry,
)


class IDEDiscoveryTests(unittest.TestCase):
    def test_unknown_generic_protocol_registers_dynamically(self):
        adapters = IDEAdapterRegistry()
        adapters.register("CLI_AGENT", object())
        manager = IDEDiscoveryManager(adapters=adapters)
        manager.add_probe(IDEDiscoveryProbe(
            "fixtures",
            lambda: [IDEScriptor(
                "future-ide-9000", name="FutureIDE9000",
                protocols=["CLI_AGENT"], capabilities=["python", "test_support"],
            )],
        ))
        manager.refresh()
        self.assertEqual(manager.registry.get("future-ide-9000").status, "AVAILABLE")

    def test_unknown_unsupported_ide_requires_adapter(self):
        manager = IDEDiscoveryManager()
        manager.add_probe(IDEDiscoveryProbe(
            "fixtures", lambda: [IDEScriptor(
                "unknown-editor", name="UnknownEditor", protocols=["FUTURE_UI"],
            )],
        ))
        manager.refresh()
        self.assertEqual(manager.registry.get("unknown-editor").status, "ADAPTER_REQUIRED")

    def test_refresh_marks_disappeared_ide_offline(self):
        state = {"present": True}
        manager = IDEDiscoveryManager()
        manager.add_probe(IDEDiscoveryProbe(
            "mutable",
            lambda: [IDEScriptor("nebula", name="NebulaCode",
                                 status="AVAILABLE")] if state["present"] else [],
        ))
        manager.refresh()
        state["present"] = False
        manager.refresh()
        ide = manager.registry.get("nebula")
        self.assertEqual(ide.status, "OFFLINE")
        self.assertEqual(ide.name, "NebulaCode")

    def test_router_uses_capabilities_and_headless_fallback(self):
        registry = IDERegistry()
        registry.register(IDEScriptor(
            "python-ide", name="ArbitraryName",
            status="AVAILABLE", capabilities=["python", "debug_support"],
        ))
        decision = IDERouter(registry).route(["python", "debug_support"])
        self.assertEqual(decision.ide.ide_id, "python-ide")
        self.assertIsNone(IDERouter(registry).route(["rust"]).ide)

    def test_workspace_is_independent_and_supports_multiple_ides(self):
        workspaces = WorkspaceRegistry()
        workspaces.register(WorkspaceDescriptor(
            "project", path_or_reference="C:\\project", node_id="desktop",
        ))
        workspaces.attach_ide("project", "ide-a")
        workspaces.attach_ide("project", "ide-b")
        self.assertEqual(workspaces.get("project").associated_ides, ["ide-a", "ide-b"])


if __name__ == "__main__":
    unittest.main()
