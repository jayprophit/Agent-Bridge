"""MIGRATED from v0.2 tests/test_protocol_v01.py — must keep passing in v0.3."""
import unittest

from protocol import normalize_action, parse_model_output, validate_action


class TestCanonical(unittest.TestCase):
    def test_write_canonical(self):
        a, raw, err = parse_model_output('{"action":"write","path":"hello.py","content":"print(1)"}')
        self.assertEqual(err, "")
        self.assertEqual(a, {"action": "write", "path": "hello.py", "content": "print(1)"})

    def test_all_actions(self):
        for text, exp in [
            ('{"action":"list","path":"."}', {"action": "list", "path": "."}),
            ('{"action":"read","path":"a.txt"}', {"action": "read", "path": "a.txt"}),
            ('{"action":"shell","command":"python x.py"}', {"action": "shell", "command": "python x.py"}),
            ('{"action":"finish","message":"done"}', {"action": "finish", "message": "done"}),
        ]:
            a, _, err = parse_model_output(text)
            self.assertEqual(err, "", text)
            self.assertEqual(a, exp, text)

    def test_edit(self):
        a, _, err = parse_model_output('{"action":"edit","path":"f","old":"x","new":"y"}')
        self.assertEqual(err, "")
        self.assertEqual(a["action"], "edit")


class TestVariants(unittest.TestCase):
    def test_name_arguments(self):
        raw = '{"name":"write","arguments":{"filePath":"test.py","content":"print(1)"}}'
        a, _, err = parse_model_output(raw)
        self.assertEqual(err, "", err)
        self.assertEqual(a, {"action": "write", "path": "test.py", "content": "print(1)"})

    def test_markdown_fence(self):
        raw = 'Here you go:\n```json\n{"action":"read","path":"a.txt"}\n```\n'
        a, _, err = parse_model_output(raw)
        self.assertEqual(err, "")
        self.assertEqual(a, {"action": "read", "path": "a.txt"})

    def test_alias_keys(self):
        obj = normalize_action({"action": "edit", "filePath": "f", "oldString": "x", "newString": "y"})
        self.assertEqual(obj.get("path"), "f")
        self.assertEqual(obj.get("old"), "x")
        self.assertEqual(obj.get("new"), "y")


class TestValidationFailures(unittest.TestCase):
    def test_unknown_action(self):
        a, raw, err = parse_model_output('{"action":"delete_v01_unknown_xyz","path":"x"}')
        self.assertIsNone(a)
        self.assertIn("unknown action", err)

    def test_missing_field(self):
        a, _, err = parse_model_output('{"action":"read"}')
        self.assertIsNone(a)
        self.assertIn("path", err)

    def test_garbage(self):
        a, raw, err = parse_model_output("hello world, no json here")
        self.assertIsNone(a)
        self.assertTrue(err)
        self.assertEqual(raw, "hello world, no json here")

    def test_empty(self):
        a, _, err = parse_model_output("   ")
        self.assertIsNone(a)
        self.assertIn("empty", err)

    def test_validate_direct(self):
        ok, res = validate_action({"action": "write", "path": "x"})
        self.assertFalse(ok)
        self.assertIn("content", res)


if __name__ == "__main__":
    unittest.main()
