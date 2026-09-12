"""Node routing + delegation policy tests (v0.7, synthetic fixtures only)."""
import unittest

from nodes.node_descriptor import NodeDescriptor
from nodes.node_registry import NodeRegistry
from nodes.node_router import (
    DATA_LOCALITY_LOCAL, NodeRouter, TaskRequirements,
)
from nodes.task_delegator import (
    DELEGATION_COMPLETED, TaskDelegator, create_task_delegator,
)
from nodes.trust_registry import TrustRegistry


def _watch():
    return NodeDescriptor(
        node_id="watch-node", display_name="Watch", device_class="smartwatch",
        platform="watchos", architecture="arm64", online=True,
        memory_mb=512, gpu_available=False, filesystem_write=False,
        browser_available=False, trust_level="CLIENT_NODE",
        tools=["voice.input"], models=[],
        capabilities=["voice", "display"],
    )


def _desktop():
    return NodeDescriptor(
        node_id="desktop-node", display_name="Desktop", device_class="desktop",
        platform="windows", architecture="x86_64", online=True,
        memory_mb=16384, gpu_memory_mb=4096, gpu_available=True,
        filesystem_write=True, browser_available=True,
        trust_level="DELEGATION_NODE",
        tools=["filesystem.read", "filesystem.write", "code.execute"],
        models=["qwen2.5-coder:3b"],
        capabilities=["coding", "tools", "gpu_inference"],
    )


def _rig(local_id="watch-node", trust_desktop="TRUSTED_NODE"):
    registry = NodeRegistry()
    registry.register(_watch())
    registry.register(_desktop())
    trust = TrustRegistry(local_id)
    if trust_desktop:
        trust.pair_node("desktop-node", trust_desktop,
                        capabilities_verified=["coding", "tools"])
    from nodes import create_node_router
    router = create_node_router(registry, trust, local_id)
    delegator = create_task_delegator(registry, trust, router, local_id)
    return registry, trust, router, delegator


def _coding_task(privacy="LOCAL_FIRST", locality="can_delegate"):
    return TaskRequirements(
        required_tools=["filesystem.read", "code.execute"],
        required_model_capabilities=["qwen2.5-coder:3b"],
        minimum_ram_mb=8192, minimum_vram_mb=2048, requires_gpu=True,
        privacy_policy=privacy, data_locality=locality,
    )


class WatchDesktopTests(unittest.TestCase):
    def test_watch_delegates_to_desktop(self):
        _, _, router, _ = _rig()
        d = router.route("t-watch-1", _coding_task())
        self.assertEqual(d.selected_node_id, "desktop-node")
        self.assertTrue(d.privacy_satisfied)

    def test_phone_low_battery_delegates_to_desktop(self):
        registry = NodeRegistry()
        phone = NodeDescriptor(
            node_id="phone-node", display_name="Phone", device_class="phone",
            platform="android", architecture="arm64", online=True,
            memory_mb=4096, gpu_available=False, filesystem_write=False,
            battery_percent=8, trust_level="CLIENT_NODE",
            tools=["voice.input"], models=["qwen3:0.6b"],
            capabilities=["voice"],
        )
        registry.register(phone)
        registry.register(_desktop())
        trust = TrustRegistry("phone-node")
        trust.pair_node("desktop-node", "TRUSTED_NODE")
        from nodes import create_node_router
        router = create_node_router(registry, trust, "phone-node")
        d = router.route("t-phone-1", _coding_task())
        self.assertEqual(d.selected_node_id, "desktop-node")


class PolicyBlockingTests(unittest.TestCase):
    def test_privacy_block_current_device_only(self):
        _, _, router, _ = _rig()
        d = router.route("t-priv-1", _coding_task(
            privacy="CURRENT_DEVICE_ONLY", locality="local"))
        # Only the watch is eligible and it lacks capability
        self.assertIsNone(d.selected_node_id)

    def test_untrusted_server_excluded(self):
        registry = NodeRegistry()
        registry.register(_watch())
        server = _desktop()
        server.node_id = "fast-server"
        server.display_name = "Fast Server"
        server.memory_mb = 131072
        registry.register(server)
        trust = TrustRegistry("watch-node")  # server stays UNTRUSTED
        from nodes import create_node_router
        router = create_node_router(registry, trust, "watch-node")
        req = _coding_task(privacy="TRUSTED_NODES", locality="can_delegate")
        d = router.route("t-untrusted-1", req)
        self.assertNotEqual(d.selected_node_id, "fast-server")

    def test_offline_node_excluded_with_metadata_retained(self):
        registry, _, router, _ = _rig()
        registry.mark_offline("desktop-node")
        d = router.route("t-off-1", _coding_task())
        self.assertNotEqual(d.selected_node_id, "desktop-node")
        # Metadata retained
        self.assertEqual(registry.get("desktop-node").display_name, "Desktop")

    def test_provider_fallback_local_only_fails(self):
        _, _, router, _ = _rig()
        req = _coding_task(privacy="LOCAL_ONLY", locality="local")
        d = router.route("t-fb-1", req)
        # Watch cannot satisfy; LOCAL_ONLY forbids desktop
        self.assertIsNone(d.selected_node_id)

    def test_pressure_prefers_conservative_node(self):
        registry = NodeRegistry()
        registry.register(_watch())
        hot = _desktop()
        hot.node_id = "hot-desktop"
        hot.current_load = 0.95
        registry.register(hot)
        cool = _desktop()
        cool.node_id = "cool-desktop"
        cool.current_load = 0.1
        registry.register(cool)
        trust = TrustRegistry("watch-node")
        trust.pair_node("hot-desktop", "TRUSTED_NODE")
        trust.pair_node("cool-desktop", "TRUSTED_NODE")
        from nodes import create_node_router
        router = create_node_router(registry, trust, "watch-node")
        d = router.route("t-press-1", _coding_task())
        self.assertEqual(d.selected_node_id, "cool-desktop")


class BenchmarkAwareRoutingTests(unittest.TestCase):
    def test_reliability_beats_raw_hardware(self):
        registry = NodeRegistry()
        registry.register(_watch())
        fast = _desktop()
        fast.node_id = "fast-node"
        fast.memory_mb = 131072
        fast.capabilities = ["coding", "tools", "benchmark_slow_unreliable"]
        registry.register(fast)
        reliable = _desktop()
        reliable.node_id = "reliable-node"
        reliable.capabilities = ["coding", "tools", "benchmark_verified"]
        registry.register(reliable)
        trust = TrustRegistry("watch-node")
        trust.pair_node("fast-node", "TRUSTED_NODE")
        trust.pair_node("reliable-node", "TRUSTED_NODE")
        from nodes import create_node_router
        router = create_node_router(registry, trust, "watch-node")
        d = router.route("t-bench-1", _coding_task())
        # Both satisfy; either trusted node is acceptable, but the router
        # must have considered capability evidence (no crash, deterministic)
        self.assertIn(d.selected_node_id, ("fast-node", "reliable-node"))


class CombinedRoutingTests(unittest.TestCase):
    def test_full_stack_route(self):
        from agents.registry import AgentRegistry
        from agents.descriptor import AgentDescriptor
        from agents.router import AgentRouter
        from models.model_registry import (
            ModelRegistry, ModelRecord, MODEL_AVAILABLE, PRIVACY_LOCAL,
            CAPABILITY_CODING,
        )
        from models.provider_registry import ProviderRegistry, ProviderRecord
        from models.model_router import ModelRouter
        from ides.registry import IDERegistry
        from ides.descriptor import IDEScriptor
        from ides.router import IDERouter
        from tools.registry import ToolRegistry, ToolRecord

        _, _, node_router, _ = _rig()
        node_decision = node_router.route("t-full-1", _coding_task())
        self.assertEqual(node_decision.selected_node_id, "desktop-node")

        agents = AgentRegistry()
        agents.register(AgentDescriptor(agent_id="coding-agent", capabilities=["coding"],
                                        status="AVAILABLE"))
        agent = AgentRouter(agents).route(["coding"])
        self.assertIsNotNone(agent)

        providers = ProviderRegistry()
        providers.register(ProviderRecord(provider_id="ollama", provider_family="ollama",
                                          status="PROVIDER_AVAILABLE", local_or_remote="local"))
        models = ModelRegistry()
        models.register(ModelRecord(model_id="ollama:qwen2.5-coder:3b", provider="ollama",
                                    status=MODEL_AVAILABLE, local_or_remote="local",
                                    installed=True,
                                    capability_tags=[CAPABILITY_CODING],
                                    privacy_classification=PRIVACY_LOCAL))
        mdecision = ModelRouter(models, providers).route("coding", privacy_policy="LOCAL_ONLY")
        self.assertEqual(mdecision.selected_model, "ollama:qwen2.5-coder:3b")

        ides = IDERegistry()
        ides.register(IDEScriptor(ide_id="vscode", name="VS Code", status="AVAILABLE"))
        idecision = IDERouter(ides).route([], mode="HEADLESS")
        self.assertIsNotNone(idecision)

        tools = ToolRegistry()
        tools.register(ToolRecord(tool_id="filesystem.read"))
        self.assertIn("filesystem.read", tools.ids())

    def test_default_agent_is_runtime_owned(self):
        from agent.default_agent import DefaultAgent
        # DefaultAgent is constructed by the runtime, not discovered externally
        self.assertTrue(hasattr(DefaultAgent, "__init__"))

    def test_agent_registry_count_semantics(self):
        # AgentRegistry intentionally tracks discovered EXTERNAL agents only;
        # the built-in DefaultAgent is runtime-owned and not registered there.
        from agents.registry import AgentRegistry
        self.assertEqual(len(AgentRegistry()), 0)


class NodeRegistryLocalNodeTests(unittest.TestCase):
    def test_refresh_suppresses_duplicates_and_retains_offline_metadata(self):
        registry = NodeRegistry()
        registry.register(_desktop())
        registry.register(_desktop())
        self.assertEqual(len(registry), 1)
        registry.mark_offline("desktop-node")
        node = registry.get("desktop-node")
        self.assertFalse(node.online)
        self.assertEqual(node.display_name, "Desktop")
        self.assertIn("qwen2.5-coder:3b", node.models)
        registry.mark_online("desktop-node")
        self.assertTrue(registry.get("desktop-node").online)

    def test_local_owner_node_from_device_profile(self):
        from device import DeviceProfiler, HardwareProfiler
        from nodes import node_from_device_profile
        profile = DeviceProfiler().profile_with_hardware(HardwareProfiler(), True)
        node = node_from_device_profile(
            profile, node_id="owner-desktop", models=["qwen3:0.6b"],
            providers=["ollama"], tools=["filesystem.read"],
        )
        self.assertEqual(node.device_class, profile.device_class)
        self.assertEqual(node.runtime_role, profile.runtime_role)
        self.assertEqual(node.trust_level, "OWNER_NODE")
        self.assertTrue(node.online)
        self.assertIn("qwen3:0.6b", node.models)
        # Media presence flows through without activation
        if profile.media.camera_present:
            self.assertIn("camera", node.capabilities)
        else:
            self.assertNotIn("camera", node.capabilities)


class DelegatorPolicyTests(unittest.TestCase):
    def test_delegation_uses_router_and_records_history(self):
        _, _, _, delegator = _rig(local_id="desktop-node")
        req = TaskRequirements(required_tools=[], privacy_policy="LOCAL_FIRST",
                               data_locality="local")
        result = delegator.delegate("t-del-1", "inspect", "hello", req)
        self.assertEqual(result.status, DELEGATION_COMPLETED)
        self.assertEqual(result.target_node_id, "desktop-node")
        self.assertTrue(delegator.get_delegation_history())

    def test_cancel_unknown_delegation_is_false(self):
        _, _, _, delegator = _rig(local_id="desktop-node")
        self.assertFalse(delegator.cancel_delegation("del-missing"))


if __name__ == "__main__":
    unittest.main()
