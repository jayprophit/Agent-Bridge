"""Small/legacy model compatibility tests (v0.8, mostly synthetic)."""
import unittest

from compat import (
    BRIDGE_STRUCTURED_ACTION, LEGACY_MODEL_MODE, NATIVE_TOOL_CALLING,
    SMALL_CONTEXT_MODE, STRICT_JSON_ACTION, TEXT_ACTION_TRANSLATION,
    LegacyActionTranslator, ModelCapabilityProbe, compact_prompt,
    negotiate_tools, select_modes,
)
from tools.registry import ToolRecord, ToolRegistry
from tools.router import ToolRouter


class StubAdapter:
    def __init__(self, calls):
        self.calls = calls

    def validate(self, arguments):
        return (True, "") if isinstance(arguments, dict) else (False, "need object")

    def execute(self, arguments, context=None):
        self.calls.append(dict(arguments))
        return {"ok": True, "echo": arguments}


def _registry(calls):
    from tools.registry import AVAILABLE
    reg = ToolRegistry()
    for tid in ("demo.write", "demo.list", "demo.finish"):
        reg.register(ToolRecord(tool_id=tid, status=AVAILABLE, available=True),
                     StubAdapter(calls))
    return reg


class ModesTests(unittest.TestCase):
    def test_native_wins(self):
        self.assertEqual(select_modes({"native_tools": True})[0], NATIVE_TOOL_CALLING)

    def test_bridge_before_strict(self):
        self.assertEqual(
            select_modes({"bridge_structured": True, "strict_json": True})[0],
            BRIDGE_STRUCTURED_ACTION)

    def test_strict_before_text(self):
        self.assertEqual(
            select_modes({"strict_json": True, "text_actions": True})[0],
            STRICT_JSON_ACTION)

    def test_text_fallback(self):
        self.assertEqual(select_modes({"text_actions": True})[0], TEXT_ACTION_TRANSLATION)

    def test_legacy_when_nothing(self):
        self.assertEqual(select_modes({})[0], LEGACY_MODEL_MODE)

    def test_small_context_is_orthogonal(self):
        modes = select_modes({"bridge_structured": True, "context_tokens": 4096})
        self.assertEqual(modes, [BRIDGE_STRUCTURED_ACTION, SMALL_CONTEXT_MODE])

    def test_no_vendor_names_in_selection(self):
        import inspect
        src = inspect.getsource(select_modes)
        for vendor in ("qwen", "llama", "deepseek", "gpt", "Muse", "gemini"):
            self.assertNotIn(vendor, src.lower())


class NegotiationTests(unittest.TestCase):
    def test_shortlist_is_bounded(self):
        from tools.cat_nodes import node_records
        reg = ToolRegistry()
        for rec in node_records():
            try:
                reg.register(rec)
            except ValueError:
                pass
        shortlist = negotiate_tools("list files in workspace", reg)
        self.assertLessEqual(len(shortlist), 13)
        self.assertIn("tools.search", shortlist)

    def test_small_context_shrinks_budget(self):
        from tools.cat_nodes import node_records
        reg = ToolRegistry()
        for rec in node_records():
            try:
                reg.register(rec)
            except ValueError:
                pass
        shortlist = negotiate_tools("list files", reg, modes=[SMALL_CONTEXT_MODE])
        self.assertLessEqual(len(shortlist), 7)

    def test_compact_prompt_names_only_listed_tools(self):
        calls = []
        reg = _registry(calls)
        prompt = compact_prompt("do things", reg, ["demo.write"],
                                modes=[SMALL_CONTEXT_MODE])
        self.assertIn("demo.write", prompt)
        self.assertNotIn("demo.list", prompt)


class TranslatorTests(unittest.TestCase):
    def test_fenced_json(self):
        calls = []
        t = LegacyActionTranslator(_registry(calls))
        res = t.translate('```json\n{"tool": "demo.write", "arguments": {"a": 1}}\n```')
        self.assertTrue(res.ok)
        self.assertEqual((res.tool_id, res.arguments), ("demo.write", {"a": 1}))

    def test_unknown_tool_rejected_never_invented(self):
        calls = []
        t = LegacyActionTranslator(_registry(calls))
        res = t.translate('{"tool": "email.send_v2", "arguments": {}}')
        self.assertFalse(res.ok)
        self.assertIn("unknown tool", res.error)

    def test_tool_line_format(self):
        calls = []
        t = LegacyActionTranslator(_registry(calls))
        res = t.translate("tool: demo.list\n")
        self.assertTrue(res.ok)
        self.assertEqual(res.tool_id, "demo.list")

    def test_repair_loop_then_safe_failure(self):
        calls = []
        t = LegacyActionTranslator(_registry(calls), max_repairs=1)
        seen = []

        def produce(hint):
            seen.append(hint)
            return "definitely not an action"
        res = t.translate_with_repair(produce)
        self.assertFalse(res.ok)
        self.assertEqual(len(seen), 2)  # initial + 1 repair
        self.assertTrue(seen[1])  # repair hint is non-empty

    def test_repair_recovers(self):
        calls = []
        t = LegacyActionTranslator(_registry(calls), max_repairs=2)
        answers = iter(['garbage', '{"tool": "demo.list", "arguments": {}}'])
        res = t.translate_with_repair(lambda hint: next(answers))
        self.assertTrue(res.ok)
        self.assertEqual(res.repairs, 1)


class ProbeTests(unittest.TestCase):
    def test_strict_model(self):
        probe = ModelCapabilityProbe()
        ev = probe.probe(lambda p: '{"tool": "tools.list", "arguments": {}}'
                         if "tools.list" in p else "BLUE",
                         context_tokens=32768)
        self.assertTrue(ev["strict_json"])
        self.assertIn(STRICT_JSON_ACTION, ev["modes"])

    def test_legacy_text_model(self):
        probe = ModelCapabilityProbe()
        ev = probe.probe(lambda p: "BLUE", context_tokens=2048)
        self.assertEqual(ev["modes"][0], TEXT_ACTION_TRANSLATION)
        self.assertIn(SMALL_CONTEXT_MODE, ev["modes"])

    def test_failing_model(self):
        probe = ModelCapabilityProbe()
        def boom(prompt):
            raise RuntimeError("nope")
        ev = probe.probe(boom, context_tokens=0)
        self.assertEqual(ev["modes"], [LEGACY_MODEL_MODE])

    def test_native_never_claimed_by_probe(self):
        probe = ModelCapabilityProbe()
        ev = probe.probe(lambda p: '{"tool_calls": []}', context_tokens=0)
        self.assertFalse(ev["native_tools"])


class LegacyEndToEndTests(unittest.TestCase):
    def test_unknown_legacy_model_completes_bounded_task(self):
        # UnknownLegacyModel9000: no native tools, small context, text-only.
        calls = []
        reg = _registry(calls)
        router = ToolRouter(reg)
        translator = LegacyActionTranslator(reg, max_repairs=2)
        script = iter([
            "I will write the file now.\ntool: demo.write",
            '{"tool": "demo.list", "arguments": {}}',
            '{"tool": "demo.finish", "arguments": {"message": "done"}}',
        ])
        probe = ModelCapabilityProbe()
        ev = probe.probe(lambda p: "BLUE", context_tokens=2048)
        modes = ev["modes"]
        self.assertIn(TEXT_ACTION_TRANSLATION, modes)
        executed = []
        for _ in range(5):
            res = translator.translate_with_repair(lambda hint: next(script))
            self.assertTrue(res.ok, res.error)
            if res.tool_id in ("demo.finish", "finish"):
                break
            out = router.call(res.tool_id, res.arguments, {"profile": ""})
            self.assertTrue(out.get("ok"), out)
            executed.append(res.tool_id)
        self.assertEqual(executed, ["demo.write", "demo.list"])


if __name__ == "__main__":
    unittest.main()
