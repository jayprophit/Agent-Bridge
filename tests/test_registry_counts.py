"""Registry count semantics (v0.7).

Models must never be reported as tools. Each registry tracks only its own
domain objects.
"""
import unittest

from tools.registry import ToolRegistry, ToolRecord
from models.model_registry import (
    ModelRegistry, ModelRecord, MODEL_AVAILABLE, PRIVACY_LOCAL,
    CAPABILITY_TOOL_CALLING, CAPABILITY_VISION,
    EVIDENCE_PROVIDER_REPORTED, EVIDENCE_BENCHMARK_VERIFIED,
    TOOL_CALL_NATIVE, TOOL_CALL_CONTENT_INTENT,
)
from models.provider_registry import ProviderRegistry, ProviderRecord
from agents.registry import AgentRegistry
from agents.descriptor import AgentDescriptor
from ides.registry import IDERegistry
from ides.descriptor import IDEScriptor


class RegistryCountTests(unittest.TestCase):
    def test_counts_are_domain_separate(self):
        tools = ToolRegistry()
        models = ModelRegistry()
        providers = ProviderRegistry()
        agents = AgentRegistry()
        ides = IDERegistry()

        tools.register(ToolRecord(tool_id="filesystem.read"))
        tools.register(ToolRecord(tool_id="filesystem.write"))
        models.register(ModelRecord(model_id="ollama:test-model", status=MODEL_AVAILABLE))
        providers.register(ProviderRecord(provider_id="p1", provider_family="ollama"))
        agents.register(AgentDescriptor(agent_id="a1"))
        ides.register(IDEScriptor(ide_id="i1", name="TestIDE"))

        self.assertEqual(len(tools), 2)
        self.assertEqual(len(models), 1)
        self.assertEqual(len(providers), 1)
        self.assertEqual(len(agents), 1)
        self.assertEqual(len(ides), 1)

        # Models are not tools: model ids never appear in the tool registry
        self.assertNotIn("ollama:test-model", tools.ids())
        self.assertIn("ollama:test-model", models.ids())

    def test_capability_evidence_does_not_fabricate(self):
        rec = ModelRecord(
            model_id="ollama:qwen3.5:2b-q4_K_M",
            status=MODEL_AVAILABLE,
            vision=True,
            capability_tags=[CAPABILITY_VISION],
            capability_evidence={"vision": EVIDENCE_PROVIDER_REPORTED},
            privacy_classification=PRIVACY_LOCAL,
        )
        # Provider metadata alone => PROVIDER_REPORTED, never PROBE_VERIFIED
        self.assertEqual(rec.evidence_for("vision"), EVIDENCE_PROVIDER_REPORTED)
        self.assertNotEqual(rec.evidence_for("vision"), "PROBE_VERIFIED")

    def test_content_intent_never_upgrades_to_native(self):
        rec = ModelRecord(model_id="m1", status=MODEL_AVAILABLE)
        rec.annotate_capability(CAPABILITY_TOOL_CALLING, EVIDENCE_BENCHMARK_VERIFIED,
                                tool_mode=TOOL_CALL_CONTENT_INTENT)
        self.assertEqual(rec.tool_calling_mode, TOOL_CALL_CONTENT_INTENT)
        with self.assertRaises(ValueError):
            rec.annotate_capability(CAPABILITY_TOOL_CALLING, EVIDENCE_BENCHMARK_VERIFIED,
                                    tool_mode=TOOL_CALL_NATIVE)


if __name__ == "__main__":
    unittest.main()
