"""Conversation adapter + Ollama Provider V2 tests (§15–§20, §27–§30).

Two things these tests protect beyond basic correctness:

1. ADAPTER HONESTY (§18). A live adapter must never claim a data capability
   it cannot fulfil. If someone "completes" an adapter by declaring
   list_conversations without wiring retrieval, these fail.

2. CAPABILITY DISCOVERY (§28). The Ollama adapter must report what the live
   runtime actually declares, not what the model name suggests. The
   llama3.2 case is the regression guard: it advertises tools and reports
   thinking values=[False], so it must be tools=True, reasoning=False.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from knowledge_fabric.conversation_adapters import (
    ALL_STATES,
    ALL_CONVERSATION_CAPABILITIES,
    AUTH_REQUIRED,
    INTERFACE_READY,
    LIVE_VERIFIED,
    AccessMode,
    ChatGPTAdapter,
    ClaudeAdapter,
    ConversationRecord,
    ConversationSourceAdapter,
    GenericConversationExportAdapter,
    HermesAdapter,
    UnsupportedCapabilityError,
    build_conversation_registry,
    hash_text,
    registry_summary,
)


class CapabilityGateTests(unittest.TestCase):
    """§16 — unadvertised capabilities raise, they do not return empty data."""

    def test_unadvertised_capability_raises(self):
        adapter = ConversationSourceAdapter()
        with self.assertRaises(UnsupportedCapabilityError):
            adapter.list_conversations()

    def test_raised_error_names_source_and_capability(self):
        adapter = ConversationSourceAdapter()
        adapter.source_id = "conversation:test"
        try:
            adapter.list_conversations()
            self.fail("expected UnsupportedCapabilityError")
        except UnsupportedCapabilityError as exc:
            self.assertEqual(exc.source_id, "conversation:test")
            self.assertEqual(exc.capability, "list_conversations")

    def test_supports_reflects_declaration(self):
        adapter = ConversationSourceAdapter()
        adapter.supported_capabilities = ("list_conversations",)
        self.assertTrue(adapter.supports("list_conversations"))
        self.assertFalse(adapter.supports("read_messages"))

    def test_capabilities_report_is_honest_about_unsupported(self):
        adapter = ConversationSourceAdapter()
        adapter.supported_capabilities = ("list_conversations",)
        caps = adapter.capabilities()
        self.assertIn("list_conversations", caps["supported"])
        self.assertIn("read_messages", caps["unsupported"])
        self.assertEqual(len(caps["supported"]) + len(caps["unsupported"]),
                         len(ALL_CONVERSATION_CAPABILITIES))


class ExportIngestionTests(unittest.TestCase):
    """§19 — owner-authorized archives ingest without a vendor adapter."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _write_json(self, payload, name="conv.json"):
        path = self.dir / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_ingests_json_conversation(self):
        path = self._write_json({
            "id": "c-1", "title": "Build notes",
            "created_at": "2026-01-01T00:00:00Z",
            "messages": [
                {"id": "m-1", "role": "user", "content": "hello"},
                {"id": "m-2", "role": "assistant", "content": "hi there"},
            ],
        })
        adapter = GenericConversationExportAdapter("chatgpt", path)
        convs = adapter.list_conversations()
        self.assertEqual(len(convs), 1)
        self.assertEqual(convs[0].conversation_id, "c-1")
        self.assertEqual(convs[0].message_count, 2)
        self.assertEqual(adapter.state, "IMPLEMENTED")

    def test_preserves_message_ids_roles_and_timestamps(self):
        path = self._write_json({
            "id": "c-2",
            "messages": [{"id": "m-9", "role": "user",
                          "content": "q", "created_at": "2026-02-02T00:00:00Z"}],
        })
        adapter = GenericConversationExportAdapter("claude", path)
        msgs = adapter.read_messages("c-2")
        self.assertEqual(msgs[0].message_id, "m-9")
        self.assertEqual(msgs[0].role, "user")
        self.assertEqual(msgs[0].created_at, "2026-02-02T00:00:00Z")

    def test_handles_chatgpt_nested_mapping_form(self):
        """Vendor exports differ; the nested mapping shape must not be dropped."""
        path = self._write_json({
            "id": "c-3",
            "mapping": {
                "root": {"message": None},
                "n1": {"message": {"id": "a", "author": {"role": "user"},
                                   "content": {"parts": ["part one"]}}},
            },
        })
        adapter = GenericConversationExportAdapter("chatgpt", path)
        msgs = adapter.read_messages("c-3")
        roles = [m.role for m in msgs]
        self.assertIn("user", roles)
        self.assertIn("part one", "".join(m.content for m in msgs))

    def test_markdown_export_becomes_one_conversation(self):
        path = self.dir / "notes.md"
        path.write_text("# Notes\nsome content", encoding="utf-8")
        adapter = GenericConversationExportAdapter("claude", path)
        convs = adapter.list_conversations()
        self.assertEqual(len(convs), 1)
        self.assertEqual(convs[0].platform, "claude")

    def test_content_hash_is_stable(self):
        path = self._write_json({
            "id": "c-4",
            "messages": [{"id": "m", "role": "user", "content": "same"}],
        })
        a1 = GenericConversationExportAdapter("x", path)
        a2 = GenericConversationExportAdapter("x", path)
        self.assertEqual(a1.get_content_hash("c-4"), a2.get_content_hash("c-4"))
        self.assertTrue(a1.get_content_hash("c-4"))

    def test_content_hash_changes_with_content(self):
        p1 = self._write_json({"id": "c", "messages": [
            {"id": "m", "role": "user", "content": "version A"}]}, "a.json")
        p2 = self._write_json({"id": "c", "messages": [
            {"id": "m", "role": "user", "content": "version B"}]}, "b.json")
        self.assertNotEqual(
            GenericConversationExportAdapter("x", p1).get_content_hash("c"),
            GenericConversationExportAdapter("x", p2).get_content_hash("c"))

    def test_zip_export_is_ingested(self):
        import zipfile
        zpath = self.dir / "export.zip"
        with zipfile.ZipFile(zpath, "w") as zf:
            zf.writestr("conv-1.json", json.dumps({
                "id": "z-1",
                "messages": [{"id": "m", "role": "user", "content": "zipped"}]}))
        adapter = GenericConversationExportAdapter("chatgpt", zpath)
        self.assertEqual(len(adapter.list_conversations()), 1)

    def test_malformed_json_degrades_to_text(self):
        """A corrupt file must not abort the import (§19 tolerance)."""
        path = self.dir / "bad.json"
        path.write_text("{not valid json", encoding="utf-8")
        adapter = GenericConversationExportAdapter("x", path)
        self.assertEqual(len(adapter.list_conversations()), 1)

    def test_missing_optional_fields_do_not_crash(self):
        path = self._write_json({"id": "c-5", "messages": []})
        adapter = GenericConversationExportAdapter("x", path)
        conv = adapter.get_conversation("c-5")
        self.assertIsNotNone(conv)
        self.assertEqual(conv.title, "")

    def test_pagination_exhausts(self):
        path = self._write_json([
            {"id": f"c{i}", "messages": []} for i in range(5)])
        adapter = GenericConversationExportAdapter("x", path)
        seen, cursor = [], ""
        while True:
            page, cursor = adapter.paginate_conversations(cursor=cursor,
                                                          page_size=2)
            seen.extend(r.conversation_id for r in page)
            if not cursor:
                break
        self.assertEqual(len(seen), 5)

    def test_unknown_conversation_returns_empty(self):
        path = self._write_json({"id": "c", "messages": []})
        adapter = GenericConversationExportAdapter("x", path)
        self.assertEqual(adapter.read_messages("nope"), [])
        self.assertEqual(adapter.get_content_hash("nope"), "")


class IncrementalSyncTests(unittest.TestCase):
    """§20 — unchanged conversations are skipped, not re-parsed."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _adapter(self):
        path = self.dir / "conv.json"
        path.write_text(json.dumps({
            "id": "c-1", "messages": [
                {"id": "m", "role": "user", "content": "stable"}]}),
            encoding="utf-8")
        return GenericConversationExportAdapter("x", path)

    def test_first_sync_ingests(self):
        summary = self._adapter().sync()
        self.assertEqual(summary["ingested_count"], 1)
        self.assertEqual(summary["skipped_count"], 0)

    def test_second_sync_skips(self):
        adapter = self._adapter()
        adapter.sync()
        summary = adapter.sync()
        self.assertEqual(summary["skipped_count"], 1)
        self.assertEqual(summary["ingested_count"], 0)

    def test_changed_conversation_is_reingested(self):
        path = self.dir / "conv.json"
        adapter = self._adapter()
        adapter.sync()
        path.write_text(json.dumps({
            "id": "c-1", "messages": [
                {"id": "m", "role": "user", "content": "CHANGED"}]}),
            encoding="utf-8")
        adapter2 = GenericConversationExportAdapter("x", path)
        adapter2._sync_cursor = dict(adapter._sync_cursor)  # carry cursor over
        summary = adapter2.sync()
        self.assertEqual(summary["ingested_count"], 1)


class AdapterHonestyTests(unittest.TestCase):
    """§18 — the core rule: a class existing is not access."""

    def setUp(self):
        self.registry = build_conversation_registry()

    def test_all_platforms_registered(self):
        expected = {"chatgpt", "claude", "manus", "kimi", "deepseek",
                    "hermes", "opencode", "openclaw"}
        self.assertEqual(set(self.registry), expected)

    def test_no_live_adapter_claims_live_verified(self):
        for name, adapter in self.registry.items():
            self.assertNotEqual(
                adapter.state, LIVE_VERIFIED,
                f"{name} must not claim LIVE_VERIFIED without a real retrieval")

    def test_no_live_adapter_advertises_data_retrieval(self):
        """The precise false claim §18 forbids."""
        forbidden = {"list_conversations", "get_conversation", "read_messages"}
        for name, adapter in self.registry.items():
            overlap = forbidden & set(adapter.supported_capabilities)
            self.assertEqual(overlap, set(),
                             f"{name} advertises {overlap} without verified access")

    def test_live_adapters_require_auth(self):
        for name in ("chatgpt", "claude"):
            self.assertEqual(self.registry[name].state, AUTH_REQUIRED)

    def test_access_modes_are_declared(self):
        for adapter in self.registry.values():
            self.assertIsInstance(adapter.access_mode, AccessMode)

    def test_unsupported_platforms_flagged(self):
        for name in ("manus", "kimi", "deepseek"):
            self.assertEqual(self.registry[name].access_mode,
                             AccessMode.UNSUPPORTED)

    def test_access_priority_prefers_official_api(self):
        from knowledge_fabric.conversation_adapters import ACCESS_PRIORITY
        self.assertEqual(ACCESS_PRIORITY[0], AccessMode.OFFICIAL_API)

    def test_states_are_from_the_declared_vocabulary(self):
        for adapter in self.registry.values():
            self.assertIn(adapter.state, ALL_STATES)

    def test_summary_separates_live_from_ready(self):
        summary = registry_summary(self.registry)
        self.assertEqual(summary["live_verified"], [])
        self.assertIn("chatgpt", summary["owner_action_required"])

    def test_unadvertised_capability_raises_on_live_adapter(self):
        adapter = self.registry["claude"]
        with self.assertRaises(UnsupportedCapabilityError):
            adapter.list_conversations()


class PrivacyTests(unittest.TestCase):
    """§26 — raw conversation text is hashed, not duplicated into the repo."""

    def test_message_dict_omits_raw_content(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.json"
            path.write_text(json.dumps({
                "id": "c", "messages": [
                    {"id": "m", "role": "user",
                     "content": "my secret password is hunter2"}]}),
                encoding="utf-8")
            adapter = GenericConversationExportAdapter("x", path)
            conv = adapter.get_conversation("c")
            rendered = json.dumps(conv.to_dict())
            self.assertNotIn("hunter2", rendered)
            self.assertIn("content_hash", rendered)

    def test_hash_text_is_deterministic(self):
        self.assertEqual(hash_text("abc"), hash_text("abc"))
        self.assertNotEqual(hash_text("abc"), hash_text("abd"))


# --------------------------------------------------------------------------
# Ollama Provider V2
# --------------------------------------------------------------------------
from compute.error_taxonomy import (  # noqa: E402
    MODEL_UNAVAILABLE,
    PROVIDER_INTERNAL,
    UNSUPPORTED_CAPABILITY,
)
from compute.ollama_provider_v2 import (  # noqa: E402
    OllamaProviderV2,
    OllamaUnsupportedCapabilityError,
    normalize_ollama_error,
)


class OllamaCapabilityDiscoveryTests(unittest.TestCase):
    """§28 — discover from the runtime, never from the model name."""

    @classmethod
    def setUpClass(cls):
        cls.provider = OllamaProviderV2()
        cls.available = cls.provider.is_available()

    def _skip_unless_live(self):
        if not self.available:
            self.skipTest("Ollama runtime not reachable")

    def test_runtime_is_discoverable(self):
        self._skip_unless_live()
        self.assertGreater(len(self.provider.list_models()), 0)

    def test_vision_model_declares_vision(self):
        """moondream is the vision model on this host."""
        self._skip_unless_live()
        caps = self.provider.discover("moondream:latest")
        self.assertTrue(caps.vision)

    def test_text_model_does_not_declare_vision(self):
        self._skip_unless_live()
        caps = self.provider.discover("llama3.2:1b-instruct-q4_K_M")
        self.assertFalse(caps.vision)

    def test_llama32_declares_tools(self):
        """REGRESSION GUARD.

        Name-based inference got this wrong — nothing in 'llama3.2' suggests
        tool calling, but /api/show declares ["completion","tools"]. Trusting
        the runtime is the whole point of discovery.
        """
        self._skip_unless_live()
        caps = self.provider.discover("llama3.2:1b-instruct-q4_K_M")
        self.assertTrue(caps.tools)

    def test_llama32_does_not_declare_reasoning(self):
        """REGRESSION GUARD: thinking values=[False] means it cannot reason."""
        self._skip_unless_live()
        caps = self.provider.discover("llama3.2:1b-instruct-q4_K_M")
        self.assertFalse(caps.reasoning)

    def test_context_length_is_discovered(self):
        """context_length lives in model_info as <arch>.context_length."""
        self._skip_unless_live()
        caps = self.provider.discover("llama3.2:1b-instruct-q4_K_M")
        self.assertGreater(caps.context_length, 0)

    def test_embedding_model_is_not_a_completion_model(self):
        self._skip_unless_live()
        self.assertTrue(self.provider.embedding_capable("nomic-embed-text:latest"))
        self.assertFalse(
            self.provider.embedding_capable("llama3.2:1b-instruct-q4_K_M"))

    def test_provider_capabilities_do_not_overclaim(self):
        """§28 — logprobs/prompt-caching/batch/audio are pinned unsupported."""
        caps = self.provider.provider_capabilities()
        for forbidden in ("logprobs", "prompt_caching", "batch", "audio"):
            self.assertFalse(caps.get(forbidden),
                             f"must not advertise {forbidden}")

    def test_provider_vs_model_distinction_is_preserved(self):
        """§28 — capabilities vary per model, not per provider."""
        self._skip_unless_live()
        provider_caps = self.provider.provider_capabilities()
        model_caps = self.provider.discover("moondream:latest")
        # The provider-level report has no per-model vision claim at all.
        self.assertNotIn("vision", provider_caps)
        self.assertTrue(model_caps.vision)

    def test_unknown_model_is_reported_unavailable(self):
        self._skip_unless_live()
        caps = self.provider.discover("definitely-not-installed:7b")
        self.assertEqual(caps.discovery_source, "unavailable")
        self.assertFalse(caps.tools)

    def test_discovery_is_cached(self):
        self._skip_unless_live()
        first = self.provider.discover("llama3.2:1b-instruct-q4_K_M")
        again = self.provider.discover("llama3.2:1b-instruct-q4_K_M")
        self.assertIs(first, again)

    def test_capabilities_serialize(self):
        caps = self.provider.discover("llama3.2:1b-instruct-q4_K_M")
        data = caps.to_dict()
        self.assertIn("supported", data)
        self.assertIn("unsupported", data)


class OllamaUnreachableTests(unittest.TestCase):
    """§29 — an unreachable runtime normalizes, it does not leak raw errors."""

    def test_unreachable_runtime_normalizes_to_provider_unavailable(self):
        import urllib.error
        provider = OllamaProviderV2(base_url="http://127.0.0.1:1")
        try:
            provider.list_models()
            self.fail("expected failure")
        except urllib.error.URLError:
            self.fail("raw URLError leaked — must be normalized")
        except Exception as exc:
            # NOTE: the taxonomy resolves the §3 alias PROVIDER_UNAVAILABLE
            # to its canonical class PROVIDER_INTERNAL, so the normalized
            # value is the latter. Asserting the alias string would pass for
            # the wrong reason and could hide a real mis-classification.
            self.assertEqual(normalize_ollama_error(exc), PROVIDER_INTERNAL)

    def test_is_available_is_false_not_raising(self):
        provider = OllamaProviderV2(base_url="http://127.0.0.1:1")
        self.assertFalse(provider.is_available())

    def test_normalize_maps_unknown_to_unknown_class(self):
        self.assertEqual(normalize_ollama_error(ValueError("x")),
                         "UNKNOWN_PROVIDER_ERROR")

    def test_normalize_maps_timeout(self):
        self.assertEqual(normalize_ollama_error(TimeoutError()), "TIMEOUT")


class OllamaUnsupportedCapabilityTests(unittest.TestCase):
    """§28 — asking for an unsupported capability fails CLOSED."""

    def test_tools_on_a_vision_only_model_raise(self):
        provider = OllamaProviderV2()
        if not provider.is_available():
            self.skipTest("Ollama runtime not reachable")
        with self.assertRaises(OllamaUnsupportedCapabilityError) as ctx:
            provider.infer("moondream:latest", "hi",
                           tools=[{"type": "function",
                                   "function": {"name": "f",
                                                "description": "d"}}])
        self.assertEqual(ctx.exception.error_class, UNSUPPORTED_CAPABILITY)

    def test_unsupported_error_does_not_failover(self):
        """Retrying the same model with the same request cannot succeed."""
        err = OllamaUnsupportedCapabilityError("m", "tools")
        self.assertFalse(err.failover_eligible)
        self.assertFalse(err.retryable)

    def test_embedding_on_a_text_model_raises(self):
        provider = OllamaProviderV2()
        if not provider.is_available():
            self.skipTest("Ollama runtime not reachable")
        from compute.ollama_provider_v2 import OllamaUnsupportedCapabilityError as E
        with self.assertRaises(E):
            provider.embed("llama3.2:1b-instruct-q4_K_M", "text")


class OllamaLiveInferenceTests(unittest.TestCase):
    """§30 — a bounded live proof, using the smallest model only."""

    @classmethod
    def setUpClass(cls):
        cls.provider = OllamaProviderV2()
        cls.available = cls.provider.is_available()
        # 0.81 GB — the smallest model on this 16 GB host, so this proof does
        # not evict anything the owner is using (§30).
        cls.model = "llama3.2:1b-instruct-q4_K_M"

    def test_bounded_inference_returns_response_and_usage(self):
        if not self.available:
            self.skipTest("Ollama runtime not reachable")
        if self.model not in self.provider.list_models():
            self.skipTest(f"{self.model} not installed")
        result = self.provider.infer(self.model, "Reply with exactly: PONG",
                                     max_tokens=16, temperature=0.0)
        self.assertIn("PONG", result["response"])
        self.assertGreater(result["usage"]["total_tokens"], 0)

    def test_inference_reports_capabilities_used(self):
        if not self.available:
            self.skipTest("Ollama runtime not reachable")
        if self.model not in self.provider.list_models():
            self.skipTest(f"{self.model} not installed")
        result = self.provider.infer(self.model, "hi", temperature=0.1)
        self.assertIn("temperature", result["capabilities_used"])

    def test_embeddings_work_on_embedding_model(self):
        if not self.available:
            self.skipTest("Ollama runtime not reachable")
        if "nomic-embed-text:latest" not in self.provider.list_models():
            self.skipTest("embedding model not installed")
        vec = self.provider.embed("nomic-embed-text:latest", "hello world")
        self.assertGreater(len(vec), 0)


if __name__ == "__main__":
    unittest.main()
